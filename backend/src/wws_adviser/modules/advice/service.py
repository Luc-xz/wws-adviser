"""Advice 服务：盘中快速建议编排（TECH §11.3）。

首请求刷新行情；组合事实（对账/可交易/新鲜度）+ 凯利资格 → 组装建议。
当前阶段（Phase 2 波4）：校准记录尚未落库，无可用信号 → 按规范返回
「暂停建议 + 原因 + 已知事实」，不静默隐藏。落库后自动产出真实区间。
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.advice.domain import (
    Advice,
    IntradayContext,
    build_intraday_advice,
)
from wws_adviser.modules.portfolio import service as portfolio_service
from wws_adviser.ports.market_data import InstrumentRef

_logger = logging.getLogger(__name__)

# 盘中建议有效期（秒）：TTL 内重复请求语义一致；收盘失效由前端/后续波实现
INTRADAY_TTL_SECONDS = 300

# 行情新鲜度阈值（PRD §20：盘中行情过期阈值 180 秒）
QUOTE_FRESH_SECONDS = 180


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


async def intraday_advice(
    db: DBSession,
    settings: Settings,
    request: Request,
    *,
    user_id: str,
    code: str,
) -> Advice:
    """POST /assistant/intraday 的编排：行情 → 事实检查 → 凯利资格 → 组装。"""
    now = now_utc_iso()
    valid_from = now
    expires_at = (
        _parse_iso(now) + timedelta(seconds=INTRADAY_TTL_SECONDS)
    ).isoformat()

    # 已知事实：账本对账状态
    try:
        account = portfolio_service.get_user_account(db, user_id)
        ledger_reconciled = bool(account.reconciled) if account is not None else False
    except Exception:
        ledger_reconciled = False

    # 行情快照（首请求刷新；适配器失败 → 不新鲜 → 暂停建议）
    quote_fresh = False
    tradable = True
    provider = getattr(request.app.state, "quote_provider", None)
    if provider is not None:
        try:
            quotes = await provider.fetch_quotes(
                [InstrumentRef(code=code, market="SSE", kind="stock")]
            )
            if quotes:
                fetched = _parse_iso(quotes[0].fetched_at)
                lag = (datetime.now(timezone.utc) - fetched).total_seconds()
                quote_fresh = lag <= QUOTE_FRESH_SECONDS
        except Exception as exc:  # noqa: BLE001 — 行情失败按不新鲜处理，不外抛
            _logger.warning("盘中行情获取失败 code=%s: %s", code, exc)

    # 凯利资格：校准记录存储在后续波接入；当前无已校准信号 → kelly_accepted=None
    ctx = IntradayContext(
        code=code, signal_id="",
        quote_fresh=quote_fresh, tradable=tradable,
        ledger_reconciled=ledger_reconciled,
        kelly_accepted=None,
    )
    advice = build_intraday_advice(
        ctx,
        advice_id=new_id(),
        valid_from=valid_from, expires_at=expires_at,
        evidence_ids=(),
    )
    return advice


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
    }
