"""概率校准测试：reliability 分箱、Platt scaling、状态机与 OOS 门禁。"""

from decimal import Decimal

import pytest

from wws_adviser.modules.analytics.calibration import (
    CalibrationEvent,
    CalibrationItem,
    CalibrationRecord,
    CalibrationState,
    apply_platt,
    evaluate_oos,
    fit_platt,
    kelly_input,
    reliability_bins,
    reliability_check,
    state_on_date,
    transition,
)
from wws_adviser.modules.analytics.signals import BacktestStats


def _items(n_pred: int, wins: int) -> list[CalibrationItem]:
    """n_pred 条预测全在同一概率档，其中 wins 条命中。"""
    return [CalibrationItem(Decimal("0.6"), i < wins) for i in range(n_pred)]


# —— reliability 分箱 ——


def test_bins_group_by_probability_band() -> None:
    items = [CalibrationItem(Decimal("0.1"), False), CalibrationItem(Decimal("0.6"), True)]
    bins = reliability_bins(items)
    assert len(bins) == 2
    b0 = next(b for b in bins if b.bin_index == 0)
    assert b0.n == 1 and b0.avg_predicted == Decimal("0.1") and b0.actual_rate == Decimal(0)
    b3 = next(b for b in bins if b.bin_index == 3)
    assert b3.actual_rate == Decimal(1)


def test_bins_unsampled_bins_absent() -> None:
    bins = reliability_bins([CalibrationItem(Decimal("0.95"), True)])
    assert [b.bin_index for b in bins] == [4]


def test_deviation_and_judgement_threshold() -> None:
    # 10 条预测 0.6，实际 4 中 → deviation = -0.2；恰好达到 min_samples 参与判定
    bins = reliability_bins(_items(10, 4), min_samples=10)
    assert len(bins) == 1 and bins[0].judged
    assert bins[0].deviation == pytest.approx(Decimal("-0.2"), abs=Decimal("1e-12"))
    bins9 = reliability_bins(_items(9, 4), min_samples=10)
    assert not bins9[0].judged  # 样本不足不判定


# —— reliability 判定 ——


def test_check_well_calibrated_passes() -> None:
    bins = reliability_bins(_items(50, 30))  # 预测 0.6 实际 0.6
    verdict = reliability_check(bins)
    assert verdict.passed
    assert verdict.judged_bins == 1


def test_check_systematic_overestimate_fails() -> None:
    bins = reliability_bins(_items(50, 15))  # 预测 0.6 实际 0.3 → 高估 0.3
    verdict = reliability_check(bins)
    assert not verdict.passed
    assert verdict.worst_overestimate == pytest.approx(Decimal("0.3"), abs=Decimal("1e-12"))


def test_check_small_sample_bins_not_judged() -> None:
    bins = reliability_bins(_items(5, 0), min_samples=10)  # 严重偏差但样本不足
    assert not reliability_check(bins).passed  # 无已判定箱 → 不能宣称通过
    assert reliability_check(bins).judged_bins == 0


def test_check_mixed_bins_worst_case() -> None:
    # 箱1（0.6 档）校准良好；箱2（0.3 档）实际 0.75 → 低估 0.45 → 失败
    items = _items(50, 30) + [
        CalibrationItem(Decimal("0.3"), i < 15) for i in range(20)
    ]
    verdict = reliability_check(reliability_bins(items))
    assert not verdict.passed
    assert verdict.worst_underestimate == pytest.approx(Decimal("0.45"), abs=Decimal("1e-12"))


# —— Platt scaling ——


def test_platt_identity_on_perfect_calibration() -> None:
    # 预测即真实（大样本 0.6 档命中 60%）→ 修正应接近恒等
    items = [CalibrationItem(Decimal("0.6"), i < 60) for i in range(100)]
    params = fit_platt(items)
    corrected = apply_platt(Decimal("0.6"), params)
    assert corrected == pytest.approx(Decimal("0.6"), abs=Decimal("0.02"))


def test_platt_corrects_overestimate() -> None:
    # 预测 0.8 实际 0.4（系统性高估）→ 修正后应显著低于 0.8
    items = [CalibrationItem(Decimal("0.8"), i < 40) for i in range(100)]
    params = fit_platt(items)
    corrected = apply_platt(Decimal("0.8"), params)
    assert corrected < Decimal("0.7")
    # 修正后重评应通过（分箱内预测≈实际）
    fixed = [CalibrationItem(apply_platt(i.predicted_p, params), i.win) for i in items]
    assert reliability_check(reliability_bins(fixed)).passed


