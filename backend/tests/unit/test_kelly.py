"""凯利计算核心测试（§9.3 资格决策流：关卡拒绝/折扣/clip/区间数学）。"""

from decimal import Decimal

import pytest

from wws_adviser.modules.analytics.kelly import (
    CalibrationState,
    KellyInput,
    RejectReason,
    wilson_interval,
    compute_kelly,
)


def _ok_input(**overrides) -> KellyInput:
    """通过全部资格关卡的基线输入（p=0.6, b=1 → f*=0.2）。"""
    base = dict(
        signal_id="sig-test",
        p_low=Decimal("0.55"), p_mid=Decimal("0.60"), p_high=Decimal("0.65"),
        b=Decimal("1"),
        n_eff=200, n_eff_oos=120,
        calibration_state=CalibrationState.CALIBRATED_OOS,
        calibration_expires_on="2026-12-31", as_of_date="2026-08-24",
        reliability_passed=True,
        kelly_discount=Decimal("0.25"),
        total_assets=Decimal("100000"),
        available_cash=Decimal("100000"),
        current_position_value=Decimal("0"),
    )
    base.update(overrides)
    return KellyInput(**base)


# —— Wilson 区间 ——


def test_wilson_known_value() -> None:
    # 60/100：点估计 0.6，区间以 0.6 为中心附近收窄
    low, mid, high = wilson_interval(60, 100)
    assert mid == Decimal("0.6")
    assert low == pytest.approx(Decimal("0.5035"), abs=Decimal("0.002"))
    assert high == pytest.approx(Decimal("0.6915"), abs=Decimal("0.002"))
    assert low < mid < high


def test_wilson_zero_successes_low_is_zero() -> None:
    low, mid, high = wilson_interval(0, 50)
    assert low == Decimal(0)
    assert mid == Decimal(0)
    assert high > Decimal(0)  # 即使全败上界仍非零（小样本诚实）


def test_wilson_all_successes_high_capped() -> None:
    low, mid, high = wilson_interval(50, 50)
    assert high == Decimal(1)
    assert mid == Decimal(1)
    assert low < Decimal(1)


def test_wilson_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        wilson_interval(1, 0)
    with pytest.raises(ValueError):
        wilson_interval(-1, 10)
    with pytest.raises(ValueError):
        wilson_interval(11, 10)


# —— 关卡 1：校准状态 ——


@pytest.mark.parametrize("state,reason", [
    (CalibrationState.UNCALIBRATED, "calibration_uncalibrated"),
    (CalibrationState.CALIBRATING, "calibration_uncalibrated"),
    (CalibrationState.STALE, "calibration_stale"),
    (CalibrationState.DECAYED, "calibration_stale"),
])
def test_gate1_rejects_non_calibrated_states(state: CalibrationState, reason: str) -> None:
    out = compute_kelly(_ok_input(calibration_state=state))
    assert not out.accepted
    assert out.reject_reason == reason
    assert out.f_min is None and out.f_max is None  # 拒绝不输出区间


def test_gate1_rejects_expired_calibration() -> None:
    out = compute_kelly(_ok_input(as_of_date="2027-01-01", calibration_expires_on="2026-12-31"))
    assert not out.accepted
    assert out.reject_reason == RejectReason.CALIBRATION_EXPIRED.value


# —— 关卡 2：样本量分档 ——


def test_gate2_rejects_insufficient_oos_samples() -> None:
    out = compute_kelly(_ok_input(n_eff_oos=29))
    assert not out.accepted
    assert out.reject_reason == RejectReason.INSUFFICIENT_SAMPLES.value


def test_gate2_low_confidence_halving() -> None:
    full = compute_kelly(_ok_input(n_eff_oos=120))
    low = compute_kelly(_ok_input(n_eff_oos=50))
    assert full.accepted and low.accepted
    assert "low_confidence" in low.flags
    assert "low_confidence" not in full.flags
    assert low.f_max * 2 == pytest.approx(full.f_max, abs=Decimal("1e-12"))
    # 轨迹须含半折扣步骤
    assert any(s.kind == "low_confidence_halving" for s in low.trail)


# —— 关卡 3：reliability ——


