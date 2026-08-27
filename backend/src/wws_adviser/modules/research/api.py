"""Research API：创建/查询/取消研究任务 + 报告读取（Phase 3 波1/波4）。"""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from wws_adviser.api.dependencies import get_current_user, get_session, get_settings
from wws_adviser.core.config import Settings
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


class ReportOut(BaseModel):
    id: str
    task_id: str
    report_type: str
    subject: str
    content_md: str
    citations: list[dict]
    generation_config: dict
    created_at: str


@router.get("/tasks/{task_id}/events")
async def task_events(
    task_id: str,
    db: Annotated[DBSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    max_seconds: int = 600,
) -> StreamingResponse:
    """任务进度 SSE 推送（Phase 3 波7）：1s 心跳查询 → 终态/超时后关闭。

    EventSource 无法带自定义头，依赖 cookie 会话；任务须属于当前用户。
    max_seconds 连接上限（默认 10 分钟，防僵尸连接；客户端可重连）。
    """
    import asyncio

    from fastapi.responses import StreamingResponse

    service.get_report_task_checked(db, task_id, user.id)  # 存在性 + 属主校验

    terminal = {"COMPLETED", "FAILED", "CANCELLED"}

    async def gen():
        deadline = asyncio.get_event_loop().time() + max(1, max_seconds)
        while asyncio.get_event_loop().time() < deadline:
            db.expire_all()  # 执行器线程在另一 session 写入，强制重读
            t = service.get_task(db, task_id)
            if t is None:
                break
            payload = json.dumps({
                "task_id": t.id, "status": t.status, "progress": t.progress,
                "report_id": t.report_id, "error_code": t.error_code,
            }, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            if t.status in terminal:
                break
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/reports/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: str,
    db: Annotated[DBSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReportOut:
    """获取研究报告（含引用清单与生成配置，FR-RES-004 可复盘）。"""
    report = service.get_report(db, report_id)
    if report is None:
        raise DomainError("报告不存在")
    task = service.get_task(db, report.task_id)
    if task is None or task.user_id != user.id:
        raise DomainError("报告不存在")
    md = ""
    if report.content_md_path:
        p = settings.data_dir / report.content_md_path
        if p.exists():
            md = p.read_text(encoding="utf-8")
    return ReportOut(
        id=report.id, task_id=report.task_id,
        report_type=report.report_type, subject=report.subject,
        content_md=md,
        citations=json.loads(report.citations_json or "[]"),
        generation_config=json.loads(report.generation_config_json or "{}"),
        created_at=report.created_at,
    )


@router.get("/reports/{report_id}/export")
async def export_report(
    report_id: str,
    db: Annotated[DBSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    format: str = "md",
) -> Response:
    """导出报告（Phase 3 波6）：md 原文 / html 自包含页面（可打印为 PDF）。"""
    if format not in ("md", "html"):
        raise DomainError(f"不支持的导出格式：{format}")
    report = service.get_report(db, report_id)
    if report is None:
        raise DomainError("报告不存在")
    task = service.get_task(db, report.task_id)
    if task is None or task.user_id != user.id:
        raise DomainError("报告不存在")
    md = ""
    if report.content_md_path:
        p = settings.data_dir / report.content_md_path
        if p.exists():
            md = p.read_text(encoding="utf-8")
    if not md:
        raise DomainError("报告内容为空，无法导出")

    from wws_adviser.modules.research import export as export_mod

    filename = export_mod.export_filename(report, format)
    if format == "html":
        body = export_mod.md_to_html(md, title=f"{report.subject} 研究报告")
        media = "text/html; charset=utf-8"
    else:
        body = md
        media = "text/markdown; charset=utf-8"
    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _to_out(t) -> TaskOut:
    return TaskOut(
        id=t.id, task_type=t.task_type, subject=t.subject, depth=t.depth,
        status=t.status, progress=t.progress, error_code=t.error_code,
        report_id=t.report_id, created_at=t.created_at,
    )
