"""行情 DTO（Decimal 以字符串传输，技术架构 §7.3）。"""

from pydantic import BaseModel


class QuoteOut(BaseModel):
    code: str
    source: str
    price: str
    change_pct: str
    market_time: str


class BarOut(BaseModel):
    business_date: str
    open: str
    high: str
    low: str
    close: str
    volume: str
    amount: str | None = None


class BarSeriesResponse(BaseModel):
    instrument_id: str
    adjustment: str = "none"
    bars: list[BarOut]


class NavOut(BaseModel):
    nav_date: str
    nav: str
    published_at: str | None = None


class NavSeriesResponse(BaseModel):
    instrument_id: str
    navs: list[NavOut]


class IngestResponse(BaseModel):
    ingested: int
    quality: str
    content_hash: str | None = None


class QualityEntry(BaseModel):
    instrument_id: str
    series: str
    business_date: str | None = None
    nav_date: str | None = None
    quality_status: str
    fetched_at: str
    source: str


class QualityResponse(BaseModel):
    items: list[QualityEntry]


class MarketStateOut(BaseModel):
    """市场状态骨架（盘中状态机留 Phase 2.1）。"""

    phase: str = "unknown"
    is_trading_day: bool | None = None
    next_event_at: str | None = None

