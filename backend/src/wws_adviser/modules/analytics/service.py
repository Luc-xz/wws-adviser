"""Analytics 服务：持仓估值 + 组合摘要 + 风险硬上限 + 收益归因（波4，AC-04）。

跨模块：经 portfolio.service 取确定性持仓状态、market_data.service 取最新价、
instruments.service 取标的元数据。确定性数值来自 portfolio 的 MWAC 计算（可追溯）。
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.modules.instruments import service as instruments_service
from wws_adviser.modules.market_data import service as market_data_service
from wws_adviser.modules.portfolio import service as portfolio_service


@dataclass
class ValuatedPosition:
    instrument_id: str
    code: str
    name: str
    industry: str | None
    quantity: Decimal
    avg_cost: Decimal
    cost_basis: Decimal
    realized_pnl: Decimal
    close_price: Decimal | None
    close_date: str | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None
    weight: Decimal | None
    freshness: str  # close_date 或 "missing"


@dataclass(frozen=True)
class Valuation:
    positions: list[ValuatedPosition]
    cash: Decimal
    total_assets: Decimal


@dataclass(frozen=True)
class Summary:
    total_assets: Decimal
    cash: Decimal
    cash_ratio: Decimal
    pnl_total: Decimal
    concentration: Decimal | None
    note: str


@dataclass(frozen=True)
class Breach:
    rule: str
    level: str
    actual: Decimal
    limit: Decimal
    instrument_id: str | None = None
    code: str | None = None
    industry: str | None = None


@dataclass(frozen=True)
class AttribRow:
    instrument_id: str
    code: str
    industry: str | None
    market_value: Decimal | None
    cost_basis: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal | None


@dataclass(frozen=True)
class IndustryRow:
    industry: str
    market_value: Decimal
    unrealized_pnl: Decimal


@dataclass(frozen=True)
class Attribution:
    by_instrument: list[AttribRow]
    by_industry: list[IndustryRow]
    cash: Decimal


def _user_account_id(db: DBSession, user_id: str) -> str:
    return portfolio_service.get_user_account(db, user_id).id


def valuate(db: DBSession, user_id: str) -> Valuation:
    """确定性持仓状态 + 最新价 → 市值/权重/未实现盈亏/新鲜度。无价标的市值留空。"""
    account_id = _user_account_id(db, user_id)
    state = portfolio_service.get_position_state(db, account_id)
    positions: list[ValuatedPosition] = []
    sum_mv = Decimal(0)
    for inst_id, st in state.positions.items():
        if st.qty <= 0:
            continue
        inst = instruments_service.get_instrument(db, inst_id)
        lp = market_data_service.latest_price(db, inst_id)
        if lp is not None:
            mv = st.qty * lp.price
            sum_mv += mv
            close_price, close_date, freshness = lp.price, lp.business_date, lp.business_date
            unreal = mv - st.cost_basis
        else:
            mv, unreal, close_price, close_date, freshness = None, None, None, None, "missing"
        positions.append(
            ValuatedPosition(
                instrument_id=inst_id,
                code=inst.code if inst else "",
                name=inst.name if inst else "",
                industry=inst.industry if inst else None,
                quantity=st.qty,
                avg_cost=st.avg_cost,
                cost_basis=st.cost_basis,
                realized_pnl=st.realized_pnl,
                close_price=close_price,
                close_date=close_date,
                market_value=mv,
                unrealized_pnl=unreal,
                weight=None,
                freshness=freshness,
            )
        )
    total_assets = state.cash + sum_mv
    for p in positions:
        if p.market_value is not None and total_assets > 0:
            p.weight = p.market_value / total_assets
    return Valuation(positions=positions, cash=state.cash, total_assets=total_assets)


def summary(db: DBSession, user_id: str) -> Summary:
    """组合摘要（AC-04）。volatility/max_drawdown/pnl_today 样本不足 → null + 标记。"""
    v = valuate(db, user_id)
    total = v.total_assets
    cash_ratio = (v.cash / total) if total > 0 else Decimal(0)
    pnl_total = sum(
        (p.realized_pnl + (p.unrealized_pnl or Decimal(0)) for p in v.positions),
        start=Decimal(0),
    )
    weights = [p.weight for p in v.positions if p.weight is not None]
    concentration = sum((w * w for w in weights), start=Decimal(0))  # Herfindahl
    return Summary(
        total_assets=total,
        cash=v.cash,
        cash_ratio=cash_ratio,
        pnl_total=pnl_total,
        concentration=concentration,
        note="volatility/max_drawdown/pnl_today 样本不足，暂不计算",
    )


def risk(db: DBSession, user_id: str, settings: Settings) -> list[Breach]:
    """评估风险硬上限（PRD FR-ANL-002）：硬上限截断、软上限告警。返回触发清单。"""
    v = valuate(db, user_id)
    breaches: list[Breach] = []
    total = v.total_assets
    single_cap = Decimal(str(settings.risk_single_cap))
    industry_cap = Decimal(str(settings.risk_industry_cap))
    cash_floor = Decimal(str(settings.risk_cash_floor))
    top_n_conc = Decimal(str(settings.risk_top_n_concentration))

    for p in v.positions:
        if p.weight is not None and p.weight > single_cap:
            breaches.append(
                Breach(
                    rule="single_cap", level="hard", instrument_id=p.instrument_id,
                    code=p.code, actual=p.weight, limit=single_cap,
                )
            )

    industry_weight: dict[str, Decimal] = {}
    for p in v.positions:
        if p.weight is not None and p.industry:
            industry_weight[p.industry] = industry_weight.get(p.industry, Decimal(0)) + p.weight
    for ind, w in industry_weight.items():
        if w > industry_cap:
            breaches.append(
                Breach(
                    rule="industry_cap", level="hard", industry=ind,
                    actual=w, limit=industry_cap,
                )
            )

    cash_ratio = (v.cash / total) if total > 0 else Decimal(0)
    if total > 0 and cash_ratio < cash_floor:
        breaches.append(
            Breach(rule="cash_floor", level="hard", actual=cash_ratio, limit=cash_floor)
        )

    top_weights = sorted((p.weight for p in v.positions if p.weight is not None), reverse=True)
    top_n_sum = sum(top_weights[: settings.risk_top_n], start=Decimal(0))
    if top_n_sum > top_n_conc:
        breaches.append(
            Breach(rule="top_n_concentration", level="soft", actual=top_n_sum, limit=top_n_conc)
        )
    return breaches


def attribution(db: DBSession, user_id: str) -> Attribution:
    """收益/市值贡献分解：按标的、按行业、现金。"""
    v = valuate(db, user_id)
    by_instrument = [
        AttribRow(
            instrument_id=p.instrument_id,
            code=p.code,
            industry=p.industry,
            market_value=p.market_value,
            cost_basis=p.cost_basis,
            realized_pnl=p.realized_pnl,
            unrealized_pnl=p.unrealized_pnl,
        )
        for p in v.positions
    ]
    industry_mv: dict[str, Decimal] = {}
    industry_unreal: dict[str, Decimal] = {}
    for p in v.positions:
        key = p.industry or "未分类"
        industry_mv[key] = industry_mv.get(key, Decimal(0)) + (p.market_value or Decimal(0))
        industry_unreal[key] = (
            industry_unreal.get(key, Decimal(0)) + (p.unrealized_pnl or Decimal(0))
        )
    by_industry = [
        IndustryRow(industry=k, market_value=industry_mv[k], unrealized_pnl=industry_unreal[k])
        for k in industry_mv
    ]
    return Attribution(by_instrument=by_instrument, by_industry=by_industry, cash=v.cash)
