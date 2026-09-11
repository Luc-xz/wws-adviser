"""Advice API：盘中快速问询 + 历史建议记录查询（3_API §3.9/§3.10）。

- POST /assistant/intraday：写操作（CSRF 全局中间件 + Idempotency-Key 强制）。
- GET /advice*：只读查询（登录必需），HOME-02 列表 / CHAT-02 详情 / 评价回读。

响应语义：建议 + 时间戳 + 有效期 + evidence IDs；数据不合格返回
「暂停建议 + 原因 + 已知事实」，不静默隐藏。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from wws_adviser.api.dependencies import get_current_user, get_session, get_settings
from wws_adviser.core.config import Settings
from wws_adviser.core.errors import MissingIdempotencyKeyError
from wws_adviser.modules.advice import service
from wws_adviser.modules.advice.schemas import (
    AdviceEvaluationOut,
    AdviceRecordListResponse,
    AdviceRecordOut,
)
from wws_adviser.modules.identity.models import User

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])
records_router = APIRouter(prefix="/api/v1/advice", tags=["advice"])


def _require_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if not idempotency_key:
        raise MissingIdempotencyKeyError()
    return idempotency_key


class IntradayRequest(BaseModel):
    code: str  # 标的代码，如 600519


class IntradayResponse(BaseModel):
    schema_version: str
    advice: dict[str, object]


@router.post("/intraday", response_model=IntradayResponse)
async def intraday(
    body: IntradayRequest,
    request: Request,
    db: Annotated[DBSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[User, Depends(get_current_user)],
    _key: Annotated[str, Depends(_require_idempotency_key)],
) -> IntradayResponse:
    advice = await service.intraday_advice(
        db, settings, request, user_id=user.id, code=body.code
    )
    return IntradayResponse(
        schema_version="1", advice=service.advice_to_payload(advice)
    )


@router.get("/coverage/{code}")
async def signal_coverage(
    code: str,
    db: Annotated[DBSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    """信号覆盖透视（W2-5 / PORT-02）：当日是否触发 + 校准状态 + 人话注解。"""
    return service.signal_coverage(db, code)


@records_router.get("", response_model=AdviceRecordListResponse)
async def list_advice_records(
    db: Annotated[DBSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    code: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AdviceRecordListResponse:
    page = service.list_records(
        db, user_id=user.id, code=code, action=action, state=state,
        cursor=cursor, limit=limit,
    )
    return AdviceRecordListResponse(
        items=[AdviceRecordOut(**service.record_to_payload(r)) for r in page.rows],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@records_router.get("/{record_id}", response_model=AdviceRecordOut)
async def get_advice_record(
    record_id: str,
    db: Annotated[DBSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> AdviceRecordOut:
    row = service.get_record(db, user_id=user.id, record_id=record_id)
    return AdviceRecordOut(**service.record_to_payload(row))


@records_router.get("/{record_id}/evaluation", response_model=AdviceEvaluationOut)
async def get_advice_evaluation(
    record_id: str,
    db: Annotated[DBSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> AdviceEvaluationOut:
    row = service.get_record(db, user_id=user.id, record_id=record_id)
    ev = service.record_to_payload(row)["evaluation"] or {}
    return AdviceEvaluationOut(
        verdict=row.verdict,
        evaluated_at=row.evaluated_at,
        spec_version=ev.get("spec_version"),
        reasons=list(ev.get("reasons", [])),
        direction_return=ev.get("direction_return"),
        horizon=ev.get("horizon"),
    )
