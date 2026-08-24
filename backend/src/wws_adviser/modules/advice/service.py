"""Advice 服务：盘中快速建议编排（TECH §11.3，Phase 2 波6 接通校准存储）。

流程：行情刷新（180s 新鲜度）→ 账本对账事实 → 当前是否触发已校准信号
（L1 机械规则在最近 bars 上评估）→ 凯利资格决策 → 组装建议。

无触发/无校准记录/数据不合格 → 按规范返回「暂停建议 + 原因 + 已知事实」，
不静默隐藏。
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.advice.domain import (
    Advice,
    IntradayContext,
    build_intraday_advice,
)
from wws_adviser.modules.analytics import calibration_service
from wws_adviser.modules.analytics import signals as sig
from wws_adviser.modules.analytics import service as analytics_service
from wws_adviser.modules.analytics.kelly import KellyOutcome, compute_kelly
from wws_adviser.modules.analytics.calibration import kelly_input
from wws_adviser.modules.portfolio import service as portfolio_service
from wws_adviser.ports.market_data import InstrumentRef

_logger = logging.getLogger(__name__)

# 盘中建议有效期（秒）：TTL 内重复请求语义一致
INTRADAY_TTL_SECONDS = 300


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _active_signal_for_code(
    db: DBSession, settings: Settings, code: str
) -> tuple[sig.SignalDefinition, sig.SignalInstance] | None:
    """评估已注册信号是否在 code 的最新 bar 触发（返回命中的定义与实例）。"""
    bars_by_code = calibration_service.load_bars_by_code(db)
    bars = bars_by_code.get(code)
    if not bars:
        return None
    latest_date = bars[-1].business_date
    for row in db.scalars(select_all_signals(db)):
        definition = calibration_service._to_signal_def(row)  # noqa: SLF001 — 同模块族内部转换
        instances = sig.breakout_signals(definition, {code: bars})
        hit = next((i for i in instances if i.trigger_date == latest_date), None)
        if hit is not None:
            return definition, hit
    return None


def select_all_signals(db: DBSession):
    from sqlalchemy import select

    from wws_adviser.modules.analytics.models import SignalRecord

    return select(SignalRecord).order_by(SignalRecord.signal_id)


def _kelly_for_code(
    db: DBSession,
    settings: Settings,
    *,
    signal_id: str,
    code: str,
    user_id: str,
    as_of: str,
) -> KellyOutcome | None:
    """信号校准记录 + 组合上下文 → 凯利结果。无校准记录 → None。"""
    record = calibration_service.latest_valid_calibration(db, signal_id, as_of=as_of)
    if record is None:
        return None
    # 组合上下文（clip 输入）
    valuation = analytics_service.valuate(db, user_id)
    position_value = Decimal(0)
    for p in valuation.positions:
        if p.code == code:
            position_value = p.market_value or position_value
    state = portfolio_service.get_position_state(
        db, portfolio_service.get_user_account(db, user_id).id
    )
    ki = kelly_input(
        record, as_of,
        total_assets=valuation.total_assets or Decimal(0),
        available_cash=state.cash,
        current_position_value=position_value,
        cash_floor=Decimal(str(settings.risk_cash_floor)),
        single_cap=Decimal(str(settings.risk_single_cap)),
        kelly_discount=Decimal(settings.kelly_discount_default),
    )
    return compute_kelly(ki)


async def intraday_advice(
    db: DBSession,
    settings: Settings,
    request: Request,
    *,
    user_id: str,
    code: str,
) -> Advice:
    """POST /assistant/intraday 的编排。"""
    now = now_utc_iso()
    expires_at = (_parse_iso(now) + timedelta(seconds=INTRADAY_TTL_SECONDS)).isoformat()

    # 已知事实：账本对账状态
    try:
        account = portfolio_service.get_user_account(db, user_id)
        ledger_reconciled = bool(account.reconciled) if account is not None else False
    except Exception:
        ledger_reconciled = False

    # 行情快照（首请求刷新；适配器失败 → 不新鲜 → 暂停建议）
    quote_fresh = False
    provider = getattr(request.app.state, "quote_provider", None)
    if provider is not None:
        try:
            quotes = await provider.fetch_quotes(
                [InstrumentRef(code=code, market="SSE", kind="stock")]
            )
            if quotes:
                lag = (datetime.now(timezone.utc) - _parse_iso(quotes[0].fetched_at)).total_seconds()
                quote_fresh = lag <= settings.intraday_freshness_threshold_seconds
        except Exception as exc:  # noqa: BLE001 — 行情失败按不新鲜处理，不外抛
            _logger.warning("盘中行情获取失败 code=%s: %s", code, exc)

    # 信号触发 + 凯利资格
    try:
        active = _active_signal_for_code(db, settings, code)
    except Exception as exc:  # noqa: BLE001 — 评估失败视同无信号（可审计）
        _logger.warning("信号评估失败 code=%s: %s", code, exc)
        active = None

    if active is None:
        ctx = IntradayContext(
            code=code, signal_id="", quote_fresh=quote_fresh, tradable=True,
            ledger_reconciled=ledger_reconciled, kelly_accepted=None,
        )
    else:
        definition, _inst = active
        as_of_date = now[:10]
        outcome = _kelly_for_code(
            db, settings, signal_id=definition.signal_id, code=code,
            user_id=user_id, as_of=as_of_date,
        )
        if outcome is None:
            ctx = IntradayContext(
                code=code, signal_id=definition.signal_id, quote_fresh=quote_fresh,
                tradable=True, ledger_reconciled=ledger_reconciled, kelly_accepted=None,
            )
        else:
            ctx = IntradayContext(
                code=code, signal_id=definition.signal_id, quote_fresh=quote_fresh,
                tradable=True, ledger_reconciled=ledger_reconciled,
                kelly_accepted=outcome.accepted, kelly_rejected=not outcome.accepted,
                kelly_f_min=outcome.f_min, kelly_f_max=outcome.f_max,
                kelly_value_min=outcome.value_min, kelly_value_max=outcome.value_max,
                kelly_suggested_lots=outcome.suggested_lots,
                kelly_reasons=(
                    (outcome.reject_reason,) if outcome.reject_reason else outcome.flags
                ),
            )

    return build_intraday_advice(
        ctx,
        advice_id=new_id(),
        valid_from=now, expires_at=expires_at,
        evidence_ids=(),
    )


def advice_to_payload(a: Advice) -> dict[str, Any]:
    """Advice → API JSON（拒绝/暂停不携带区间，字段保持可审计）。"""
    return {
        "advice_id": a.advice_id,
        "signal_id": a.signal_id,
        "code": a.code,
        "action": a.action.value,
        "state": a.state.value,
        "valid_from": a.valid_from,
        "expires_at": a.expires_at,
        "actionable": a.state.value == "published" and not a.invalidated,
        "trigger_conditions": list(a.trigger_conditions),
        "invalidated": a.invalidated,
        "invalidation_reasons": list(a.invalidation_reasons),
        "f_min": str(a.f_min) if a.f_min is not None else None,
        "f_max": str(a.f_max) if a.f_max is not None else None,
        "value_min": str(a.value_min) if a.value_min is not None else None,
        "value_max": str(a.value_max) if a.value_max is not None else None,
        "suggested_lots": a.suggested_lots,
        "reasons": list(a.reasons),
        "evidence_ids": list(a.evidence_ids),
    }
