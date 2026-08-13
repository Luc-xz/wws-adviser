"""AKShare 净值适配器（NAVProvider）——脚手架。

fund_open_fund_info_em(indicator="单位净值走势") 返回历史净值 DF；按 as_of 取该日（无则取最新）。
akshare 懒加载；`rows_to_nav` 纯函数可单测。真实调用留待实录。
"""

import asyncio
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from wws_adviser.core.time import now_utc_iso
from wws_adviser.ports.market_data import InstrumentRef, RawNAV, SourceDelayClass


def _dec(v: object) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def rows_to_nav(
    rows: list[dict[str, Any]], *, source: str, source_url: str, as_of: date
) -> RawNAV:
    """历史净值记录 → 命中 as_of 的 RawNAV（无则取最新一行）。纯函数，可单测。"""
    now = now_utc_iso()
    target = as_of.isoformat()
    chosen: dict[str, Any] | None = None
    latest: dict[str, Any] | None = None
    for r in rows:
        d = str(r.get("净值日期", ""))[:10]
        if d == target:
            chosen = r
            break
        if latest is None or d > str(latest.get("净值日期", ""))[:10]:
            latest = r
    row = chosen or latest
    if row is None:
        nav = Decimal("0")
        published = target
    else:
        nav = _dec(row.get("单位净值", row.get("累计净值", 0)))
        published = str(row.get("净值日期", target))[:10]
    return RawNAV(
        source=source,
        source_url=source_url,
        market_time=now,
        fetched_at=now,
        received_at=now,
        source_delay_class=SourceDelayClass.END_OF_DAY,
        nav=nav,
        published_at=published,
    )


class AKShareNAVProvider:
    def __init__(self, *, env: str = "dev") -> None:
        self._env = env

    async def fetch_nav(self, instrument: InstrumentRef, as_of: date) -> RawNAV:
        import akshare as ak  # type: ignore[import-not-found]

        df = await asyncio.to_thread(
            ak.fund_open_fund_info_em, symbol=instrument.code, indicator="单位净值走势"
        )
        rows: list[dict[str, Any]] = list(df.to_dict("records"))
        return rows_to_nav(
            rows, source="akshare", source_url=f"akshare://nav/{instrument.code}", as_of=as_of
        )
