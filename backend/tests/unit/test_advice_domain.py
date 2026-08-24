"""Advice 领域测试：FSM、发布门禁、冲突处理、有效期与盘中组装。"""

from decimal import Decimal

import pytest

from wws_adviser.modules.advice.domain import (
    Advice,
    AdviceAction,
    AdviceState,
    IntradayContext,
    build_intraday_advice,
)


def _advice(**overrides) -> Advice:
    base = dict(
        advice_id="a1", signal_id="s1", code="600519",
        action=AdviceAction.BUY, state=AdviceState.PUBLISHED,
        valid_from="2026-08-24T02:00:00+00:00", expires_at="2026-08-24T02:05:00+00:00",
        f_min=Decimal("0.02"), f_max=Decimal("0.05"),
    )
    base.update(overrides)
    return Advice(**base)


# —— FSM ——


def test_happy_path_full_transitions() -> None:
    from wws_adviser.modules.advice.domain import next_check

    s = AdviceState.DRAFT
    seen = [s]
    for _ in range(5):
        s = next_check(s)
        seen.append(s)
    assert seen == [
        AdviceState.DRAFT, AdviceState.DATA_CHECKED, AdviceState.RISK_CHECKED,
        AdviceState.MODEL_EXPLAINED, AdviceState.OUTPUT_VALIDATED, AdviceState.PUBLISHED,
    ]


def test_advance_from_published_raises() -> None:
    from wws_adviser.modules.advice.domain import next_check

    with pytest.raises(ValueError, match="终态"):
        next_check(AdviceState.PUBLISHED)


def test_degrade_and_block_from_any_check_state() -> None:
    from wws_adviser.modules.advice.domain import block, degrade, next_check

    for s in (AdviceState.DRAFT, AdviceState.DATA_CHECKED, AdviceState.MODEL_EXPLAINED):
        assert degrade(s) is AdviceState.DEGRADED
        assert block(s) is AdviceState.BLOCKED
    # 终态不可再变
    with pytest.raises(ValueError):
        degrade(AdviceState.DEGRADED)
    with pytest.raises(ValueError):
        block(AdviceState.BLOCKED)
    with pytest.raises(ValueError):
        next_check(AdviceState.DEGRADED)


# —— 发布门禁 ——


def test_publish_gate_all_pass() -> None:
    from wws_adviser.modules.advice.domain import PublishChecks, publish_gate

    ok, failed = publish_gate(PublishChecks(
        ledger_reconciled=True, quote_fresh=True, instrument_tradable=True,
        numbers_deterministic=True, within_hard_limits=True,
        has_validity_window=True, evidence_complete=True,
    ))
    assert ok and failed == ()


def test_publish_gate_reports_each_failure() -> None:
    from wws_adviser.modules.advice.domain import PublishChecks, publish_gate

    ok, failed = publish_gate(PublishChecks(
        ledger_reconciled=True, quote_fresh=False, instrument_tradable=False,
        numbers_deterministic=True, within_hard_limits=False,
        has_validity_window=True, evidence_complete=True,
    ))
    assert not ok
    assert set(failed) == {"行情过期", "标的不可交易", "突破硬性风险限制"}


# —— 冲突处理 ——


def test_conflict_resolved_by_deterministic_rebuild() -> None:
    from wws_adviser.modules.advice.domain import resolve_conflict

    assert resolve_conflict(model_conflicts=True, deterministic_rebuild_ok=True) is AdviceAction.HOLD
    assert resolve_conflict(model_conflicts=False, deterministic_rebuild_ok=False) is AdviceAction.HOLD


def test_conflict_without_rebuild_suspends() -> None:
    from wws_adviser.modules.advice.domain import resolve_conflict

    assert resolve_conflict(model_conflicts=True, deterministic_rebuild_ok=False) is AdviceAction.SUSPEND


# —— 有效期 ——


def test_is_actionable_respects_window_and_invalidation() -> None:
    from wws_adviser.modules.advice.domain import invalidate, is_actionable

    a = _advice()
    assert is_actionable(a, "2026-08-24T02:01:00+00:00")
    assert not is_actionable(a, "2026-08-24T01:59:00+00:00")   # 早于窗口
    assert not is_actionable(a, "2026-08-24T02:05:00+00:00")   # 到期即失效
    dead = invalidate(a, "行情过期")
    assert not is_actionable(dead, "2026-08-24T02:01:00+00:00")
    assert "行情过期" in dead.invalidation_reasons


def test_invalidate_only_published_or_degraded() -> None:
    from wws_adviser.modules.advice.domain import invalidate

    with pytest.raises(ValueError):
        invalidate(_advice(state=AdviceState.DRAFT), "x")


# —— 盘中组装 ——


def _ctx(**overrides) -> IntradayContext:
    base = dict(
        code="600519", signal_id="sig-1",
        quote_fresh=True, tradable=True, ledger_reconciled=True,
        kelly_accepted=True, kelly_rejected=False,
        kelly_f_min=Decimal("0.02"), kelly_f_max=Decimal("0.05"),
        kelly_value_min=Decimal("2000"), kelly_value_max=Decimal("5000"),
        kelly_suggested_lots=5, kelly_reasons=("fractional_discount ×0.25",),
    )
    base.update(overrides)
    return IntradayContext(**base)


def test_build_published_interval_advice() -> None:
    a = build_intraday_advice(
        _ctx(), advice_id="a1",
        valid_from="2026-08-24T02:00:00+00:00", expires_at="2026-08-24T02:05:00+00:00",
    )
    assert a.state is AdviceState.PUBLISHED
    assert a.action is AdviceAction.BUY
    assert a.f_min == Decimal("0.02") and a.f_max == Decimal("0.05")
    assert a.suggested_lots == 5
    assert a.has_position_interval
    assert a.trigger_conditions  # 发布形态必须带触发/失效条件


def test_build_suspend_when_data_unqualified() -> None:
    a = build_intraday_advice(
        _ctx(quote_fresh=False, ledger_reconciled=False),
        advice_id="a1", valid_from="t0", expires_at="t1",
    )
    assert a.state is AdviceState.DEGRADED
    assert a.action is AdviceAction.SUSPEND
    assert not a.has_position_interval  # 暂停不携带区间
    assert "行情过期" in a.reasons and "账本未对账" in a.reasons


def test_build_suspend_when_no_calibrated_signal() -> None:
    a = build_intraday_advice(
        _ctx(kelly_accepted=None),
        advice_id="a1", valid_from="t0", expires_at="t1",
    )
    assert a.action is AdviceAction.SUSPEND
    assert "无已校准信号" in a.reasons


def test_build_hold_without_interval_when_kelly_rejected() -> None:
    a = build_intraday_advice(
        _ctx(kelly_rejected=True, kelly_accepted=False, kelly_f_min=None,
             kelly_f_max=None, kelly_value_min=None, kelly_value_max=None,
             kelly_reasons=("insufficient_samples",)),
        advice_id="a1", valid_from="t0", expires_at="t1",
    )
    assert a.state is AdviceState.DEGRADED
    assert a.action is AdviceAction.HOLD
    assert not a.has_position_interval
    assert a.reasons == ("insufficient_samples",)


def test_build_hold_when_kelly_zero_interval() -> None:
    a = build_intraday_advice(
        _ctx(kelly_f_min=Decimal(0), kelly_f_max=Decimal(0),
             kelly_value_min=Decimal(0), kelly_value_max=Decimal(0), kelly_suggested_lots=0),
        advice_id="a1", valid_from="t0", expires_at="t1",
    )
    assert a.action is AdviceAction.HOLD
    assert a.state is AdviceState.PUBLISHED
