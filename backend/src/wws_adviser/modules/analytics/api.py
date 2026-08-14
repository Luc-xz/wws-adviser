"""/api/v1/positions 与 /api/v1/analytics 端点（3_API §3.4/§3.8，波4）。

持仓/盈亏数值来自 portfolio 的确定性 MWAC 计算（可追溯）；估值叠加 market_data 最新价。
"""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from wws_adviser.api.dependencies import get_current_user, get_session, get_settings
from wws_adviser.core.config import Settings
from wws_adviser.modules.analytics import service
from wws_adviser.modules.analytics.schemas import (
    AnalyticsSummary,
    AttributionResponse,
    PositionHistoryItem,
    PositionListResponse,
    PositionOut,
    PositionsHistoryResponse,
    RiskBreach,
    RiskResponse,
)
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.portfolio import service as portfolio_service
from wws_adviser.modules.portfolio.domain import from_scaled_int

positions_router = APIRouter(prefix="/api/v1/positions", tags=["positions"])
analytics_router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

DBDep = Annotated[DBSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
UserDep = Annotated[User, Depends(get_current_user)]


def _s(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def _pos_out(p: service.ValuatedPosition) -> PositionOut:
    return PositionOut(
        instrument_id=p.instrument_id,
        code=p.code,
        name=p.name,
        industry=p.industry,
        quantity=format(p.quantity, "f"),
        avg_cost=format(p.avg_cost, "f"),
        cost_basis=format(p.cost_basis, "f"),
        realized_pnl=format(p.realized_pnl, "f"),
        close_price=_s(p.close_price),
        close_date=p.close_date,
        market_value=_s(p.market_value),
        unrealized_pnl=_s(p.unrealized_pnl),
        weight=_s(p.weight),
        freshness=p.freshness,
    )


def _account_id(db: DBSession, user: User) -> str:
    return portfolio_service.get_user_account(db, user.id).id


@positions_router.get("", response_model=PositionListResponse)
async def get_positions(db: DBDep, user: UserDep) -> PositionListResponse:
    v = service.valuate(db, user.id)
    return PositionListResponse(
        items=[_pos_out(p) for p in v.positions],
        cash=format(v.cash, "f"),
        total_assets=format(v.total_assets, "f"),
    )


@positions_router.get("/history", response_model=PositionsHistoryResponse)
async def get_positions_history(
    db: DBDep, user: UserDep, instrument_id: str | None = None, limit: int = 100
) -> PositionsHistoryResponse:
    account_id = _account_id(db, user)
    snaps = portfolio_service.list_position_snapshots(
        db, account_id=account_id, instrument_id=instrument_id, limit=limit
    )
    return PositionsHistoryResponse(
        items=[
            PositionHistoryItem(
                business_date=s.business_date,
                instrument_id=s.instrument_id,
                quantity=s.quantity,
                avg_cost=str(from_scaled_int(s.avg_cost_minor, s.avg_cost_scale)),
                realized_pnl=str(from_scaled_int(s.realized_pnl_minor, s.realized_pnl_scale)),
            )
            for s in snaps
        ]
    )


@analytics_router.get("/summary", response_model=AnalyticsSummary)
async def get_summary(db: DBDep, user: UserDep) -> AnalyticsSummary:
    s = service.summary(db, user.id)
    return AnalyticsSummary(
        total_assets=format(s.total_assets, "f"),
        cash=format(s.cash, "f"),
        cash_ratio=format(s.cash_ratio, "f"),
        pnl_total=format(s.pnl_total, "f"),
        concentration=_s(s.concentration),
        volatility=None,
        max_drawdown=None,
        pnl_today=None,
        note=s.note,
    )


@analytics_router.get("/risk", response_model=RiskResponse)
async def get_risk(db: DBDep, user: UserDep, settings: SettingsDep) -> RiskResponse:
    breaches = service.risk(db, user.id, settings)
    return RiskResponse(
        breaches=[
            RiskBreach(
                rule=b.rule,
                level=b.level,
                actual=format(b.actual, "f"),
                limit=format(b.limit, "f"),
                instrument_id=b.instrument_id,
                code=b.code,
                industry=b.industry,
            )
            for b in breaches
        ]
    )


@analytics_router.get("/attribution", response_model=AttributionResponse)
async def get_attribution(db: DBDep, user: UserDep) -> AttributionResponse:
    a = service.attribution(db, user.id)

    def _irow(r: service.AttribRow) -> dict[str, object]:
        return {
            "instrument_id": r.instrument_id,
            "code": r.code,
            "industry": r.industry,
            "market_value": _s(r.market_value),
            "cost_basis": format(r.cost_basis, "f"),
            "realized_pnl": format(r.realized_pnl, "f"),
            "unrealized_pnl": _s(r.unrealized_pnl),
        }

    return AttributionResponse(
        by_instrument=[_irow(r) for r in a.by_instrument],
        by_industry=[
            {
                "industry": r.industry,
                "market_value": format(r.market_value, "f"),
                "unrealized_pnl": format(r.unrealized_pnl, "f"),
            }
            for r in a.by_industry
        ],
        cash=format(a.cash, "f"),
    )
