"""Market data 领域：解析/校验/质量状态/新鲜度。纯领域，禁框架 import。

Phase 1 兑现 parse_quote 的 scale 校正，并新增日线（parse_bars）/净值（parse_nav）解析、
OHLC 合法性校验、质量状态（日线口径）与新鲜度骨架（5_DATA_INGESTION_AND_QUALITY.md）。
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from wws_adviser.core.errors import DomainError
from wws_adviser.ports.market_data import BarRow, RawDataset, RawNAV, RawQuote


class QuoteUnavailableError(DomainError):
    code = "DATA_MISSING"
    status = 409
    title = "行情不可用"


class BarParseError(DomainError):
    """日线解析/校验失败（OHLC 非法等）。上层据此记 quality_status=PARSE_FAILED。"""

    code = "DATA_MISSING"
    status = 409
    title = "日线解析失败"


class QualityStatus(StrEnum):
    """数据质量状态（2_DATA_MODEL §6.4 / 5_DATA §7）。"""

    OK = "OK"
    DELAYED = "DELAYED"
    MISSING = "MISSING"
    CONFLICT = "CONFLICT"
    PARSE_FAILED = "PARSE_FAILED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


@dataclass(frozen=True)
class NormalizedQuote:
    code: str
    source: str
    price: Decimal
    change_pct: Decimal
    market_time: str


@dataclass(frozen=True)
class NormalizedBar:
    business_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class NormalizedNAV:
    nav: Decimal
    published_at: str


def _quantize(value: Decimal, scale: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-scale))


def parse_quote(raw: RawQuote, code: str, *, price_scale: int = 4) -> NormalizedQuote:
    """原始行情 → 标准化行情。Phase-1 addendum：price/change_pct 按 scale 校正。"""
    return NormalizedQuote(
        code=code,
        source=raw.source,
        price=_quantize(raw.price, price_scale),
        change_pct=_quantize(raw.change_pct, price_scale),
        market_time=raw.market_time,
    )


def _validate_ohlc(op: Decimal, hi: Decimal, lo: Decimal, cl: Decimal, business_date: date) -> None:
    """OHLC 合法性：low ≤ open,close ≤ high。违者抛 BarParseError。"""
    if not (lo <= op <= hi and lo <= cl <= hi):
        raise BarParseError(
            f"OHLC 非法（{business_date}）：low={lo} open={op} close={cl} high={hi}"
        )


def parse_bars(
    raw: RawDataset, *, price_scale: int = 4, qty_scale: int = 6
) -> list[NormalizedBar]:
    """RawDataset → 标准化日线列表。量化到 scale 并校验 OHLC 合法性（非法行抛错）。"""
    out: list[NormalizedBar] = []
    for bar in raw.bars:
        op = _quantize(bar.open, price_scale)
        hi = _quantize(bar.high, price_scale)
        lo = _quantize(bar.low, price_scale)
        cl = _quantize(bar.close, price_scale)
        v = _quantize(bar.volume, qty_scale)
        _validate_ohlc(op, hi, lo, cl, bar.date)
        out.append(
            NormalizedBar(business_date=bar.date, open=op, high=hi, low=lo, close=cl, volume=v)
        )
    return out


def parse_nav(raw: RawNAV, *, nav_scale: int = 6) -> NormalizedNAV:
    """RawNAV → 标准化净值（量化到 nav_scale）。"""
    return NormalizedNAV(nav=_quantize(raw.nav, nav_scale), published_at=raw.published_at)


def is_ohlc_legal(bar: BarRow) -> bool:
    lo, hi, op, cl = bar.low, bar.high, bar.open, bar.close
    return lo <= op <= hi and lo <= cl <= hi


def assign_quality_status(
    *, latest_bar_date: date | None, expected_trading_day: date
) -> QualityStatus:
    """日线口径质量状态（5_DATA §7 骨架）：

    - 无任何日线 → MISSING
    - 最新日线已覆盖期望交易日 → OK
    - 有数据但落后 → DELAYED
    CONFLICT/PARSE_FAILED/SOURCE_UNAVAILABLE 由流水线其他阶段置位。
    """
    if latest_bar_date is None:
        return QualityStatus.MISSING
    if latest_bar_date >= expected_trading_day:
        return QualityStatus.OK
    return QualityStatus.DELAYED


def is_daily_complete(
    latest_record_date: date | None, expected_trading_day: date
) -> bool:
    """新鲜度骨架：最近交易日完整（DAILY_COMPLETE）。盘中 180s 门禁留 Phase 2.1。"""
    return latest_record_date is not None and latest_record_date >= expected_trading_day
