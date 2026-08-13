"""AKShare 快照适配器（QuoteProvider）——脚手架。

stock_zh_a_spot_em / fund_etf_spot_em 返回全市场快照 DF；按 code 过滤一行。
akshare 懒加载；`rows_to_quote` 纯函数可单测。真实调用留待实录。
"""

import asyncio
from decimal import Decimal, InvalidOperation
from typing import Any

from wws_adviser.core.time import now_utc_iso
from wws_adviser.ports.market_data import InstrumentRef, RawQuote, SourceDelayClass


def _dec(v: object) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return Decimal("0")


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


class AKShareQuoteProvider:
    def __init__(self, *, env: str = "dev") -> None:
        self._env = env

    async def fetch_quotes(self, instruments: list[InstrumentRef]) -> list[RawQuote]:
        import akshare as ak  # type: ignore[import-not-found]

        out: list[RawQuote] = []
        # 股票与 ETF 分别拉全市场快照，再按 code 过滤（spot 接口为全市场，见 §11.2）
        stock_codes = [i.code for i in instruments if i.kind.lower() == "stock"]
        etf_codes = [i.code for i in instruments if i.kind.lower() == "etf"]
        now = now_utc_iso()
        if stock_codes:
            df = await asyncio.to_thread(ak.stock_zh_a_spot_em)
            records: list[dict[str, Any]] = list(df.to_dict("records"))
            for code in stock_codes:
                q = rows_to_quote(records, code=code, market_time=now)
                if q is not None:
                    out.append(q)
        if etf_codes:
            df = await asyncio.to_thread(ak.fund_etf_spot_em)
            records = list(df.to_dict("records"))
            for code in etf_codes:
                q = rows_to_quote(records, code=code, market_time=now)
                if q is not None:
                    out.append(q)
        return out