def test_gate3_rejects_failed_reliability() -> None:
    out = compute_kelly(_ok_input(reliability_passed=False))
    assert not out.accepted
    assert out.reject_reason == RejectReason.CALIBRATION_FAILED.value


# —— 关卡 4：p 区间宽度 ——


def test_gate4_wide_interval_uses_p_low() -> None:
    out = compute_kelly(_ok_input(p_low=Decimal("0.40"), p_mid=Decimal("0.60"), p_high=Decimal("0.80")))
    assert out.accepted
    assert "wide_p_interval" in out.flags
    # 有效中枢被替换为 p_low=0.40 → f*(0.4, b=1) = -0.2 < 0 → 无正边际坍缩为 0
    assert out.f_min == Decimal(0) and out.f_max == Decimal(0)
    assert "negative_edge" in out.flags


def test_gate4_narrow_interval_no_flag() -> None:
    out = compute_kelly(_ok_input())  # 宽度 0.10 < 0.30
    assert "wide_p_interval" not in out.flags


# —— 关卡 5：b 符号与极端性 ——


def test_gate5_non_positive_payoff_outputs_zero() -> None:
    out = compute_kelly(_ok_input(b=Decimal(0)))
    assert out.accepted
    assert out.f_min == Decimal(0) and out.f_max == Decimal(0)
    assert "non_positive_payoff" in out.flags


def test_gate5_extreme_payoff_keeps_lower_bound_only() -> None:
    out = compute_kelly(_ok_input(b=Decimal("15")))
    assert out.accepted
    assert "extreme_payoff" in out.flags
    # 仅区间下限：f_max == f_min（来自 p_low 的折扣后下限）
    assert out.f_min == out.f_max
    assert out.f_max > Decimal(0)


def test_gate5_boundary_b_values_accepted_full_interval() -> None:
    # b=0.1 需 p>1/1.1≈0.909 才有正边际；b=10 时基线 p 即有正边际
    out_low_b = compute_kelly(_ok_input(
        b=Decimal("0.1"),
        p_low=Decimal("0.92"), p_mid=Decimal("0.94"), p_high=Decimal("0.96"),
    ))
    assert out_low_b.accepted
    assert "extreme_payoff" not in out_low_b.flags
    assert out_low_b.f_min < out_low_b.f_max

    out_high_b = compute_kelly(_ok_input(b=Decimal("10")))
    assert out_high_b.accepted
    assert "extreme_payoff" not in out_high_b.flags
    assert out_high_b.f_min < out_high_b.f_max


# —— 关卡 6/7/8：区间数学与折扣 ——


def test_kelly_math_known_example() -> None:
    # p=0.60, b=1 → f* = 0.6 − 0.4/1 = 0.2；折扣 0.25 → 0.05
    out = compute_kelly(_ok_input())
    assert out.f_max == pytest.approx(Decimal("0.05"), abs=Decimal("1e-12"))
    # f_low 来自 p=0.55：0.55−0.45 = 0.10 → ×0.25 = 0.025
    assert out.f_min == pytest.approx(Decimal("0.025"), abs=Decimal("1e-12"))
    assert out.value_max == pytest.approx(Decimal("5000"), abs=Decimal("1e-8"))


def test_negative_edge_collapses_to_zero() -> None:
    out = compute_kelly(_ok_input(p_low=Decimal("0.30"), p_mid=Decimal("0.35"), p_high=Decimal("0.40")))
    assert out.accepted
    assert out.f_min == Decimal(0) and out.f_max == Decimal(0)
    assert "negative_edge" in out.flags


def test_confidence_and_liquidity_discounts_applied() -> None:
    out = compute_kelly(_ok_input(confidence_discount=Decimal("0.8"), liquidity_discount=Decimal("0.5")))
    # 0.05 × 0.8 × 0.5 = 0.02
    assert out.f_max == pytest.approx(Decimal("0.02"), abs=Decimal("1e-12"))
    kinds = [s.kind for s in out.trail]
    assert "confidence_discount" in kinds and "liquidity_discount" in kinds


# —— 关卡 9：clip ——


