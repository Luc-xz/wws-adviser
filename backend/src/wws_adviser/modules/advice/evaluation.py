"""建议结果评价与行为偏差分析（FR-REV-003，评价口径版本化）。

核心原则：条件式建议的评价本质是「条件设计是否合理 + 触发后方向」，
不是「涨没涨」——未触发即合理（避免错误触发）。

按动作类型口径（EVAL_SPEC v1）：
    BUY（条件式增加） 触发后 5–20 日：触发是否出现 + 出现后方向；次口径 MAE
    REDUCE（减少）     失效前：减仓后相对基准超额（避免"卖了就涨"道德化）；次口径波动变化
    HOLD（观察）       不评价收益：是否进入可操作状态
    SUSPEND（暂停）    不评价收益：数据恢复后是否本该给建议

评价回灌：同类信号方向错误率高 → 建议下调 p 或转 DECAYED（接通
「凯利输入 ↔ 建议评价 ↔ 信号校准」闭环）。
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from wws_adviser.modules.advice.domain import AdviceAction


EVALUATION_SPEC_VERSION = "1"


class Verdict(StrEnum):
    """评价结论（不得只用涨跌二分）。"""

    REASONABLE_UNTRIGGERED = "reasonable_untriggered"  # 条件未出现：避免错误触发，合理
    DIRECTION_CORRECT = "direction_correct"
    DIRECTION_WRONG = "direction_wrong"
    AVOIDED_LOSS = "avoided_loss"          # REDUCE：减仓后跑赢基准（超额>0）
    REDUCED_TOO_EARLY = "reduced_too_early"  # REDUCE：减仓后跑输基准
    ACTIONABLE_LATER = "actionable_later"   # HOLD：进入可操作状态
    STILL_OBSERVING = "still_observing"
    SUSPEND_UNWARRANTED = "suspend_unwarranted"  # 数据恢复且本该给建议（降级过频信号）
    SUSPEND_WARRANTED = "suspend_warranted"
    INCONCLUSIVE = "inconclusive"           # 事实缺失：诚实标注不强行判


@dataclass(frozen=True)
class ObservationFacts:
    """观察窗口内的事实（由调用方从行情/组合重建，纯函数消费）。"""

    trigger_occurred: bool | None = None            # 触发条件是否出现
    direction_return: Decimal | None = None         # 触发后窗口收益（BUY 主口径）
    benchmark_return: Decimal | None = None         # 基准收益（REDUCE 口径）
    max_adverse_excursion: Decimal | None = None    # 区间内最大不利波动（BUY 次口径）
    portfolio_vol_before: Decimal | None = None     # 组合波动（REDUCE 次口径）
    portfolio_vol_after: Decimal | None = None
    became_actionable: bool | None = None           # HOLD：后续进入可操作状态
    data_recovered: bool | None = None              # SUSPEND：数据是否恢复
    advice_would_be_warranted: bool | None = None   # SUSPEND 主口径：恢复后本该给建议


@dataclass(frozen=True)
class AdviceEvaluation:
    advice_id: str
    action: AdviceAction
    spec_version: str
    verdict: Verdict
    reasons: tuple[str, ...]
    excess_vs_benchmark: Decimal | None = None
    max_adverse_excursion: Decimal | None = None


def evaluate(advice_id: str, action: AdviceAction, f: ObservationFacts) -> AdviceEvaluation:
    """按动作类型分派评价口径。事实缺失 → INCONCLUSIVE（不强行判）。"""
    handler = {
        AdviceAction.BUY: _evaluate_buy,
        AdviceAction.REDUCE: _evaluate_reduce,
        AdviceAction.HOLD: _evaluate_hold,
        AdviceAction.SUSPEND: _evaluate_suspend,
    }[action]
    return handler(advice_id, action, f)


def _evaluate_buy(advice_id: str, action: AdviceAction, f: ObservationFacts) -> AdviceEvaluation:
    if f.trigger_occurred is None or f.direction_return is None:
        return AdviceEvaluation(advice_id, action, EVALUATION_SPEC_VERSION,
                                Verdict.INCONCLUSIVE, ("观察窗口事实缺失",))
    if not f.trigger_occurred:
        # 条件设计合理：未触发避免了错误触发（即便后来上涨）
        return AdviceEvaluation(advice_id, action, EVALUATION_SPEC_VERSION,
                                Verdict.REASONABLE_UNTRIGGERED, ("触发条件未出现",),
                                max_adverse_excursion=f.max_adverse_excursion)
    verdict = Verdict.DIRECTION_CORRECT if f.direction_return > 0 else Verdict.DIRECTION_WRONG
    return AdviceEvaluation(advice_id, action, EVALUATION_SPEC_VERSION, verdict,
                            (f"触发后窗口收益 {f.direction_return}",),
                            max_adverse_excursion=f.max_adverse_excursion)


def _evaluate_reduce(advice_id: str, action: AdviceAction, f: ObservationFacts) -> AdviceEvaluation:
    if f.direction_return is None or f.benchmark_return is None:
        return AdviceEvaluation(advice_id, action, EVALUATION_SPEC_VERSION,
                                Verdict.INCONCLUSIVE, ("观察窗口事实缺失",))
    excess = f.direction_return - f.benchmark_return
    # 减仓后该标的跑输基准 → 减仓正确（避免"卖了就涨"的道德化误判）
    verdict = Verdict.AVOIDED_LOSS if excess < 0 else Verdict.REDUCED_TOO_EARLY
    vol_note = ""
    if f.portfolio_vol_before is not None and f.portfolio_vol_after is not None:
        vol_note = f"；组合波动 {f.portfolio_vol_before}→{f.portfolio_vol_after}"
    return AdviceEvaluation(advice_id, action, EVALUATION_SPEC_VERSION, verdict,
                            (f"相对基准超额 {excess}{vol_note}",),
                            excess_vs_benchmark=excess)


def _evaluate_hold(advice_id: str, action: AdviceAction, f: ObservationFacts) -> AdviceEvaluation:
    if f.became_actionable is None:
        return AdviceEvaluation(advice_id, action, EVALUATION_SPEC_VERSION,
                                Verdict.INCONCLUSIVE, ("观察窗口事实缺失",))
    verdict = Verdict.ACTIONABLE_LATER if f.became_actionable else Verdict.STILL_OBSERVING
    return AdviceEvaluation(advice_id, action, EVALUATION_SPEC_VERSION, verdict, ())


def _evaluate_suspend(advice_id: str, action: AdviceAction, f: ObservationFacts) -> AdviceEvaluation:
    if f.data_recovered is None or f.advice_would_be_warranted is None:
        return AdviceEvaluation(advice_id, action, EVALUATION_SPEC_VERSION,
                                Verdict.INCONCLUSIVE, ("观察窗口事实缺失",))
    if f.data_recovered and f.advice_would_be_warranted:
        return AdviceEvaluation(advice_id, action, EVALUATION_SPEC_VERSION,
                                Verdict.SUSPEND_UNWARRANTED, ("数据恢复且本该给出建议",))
    return AdviceEvaluation(advice_id, action, EVALUATION_SPEC_VERSION,
                             Verdict.SUSPEND_WARRANTED, ())


# —— 评价回灌校准（闭环：差评信号 → 降 p / DECAYED 建议）——


@dataclass(frozen=True)
class BackfeedRecommendation:
    signal_id: str
    n_evaluated: int
    wrong_rate: Decimal                  # 方向错误占已触发评价比
    action: str                          # "reduce_p" | "decay" | "none"
    suggested_p_factor: Decimal          # reduce_p 时建议的 p 乘数（<1）


def backfeed(
    signal_id: str,
    evaluations: list[AdviceEvaluation],
    *,
    wrong_threshold: Decimal = Decimal("0.5"),
    decay_threshold: Decimal = Decimal("0.7"),
    min_samples: int = 10,
) -> BackfeedRecommendation:
    """同类信号评价回灌：错误率过半 → 建议 p ×0.8；持续 ≥70% → 建议 DECAYED。

    只统计已触发的方向性评价（BUY 触发后/REDUCE），非方向性结论不掺入。
    样本不足 → none（诚实：不拿小样本惩罚信号）。
    """
    directional = [e for e in evaluations if e.verdict in
                   (Verdict.DIRECTION_CORRECT, Verdict.DIRECTION_WRONG,
                    Verdict.AVOIDED_LOSS, Verdict.REDUCED_TOO_EARLY)]
    if len(directional) < min_samples:
        return BackfeedRecommendation(signal_id, len(directional), Decimal(0), "none", Decimal(1))
    wrong = sum(1 for e in directional if e.verdict in (Verdict.DIRECTION_WRONG, Verdict.REDUCED_TOO_EARLY))
    wrong_rate = Decimal(wrong) / Decimal(len(directional))
    if wrong_rate >= decay_threshold:
        return BackfeedRecommendation(signal_id, len(directional), wrong_rate, "decay", Decimal(1))
    if wrong_rate >= wrong_threshold:
        return BackfeedRecommendation(signal_id, len(directional), wrong_rate,
                                      "reduce_p", Decimal("0.8"))
    return BackfeedRecommendation(signal_id, len(directional), wrong_rate, "none", Decimal(1))


# —— 行为偏差分析（收市后复盘用，纯启发式）——


class BiasKind(StrEnum):
    DISPOSAL_EFFECT = "disposal_effect"    # 处置效应：卖盈持亏
    CHASING = "chasing"                     # 追涨：买在近期高点附近
    OVERTRADING = "overtrading"             # 过度交易
    RULE_DEVIATION = "rule_deviation"       # 偏离风险规则：上限外仍加仓


@dataclass(frozen=True)
class TradeFact:
    code: str
    kind: str                              # BUY / SELL
    price: Decimal
    unrealized_pnl_sign: int | None = None  # 交易时该标的浮盈亏符号（1 盈 / -1 亏 / None）
    price_percentile_20d: Decimal | None = None  # 买价在近 20 日价格分位（0–1）
    weight_after: Decimal | None = None    # 交易后该标的组合权重
    single_cap: Decimal | None = None


@dataclass(frozen=True)
class BiasFinding:
    kind: BiasKind
    code: str | None
    evidence: str


def analyze_behavioral_bias(
    trades: list[TradeFact], *, window_size: int = 20, overtrade_per_month: int = 15
) -> list[BiasFinding]:
    """纯启发式偏差检测：只陈述模式，不道德化判定（FR 第 6 节复盘口径）。"""
    findings: list[BiasFinding] = []

    sells = [t for t in trades if t.kind == "SELL" and t.unrealized_pnl_sign is not None]
    holds_signs = [t.unrealized_pnl_sign for t in trades
                   if t.kind == "BUY" and t.unrealized_pnl_sign is not None]
    if len(sells) >= 3:
        sell_win_ratio = Decimal(sum(1 for t in sells if t.unrealized_pnl_sign > 0)) / Decimal(len(sells))
        hold_win_ratio = (Decimal(sum(1 for s in holds_signs if s > 0)) / Decimal(len(holds_signs))
                          if holds_signs else None)
        # 卖出多为浮盈、而持仓多为浮亏 → 处置效应模式
        if sell_win_ratio >= Decimal("0.7") and (hold_win_ratio is not None and hold_win_ratio <= Decimal("0.3")):
            findings.append(BiasFinding(
                BiasKind.DISPOSAL_EFFECT, None,
                f"卖出中 {sell_win_ratio} 为浮盈标的，持仓中 {hold_win_ratio} 为浮亏标的",
            ))

    for t in trades:
        if t.kind == "BUY" and t.price_percentile_20d is not None:
            if t.price_percentile_20d >= Decimal("0.95"):
                findings.append(BiasFinding(
                    BiasKind.CHASING, t.code,
                    f"买入价处于近 {window_size} 日 {t.price_percentile_20d} 分位",
                ))
        if t.kind == "BUY" and t.weight_after is not None and t.single_cap is not None:
            if t.weight_after > t.single_cap:
                findings.append(BiasFinding(
                    BiasKind.RULE_DEVIATION, t.code,
                    f"买入后权重 {t.weight_after} 超单标的上限 {t.single_cap}",
                ))

    n_buys = sum(1 for t in trades if t.kind == "BUY")
    if n_buys > overtrade_per_month:
        findings.append(BiasFinding(
            BiasKind.OVERTRADING, None,
            f"月内买入 {n_buys} 笔超过 {overtrade_per_month} 笔阈值",
        ))
    return findings
