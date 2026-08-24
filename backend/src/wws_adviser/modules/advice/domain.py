"""Advice 领域：有限状态机、发布门禁、冲突处理与有效期控制（TECH §9.4/§11.3）。

FSM：DRAFT → DATA_CHECKED → RISK_CHECKED → MODEL_EXPLAINED → OUTPUT_VALIDATED
→ PUBLISHED；任一步失败 → DEGRADED 或 BLOCKED（终态）。

安全原则：
- 发布前七项检查任一不过 → 不发布；模型建议与规则冲突时优先用确定性规则
  重建安全摘要，无法重建则发布「暂停建议」。
- 建议必须携带有效期与触发/失效条件；过期或失效后不再可操作。
- 拒绝/暂停的建议不携带仓位区间，只携带原因类别。
"""

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum
from typing import Sequence


SCHEMA_VERSION = "1"


class AdviceState(StrEnum):
    DRAFT = "draft"
    DATA_CHECKED = "data_checked"
    RISK_CHECKED = "risk_checked"
    MODEL_EXPLAINED = "model_explained"
    OUTPUT_VALIDATED = "output_validated"
    PUBLISHED = "published"
    DEGRADED = "degraded"      # 终态：可发布降级内容（如暂停建议+已知事实）
    BLOCKED = "blocked"        # 终态：不可发布


class AdviceAction(StrEnum):
    """允许的动作类型（评价口径按动作类型，FR-ADV 评价波实现）。"""

    BUY = "buy"                # 提升风险预算（区间）
    REDUCE = "reduce"          # 降低风险预算
    HOLD = "hold"              # 维持
    SUSPEND = "suspend"        # 暂停建议（数据不合格/无法重建安全摘要）


_HAPPY_PATH: tuple[AdviceState, ...] = (
    AdviceState.DRAFT,
    AdviceState.DATA_CHECKED,
    AdviceState.RISK_CHECKED,
    AdviceState.MODEL_EXPLAINED,
    AdviceState.OUTPUT_VALIDATED,
    AdviceState.PUBLISHED,
)


def next_check(state: AdviceState) -> AdviceState:
    """推进到下一检查态；非快乐路径状态推进为编程错误（fail loud）。"""
    try:
        i = _HAPPY_PATH.index(state)
    except ValueError:
        raise ValueError(f"状态 {state.value} 不可推进") from None
    if i + 1 >= len(_HAPPY_PATH):
        raise ValueError("PUBLISHED 为终态，不可继续推进")
    return _HAPPY_PATH[i + 1]


def degrade(state: AdviceState) -> AdviceState:
    """任一检查步失败 → DEGRADED（可发布降级内容）。"""
    if state in (AdviceState.DEGRADED, AdviceState.BLOCKED):
        raise ValueError(f"终态 {state.value} 不可再降级")
    return AdviceState.DEGRADED


def block(state: AdviceState) -> AdviceState:
    """硬失败（安全防线不可重建）→ BLOCKED。"""
    if state in (AdviceState.DEGRADED, AdviceState.BLOCKED):
        raise ValueError(f"终态 {state.value} 不可再变更")
    return AdviceState.BLOCKED


# —— 发布门禁（七项检查，§9.4）——


@dataclass(frozen=True)
class PublishChecks:
    ledger_reconciled: bool            # 账本已对账
    quote_fresh: bool                  # 行情新鲜（阈值上游判定）
    instrument_tradable: bool          # 可交易（非停牌/异常）
    numbers_deterministic: bool        # 数值与确定性结果一致
    within_hard_limits: bool           # 未突破硬限制
    has_validity_window: bool          # 含有效期与触发/失效条件
    evidence_complete: bool            # 关键事实的证据 ID 齐备


_CHECK_NAMES: tuple[tuple[str, str], ...] = (
    ("ledger_reconciled", "账本未对账"),
    ("quote_fresh", "行情过期"),
    ("instrument_tradable", "标的不可交易"),
    ("numbers_deterministic", "数值与确定性结果不一致"),
    ("within_hard_limits", "突破硬性风险限制"),
    ("has_validity_window", "缺少有效期/触发失效条件"),
    ("evidence_complete", "关键事实证据不齐"),
)


def publish_gate(checks: PublishChecks) -> tuple[bool, tuple[str, ...]]:
    """全部通过 → (True, ())；否则 (False, 未通过项原因链)。"""
    failed = tuple(name for attr, name in _CHECK_NAMES if not getattr(checks, attr))
    return (not failed, failed)


def resolve_conflict(
    *, model_conflicts: bool, deterministic_rebuild_ok: bool
) -> AdviceAction:
    """模型与规则冲突：能重建 → 用确定性结果（BUY/REDUCE/HOLD 由上游定）；
    不能重建 → 暂停建议。本函数只回答冲突场景的降级动作。
    """
    if not model_conflicts or deterministic_rebuild_ok:
        return AdviceAction.HOLD  # 无冲突或已重建，动作由上游确定性结果给出
    return AdviceAction.SUSPEND


