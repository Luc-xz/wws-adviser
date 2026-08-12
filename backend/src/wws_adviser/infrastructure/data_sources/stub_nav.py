"""StubNAVProvider：合成净值（source="stub"），禁生产。"""

from datetime import date
from decimal import Decimal

from wws_adviser.core.time import now_utc_iso
from wws_adviser.infrastructure import assert_not_prod
from wws_adviser.ports.market_data import (
    InstrumentRef,
    RawNAV,
    SourceDelayClass,
)


class StubNAVProvider:
    def __init__(self, *, env: str = "dev") -> None:
        assert_not_prod(env)

    async def fetch_nav(self, instrument: InstrumentRef, as_of: date) -> RawNAV:
        now = now_utc_iso()
        return RawNAV(
            source="stub",
            source_url=f"stub://nav/{instrument.code}",
            market_time=now,
            fetched_at=now,
            received_at=now,
            source_delay_class=SourceDelayClass.END_OF_DAY,
            nav=Decimal("1.0000"),
            published_at=now,
        )
