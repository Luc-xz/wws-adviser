"""StubBarProvider：合成日线（source="stub"），禁生产。"""

from datetime import date

from wws_adviser.core.time import now_utc_iso
from wws_adviser.infrastructure import assert_not_prod
from wws_adviser.ports.market_data import (
    InstrumentRef,
    RawDataset,
    SourceDelayClass,
)


class StubBarProvider:
    def __init__(self, *, env: str = "dev") -> None:
        assert_not_prod(env)

    async def fetch_daily_bars(
        self, instrument: InstrumentRef, start: date, end: date
    ) -> RawDataset:
        now = now_utc_iso()
        return RawDataset(
            source="stub",
            source_url=f"stub://bars/{instrument.code}",
            market_time=now,
            fetched_at=now,
            received_at=now,
            source_delay_class=SourceDelayClass.END_OF_DAY,
            bars=[],
        )
