"""Advice API：盘中快速问询（POST /assistant/intraday，TECH §11.3）。

写操作（CSRF 全局中间件 + Idempotency-Key 强制）；登录必需。
响应语义：建议 + 时间戳 + 有效期 + evidence IDs；数据不合格返回
「暂停建议 + 原因 + 已知事实」，不静默隐藏。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from wws_adviser.api.dependencies import get_current_user, get_session, get_settings
from wws_adviser.core.config import Settings
from wws_adviser.core.errors import MissingIdempotencyKeyError
from wws_adviser.modules.advice import service
from wws_adviser.modules.identity.models import User

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])


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
