"""Research API：创建/查询/取消研究任务（Phase 3 波1）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from wws_adviser.api.dependencies import get_current_user, get_session
from wws_adviser.core.errors import DomainError, MissingIdempotencyKeyError
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.research import service

router = APIRouter(prefix="/api/v1/research", tags=["research"])


def _require_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if not idempotency_key:
        raise MissingIdempotencyKeyError()
    return idempotency_key


class CreateTaskRequest(BaseModel):
    task_type: str                     # company | industry
    subject: str                       # 证券代码或行业名称
    peer_codes: list[str] | None = None
    time_span: str | None = None
    depth: str = "standard"            # quick | standard | deep


class TaskOut(BaseModel):
    id: str
    task_type: str
    subject: str
    depth: str
    status: str
    progress: int
    error_code: str | None
    report_id: str | None
    created_at: str


class TaskListResponse(BaseModel):
    items: list[TaskOut]


@router.post("/tasks", response_model=TaskOut)
async def create_task(
    body: CreateTaskRequest,
    db: Annotated[DBSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    _key: Annotated[str, Depends(_require_idempotency_key)],
) -> TaskOut:
    task = service.create_task(
        db, user_id=user.id,
        task_type=body.task_type, subject=body.subject,
        peer_codes=body.peer_codes, time_span=body.time_span,
        depth=body.depth,
    )
    return _to_out(task)


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    db: Annotated[DBSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    limit: int = 20,
) -> TaskListResponse:
    tasks = service.list_tasks(db, user.id, limit=limit)
    return TaskListResponse(items=[_to_out(t) for t in tasks])


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: str,
    db: Annotated[DBSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> TaskOut:
    task = service.get_task(db, task_id)
    if task is None or task.user_id != user.id:
        raise DomainError("任务不存在")
    return _to_out(task)


@router.post("/tasks/{task_id}/cancel", response_model=TaskOut)
async def cancel_task(
    task_id: str,
    db: Annotated[DBSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    _key: Annotated[str, Depends(_require_idempotency_key)],
) -> TaskOut:
    task = service.cancel_task(db, task_id, user.id)
    return _to_out(task)


def _to_out(t) -> TaskOut:
    return TaskOut(
        id=t.id, task_type=t.task_type, subject=t.subject, depth=t.depth,
        status=t.status, progress=t.progress, error_code=t.error_code,
        report_id=t.report_id, created_at=t.created_at,
    )