def test_clip_cash_floor_binds() -> None:
    # 可用现金 3000，现金下限 10%×100000=10000 → 可投上限 = 3000−10000 < 0 → 0
    out = compute_kelly(_ok_input(available_cash=Decimal("3000")))
    assert out.accepted
    assert out.value_max == Decimal(0)
    assert any(s.kind == "clip_cash_floor" for s in out.trail)


def test_clip_single_cap_binds() -> None:
    # 单标的上限 30%×10万=30000，已有持仓 28000 → 新增上限 2000 < 5000
    out = compute_kelly(_ok_input(current_position_value=Decimal("28000")))
    assert out.value_max == Decimal("2000")
    assert any(s.kind == "clip_single_cap" for s in out.trail)


def test_clip_industry_and_portfolio_headrooms() -> None:
    out = compute_kelly(_ok_input(industry_headroom_value=Decimal("1500")))
    assert out.value_max == Decimal("1500")
    out2 = compute_kelly(_ok_input(portfolio_headroom_value=Decimal("800")))
    assert out2.value_max == Decimal("800")
    assert any(s.kind == "clip_portfolio" for s in out2.trail)


def test_clip_compresses_interval_min() -> None:
    out = compute_kelly(_ok_input(portfolio_headroom_value=Decimal("1000")))  # < value_min 2500
    assert out.value_max == Decimal("1000")
    assert out.value_min == Decimal("1000")  # 下限被压到与上限一致
    assert out.f_min == out.f_max


# —— 关卡 10：整手取整 ——


def test_lot_rounding_too_small_for_one_lot() -> None:
    # f_max 5000 元、价格 1300、每手 13 万：不足一手，无法以整手安全表达
    # → 只显示仓位区间（suggested_lots=None + rounding_imprecise 标记）
    out = compute_kelly(_ok_input(price=Decimal("1300")))
    assert out.accepted
    assert out.suggested_lots is None
    assert "rounding_imprecise" in out.flags
    assert out.value_max == pytest.approx(Decimal("5000"), abs=Decimal("1e-8"))


def test_lot_rounding_whole_lots() -> None:
    out = compute_kelly(_ok_input(price=Decimal("10"), total_assets=Decimal("100000"),
                                  available_cash=Decimal("100000")))
    # 5000 / (10×100) = 5 手
    assert out.suggested_lots == 5


def test_lot_rounding_none_without_price() -> None:
    out = compute_kelly(_ok_input())
    assert out.suggested_lots is None


# —— 无组合上下文（纯研究口径）——


def test_no_portfolio_context_returns_fraction_interval() -> None:
    out = compute_kelly(_ok_input(total_assets=Decimal(0), available_cash=Decimal(0)))
    assert out.accepted
    assert out.f_max == pytest.approx(Decimal("0.05"), abs=Decimal("1e-12"))
    assert out.value_max is None


# —— 输入校验 fail loud ——


def test_validation_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError, match="概率区间"):
        compute_kelly(_ok_input(p_low=Decimal("0.7"), p_mid=Decimal("0.6"), p_high=Decimal("0.65")))
    with pytest.raises(ValueError, match="凯利折扣"):
        compute_kelly(_ok_input(kelly_discount=Decimal("0.5")))
    with pytest.raises(ValueError, match="凯利折扣"):
        compute_kelly(_ok_input(kelly_discount=Decimal("0.05")))
    with pytest.raises(ValueError, match="confidence_discount"):
        compute_kelly(_ok_input(confidence_discount=Decimal("1.5")))


def test_trail_records_every_binding_adjustment() -> None:
    out = compute_kelly(_ok_input(
        n_eff_oos=50,  # 半折扣
        confidence_discount=Decimal("0.8"),
        current_position_value=Decimal("29000"),  # 单标的上限剩余 1000，真实受限
    ))
    kinds = [s.kind for s in out.trail]
    assert "fractional_discount" in kinds
    assert "low_confidence_halving" in kinds
    assert "confidence_discount" in kinds
    assert "clip_single_cap" in kinds
    # 每步的 before/after 单调不增（金额上限语义）
    valued = [s for s in out.trail if s.before is not None and s.kind.startswith("clip")]
    for s in valued:
        assert s.after is not None and s.after <= s.before
