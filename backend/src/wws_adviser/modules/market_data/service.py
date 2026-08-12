"""Market data 服务：通过 QuoteProvider 端口取行情（依赖注入，不 import 适配器）。"""

from wws_adviser.modules.market_data.domain import (
    NormalizedQuote,
    QuoteUnavailableError,
    parse_quote,
)
from wws_adviser.ports.market_data import InstrumentRef, QuoteProvider


async def get_quote(
    instrument: InstrumentRef, provider: QuoteProvider
) -> NormalizedQuote:
    quotes = await provider.fetch_quotes([instrument])
    if not quotes:
        raise QuoteUnavailableError(f"无行情：{instrument.code}")
    return parse_quote(quotes[0], instrument.code)
