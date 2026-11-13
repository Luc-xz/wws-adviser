"""/api/v1/jobs 端点：任务列表/聚合/批次条目（3_API §3.13，采集监控面板波1）。

需登录，只读。单查 GET /api/v1/jobs/{job_id} 早在波5 由 reports/api.py 注册，
此处不重复（本模块路由须先于 reports_router 挂载，见 api/app.py 注释）。
"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DBSession

from wws_adviser.api.dependencies import get_current_user, get_session
from wws_adviser.core.errors import DomainError
from wws_adviser.modules.collections import repository as collections_repository
from wws_adviser.modules.collections import service as collections_service
from wws_adviser.modules.collections.domain import decode_cursor, encode_cursor, parse_result_ref
from wws_adviser.modules.collections.schemas import IngestItemListResponse, item_to_out
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.jobs import repository, service
from wws_adviser.modules.jobs.schemas import (
    JobListResponse,
    JobRunOut,
    JobStatsResponse,
)

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

DBDep = Annotated[DBSession, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]


class InvalidCursorError(DomainError):
    code = "VALIDATION_ERROR"
    status = 400
    title = "无效分页游标"


@router.get("", response_model=JobListResponse)
async def list_jobs(
    db: DBDep,
    user: UserDep,
    job_type: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    business_date: Annotated[str | None, Query()] = None,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> JobListResponse:
    """任务列表（created_at DESC；响应含 result_ref 摘要与条目计数）。"""
    cursor_created_at: str | None = None
    cursor_id: str | None = None
    if cursor:
        try:
            cursor_created_at, cursor_id = decode_cursor(cursor)
        except ValueError as exc:
            raise InvalidCursorError(str(exc)) from exc
    runs, has_more = service.list_runs(
        db,
        job_type=job_type,
        status=status,
        business_date=business_date,
        date_from=date_from,
        date_to=date_to,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
        limit=limit,
    )
    counts = collections_repository.item_counts_by_run(db, [r.id for r in runs])
    next_cursor = (
        encode_cursor(created_at=runs[-1].created_at, item_id=runs[-1].id)
        if has_more and runs
        else None
    )
    return JobListResponse(
        items=[
            JobRunOut(
                id=r.id,
                job_type=r.job_type,
                business_date=r.business_date,
                scope_key=r.scope_key,
                status=r.status,
                attempt=r.attempt,
                max_attempts=r.max_attempts,
                progress=r.progress,
                error_code=r.error_code,
                result_ref=r.result_ref,
                result_summary=parse_result_ref(r.result_ref),
                item_counts=counts.get(r.id, {}),
                started_at=r.started_at,
                completed_at=r.completed_at,
                created_at=r.created_at,
            )
            for r in runs
        ],
        next_cursor=next_cursor,
    )


@router.get("/stats", response_model=JobStatsResponse)
async def get_job_stats(
    db: DBDep,
    user: UserDep,
    window_days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> JobStatsResponse:
    stats = service.run_stats(db, window_days=window_days)
    return JobStatsResponse(
        window_days=cast(int, stats["window_days"]),
        total=cast(int, stats["total"]),
        by_status=cast("dict[str, int]", stats["by_status"]),
        success_rate=cast("float | None", stats["success_rate"]),
        avg_duration_ms=cast("int | None", stats["avg_duration_ms"]),
        consecutive_failures=cast("dict[str, int]", stats["consecutive_failures"]),
    )


@router.get("/{job_id}/items", response_model=IngestItemListResponse)
async def list_job_items(
    job_id: str,
    db: DBDep,
    user: UserDep,
    category: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> IngestItemListResponse:
    """批次采集条目明细（ingest_items；历史批次为空列表）。"""
    if repository.get_by_id(db, job_id) is None:
        raise service.JobNotFoundError(job_id)
    try:
        items, next_cursor = collections_service.list_items_page(
            db,
            run_id=job_id,
            category=category,
            status=status,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise InvalidCursorError(str(exc)) from exc
    return IngestItemListResponse(items=[item_to_out(i) for i in items], next_cursor=next_cursor)
