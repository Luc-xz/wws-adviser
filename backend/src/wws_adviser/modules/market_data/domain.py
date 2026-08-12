"""Market data 领域：RawQuote → NormalizedQuote 纯函数。禁框架 import。"""

from dataclasses import dataclass
from decimal import Decimal

from wws_adviser.core.errors import DomainError
from wws_adviser.ports.market_data import RawQuote


class QuoteUnavailableError(DomainError):
    code = "DATA_MISSING"
    status = 409
    title = "行情不可用"


@dataclass(frozen=True)
class NormalizedQuote:
    code: str
    source: str
    price: Decimal
    change_pct: Decimal
    market_time: str


def parse_quote(raw: RawQuote, code: str) -> NormalizedQuote:
    """原始行情 → 标准化行情。Phase 0 直取；Phase 1 加单位/scale 校正。"""
    return NormalizedQuote(
        code=code,
        source=raw.source,
        price=raw.price,
        change_pct=raw.change_pct,
        market_time=raw.market_time,
    )
