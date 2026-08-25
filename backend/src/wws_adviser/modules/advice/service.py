"""Advice 服务：盘中快速建议编排（TECH §11.3，Phase 2 波6/核对补强）。

流程：TTL 缓存复用 → 行情刷新（180s 新鲜度）→ 账本对账/标的可交易事实 →
当日信号触发评估 → 校准记录（读时过期）→ 凯利资格 → publish_gate → 组装落库。

降级原因码（PRD FR-ANL-004）：data_stale / market_abnormal /
ledger_unreconciled / no_calibrated_signal / gate:*——不静默隐藏。
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.advice.domain import (
    AdjustmentStep,
    Advice,
    IntradayContext,
    build_intraday_advice,
)
from wws_adviser.modules.advice.models import AdviceRecord
from wws_adviser.modules.analytics import calibration_service
from wws_adviser.modules.analytics import service as analytics_service
from wws_adviser.modules.analytics import signals as sig
from wws_adviser.modules.analytics.calibration import kelly_input
from wws_adviser.modules.analytics.kelly import KellyOutcome, compute_kelly
from wws_adviser.modules.analytics.models import SignalRecord
from wws_adviser.modules.instruments.models import Instrument
from wws_adviser.modules.market_data import repository as md_repository
from wws_adviser.modules.portfolio import service as portfolio_service
from wws_adviser.ports.market_data import InstrumentRef

_logger = logging.getLogger(__name__)

# 盘中建议有效期（秒）：TTL 内重复请求复用缓存（§11.3）
INTRADAY_TTL_SECONDS = 300

# 进程内 TTL 缓存：code → (expires_at, advice)。单实例单用户形态足够；
# 缓存命中时不重复刷新行情（重复请求语义一致）。
_cache: dict[str, tuple[str, Advice]] = {}


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _is_tradable(db: DBSession, code: str) -> bool:
    row = db.scalar(select(Instrument).where(Instrument.code == code))
    return bool(row.tradable) if row is not None else True


def _active_signal_for_code(
    db: DBSession, code: str
) -> tuple[sig.SignalDefinition, sig.SignalInstance] | None:
    """评估已注册信号是否在 code 的最新 bar 触发（返回命中的定义与实例）。"""
    bars_by_code = calibration_service.load_bars_by_code(db)
    bars = bars_by_code.get(code)
    if not bars:
        return None
    latest_date = bars[-1].business_date
    for row in db.scalars(select(SignalRecord).order_by(SignalRecord.signal_id)):
        definition = calibration_service._to_signal_def(row)  # noqa: SLF001 — 同模块族内部转换
        instances = sig.breakout_signals(definition, {code: bars})
        hit = next((i for i in instances if i.trigger_date == latest_date), None)
        if hit is not None:
            return definition, hit
    return None


def _evidence_refs(db: DBSession, code: str, calibration_row_id: str | None) -> tuple[str, ...]:
    """关键事实证据引用：校准记录 + 最新行情记录（发布门禁 evidence_complete）。"""
    refs: list[str] = []
    if calibration_row_id:
        refs.append(f"calibration:{calibration_row_id}")
    inst = db.scalar(select(Instrument).where(Instrument.code == code))
    if inst is not None:
        latest = md_repository.latest_market_record_any_source(db, inst.id)
        if latest is not None:
            refs.append(f"market_record:{latest.id}")
    return tuple(refs)


def _kelly_for_code(
    db: DBSession,
    settings: Settings,
    *,
    signal_id: str,
    code: str,
    user_id: str,
    as_of: str,
) -> tuple[KellyOutcome | None, str | None]:
    """信号校准记录 + 组合上下文 → 凯利结果。返回 (outcome, 校准记录行 id)。"""
    record, row_id = calibration_service.latest_valid_calibration_with_row(
        db, signal_id, as_of=as_of
    )
    if record is None:
        return None, None
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
    return compute_kelly(ki), row_id


async def intraday_advice(
    db: DBSession,
    settings: Settings,
    request: Request,
    *,
    user_id: str,
    code: str,
) -> Advice:
    """POST /assistant/intraday 的编排（TTL 内重复请求复用缓存）。"""
    now = now_utc_iso()
    cached = _cache.get(code)
    if cached is not None and cached[1].actionable and cached[0] > now:
        return cached[1]
    expires_at = (_parse_iso(now) + timedelta(seconds=INTRADAY_TTL_SECONDS)).isoformat()

    try:
        account = portfolio_service.get_user_account(db, user_id)
        ledger_reconciled = bool(account.reconciled) if account is not None else False
    except Exception:
        ledger_reconciled = False

    quote_fresh = False
    provider = getattr(request.app.state, "quote_provider", None)
    if provider is not None:
        try:
            quotes = await provider.fetch_quotes(
                [InstrumentRef(code=code, market="SSE", kind="stock")]
            )
            if quotes:
                lag = (datetime.now(UTC) - _parse_iso(quotes[0].fetched_at)).total_seconds()
                quote_fresh = lag <= settings.intraday_freshness_threshold_seconds
        except Exception as exc:  # noqa: BLE001 — 行情失败按不新鲜处理，不外抛
            _logger.warning("盘中行情获取失败 code=%s: %s", code, exc)

    tradable = _is_tradable(db, code)

    try:
        active = _active_signal_for_code(db, code)
    except Exception as exc:  # noqa: BLE001 — 评估失败视同无信号（可审计）
        _logger.warning("信号评估失败 code=%s: %s", code, exc)
        active = None

    calibration_row_id: str | None = None
    if active is None:
        ctx = IntradayContext(
            code=code, signal_id="", quote_fresh=quote_fresh, tradable=tradable,
            ledger_reconciled=ledger_reconciled, kelly_accepted=None,
        )
    else:
        definition, _inst = active
        outcome, calibration_row_id = _kelly_for_code(
            db, settings, signal_id=definition.signal_id, code=code,
            user_id=user_id, as_of=now[:10],
        )
        if outcome is None:
            ctx = IntradayContext(
                code=code, signal_id=definition.signal_id, quote_fresh=quote_fresh,
                tradable=tradable, ledger_reconciled=ledger_reconciled, kelly_accepted=None,
            )
        else:
            trail = tuple(
                AdjustmentStep(kind=s.kind, note=s.note, before=s.before, after=s.after)
                for s in outcome.trail
            )
            ctx = IntradayContext(
                code=code, signal_id=definition.signal_id, quote_fresh=quote_fresh,
                tradable=tradable, ledger_reconciled=ledger_reconciled,
                kelly_accepted=outcome.accepted, kelly_rejected=not outcome.accepted,
                kelly_f_min=outcome.f_min, kelly_f_max=outcome.f_max,
                kelly_value_min=outcome.value_min, kelly_value_max=outcome.value_max,
                kelly_suggested_lots=outcome.suggested_lots,
                kelly_reasons=(
                    (outcome.reject_reason,) if outcome.reject_reason else outcome.flags
                ),
                kelly_trail=trail,
            )

    evidence = _evidence_refs(db, code, calibration_row_id)
    advice = build_intraday_advice(
        ctx,
        advice_id=new_id(),
        valid_from=now, expires_at=expires_at,
        evidence_ids=evidence,
    )
    _persist(db, user_id, advice)
    if advice.state.value == "published":
        _cache[code] = (advice.expires_at, advice)
    else:
        _cache.pop(code, None)
    return advice


def _persist(db: DBSession, user_id: str, advice: Advice) -> None:
    """建议落库（FR-REV-003：保存建议时的数据快照；TECH §9.3：原因链写入 Advice 记录）。"""
    now = now_utc_iso()
    db.add(AdviceRecord(
        id=advice.advice_id, user_id=user_id,
        signal_id=advice.signal_id, code=advice.code,
        action=advice.action.value, state=advice.state.value,
        valid_from=advice.valid_from, expires_at=advice.expires_at,
        f_min=str(advice.f_min) if advice.f_min is not None else None,
        f_max=str(advice.f_max) if advice.f_max is not None else None,
        value_min=str(advice.value_min) if advice.value_min is not None else None,
        value_max=str(advice.value_max) if advice.value_max is not None else None,
        suggested_lots=advice.suggested_lots,
        reasons_json=json.dumps(list(advice.reasons), ensure_ascii=False),
        trail_json=json.dumps(
            [
                {"kind": s.kind, "note": s.note,
                 "before": str(s.before) if s.before is not None else None,
                 "after": str(s.after) if s.after is not None else None}
                for s in advice.trail
            ], ensure_ascii=False,
        ),
        evidence_json=json.dumps(list(advice.evidence_ids), ensure_ascii=False),
        created_at=now, updated_at=now, row_version=1,
    ))
    db.commit()


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
        # 完整调整轨迹（计算输入/折扣/约束 → 最终区间，PRD 展示规则）
        "trail": [
            {"kind": s.kind, "note": s.note,
             "before": str(s.before) if s.before is not None else None,
             "after": str(s.after) if s.after is not None else None}
            for s in a.trail
        ],
    }
