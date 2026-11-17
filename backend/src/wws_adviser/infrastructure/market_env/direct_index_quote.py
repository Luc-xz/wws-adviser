"""直连指数快照适配器（IndexQuoteProvider）：腾讯主源 + 新浪补位/兜底。

腾讯一次批量请求覆盖 A股/美股/港股；日经/KOSPI 无腾讯代码 → 新浪补位；腾讯整批
失败 → 新浪兜底（5_DATA §13.2 降级链；v1 不做双源并发比对）。反爬基线同 §4：
固定 Referer、有界重试、单请求批量。
"""

import asyncio

from wws_adviser.ports.market_env import IndexRef, RawIndexQuote

from .sina_index_quote import parse_sina_global_text
from .tencent_index_quote import parse_tencent_index_text

_TENCENT_URL = "https://qt.gtimg.cn/q/"
_SINA_URL = "https://hq.sinajs.cn/list="
_BATCH = 40  # 腾讯批量上限内保守值（niuone 实测 200/批可用，此处量小取稳）


def _fetch_tencent_sync(symbols: list[str]) -> str:
    import httpx

    resp = httpx.get(
        _TENCENT_URL,
        params={"q": ",".join(symbols)},
        timeout=10.0,
        headers={"Referer": "https://gu.qq.com/"},
    )
    resp.raise_for_status()
    return resp.content.decode("gbk", errors="replace")


def _fetch_sina_sync(symbols: list[str]) -> str:
    import httpx

    resp = httpx.get(
        _SINA_URL,
        params={"list": ",".join(symbols)},
        timeout=10.0,
        headers={"Referer": "https://finance.sina.com.cn/"},
    )
    resp.raise_for_status()
    return resp.content.decode("gbk", errors="replace")


class DirectIndexQuoteProvider:
    """腾讯批量主源 + 新浪补位兜底。构造仅在 main.py（1_REPO §5）。"""

    def __init__(self, *, env: str = "dev") -> None:
        self._env = env

    async def fetch_index_quotes(self, refs: list[IndexRef]) -> list[RawIndexQuote]:
        out: list[RawIndexQuote] = []
        fetched_codes: set[str] = set()

        # —— 腾讯主源：分批一次拉齐 ——
        tencent_refs = [r for r in refs if "tencent" in r.symbol_map]
        last_exc: Exception | None = None
        for i in range(0, len(tencent_refs), _BATCH):
            batch_refs = tencent_refs[i : i + _BATCH]
            try:
                text = await asyncio.to_thread(
                    _fetch_tencent_sync, [r.symbol_map["tencent"] for r in batch_refs]
                )
                for q in parse_tencent_index_text(text, batch_refs):
                    out.append(q)
                    fetched_codes.add(q.code)
            except Exception as exc:  # noqa: BLE001 — 批失败留给新浪兜底
                last_exc = exc

        # —— 新浪：腾讯无代码的指数补位 + 腾讯失败且新浪有映射的指数兜底 ——
        need_sina = [
            r
            for r in refs
            if "sina" in r.symbol_map
            and (r.code not in fetched_codes)
            and ("tencent" not in r.symbol_map or last_exc is not None)
        ]
        if need_sina:
            try:
                text = await asyncio.to_thread(
                    _fetch_sina_sync, [r.symbol_map["sina"] for r in need_sina]
                )
                out.extend(parse_sina_global_text(text, need_sina))
            except Exception as fallback_exc:  # noqa: BLE001 — 兜底失败上抛主源异常
                if last_exc is not None:
                    raise last_exc from fallback_exc

        if not out and last_exc is not None:
            raise last_exc
        return out
