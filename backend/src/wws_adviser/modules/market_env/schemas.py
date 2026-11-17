"""Market env API schema（3_API §3.18；数值字段一律字符串，十进制契约）。"""

from pydantic import BaseModel


class IndexQuoteOut(BaseModel):
    code: str
    name: str
    group: str
    price: str
    change_pct: str
    volume: str | None = None
    amount: str | None = None
    market_time: str


class SectorFlowOut(BaseModel):
    board_code: str
    kind: str
    board_name: str
    change_pct: str | None = None
    turnover: str | None = None
    net_main_inflow: str | None = None
    leader_name: str | None = None
    snapshot_at: str


class FreshnessOut(BaseModel):
    """研究级新鲜度（5_DATA §13.4）：仅展示，不触发 PAUSE_ADVICE（ADR-0014 决策 5）。"""

    cn_quote_age_seconds: int | None = None
    cn_quote_fresh: bool | None = None
    sector_flow_age_seconds: int | None = None
    sector_flow_fresh: bool | None = None


class MarketEnvOverview(BaseModel):
    generated_at: str
    cn_indices: list[IndexQuoteOut]
    market_turnover: str | None = None
    active_sectors: list[SectorFlowOut]
    net_inflow_top: list[SectorFlowOut]
    net_outflow_top: list[SectorFlowOut]
    overseas: list[IndexQuoteOut]
    futures: list[IndexQuoteOut]
    freshness: FreshnessOut


class IndexBarOut(BaseModel):
    business_date: str
    open: str | None = None
    high: str | None = None
    low: str | None = None
    close: str | None = None
    volume: str | None = None
    amount: str | None = None


class IndexBarsResponse(BaseModel):
    code: str
    source: str | None = None
    items: list[IndexBarOut]
