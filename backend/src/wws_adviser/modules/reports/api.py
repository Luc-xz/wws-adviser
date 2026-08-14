"""/api/v1/reports + /api/v1/jobs 端点（3_API §3.11/§3.13，波5）。

POST /reports/generate：入队（幂等）+ 内联领取执行（MVP 单进程），返回 job_run_id。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session as DBSession

from wws_adviser.api.dependencies import get_current_user, get_session, get_settings
from wws_adviser.core.config import Settings
from wws_adviser.core.errors import DomainError, MissingIdempotencyKeyError
from wws_adviser.core.time import business_date
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.jobs import repository as jobs_repository
from wws_adviser.modules.reports import executor, repository, service
from wws_adviser.modules.reports.domain import ReportType
from wws_adviser.modules.reports.models import Report
from wws_adviser.modules.reports.schemas import (
    GenerateRequest,
    GenerateResponse,
    JobOut,
    ReportDetail,
    ReportListResponse,
    ReportOut,
)

router = APIRouter(prefix="/api/v1", tags=["reports"])

DBDep = Annotated[DBSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
UserDep = Annotated[User, Depends(get_current_user)]


def _require_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if not idempotency_key:
        raise MissingIdempotencyKeyError()
    return idempotency_key


def _to_out(r: Report) -> ReportOut:
    return ReportOut(
        id=r.id,
        report_type=r.report_type,
        business_date=r.business_date,
        status=r.status,
        version=r.version,
        sources_count=r.sources_count,
        schema_version=r.schema_version,
        risk_ruleset_version=r.risk_ruleset_version,
        generated_at=r.generated_at,
        analysis_snapshot_id=r.analysis_snapshot_id,
        manifest_path=r.manifest_path,
        content_json_path=r.content_json_path,
        content_md_path=r.content_md_path,
    )


def _to_detail(r: Report, settings: Settings, flags: list[str] | None = None) -> ReportDetail:
    content = service.get_report_content(settings.data_dir, r)
    snap_flags: list[str] = []
    if flags is not None:
        snap_flags = flags
    return ReportDetail(
        **_to_out(r).model_dump(),
        content=content,
        degradation_flags=snap_flags,
    )


@router.get("/reports", response_model=ReportListResponse)
async def list_reports(
    db: DBDep,
    user: UserDep,
    report_type: Annotated[str | None, Query()] = None,
    business_date: Annotated[str | None, Query()] = None,
) -> ReportListResponse:
    reports = repository.list_reports(
        db, report_type=report_type, business_date=business_date
    )
    return ReportListResponse(items=[_to_out(r) for r in reports])


@router.get("/reports/{report_id}", response_model=ReportDetail)
async def get_report(
    report_id: str, db: DBDep, user: UserDep, settings: SettingsDep
) -> ReportDetail:
    r = repository.get_report(db, report_id)
    if r is None:
        raise DomainError("报告不存在")
    return _to_detail(r, settings)


@router.get("/reports/{report_id}/render", response_class=PlainTextResponse)
async def render_report(
    report_id: str,
    db: DBDep,
    user: UserDep,
    settings: SettingsDep,
    format: Annotated[str, Query()] = "md",
) -> PlainTextResponse:
    r = repository.get_report(db, report_id)
    if r is None:
        raise DomainError("报告不存在")
    text = service.read_render(settings.data_dir, r, format)
    if text is None:
        raise DomainError(f"渲染产物不存在（format={format}）")
    return PlainTextResponse(text)


@router.post("/reports/generate", response_model=GenerateResponse)
async def generate_report(
    body: GenerateRequest,
    request: Request,
    db: DBDep,
    settings: SettingsDep,
    user: UserDep,
    _key: Annotated[str, Depends(_require_idempotency_key)],
) -> GenerateResponse:
    try:
        rt = ReportType(body.report_type)
    except ValueError:
        raise DomainError(f"未知报告类型：{body.report_type}") from None
    bd = body.business_date or business_date().isoformat()
    job = executor.enqueue_report_job(db, settings, report_type=rt, business_date=bd)
    model_port = getattr(request.app.state, "model_port", None)
    try:
        result = await service.generate_report(
            db,
            settings=settings,
            data_dir=settings.data_dir,
            user_id=user.id,
            report_type=rt,
            business_date=bd,
            job_run_id=job.id,
            manual=True,
            model_port=model_port,
        )
        return GenerateResponse(
            job_run_id=job.id,
            report=_to_detail(result.report, settings, result.degradation_flags),
        )
    except service.NotTradingDayError as exc:
        return GenerateResponse(job_run_id=job.id, skipped=True, skip_reason=exc.detail)


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str, db: DBDep, user: UserDep) -> JobOut:
    job = jobs_repository.get_by_id(db, job_id)
    if job is None:
        raise DomainError("任务不存在")
    return JobOut(
        id=job.id,
        job_type=job.job_type,
        business_date=job.business_date,
        status=job.status,
        attempt=job.attempt,
        progress=job.progress,
        error_code=job.error_code,
        result_ref=job.result_ref,
    )
