"""AKShare 快照适配器（QuoteProvider）——单股轻量接口。

VPS 实测（2026-08）：全市场快照（stock_zh_a_spot_em 分页拉 ~5400 行）会触发东财
WAF 对数据中心 IP 的风控（RemoteDisconnected，且连累其他接口进入冷却）。改用
push2 qt/stock/get 单股查询（每股一次请求、响应 <1KB），实测稳定。
`payload_to_quote` 纯函数可单测；`rows_to_quote` 保留兼容旧测试/全量快照场景。
"""

import asyncio
from decimal import Decimal, InvalidOperation
from typing import Any

from wws_adviser.core.time import now_utc_iso
from wws_adviser.ports.market_data import InstrumentRef, RawQuote, SourceDelayClass

_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
_QUOTE_FIELDS = "f43,f57,f58,f47,f48,f169,f170"  # 价/代码/名称/量(手)/额(元)/涨跌额/涨跌幅
_TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q/"


def _dec(v: object) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def secid_for(market: str, code: str) -> str:
    """市场+代码 → 东财 secid（SSE=1. BSE/SZSE=0.）。市场缺失按代码前缀推断。"""
    m = (market or "").upper()
    if m in {"SSE", "SH"}:
        prefix = "1"
    elif m in {"SZSE", "SZ", "BSE"}:
        prefix = "0"
    elif code.startswith("6") or code.startswith("5"):
        prefix = "1"
    else:
        prefix = "0"
    return f"{prefix}.{code}"


def payload_to_quote(
    data: dict[str, Any] | None, *, code: str, market_time: str
) -> RawQuote | None:
    """qt/stock/get 的 data 节点 → RawQuote（data 空或停牌无价 → None）。纯函数，可单测。"""
    if not data:
        return None
    price = data.get("f43")
    if price in (None, "", "-"):
        return None
    now = now_utc_iso()
    return RawQuote(
        source="akshare",
        source_url=f"akshare://quote/{code}",
        market_time=market_time or now,
        fetched_at=now,
        received_at=now,
        source_delay_class=SourceDelayClass.REALTIME,
        price=_dec(price),
        change_pct=_dec(data.get("f170", 0)),
        volume=_dec(data.get("f47", 0)),
        amount=_dec(data.get("f48", 0)),
        bid_ask=None,
    )


def rows_to_quote(
    rows: list[dict[str, Any]],
    *,
    code: str,
    market_time: str,
) -> RawQuote | None:
    """全市场快照记录 → 命中 code 的 RawQuote（无则 None）。纯函数，可单测。"""
    row: dict[str, Any] | None = None
    for r in rows:
        if str(r.get("代码", "")) == code:
            row = r
            break
    if row is None:
        return None
    now = now_utc_iso()
    return RawQuote(
        source="akshare",
        source_url=f"akshare://quote/{code}",
        market_time=market_time or now,
        fetched_at=now,
        received_at=now,
        source_delay_class=SourceDelayClass.REALTIME,
        price=_dec(row.get("最新价", 0)),
        change_pct=_dec(row.get("涨跌幅", 0)),
        volume=_dec(row.get("成交量", 0)),
        amount=_dec(row.get("成交额", 0)),
        bid_ask=None,
    )


def tencent_symbol(market: str, code: str) -> str:
    """市场+代码 → 腾讯代码（sh510500 / sz159558）。与东财 secid 同前缀规则。"""
    prefix = secid_for(market, code).split(".")[0]
    return f"{'sh' if prefix == '1' else 'sz'}{code}"


def tencent_text_to_quote(
    text: str, *, code: str, market_time: str
) -> RawQuote | None:
    """腾讯 qt.gtimg.cn 响应文本 → RawQuote。纯函数，可单测。

    协议：v_sh510500="1~名称~代码~现价~昨收~今开~成交量(手)~…"（~ 分隔）。
    涨跌幅由 现价/昨收 自算（不依赖字段位序，更稳）；停牌现价为 0 → None。
    """
    parts = text.split("~")
    if len(parts) < 7:
        return None
    try:
        price = Decimal(parts[3])
        prev = Decimal(parts[4])
        volume = Decimal(parts[6])
    except InvalidOperation:
        return None
    if price <= 0:
        return None
    change_pct = ((price - prev) / prev * 100) if prev > 0 else Decimal(0)
    now = now_utc_iso()
    return RawQuote(
        source="tencent",
        source_url=f"tencent://quote/{code}",
        market_time=market_time or now,
        fetched_at=now,
        received_at=now,
        source_delay_class=SourceDelayClass.REALTIME,
        price=price,
        change_pct=change_pct,
        volume=volume,
        amount=Decimal(0),
        bid_ask=None,
    )


def _fetch_tencent_sync(
    instrument: InstrumentRef, market_time: str
) -> RawQuote | None:
    import httpx

    sym = tencent_symbol(instrument.market, instrument.code)
    resp = httpx.get(_TENCENT_QUOTE_URL + sym, timeout=10.0)
    resp.raise_for_status()
    # 响应为 GBK 编码文本（v_sh510500="…"）
    return tencent_text_to_quote(
        resp.content.decode("gbk", errors="replace"),
        code=instrument.code, market_time=market_time,
    )


def _fetch_one_sync(instrument: InstrumentRef, market_time: str) -> RawQuote | None:
    import time

    import httpx

    params = {
        "secid": secid_for(instrument.market, instrument.code),
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fields": _QUOTE_FIELDS,
    }
    # 东财对数据中心 IP 有分钟级滚动风控（间歇性断连），短退避重试可跨过封锁窗口；
    # 重试全败 → 腾讯备用源（长封锁期兜底，2026-08 实测东财封锁可持续数日）
    last_exc: Exception | None = None
    for delay in (0, 1, 3):
        if delay:
            time.sleep(delay)
        try:
            resp = httpx.get(_QUOTE_URL, params=params, timeout=10.0)
            resp.raise_for_status()
            payload = resp.json().get("data")
            return payload_to_quote(payload, code=instrument.code, market_time=market_time)
        except Exception as exc:  # noqa: BLE001 — 传输层抖动重试
            last_exc = exc
    try:
        return _fetch_tencent_sync(instrument, market_time)
    except Exception as fallback_exc:  # noqa: BLE001 — 备源也失败才上抛主源异常（可审计）
        raise last_exc from fallback_exc


class AKShareQuoteProvider:
    def __init__(self, *, env: str = "dev") -> None:
        self._env = env

    async def fetch_quotes(self, instruments: list[InstrumentRef]) -> list[RawQuote]:
        out: list[RawQuote] = []
        for instrument in instruments:
            market_time = now_utc_iso()
            q = await asyncio.to_thread(_fetch_one_sync, instrument, market_time)
            if q is not None:
                out.append(q)
        return out
