"""建议评价回填服务（FR-REV-003：观察窗口后评价 + 回灌校准闭环）。

每日调度（ADVICE_REVIEW job）：
    到期建议（有效期已过 min_age_days）→ 从日线重建观察事实（触发后窗口收益）→
    按动作类型口径评价 → 写回 advice_records.verdict → 回灌信号校准
    （错误率过半建议 p×0.8、持续 ≥70% 走状态机转 DECAYED）。

事实可得性（诚实口径）：基准收益暂缺（无指数行情）→ REDUCE 口径
INCONCLUSIVE；BUY 口径以触发后窗口收益判定方向。
"""

import json
import logging
from datetime import date as Date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.advice.domain import AdviceAction
from wws_adviser.modules.advice.evaluation import (
    AdviceEvaluation,
    ObservationFacts,
    backfeed,
    evaluate,
)
from wws_adviser.modules.advice.models import AdviceRecord
from wws_adviser.modules.analytics import calibration_service
from wws_adviser.modules.analytics.calibration import (
    CalibrationEvent,
    CalibrationState,
    transition,
)
from wws_adviser.modules.analytics.models import SignalCalibration
from wws_adviser.modules.market_data.domain import NormalizedBar

_logger = logging.getLogger(__name__)

# 观察窗口：建议到期后再等的最少自然日（覆盖 5 个交易日的持有窗口）
DEFAULT_MIN_AGE_DAYS = 10
# 回看建议的最大条数（每日批处理上限）
BATCH_LIMIT = 200


def _horizon_for(db: DBSession, signal_id: str) -> int:
    from wws_adviser.modules.analytics.models import SignalRecord

    row = db.scalar(select(SignalRecord).where(SignalRecord.signal_id == signal_id))
    return row.horizon_days if row is not None else 5


def _direction_return(
    bars_by_code: dict[str, list[NormalizedBar]], code: str, advice_date: str, horizon: int
) -> Decimal | None:
    """触发后窗口收益：建议日次一交易日收盘入场，持有 horizon 个交易日收盘出场。"""
    bars = bars_by_code.get(code)
    if not bars:
        return None
    idx = next(
        (i for i, b in enumerate(bars) if b.business_date.isoformat() >= advice_date),
        None,
    )
    if idx is None or idx + horizon >= len(bars):
        return None
    entry, exit_bar = bars[idx], bars[idx + horizon]
    if entry.close <= 0:
        return None
    return (exit_bar.close - entry.close) / entry.close


def review_due_advices(
    db: DBSession,
    settings: Settings,
    *,
    min_age_days: int = DEFAULT_MIN_AGE_DAYS,
    today: str | None = None,
) -> dict[str, Any]:
    """评价到期建议并回灌校准。返回汇总（可审计）。"""
    today = today or Date.today().isoformat()
    rows = db.scalars(
        select(AdviceRecord)
        .where(
            AdviceRecord.verdict.is_(None),
            AdviceRecord.expires_at < today,
        )
        .order_by(AdviceRecord.created_at)
        .limit(BATCH_LIMIT)
    ).all()
    if not rows:
        return {"reviewed": 0, "signals": {}}

    bars_by_code = calibration_service.load_bars_by_code(db)
    evaluations_by_signal: dict[str, list[AdviceEvaluation]] = {}
    reviewed = 0
    for row in rows:
        if row.signal_id == "":
            continue  # 无信号的建议（降级形态）无可评价方向
        horizon = _horizon_for(db, row.signal_id)
        advice_date = (row.valid_from or "")[:10]
        direction = _direction_return(bars_by_code, row.code, advice_date, horizon)
        action = AdviceAction(row.action)
        facts = ObservationFacts(
            trigger_occurred=True if action is AdviceAction.BUY else None,
            direction_return=direction,
            benchmark_return=None,  # 指数基准行情未接入：REDUCE 口径诚实置 None
        )
        evaluation = evaluate(row.id, action, facts)
        row.verdict = evaluation.verdict.value
        row.evaluated_at = now_utc_iso()
        row.evaluation_json = json.dumps(
            {
                "spec_version": evaluation.spec_version,
                "reasons": list(evaluation.reasons),
                "direction_return": str(direction) if direction is not None else None,
                "horizon": horizon,
            },
            ensure_ascii=False,
        )
        reviewed += 1
        evaluations_by_signal.setdefault(row.signal_id, []).append(evaluation)

    # 回灌：错误率 → 降 p / DECAYED（闭环「凯利输入 ↔ 建议评价 ↔ 信号校准」）
    signal_summary: dict[str, Any] = {}
    for signal_id, evals in evaluations_by_signal.items():
        rec = backfeed(signal_id, evals)
        applied = _apply_backfeed(db, signal_id, rec.action, rec.suggested_p_factor)
        signal_summary[signal_id] = {
            "n_evaluated": rec.n_evaluated,
            "wrong_rate": str(rec.wrong_rate),
            "recommendation": rec.action,
            "applied": applied,
        }
    db.commit()
    _logger.info("建议评价回填完成：%s", {"reviewed": reviewed, "signals": signal_summary})
    return {"reviewed": reviewed, "signals": signal_summary}


def _apply_backfeed(
    db: DBSession, signal_id: str, action: str, p_factor: Decimal
) -> str:
    """把回灌结论作用到校准记录。返回实际动作（可审计）。"""
    row = db.scalar(
        select(SignalCalibration)
        .where(SignalCalibration.signal_id == signal_id)
        .order_by(SignalCalibration.updated_at.desc())
        .limit(1)
    )
    if row is None:
        return "no_record"
    if action == "reduce_p" and row.state == CalibrationState.CALIBRATED_OOS.value:
        # p 区间整体下调（诚实地板 0.05：不得把 p 压成负边际假象）
        for col in ("p_low", "p_mid", "p_high"):
            new_p = max(Decimal("0.05"), Decimal(getattr(row, col)) * p_factor)
            setattr(row, col, str(new_p))
        row.updated_at = now_utc_iso()
        row.row_version += 1
        return f"p×{p_factor}"
    if action == "decay":
        # 状态机合法路径：CALIBRATED_OOS --EXPIRE--> STALE --DECAY--> DECAYED
        state = CalibrationState(row.state)
        for event in (CalibrationEvent.EXPIRE, CalibrationEvent.DECAY):
            try:
                state = transition(state, event)
            except ValueError:
                continue  # 当前态不吃该事件则跳过（如已 STALE 不再 EXPIRE）
        row.state = state.value
        row.updated_at = now_utc_iso()
        row.row_version += 1
        return f"state→{state.value}"
    return "none"
