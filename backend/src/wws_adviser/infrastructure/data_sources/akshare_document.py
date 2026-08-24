"""AKShare 公告适配器（DocumentProvider）——按股票查询东财公告。

VPS 实测（2026-08）：akshare 的 stock_notice_report(symbol=…) 参数语义是公告类型
（"全部"/"重大事项"/…），按日期返回全市场公告，不能按代码查询（传代码直接 KeyError）。
改用东财公告中心按股票的轻量接口（np-anotice-stock，每股票一次请求）。
`rows_to_document_ref` 保留兼容旧测试；`notice_payload_to_refs` 为新纯函数。
"""

import asyncio
from datetime import datetime
from typing import Any

from wws_adviser.core.time import now_utc_iso
from wws_adviser.ports.document_source import DocumentRef, DocumentScope, RawDocument
from wws_adviser.ports.market_data import SourceDelayClass

_NOTICE_URL = "https://np-anotice-stock.eastmoney.com/api/security/ann"


def rows_to_document_ref(
    rows: list[dict[str, Any]], *, source: str = "akshare"
) -> list[DocumentRef]:
    """akshare 公告 DF 记录（中文列名）→ list[DocumentRef]。纯函数，可单测。

    兼容常见列名：公告标题/标题、公告时间/日期、网址/url、公告类型/类型。
    """
    out: list[DocumentRef] = []
    for r in rows:
        title = str(r.get("公告标题", r.get("标题", "")))
        if not title:
            continue
        published = str(r.get("公告时间", r.get("日期", "")))[:10]
        url = str(r.get("网址", r.get("url", "")))
        kind = str(r.get("公告类型", r.get("类型", "announcement"))).lower() or "announcement"
        out.append(
            DocumentRef(
                source_url=url or f"akshare://announcement/{title}",
                kind=kind,
                title=title,
                published_at=published,
            )
        )
    return out


def notice_payload_to_refs(
    items: list[dict[str, Any]], *, code: str
) -> list[DocumentRef]:
    """np-anotice-stock 的 data.list 记录 → list[DocumentRef]。纯函数，可单测。"""
    out: list[DocumentRef] = []
    for it in items:
        title = str(it.get("title", "")).strip()
        if not title:
            continue
        art_code = str(it.get("art_code", ""))
        published = str(it.get("notice_date", ""))[:10]
        url = (
            f"https://data.eastmoney.com/notices/detail/{code}/{art_code}.html"
            if art_code
            else f"akshare://announcement/{code}/{title}"
        )
        out.append(
            DocumentRef(
                source_url=url,
                kind="announcement",
                title=title,
                published_at=published,
            )
        )
    return out


class AKShareDocumentProvider:
    def __init__(self, *, env: str = "dev") -> None:
        self._env = env

    async def discover(
        self, scope: DocumentScope, since: datetime
    ) -> list[DocumentRef]:
        if scope.instrument is None:
            return []
        code = scope.instrument.code
        items = await asyncio.to_thread(_fetch_notices_sync, code)
        refs = notice_payload_to_refs(items, code=code)
        since_date = since.date().isoformat()
        return [r for r in refs if not r.published_at or r.published_at >= since_date]

    async def download(self, ref: DocumentRef) -> RawDocument:
        now = now_utc_iso()
        # MVP：公告正文需按 source_url 抓取（akshare 无直接正文接口），此处返回标题占位
        body = ref.title
        return RawDocument(
            source="akshare",
            source_url=ref.source_url,
            market_time=now,
            fetched_at=now,
            received_at=now,
            source_delay_class=SourceDelayClass.DELAYED,
            kind=ref.kind,
            title=ref.title,
            content=body.encode("utf-8"),
            text=body,
        )


def _fetch_notices_sync(code: str) -> list[dict[str, Any]]:
    import httpx

    params = {
        "sr": "-1",
        "page_size": "50",
        "page_index": "1",
        "ann_type": "A",
        "stock_list": code,
    }
    resp = httpx.get(_NOTICE_URL, params=params, timeout=10.0)
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    return list(data.get("list") or [])
