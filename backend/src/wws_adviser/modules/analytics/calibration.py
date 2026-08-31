"""概率校准：reliability 分箱、Platt scaling 与校准状态机（FR-ANL-003）。

职责边界：
- `p` 只能在回测/校准服务内写入（本模块），模型 Gateway 无权。
- reliability：对历史预测概率分箱，实际命中率须落在预测概率附近；系统性高估的
  信号拒绝，或经 Platt scaling 修正后重评，修正参数记录入版本。
- 状态机：UNCALIBRATED → CALIBRATING → CALIBRATED(oos_pass) → STALE → DECAYED；
  有效期默认 60 个交易日（到期自动 STALE，凯利拒绝直到重跑样本外并通过）。

纯函数 + 全 Decimal；交易日历由调用方注入（有效期按交易日计）。
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from wws_adviser.modules.analytics.kelly import CalibrationState, KellyInput
from wws_adviser.modules.analytics.signals import BacktestStats

SCHEMA_VERSION = "1"

DEFAULT_TTL_TRADING_DAYS = 60
DEFAULT_BIN_COUNT = 5
DEFAULT_BIN_MIN_SAMPLES = 10
# |实际命中率 − 预测均值| 超过此值判失准
DEFAULT_REL_TOLERANCE = Decimal("0.10")


# —— reliability 分箱 ——


@dataclass(frozen=True)
class CalibrationItem:
    """单条校准样本：信号触发时的预测概率（版本化回测口径）与事后是否盈利。"""

    predicted_p: Decimal
    win: bool


@dataclass(frozen=True)
class ReliabilityBin:
    bin_index: int
    bin_low: Decimal          # [bin_low, bin_high)
    bin_high: Decimal
    n: int
    avg_predicted: Decimal
    actual_rate: Decimal
    deviation: Decimal        # actual − predicted
    judged: bool              # 样本量是否足够参与判定


def reliability_bins(
    items: Sequence[CalibrationItem],
    bin_count: int = DEFAULT_BIN_COUNT,
    min_samples: int = DEFAULT_BIN_MIN_SAMPLES,
) -> list[ReliabilityBin]:
    """等宽分箱（[0,1] 分 bin_count 档），统计每箱预测均值与实际命中率。"""
    width = Decimal(1) / Decimal(bin_count)
    buckets: list[list[CalibrationItem]] = [[] for _ in range(bin_count)]
    for it in items:
        pos = (it.predicted_p / width).to_integral_value(rounding="ROUND_DOWN")
        idx = min(bin_count - 1, int(pos))
        buckets[idx].append(it)
    out: list[ReliabilityBin] = []
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        n = len(bucket)
        avg_pred = sum((b.predicted_p for b in bucket), Decimal(0)) / Decimal(n)
        hits = sum(1 for b in bucket if b.win)
        actual = Decimal(hits) / Decimal(n)
        out.append(ReliabilityBin(
            bin_index=i, bin_low=width * i,
            bin_high=width * (i + 1),
            n=n, avg_predicted=avg_pred, actual_rate=actual,
            deviation=actual - avg_pred, judged=n >= min_samples,
        ))
    return out


@dataclass(frozen=True)
class ReliabilityVerdict:
    passed: bool
    worst_overestimate: Decimal     # 正值=高估（危险方向），取已判定箱最大偏差
    worst_underestimate: Decimal    # 正值=低估
    judged_bins: int


def reliability_check(
    bins: Sequence[ReliabilityBin], tolerance: Decimal = DEFAULT_REL_TOLERANCE
) -> ReliabilityVerdict:
    """判定：所有样本量足够的箱 |实际−预测| ≤ tolerance。

    只有系统性偏差才判失败；样本不足的箱不参与（诚实标注 judged=False）。
    """
    over = Decimal(0)
    under = Decimal(0)
    judged = 0
    for b in bins:
        if not b.judged:
            continue
        judged += 1
        if -b.deviation > over:    # actual 低于预测 → 高估（危险方向）
            over = -b.deviation
        if b.deviation > under:    # actual 高于预测 → 低估
            under = b.deviation
    passed = judged > 0 and over <= tolerance and under <= tolerance
    return ReliabilityVerdict(
        passed=passed, worst_overestimate=over, worst_underestimate=under, judged_bins=judged
    )


# —— Platt scaling（1 参数逻辑斯蒂重校准，零依赖梯度法）——


@dataclass(frozen=True)
class PlattParams:
    a: Decimal   # logit 缩放
    b: Decimal   # logit 平移


def _logit(p: Decimal) -> float:
    x = min(max(float(p), 1e-6), 1 - 1e-6)
    return math.log(x / (1 - x))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def fit_platt(
    items: Sequence[CalibrationItem],
    iterations: int = 300,
    lr: float = 0.5,
    l2: float = 1e-3,
) -> PlattParams:
    """拟合 p' = sigmoid(a·logit(p)+b)，最小化 log-loss（含小 L2 正则）。

    确定性：固定迭代次数；小数据量（校准场景）足够稳定。
    初始 a=1, b=0（恒等映射）。
    """
    zs = [_logit(it.predicted_p) for it in items]
    ys = [1.0 if it.win else 0.0 for it in items]
    a, b = 1.0, 0.0
    n = float(len(items))
    for _ in range(iterations):
        ga, gb = 0.0, 0.0
        for z, y in zip(zs, ys, strict=True):
            err = _sigmoid(a * z + b) - y
            ga += err * z
            gb += err
        ga = ga / n + l2 * a / n
        gb = gb / n + l2 * b / n
        a -= lr * ga
        b -= lr * gb
    return PlattParams(a=Decimal(str(round(a, 6))), b=Decimal(str(round(b, 6))))


def apply_platt(p: Decimal, params: PlattParams) -> Decimal:
    z = float(params.a) * _logit(p) + float(params.b)
    return Decimal(str(round(_sigmoid(z), 6)))


# —— 校准状态机 ——


class CalibrationEvent(StrEnum):
    START = "start"            # 开始回测/校准
    PASS_OOS = "pass_oos"      # 样本外通过（n_eff 门禁 + reliability）
    FAIL_OOS = "fail_oos"
    EXPIRE = "expire"          # 有效期到（按交易日历判定）
    DECAY = "decay"            # 长期未重校准（如再翻倍 TTL 未更新）


_VALID_TRANSITIONS: dict[CalibrationState, dict[CalibrationEvent, CalibrationState]] = {
    CalibrationState.UNCALIBRATED: {
        CalibrationEvent.START: CalibrationState.CALIBRATING,
    },
    CalibrationState.CALIBRATING: {
        CalibrationEvent.PASS_OOS: CalibrationState.CALIBRATED_OOS,
        CalibrationEvent.FAIL_OOS: CalibrationState.UNCALIBRATED,
        CalibrationEvent.START: CalibrationState.CALIBRATING,
    },
    CalibrationState.CALIBRATED_OOS: {
        CalibrationEvent.EXPIRE: CalibrationState.STALE,
        CalibrationEvent.START: CalibrationState.CALIBRATING,
    },
    CalibrationState.STALE: {
        CalibrationEvent.START: CalibrationState.CALIBRATING,
        CalibrationEvent.DECAY: CalibrationState.DECAYED,
        CalibrationEvent.PASS_OOS: CalibrationState.CALIBRATED_OOS,  # 重跑样本外直接通过
    },
    CalibrationState.DECAYED: {
        CalibrationEvent.START: CalibrationState.CALIBRATING,
    },
}


def transition(state: CalibrationState, event: CalibrationEvent) -> CalibrationState:
    """非法转换抛 ValueError（状态机完整性先于容错）。"""
    target = _VALID_TRANSITIONS.get(state, {}).get(event)
    if target is None:
        raise ValueError(f"非法状态转换：{state.value} --{event.value}--> ∅")
    return target


# —— 样本外门禁评估（n_eff 独立达标 + reliability）——


@dataclass(frozen=True)
class OOSVerdict:
    passed: bool
    reasons: tuple[str, ...]          # 未通过时的原因链（可审计）
    reliability: ReliabilityVerdict
    platt_applied: bool


def evaluate_oos(
    oos_stats: BacktestStats,
    oos_items: Sequence[CalibrationItem],
    *,
    n_eff_oos: int,
    reliability_tolerance: Decimal = DEFAULT_REL_TOLERANCE,
) -> OOSVerdict:
    """样本外评估：n_eff 独立达标（不得拿样本内凑）+ reliability（含 Platt 重评）。

    reliability 未过 → 拟合 Platt 修正后重评；仍不过 → 失败（修正记录由调用方入版本）。
    """
    reasons: list[str] = []
    if n_eff_oos < 30:
        reasons.append(f"n_eff_oos={n_eff_oos} < 30")
    if not oos_items:
        reasons.append("无样本外校准样本")
    reliability = reliability_check(reliability_bins(oos_items), tolerance=reliability_tolerance)
    platt_applied = False
    if oos_items and not reliability.passed:
        platt = fit_platt(oos_items)
        corrected = [
            CalibrationItem(apply_platt(i.predicted_p, platt), i.win)
            for i in oos_items
        ]
        reliability = reliability_check(
            reliability_bins(corrected), tolerance=reliability_tolerance
        )
        platt_applied = True
    if not reliability.passed:
        over, under = reliability.worst_overestimate, reliability.worst_underestimate
        reasons.append(f"reliability 失准（over={over}, under={under}）")
    return OOSVerdict(
        passed=not reasons, reasons=tuple(reasons),
        reliability=reliability, platt_applied=platt_applied,
    )


# —— 校准记录（版本化）与凯利输入组装 ——

@dataclass(frozen=True)
class CalibrationRecord:
    """一份信号版本的校准结论（持久化结构在集成波落库）。"""

    signal_id: str
    signal_version: str
    state: CalibrationState
    calibrated_on: str            # ISO 日期
    expires_on: str               # ISO 日期（calibrated_on + TTL 交易日）
    p_low: Decimal
    p_mid: Decimal
    p_high: Decimal
    b: Decimal
    n_eff: int
    n_eff_oos: int
    reliability_passed: bool
    platt: PlattParams | None = None


def state_on_date(record: CalibrationRecord, as_of: str) -> CalibrationState:
    """读时判定：CALIBRATED_OOS 且已过有效期 → 视同 STALE（凯利关卡 1 消费）。"""
    if record.state is CalibrationState.CALIBRATED_OOS and as_of > record.expires_on:
        return CalibrationState.STALE
    return record.state


def kelly_input(
    record: CalibrationRecord,
    as_of: str,
    **portfolio_context: object,
) -> KellyInput:
    """校准记录 + 组合上下文 → 凯利输入（唯一合法组装路径）。"""
    base: dict[str, object] = dict(
        signal_id=record.signal_id,
        p_low=record.p_low, p_mid=record.p_mid, p_high=record.p_high,
        b=record.b, n_eff=record.n_eff, n_eff_oos=record.n_eff_oos,
        calibration_state=state_on_date(record, as_of),
        calibration_expires_on=record.expires_on,
        as_of_date=as_of,
        reliability_passed=record.reliability_passed,
    )
    base.update(portfolio_context)
    return KellyInput(**base)  # type: ignore[arg-type]
