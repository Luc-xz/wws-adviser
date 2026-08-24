"""凯利计算核心（纯领域服务，TECHNICAL_ARCHITECTURE §9.3）。

定位为组合层风险预算：`p` 的校准对象是全市场同类信号的历史回测（非用户个体持仓），
带 Wilson 置信区间，`f*` 因此报区间不报单点。资格决策流任一关卡拒绝即终止并保留原因链。

边界约束（§9.3 要点）：
- 任何模型文本或模型自报"置信度"都不能进入 `p`；本模块的调用方只能是回测/校准服务。
- 凯利折扣 0.10~0.25 是"凯利假设不成立 + 估计误差 + 风险厌恶高于对数效用"三重修正的
  诚实地板，非精确推导；UI 与文档不得呈现为精确值。
- 拒绝时只输出拒绝原因类别，不输出仓位区间；折扣时输出原因链。

零外部依赖（不含 DB/Web/SDK），全部 Decimal 计算（§7.3 数值精度）。
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


# —— 版本化输入/输出（结构变更须升 schema_version）——

SCHEMA_VERSION = "1"


class CalibrationState(StrEnum):
    """校准状态机（§9.3 输入结构；转换由校准服务驱动）。"""

    UNCALIBRATED = "uncalibrated"
    CALIBRATING = "calibrating"
    CALIBRATED_OOS = "calibrated_oos"
    STALE = "stale"
    DECAYED = "decayed"


class RejectReason(StrEnum):
    """拒绝原因类别（§9.3：拒绝时不输出具体仓位区间）。"""

    CALIBRATION_UNCALIBRATED = "calibration_uncalibrated"
    CALIBRATION_STALE = "calibration_stale"
    CALIBRATION_EXPIRED = "calibration_expired"
    CALIBRATION_FAILED = "calibration_failed"
    INSUFFICIENT_SAMPLES = "insufficient_samples"


class Flag(StrEnum):
    """折扣/降级标记（输出原因链的组成部分）。"""

    LOW_CONFIDENCE = "low_confidence"          # 30≤n_eff_oos<100：半折扣
    WIDE_P_INTERVAL = "wide_p_interval"        # p 区间过宽：取 p_low + 额外折扣
    NON_POSITIVE_PAYOFF = "non_positive_payoff"  # b≤0：输出 0
    EXTREME_PAYOFF = "extreme_payoff"          # b 越界：仅区间下限
    NEGATIVE_EDGE = "negative_edge"            # f* 为负：下限 0
    ROUNDING_IMPRECISE = "rounding_imprecise"  # 无法安全取整到手数：只显示区间


@dataclass(frozen=True)
class AdjustmentStep:
    """调整轨迹的一步（before/after 为组合占比分数）。"""

    kind: str
    note: str
    before: Decimal | None
    after: Decimal | None


@dataclass(frozen=True)
class KellyInput:
    """凯利输入（版本化结构，§9.3）。由回测/校准服务组装，模型 Gateway 无权写入 p 字段。"""

    signal_id: str
    # 概率区间：来自全市场同类信号回测的 Wilson 区间
    p_low: Decimal
    p_mid: Decimal
    p_high: Decimal
    b: Decimal                       # 平均盈利 / 平均亏损
    n_eff: int                       # 有效样本数（重叠信号衰减后）
    n_eff_oos: int                   # 样本外有效样本数
    calibration_state: CalibrationState
    calibration_expires_on: str | None = None  # ISO 日期（YYYY-MM-DD）
    as_of_date: str = ""                       # 评估日（ISO），过期判定基准
    reliability_passed: bool = False           # reliability 校准结论（Platt 修正上游完成）

    # 折扣参数（越界视为配置错误，fail loud）
    kelly_discount: Decimal = Decimal("0.25")        # 分数凯利折扣 0.10~0.25
    confidence_discount: Decimal = Decimal("1")      # 置信折扣乘数（按 n_eff 分层，≤1）
    liquidity_discount: Decimal = Decimal("1")       # 流动性折扣乘数（≤1）
    max_p_interval_width: Decimal = Decimal("0.30")  # p 区间宽度上限
    wide_p_extra_discount: Decimal = Decimal("0.50") # 宽区间的额外折扣乘数

    # 组合上下文（clip 用；金额与占比均为组合口径）
    total_assets: Decimal = Decimal("0")
    available_cash: Decimal = Decimal("0")
    current_position_value: Decimal = Decimal("0")   # 该标的当前市值
    cash_floor: Decimal = Decimal("0.10")            # 现金下限（组合占比）
    single_cap: Decimal = Decimal("0.30")            # 单标的组合占比上限
    industry_headroom_value: Decimal | None = None   # 行业上限剩余额度（货币额）
    portfolio_headroom_value: Decimal | None = None  # 组合波动/回撤约束剩余额度（货币额）

    # 取整校验（可选：不提供价格则跳过取整检查）
    price: Decimal | None = None
    lot_size: Decimal = Decimal("100")


@dataclass(frozen=True)
class KellyOutcome:
    """凯利输出：接受 → [f_min, f_max] + 调整轨迹；拒绝 → 仅原因类别。"""

    schema_version: str
    signal_id: str
    accepted: bool
    f_min: Decimal | None = None            # 组合占比下限
    f_max: Decimal | None = None            # 组合占比上限
    value_min: Decimal | None = None        # 货币额下限
    value_max: Decimal | None = None        # 货币额上限
    suggested_lots: int | None = None       # f_max 可安全取整时给整手建议
    flags: tuple[str, ...] = field(default_factory=tuple)
    trail: tuple[AdjustmentStep, ...] = field(default_factory=tuple)
    reject_reason: str | None = None


# —— Wilson 置信区间（纯函数）——

def wilson_interval(
    successes: int, n: int, z: Decimal = Decimal("1.96")
) -> tuple[Decimal, Decimal, Decimal]:
    """二项比例的 Wilson score 区间 → (low, mid, high)；mid 为点估计 p̂。

    n≤0 或 successes∉[0,n] 为调用方错误，抛 ValueError（回测服务负责保证输入）。
    """
    if n <= 0:
        raise ValueError(f"wilson_interval: n 必须为正数，收到 {n}")
    if not 0 <= successes <= n:
        raise ValueError(f"wilson_interval: successes 须在 [0, n]，收到 {successes}/{n}")
    phat = Decimal(successes) / Decimal(n)
    z2 = z * z
    denom = Decimal(1) + z2 / Decimal(n)
    center = (phat + z2 / (Decimal(2) * Decimal(n))) / denom
    radicand = phat * (Decimal(1) - phat) / Decimal(n) + z2 / (
        Decimal(4) * Decimal(n) * Decimal(n)
    )
    half = z * radicand.sqrt() / denom
    low = max(Decimal(0), center - half)
    high = min(Decimal(1), center + half)
    return (low, phat, high)


# —— 输入校验（配置/编程错误 fail loud，区别于决策流拒绝）——

def _validate(inp: KellyInput) -> None:
    errors: list[str] = []
    if not inp.signal_id:
        errors.append("signal_id 不能为空")
    if not (Decimal(0) <= inp.p_low <= inp.p_mid <= inp.p_high <= Decimal(1)):
        errors.append(f"概率区间须满足 0≤p_low≤p_mid≤p_high≤1，收到 {inp.p_low}/{inp.p_mid}/{inp.p_high}")
    if not (Decimal("0.10") <= inp.kelly_discount <= Decimal("0.25")):
        errors.append(f"凯利折扣须在 [0.10, 0.25]，收到 {inp.kelly_discount}")
    for name, d in (("confidence_discount", inp.confidence_discount),
                    ("liquidity_discount", inp.liquidity_discount)):
        if not (Decimal(0) < d <= Decimal(1)):
            errors.append(f"{name} 须在 (0, 1]，收到 {d}")
    if inp.n_eff < 0 or inp.n_eff_oos < 0:
        errors.append("n_eff / n_eff_oos 不能为负")
    if inp.total_assets < 0 or inp.available_cash < 0 or inp.current_position_value < 0:
        errors.append("组合上下文金额不能为负")
    if errors:
        raise ValueError("KellyInput 校验失败：" + "; ".join(errors))


def _fstar(p: Decimal, b: Decimal) -> Decimal:
    """凯利分数 f* = p − (1−p)/b。b 为正（关卡 5 已保证）。"""
    return p - (Decimal(1) - p) / b


def _clip_value(
    trail: list[AdjustmentStep], flags: list[str],
    kind: str, note: str, value: Decimal, cap: Decimal | None,
) -> Decimal:
    """对货币额施加一道上限 cap；受限时记录轨迹。返回 min(value, cap)。"""
    if cap is None or value <= cap:
        return value
    trail.append(AdjustmentStep(kind=kind, note=note, before=value, after=cap))
    return cap


def compute_kelly(inp: KellyInput) -> KellyOutcome:
    """资格决策流（§9.3）：任一关卡拒绝即终止并保留原因链。"""
    _validate(inp)
    trail: list[AdjustmentStep] = []
    flags: list[str] = []

    def rejected(reason: RejectReason) -> KellyOutcome:
        return KellyOutcome(
            schema_version=SCHEMA_VERSION, signal_id=inp.signal_id,
            accepted=False, reject_reason=reason.value,
            flags=tuple(flags), trail=tuple(trail),
        )

    # 关卡 1：校准状态（CALIBRATED(oos) 且未过期）
    state_reason = {
        CalibrationState.UNCALIBRATED: RejectReason.CALIBRATION_UNCALIBRATED,
        CalibrationState.CALIBRATING: RejectReason.CALIBRATION_UNCALIBRATED,
        CalibrationState.STALE: RejectReason.CALIBRATION_STALE,
        CalibrationState.DECAYED: RejectReason.CALIBRATION_STALE,
    }.get(inp.calibration_state)
    if state_reason is not None:
        return rejected(state_reason)
    if (
        inp.calibration_expires_on
        and inp.as_of_date
        and inp.as_of_date > inp.calibration_expires_on
    ):
        return rejected(RejectReason.CALIBRATION_EXPIRED)

    # 关卡 2：样本外有效样本 30/100 分档
    if inp.n_eff_oos < 30:
        return rejected(RejectReason.INSUFFICIENT_SAMPLES)
    low_confidence = inp.n_eff_oos < 100

    # 关卡 3：reliability 校准（Platt 修正由上游校准服务完成，此处消费结论）
    if not inp.reliability_passed:
        return rejected(RejectReason.CALIBRATION_FAILED)

    # 关卡 4：p 区间宽度 —— 过宽则取 p_low 作为有效中枢并施加额外折扣
    p_low, p_mid = inp.p_low, inp.p_mid
    if (inp.p_high - inp.p_low) > inp.max_p_interval_width:
        flags.append(Flag.WIDE_P_INTERVAL.value)
        p_mid = p_low
        trail.append(AdjustmentStep(
            kind="wide_p_interval", note=f"区间宽 {inp.p_high - inp.p_low} 超过 {inp.max_p_interval_width}，有效 p_mid 取 p_low",
            before=inp.p_mid, after=p_low,
        ))

    # 关卡 5：b 的符号与极端性
    if inp.b <= 0:
        return KellyOutcome(
            schema_version=SCHEMA_VERSION, signal_id=inp.signal_id, accepted=True,
            f_min=Decimal(0), f_max=Decimal(0),
            value_min=Decimal(0), value_max=Decimal(0), suggested_lots=0,
            flags=tuple(flags + [Flag.NON_POSITIVE_PAYOFF.value]),
            trail=tuple(trail), reject_reason=None,
        )
    extreme = not (Decimal("0.1") <= inp.b <= Decimal("10"))

    # 关卡 6：凯利分数（报区间：f*_lower 用 p_low，f*_mid 用 p_mid）
    f_low = _fstar(p_low, inp.b)
    f_mid = _fstar(p_mid, inp.b)
    if f_mid <= 0:
        # 无正边际：区间坍缩为 0（f_low 必然更小）
        return KellyOutcome(
            schema_version=SCHEMA_VERSION, signal_id=inp.signal_id, accepted=True,
            f_min=Decimal(0), f_max=Decimal(0),
            value_min=Decimal(0), value_max=Decimal(0), suggested_lots=0,
            flags=tuple(flags + [Flag.NEGATIVE_EDGE.value]),
            trail=tuple(trail), reject_reason=None,
        )
    f_min, f_max = (max(Decimal(0), f_low), f_mid)
    if extreme:
        flags.append(Flag.EXTREME_PAYOFF.value)
        f_max = f_min  # 仅区间下限
        trail.append(AdjustmentStep(
            kind="extreme_payoff", note=f"b={inp.b} 越界 [0.1, 10]，仅保留区间下限",
            before=_fstar(p_mid, inp.b), after=f_min,
        ))

    # 关卡 7：分数凯利折扣（组合层预算语义，三重修正地板）
    before = f_max
    f_max = f_max * inp.kelly_discount
    f_min = f_min * inp.kelly_discount
    trail.append(AdjustmentStep(
        kind="fractional_discount", note=f"分数凯利折扣 ×{inp.kelly_discount}",
        before=before, after=f_max,
    ))

    # 关卡 2 附加：样本量分档半折扣（30≤n_eff_oos<100）
    if low_confidence:
        flags.append(Flag.LOW_CONFIDENCE.value)
        before = f_max
        f_max = f_max / Decimal(2)
        f_min = f_min / Decimal(2)
        trail.append(AdjustmentStep(
            kind="low_confidence_halving",
            note=f"n_eff_oos={inp.n_eff_oos} 在 [30, 100)，半折扣", before=before, after=f_max,
        ))

    # 关卡 8：置信折扣 / 流动性折扣（按 n_eff 分层，上游给定乘数）
    for kind, mult, note in (
        ("confidence_discount", inp.confidence_discount, "置信折扣"),
        ("liquidity_discount", inp.liquidity_discount, "流动性折扣"),
    ):
        if mult < Decimal(1):
            before = f_max
            f_max = f_max * mult
            f_min = f_min * mult
            trail.append(AdjustmentStep(kind=kind, note=f"{note} ×{mult}", before=before, after=f_max))

    # 关卡 9：clip（现金下限 → 单标的上限 → 行业上限 → 组合）
    #   f 为组合占比，换算货币额受限后回算，保证输出语义一致
    if inp.total_assets > 0:
        value_max = f_max * inp.total_assets
        value_min = f_min * inp.total_assets
        value_max = _clip_value(
            trail, flags, "clip_cash_floor",
            f"现金约束（保留现金下限 {inp.cash_floor}）",
            value_max, inp.available_cash - inp.cash_floor * inp.total_assets,
        )
        value_max = _clip_value(
            trail, flags, "clip_single_cap",
            f"单标的上限 {inp.single_cap}",
            value_max,
            inp.single_cap * inp.total_assets - inp.current_position_value,
        )
        value_max = _clip_value(
            trail, flags, "clip_industry_cap", "行业上限剩余额度",
            value_max, inp.industry_headroom_value,
        )
        value_max = _clip_value(
            trail, flags, "clip_portfolio", "组合波动/回撤约束剩余额度",
            value_max, inp.portfolio_headroom_value,
        )
        value_max = max(Decimal(0), value_max)
        if value_max < value_min:
            value_min = value_max  # clip 可能压到区间下限之下
        f_min, f_max = value_min / inp.total_assets, value_max / inp.total_assets

        # 关卡 10：最小交易单位取整（不能安全取整时只显示区间）
        lots: int | None = None
        if inp.price is not None and inp.price > 0 and value_max > 0:
            raw_lots = int((value_max / (inp.price * inp.lot_size)).to_integral_value(rounding="ROUND_DOWN"))
            lots = raw_lots
            lots_value = Decimal(raw_lots) * inp.price * inp.lot_size
            if lots_value > value_max:
                lots = max(0, raw_lots - 1)
            elif lots_value < value_min and lots_value == Decimal(0):
                flags.append(Flag.ROUNDING_IMPRECISE.value)
                lots = None  # 无法以整手表达下限：只显示区间
        elif value_max == 0:
            lots = 0

        return KellyOutcome(
            schema_version=SCHEMA_VERSION, signal_id=inp.signal_id, accepted=True,
            f_min=f_min, f_max=f_max, value_min=value_min, value_max=value_max,
            suggested_lots=lots, flags=tuple(flags), trail=tuple(trail),
        )

    # 无组合上下文（纯回测/研究口径）：直接返回分数区间
    return KellyOutcome(
        schema_version=SCHEMA_VERSION, signal_id=inp.signal_id, accepted=True,
        f_min=f_min, f_max=f_max, flags=tuple(flags), trail=tuple(trail),
    )
