"""建议评价与行为偏差分析测试（FR-REV-003 口径）。"""

from decimal import Decimal

from wws_adviser.modules.advice.domain import AdviceAction
from wws_adviser.modules.advice.evaluation import (
    BackfeedRecommendation,
    BiasKind,
    ObservationFacts,
    TradeFact,
    Verdict,
    analyze_behavioral_bias,
    backfeed,
    evaluate,
)


def _eval(action: AdviceAction, **facts) -> object:
    return evaluate("a1", action, ObservationFacts(**facts))


# —— BUY：条件式增加 ——


def test_buy_untriggered_is_reasonable() -> None:
    """核心原则：条件未出现即合理（即便后来上涨）——避免错误触发。"""
    e = _eval(AdviceAction.BUY, trigger_occurred=False, direction_return=Decimal("0.10"))
    assert e.verdict is Verdict.REASONABLE_UNTRIGGERED
    assert e.max_adverse_excursion is None


def test_buy_triggered_direction() -> None:
    up = _eval(AdviceAction.BUY, trigger_occurred=True, direction_return=Decimal("0.05"),
               max_adverse_excursion=Decimal("-0.02"))
    assert up.verdict is Verdict.DIRECTION_CORRECT
    assert up.max_adverse_excursion == Decimal("-0.02")
    down = _eval(AdviceAction.BUY, trigger_occurred=True, direction_return=Decimal("-0.03"))
    assert down.verdict is Verdict.DIRECTION_WRONG


def test_buy_missing_facts_inconclusive() -> None:
    e = _eval(AdviceAction.BUY, trigger_occurred=None)
    assert e.verdict is Verdict.INCONCLUSIVE


# —— REDUCE：避免"卖了就涨"道德化 ——


def test_reduce_avoided_loss_vs_benchmark() -> None:
    # 减仓后标的 -5%、基准 -1% → 超额 -4% < 0 → 减仓正确
    e = _eval(AdviceAction.REDUCE, direction_return=Decimal("-0.05"),
              benchmark_return=Decimal("-0.01"))
    assert e.verdict is Verdict.AVOIDED_LOSS
    assert e.excess_vs_benchmark == Decimal("-0.04")


def test_reduce_too_early() -> None:
    e = _eval(AdviceAction.REDUCE, direction_return=Decimal("0.08"),
              benchmark_return=Decimal("0.02"))
    assert e.verdict is Verdict.REDUCED_TOO_EARLY


# —— HOLD / SUSPEND ——


def test_hold_actionable_later() -> None:
    assert _eval(AdviceAction.HOLD, became_actionable=True).verdict is Verdict.ACTIONABLE_LATER
    assert _eval(AdviceAction.HOLD, became_actionable=False).verdict is Verdict.STILL_OBSERVING


def test_suspend_unwarranted_when_data_recovered() -> None:
    e = _eval(AdviceAction.SUSPEND, data_recovered=True, advice_would_be_warranted=True)
    assert e.verdict is Verdict.SUSPEND_UNWARRANTED
    e2 = _eval(AdviceAction.SUSPEND, data_recovered=True, advice_would_be_warranted=False)
    assert e2.verdict is Verdict.SUSPEND_WARRANTED


# —— 回灌校准 ——


def _directionals(n_correct: int, n_wrong: int) -> list[object]:
    out = []
    for _ in range(n_correct):
        out.append(evaluate("a", AdviceAction.BUY, ObservationFacts(
            trigger_occurred=True, direction_return=Decimal("0.02"))))
    for _ in range(n_wrong):
        out.append(evaluate("a", AdviceAction.BUY, ObservationFacts(
            trigger_occurred=True, direction_return=Decimal("-0.02"))))
    return out


def test_backfeed_none_below_threshold() -> None:
    rec = backfeed("s", _directionals(8, 2))
    assert rec.action == "none" and rec.wrong_rate == Decimal("0.2")


def test_backfeed_reduce_p_over_half_wrong() -> None:
    rec = backfeed("s", _directionals(4, 6))
    assert rec.action == "reduce_p"
    assert rec.suggested_p_factor == Decimal("0.8")
    assert rec.wrong_rate == Decimal("0.6")


def test_backfeed_decay_sustained_bad() -> None:
    rec = backfeed("s", _directionals(2, 8))
    assert rec.action == "decay"


def test_backfeed_small_sample_no_penalty() -> None:
    rec = backfeed("s", _directionals(0, 5), min_samples=10)
    assert rec.action == "none"
    assert rec.n_evaluated == 5  # 诚实记录：样本不足不惩罚


def test_backfeed_ignores_non_directional() -> None:
    """未触发/观察结论不掺入方向错误率。"""
    untriggered = [evaluate("a", AdviceAction.BUY, ObservationFacts(trigger_occurred=False,
                                                                    direction_return=Decimal(0)))]
    rec = backfeed("s", untriggered + _directionals(10, 0))
    assert rec.n_evaluated == 10  # 只算方向性评价
    assert rec.action == "none"


# —— 行为偏差 ——


def test_bias_disposal_effect_detected() -> None:
    trades = (
        [TradeFact(code=f"C{i}", kind="SELL", price=Decimal("10"), unrealized_pnl_sign=1)
         for i in range(5)]  # 卖的全是浮盈
        + [TradeFact(code=f"H{i}", kind="BUY", price=Decimal("10"), unrealized_pnl_sign=-1)
           for i in range(5)]  # 持的全是浮亏
    )
    findings = analyze_behavioral_bias(trades)
    assert any(f.kind is BiasKind.DISPOSAL_EFFECT for f in findings)


def test_bias_no_disposal_effect_when_mixed() -> None:
    trades = [TradeFact(code="C1", kind="SELL", price=Decimal("10"), unrealized_pnl_sign=-1)]
    assert not any(f.kind is BiasKind.DISPOSAL_EFFECT
                   for f in analyze_behavioral_bias(trades))


def test_bias_chasing_high_percentile_buy() -> None:
    trades = [TradeFact(code="C1", kind="BUY", price=Decimal("100"),
                        price_percentile_20d=Decimal("0.97"))]
    findings = analyze_behavioral_bias(trades)
    assert findings[0].kind is BiasKind.CHASING and findings[0].code == "C1"


def test_bias_rule_deviation_over_cap() -> None:
    trades = [TradeFact(code="C1", kind="BUY", price=Decimal("10"),
                        weight_after=Decimal("0.35"), single_cap=Decimal("0.30"))]
    assert any(f.kind is BiasKind.RULE_DEVIATION for f in analyze_behavioral_bias(trades))


def test_bias_overtrading() -> None:
    trades = [TradeFact(code=f"C{i%5}", kind="BUY", price=Decimal("10")) for i in range(16)]
    assert any(f.kind is BiasKind.OVERTRADING for f in analyze_behavioral_bias(trades))


def test_bias_clean_trades_no_findings() -> None:
    trades = [
        TradeFact(code="C1", kind="BUY", price=Decimal("10"), price_percentile_20d=Decimal("0.5")),
        TradeFact(code="C2", kind="SELL", price=Decimal("10"), unrealized_pnl_sign=-1),
    ]
    assert analyze_behavioral_bias(trades) == []