def test_platt_monotonic_preserved() -> None:
    items = [CalibrationItem(Decimal("0.3"), i < 20) for i in range(100)]
    params = fit_platt(items)
    ps = [apply_platt(Decimal(x), params) for x in ("0.1", "0.3", "0.5", "0.7", "0.9")]
    assert ps == sorted(ps)  # 修正保持概率单调


# —— 状态机 ——


def test_happy_path_transitions() -> None:
    s = CalibrationState.UNCALIBRATED
    s = transition(s, CalibrationEvent.START)
    assert s is CalibrationState.CALIBRATING
    s = transition(s, CalibrationEvent.PASS_OOS)
    assert s is CalibrationState.CALIBRATED_OOS
    s = transition(s, CalibrationEvent.EXPIRE)
    assert s is CalibrationState.STALE
    s = transition(s, CalibrationEvent.START)
    assert s is CalibrationState.CALIBRATING
    s = transition(s, CalibrationEvent.FAIL_OOS)
    assert s is CalibrationState.UNCALIBRATED


def test_stale_can_repass_directly() -> None:
    s = transition(CalibrationState.STALE, CalibrationEvent.PASS_OOS)
    assert s is CalibrationState.CALIBRATED_OOS


def test_illegal_transitions_raise() -> None:
    with pytest.raises(ValueError, match="非法状态转换"):
        transition(CalibrationState.UNCALIBRATED, CalibrationEvent.PASS_OOS)
    with pytest.raises(ValueError, match="非法状态转换"):
        transition(CalibrationState.CALIBRATED_OOS, CalibrationEvent.DECAY)


# —— OOS 门禁 ——


def _stats() -> BacktestStats:
    return BacktestStats(
        signal_id="s", n_total=100, n_win=60, n_loss=40,
        avg_win=Decimal("0.05"), avg_loss=Decimal("0.04"), b=Decimal("1.25"),
        p_low=Decimal("0.55"), p_mid=Decimal("0.6"), p_high=Decimal("0.65"),
        avg_cost=Decimal("0.002"),
    )


def test_oos_pass_with_good_calibration() -> None:
    items = [CalibrationItem(Decimal("0.6"), i < 60) for i in range(100)]
    verdict = evaluate_oos(_stats(), items, n_eff_oos=80)
    assert verdict.passed and verdict.reasons == ()
    assert not verdict.platt_applied


def test_oos_fails_insufficient_n_eff() -> None:
    items = [CalibrationItem(Decimal("0.6"), i < 60) for i in range(100)]
    verdict = evaluate_oos(_stats(), items, n_eff_oos=29)
    assert not verdict.passed
    assert any("n_eff_oos=29" in r for r in verdict.reasons)


def test_oos_platt_rescue_overestimate() -> None:
    # 高估 0.8→0.4：原始 reliability 失败 → Platt 修正后通过
    items = [CalibrationItem(Decimal("0.8"), i < 40) for i in range(100)]
    verdict = evaluate_oos(_stats(), items, n_eff_oos=80)
    assert verdict.platt_applied
    assert verdict.passed


def test_oos_fails_without_samples() -> None:
    verdict = evaluate_oos(_stats(), [], n_eff_oos=80)
    assert not verdict.passed
    assert any("无样本外校准样本" in r for r in verdict.reasons)


# —— 记录读时判定 + 凯利输入组装 ——


def _record(state: CalibrationState = CalibrationState.CALIBRATED_OOS) -> CalibrationRecord:
    return CalibrationRecord(
        signal_id="s", signal_version="v1", state=state,
        calibrated_on="2026-06-01", expires_on="2026-08-31",
        p_low=Decimal("0.55"), p_mid=Decimal("0.6"), p_high=Decimal("0.65"),
        b=Decimal("1.25"), n_eff=200, n_eff_oos=120, reliability_passed=True,
    )


def test_state_on_date_expires_to_stale() -> None:
    rec = _record()
    assert state_on_date(rec, "2026-08-24") is CalibrationState.CALIBRATED_OOS
    assert state_on_date(rec, "2026-09-01") is CalibrationState.STALE
    assert state_on_date(rec, "2026-08-31") is CalibrationState.CALIBRATED_OOS  # 当日未过


def test_kelly_input_assembly() -> None:
    ki = kelly_input(
        _record(), "2026-08-24",
        total_assets=Decimal("100000"), available_cash=Decimal("100000"),
    )
    assert ki.p_mid == Decimal("0.6") and ki.b == Decimal("1.25")
    assert ki.n_eff_oos == 120 and ki.reliability_passed
    assert ki.calibration_state is CalibrationState.CALIBRATED_OOS
    # 过期后组装 → STALE → 凯利关卡 1 拒绝
    ki_stale = kelly_input(_record(), "2026-09-01", total_assets=Decimal("100000"))
    assert ki_stale.calibration_state is CalibrationState.STALE
