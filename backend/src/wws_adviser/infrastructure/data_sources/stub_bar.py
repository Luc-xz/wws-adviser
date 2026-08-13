"""StubBarProvider：合成日线（source="stub"），禁生产。

为闭环可测，按 [start, end] 内的工作日合成确定性 OHLCV（值由 code 派生，稳定）。
"""

from datetime import date, timedelta
from decimal import Decimal

from wws_adviser.core.time import now_utc_iso
from wws_adviser.infrastructure import assert_not_prod
from wws_adviser.ports.market_data import (
    BarRow,
    InstrumentRef,
    RawDataset,
    SourceDelayClass,
)


def _seed(code: str) -> int:
    """code → 稳定整数种子（决定合成价格基准）。"""
    return sum(ord(c) for c in code) % 100


class StubBarProvider:
    def __init__(self, *, env: str = "dev") -> None:
        assert_not_prod(env)

    async def fetch_daily_bars(
        self, instrument: InstrumentRef, start: date, end: date
    ) -> RawDataset:
        now = now_utc_iso()
        base = Decimal(100 + _seed(instrument.code))
        bars: list[BarRow] = []
        cur = start
        while cur <= end:
            if cur.weekday() < 5:  # 周一..周五
                offset = Decimal((cur - start).days)
                close = base + offset
                bars.append(
                    BarRow(
                        date=cur,
                        open=close - Decimal("1"),
                        high=close + Decimal("1"),
                        low=close - Decimal("2"),
                        close=close,
                        volume=Decimal("1000"),
                    )
                )
            cur += timedelta(days=1)
        return RawDataset(
            source="stub",
            source_url=f"stub://bars/{instrument.code}",
            market_time=now,
            fetched_at=now,
            received_at=now,
            source_delay_class=SourceDelayClass.END_OF_DAY,
            bars=bars,
        )