# —— 建议结构与有效期 ——


@dataclass(frozen=True)
class Advice:
    """一条建议（发布或降级形态）。拒绝/暂停不携带仓位区间。"""

    advice_id: str
    signal_id: str
    code: str
    action: AdviceAction
    state: AdviceState
    valid_from: str                      # ISO 时间
    expires_at: str                      # ISO 时间（含收盘失效语义由服务层设置）
    trigger_conditions: tuple[str, ...] = ()
    invalidation_reasons: tuple[str, ...] = ()
    f_min: Decimal | None = None
    f_max: Decimal | None = None
    value_min: Decimal | None = None
    value_max: Decimal | None = None
    suggested_lots: int | None = None
    reasons: tuple[str, ...] = ()        # 拒绝/折扣原因链（写入 Advice 记录）
    evidence_ids: tuple[str, ...] = ()
    model_explanation: str | None = None
    invalidated: bool = False

    @property
    def has_position_interval(self) -> bool:
        return self.f_min is not None and self.f_max is not None


def is_actionable(advice: Advice, now_iso: str) -> bool:
    """可操作：已发布、在有效窗口内、未被失效。"""
    if advice.state is not AdviceState.PUBLISHED or advice.invalidated:
        return False
    return advice.valid_from <= now_iso < advice.expires_at


def invalidate(advice: Advice, reason: str) -> Advice:
    """标记失效（触发/失效条件命中或行情过期等），不可逆。"""
    if advice.state not in (AdviceState.PUBLISHED, AdviceState.DEGRADED):
        raise ValueError("仅已发布/降级建议可标记失效")
    return replace(
        advice, invalidated=True,
        invalidation_reasons=advice.invalidation_reasons + (reason,),
    )


# —— 盘中建议组装（纯函数；数据不合格 → 暂停建议 + 已知事实）——


@dataclass(frozen=True)
class IntradayContext:
    code: str
    signal_id: str
    quote_fresh: bool
    tradable: bool
    ledger_reconciled: bool
    # 凯利结果（None = 无已校准信号可用）
    kelly_accepted: bool | None = None
    kelly_f_min: Decimal | None = None
    kelly_f_max: Decimal | None = None
    kelly_value_min: Decimal | None = None
    kelly_value_max: Decimal | None = None
    kelly_suggested_lots: int | None = None
    kelly_reasons: tuple[str, ...] = ()
    kelly_rejected: bool = False


def build_intraday_advice(
    ctx: IntradayContext,
    *,
    advice_id: str,
    valid_from: str,
    expires_at: str,
    evidence_ids: Sequence[str] = (),
) -> Advice:
    """组装盘中建议：数据不合格/无校准信号 → SUSPEND（不带区间，带原因与已知事实）。"""
    known_facts: list[str] = [f"标的={ctx.code}"]
    data_failures: list[str] = []
    if not ctx.ledger_reconciled:
        data_failures.append("账本未对账")
    if not ctx.quote_fresh:
        data_failures.append("行情过期")
    if not ctx.tradable:
        data_failures.append("标的不可交易")
    if ctx.kelly_accepted is None:
        data_failures.append("无已校准信号")

    if data_failures:
        return Advice(
            advice_id=advice_id, signal_id=ctx.signal_id, code=ctx.code,
            action=AdviceAction.SUSPEND, state=AdviceState.DEGRADED,
            valid_from=valid_from, expires_at=expires_at,
            reasons=tuple(data_failures), evidence_ids=tuple(evidence_ids),
        )

    if ctx.kelly_rejected or not ctx.kelly_accepted:
        # 凯利拒绝：只输出原因类别，不输出区间（凯利输出协议）
        return Advice(
            advice_id=advice_id, signal_id=ctx.signal_id, code=ctx.code,
            action=AdviceAction.HOLD, state=AdviceState.DEGRADED,
            valid_from=valid_from, expires_at=expires_at,
            reasons=ctx.kelly_reasons, evidence_ids=tuple(evidence_ids),
        )

    action = AdviceAction.BUY if (ctx.kelly_f_max or Decimal(0)) > 0 else AdviceAction.HOLD
    return Advice(
        advice_id=advice_id, signal_id=ctx.signal_id, code=ctx.code,
        action=action, state=AdviceState.PUBLISHED,
        valid_from=valid_from, expires_at=expires_at,
        trigger_conditions=("开盘有效", "收盘自动失效"),
        f_min=ctx.kelly_f_min, f_max=ctx.kelly_f_max,
        value_min=ctx.kelly_value_min, value_max=ctx.kelly_value_max,
        suggested_lots=ctx.kelly_suggested_lots,
        reasons=ctx.kelly_reasons, evidence_ids=tuple(evidence_ids),
    )
