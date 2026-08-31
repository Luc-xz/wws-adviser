"""AKShare 交易日历适配器（TradingCalendarProvider）。

ak.tool_trade_date_hist_sina（新浪源，全历史交易日，trade_date 列）；akshare 懒加载同
其他适配器。rows_to_days 纯函数可单测（无 pandas）。节假日 = 不在交易日列表中。
"""

import asyncio
from datetime import date
from typing import Any


def rows_to_days(rows: list[dict[str, Any]]) -> list[date]:
    """akshare DF 记录（trade_date 列）→ 排序去重的交易日列表。纯函数，可单测。"""
    out: set[date] = set()
    for r in rows:
        raw = r.get("trade_date")
        if raw in (None, ""):
            continue
        out.add(date.fromisoformat(str(raw)[:10]))
    return sorted(out)


class AKShareCalendarProvider:
    def __init__(self, *, env: str = "dev") -> None:
        self._env = env

    async def fetch_trading_dates(self, start: date, end: date) -> list[date]:
        import akshare as ak  # type: ignore[import-not-found]

        df = await asyncio.to_thread(ak.tool_trade_date_hist_sina)
        return [d for d in rows_to_days(df.to_dict("records")) if start <= d <= end]
