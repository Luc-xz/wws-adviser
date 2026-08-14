"""Analytics DTO（金额/数量/比例为字符串传输）。"""

from pydantic import BaseModel


class PositionOut(BaseModel):
    instrument_id: str
    code: str
    name: str
    industry: str | None = None
    quantity: str
    avg_cost: str
    cost_basis: str
    realized_pnl: str
    close_price: str | None = None
    close_date: str | None = None
    market_value: str | None = None
    unrealized_pnl: str | None = None
    weight: str | None = None
    freshness: str


class PositionListResponse(BaseModel):
    items: list[PositionOut]
    cash: str
    total_assets: str


class PositionHistoryItem(BaseModel):
    business_date: str
    instrument_id: str
    quantity: str
    avg_cost: str
    realized_pnl: str


class PositionsHistoryResponse(BaseModel):
    items: list[PositionHistoryItem]


class AnalyticsSummary(BaseModel):
    total_assets: str
    cash: str
    cash_ratio: str
    pnl_total: str
    concentration: str | None = None
    volatility: str | None = None
    max_drawdown: str | None = None
    pnl_today: str | None = None
    note: str | None = None


class RiskBreach(BaseModel):
    rule: str
    level: str  # hard | soft
    actual: str
    limit: str
    instrument_id: str | None = None
    code: str | None = None
    industry: str | None = None


class RiskResponse(BaseModel):
    breaches: list[RiskBreach]


class AttributionResponse(BaseModel):
    by_instrument: list[dict[str, object]]
    by_industry: list[dict[str, object]]
    cash: str
