"""AKShare 日线适配器（BarProvider）——脚手架。

akshare 为 optional extra（重依赖：pandas/numpy/JS 引擎），**懒加载**：未安装时本模块仍可
导入，仅当 settings.market_data_source=="akshare" 且可导入时由 main.py 构造。
真实 akshare 调用 + DF 获取留待国内 VPS 实录验证；`rows_to_dataset` 为纯函数，可单测（无 pandas）。
"""

import asyncio
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from wws_adviser.core.time import now_utc_iso
from wws_adviser.ports.market_data import BarRow, InstrumentRef, RawDataset, SourceDelayClass


def _dec(v: object) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _parse_date(s: object) -> date:
    return date.fromisoformat(str(s)[:10])


def rows_to_dataset(
    rows: list[dict[str, Any]], *, source: str, source_url: str
) -> RawDataset:
    """akshare DF 记录（中文列名）→ RawDataset。纯函数，可单测。"""
    now = now_utc_iso()
    bars = [
        BarRow(
            date=_parse_date(r.get("日期", r.get("date", ""))),
            open=_dec(r.get("开盘", 0)),
            high=_dec(r.get("最高", 0)),
            low=_dec(r.get("最低", 0)),
            close=_dec(r.get("收盘", 0)),
            volume=_dec(r.get("成交量", 0)),
        )
        for r in rows
    ]
    return RawDataset(
        source=source,
        source_url=source_url,
        market_time=now,
        fetched_at=now,
        received_at=now,
        source_delay_class=SourceDelayClass.END_OF_DAY,
        bars=bars,
    )


class AKShareBarProvider:
    """股票用 stock_zh_a_hist，ETF 用 fund_etf_hist_em。"""

    def __init__(self, *, env: str = "dev", adjust: str = "") -> None:
        self._env = env
        self._adjust = adjust  # "" | "qfq" | "hfq"

    def _fetch_df(
        self, ak: Any, instrument: InstrumentRef, start: date, end: date
    ) -> Any:
        start_s, end_s = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
        if instrument.kind.lower() == "etf":
            return ak.fund_etf_hist_em(
                symbol=instrument.code, period="daily",
                start_date=start_s, end_date=end_s, adjust=self._adjust,
            )
        return ak.stock_zh_a_hist(
            symbol=instrument.code, period="daily",
            start_date=start_s, end_date=end_s, adjust=self._adjust,
        )

    async def fetch_daily_bars(
        self, instrument: InstrumentRef, start: date, end: date
    ) -> RawDataset:
        import akshare as ak  # type: ignore[import-not-found]

        # 东财对数据中心 IP 有分钟级滚动风控（间歇性断连），短退避重试可跨过封锁窗口
        last_exc: Exception | None = None
        df: Any = None
        for delay in (0, 2, 5):
            if delay:
                await asyncio.sleep(delay)
            try:
                df = await asyncio.to_thread(self._fetch_df, ak, instrument, start, end)
                break
            except Exception as exc:  # noqa: BLE001 — 传输层抖动重试；末次异常上抛由服务层降级
                last_exc = exc
        else:
            raise last_exc
        rows: list[dict[str, Any]] = list(df.to_dict("records"))
        return rows_to_dataset(
            rows, source="akshare", source_url=f"akshare://bars/{instrument.code}"
        )
