"""StubQuoteProvider：合成行情（source="stub"），禁生产。"""

from decimal import Decimal

from wws_adviser.core.time import now_utc_iso
from wws_adviser.infrastructure import assert_not_prod
from wws_adviser.ports.market_data import (
    InstrumentRef,
    RawQuote,
    SourceDelayClass,
)

_STUB_SOURCE = "stub"


class StubQuoteProvider:
    """占位行情适配器：为每个 InstrumentRef 返回一条合成 RawQuote。"""

    def __init__(self, *, env: str = "dev") -> None:
        assert_not_prod(env)

    async def fetch_quotes(self, instruments: list[InstrumentRef]) -> list[RawQuote]:
        now = now_utc_iso()
        return [
            RawQuote(
                source=_STUB_SOURCE,
                source_url=f"stub://quote/{ref.code}",
                market_time=now,
                fetched_at=now,
                received_at=now,
                source_delay_class=SourceDelayClass.REALTIME,
                price=Decimal("100.00"),
                change_pct=Decimal("1.23"),
                volume=Decimal("10000"),
                amount=Decimal("1000000.00"),
                bid_ask=None,
            )
            for ref in instruments
        ]
