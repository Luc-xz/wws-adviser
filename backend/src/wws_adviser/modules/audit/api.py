"""Audit API：审计事件只读查询（W2.5-5，DATA-01 审计日志入口）。

审计事件是系统级流水（单用户部署，无跨用户隔离问题）；登录必需。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.api.dependencies import get_current_user, get_session
from wws_adviser.modules.audit.models import AuditEvent
from wws_adviser.modules.identity.models import User

router = APIRouter(prefix="/api/v1/audit-events", tags=["audit"])


class AuditEventOut(BaseModel):
    id: str
    action: str
    target_type: str | None
    target_id: str | None
    occurred_at: str
    request_id: str | None


class AuditEventListResponse(BaseModel):
    items: list[AuditEventOut]


@router.get("", response_model=AuditEventListResponse)
async def list_audit_events(
    db: Annotated[DBSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditEventListResponse:
    """最近审计事件（occurred_at 倒序）。只读，不校验 CSRF。"""
    rows = db.scalars(
        select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(limit)
    ).all()
    return AuditEventListResponse(
        items=[
            AuditEventOut(
                id=r.id,
                action=r.action,
                target_type=r.target_type,
                target_id=r.target_id,
                occurred_at=r.occurred_at,
                request_id=r.request_id,
            )
            for r in rows
        ]
    )
