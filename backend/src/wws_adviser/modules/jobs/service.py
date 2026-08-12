"""Jobs 服务：幂等入队 + 条件领取（CAS）+ lease 过期重领 + 完成/失败/取消。

并发安全靠条件 UPDATE 的 rowcount（单进程 + CAS），不依赖 SELECT FOR UPDATE
（SQLite 不支持；PostgreSQL 迁移后可加 with_for_update）。
"""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import and_, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.sql.elements import ColumnElement

from wws_adviser.core.config import Settings
from wws_adviser.core.errors import DomainError
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.audit import service as audit_service
from wws_adviser.modules.jobs import repository
from wws_adviser.modules.jobs.domain import JobStatus, JobType, can_transition
from wws_adviser.modules.jobs.models import JobRun


class JobNotFoundError(DomainError):
    code = "NOT_FOUND"
    status = 404
    title = "任务不存在"


class InvalidTransitionError(DomainError):
    code = "CONFLICT"
    status = 409
    title = "非法状态转换"


def _claimable_filter(now_iso: str) -> ColumnElement[bool]:
    """PENDING/RETRY_WAIT，或 RUNNING 且 lease 已过期。"""
    return or_(
        JobRun.status.in_([JobStatus.PENDING.value, JobStatus.RETRY_WAIT.value]),
        and_(
            JobRun.status == JobStatus.RUNNING.value,
            JobRun.lease_until.is_not(None),
            JobRun.lease_until < now_iso,
        ),
    )


def enqueue(
    db: DBSession,
    settings: Settings,
    *,
    job_type: str | JobType,
    business_date: str,
    scope_key: str,
    config_version: int = 1,
    idempotency_key: str | None = None,
    request_id: str | None = None,
) -> JobRun:
    """幂等入队：UNIQUE 冲突返回已存在任务（不创建第二个，见 6_MODEL §8.3）。"""
    jt = job_type.value if isinstance(job_type, JobType) else job_type
    job = JobRun(
        id=new_id(),
        job_type=jt,
        business_date=business_date,
        scope_key=scope_key,
        idempotency_key=idempotency_key,
        config_version=config_version,
        status=JobStatus.PENDING.value,
        attempt=0,
        max_attempts=settings.job_max_attempts,
        created_at=now_utc_iso(),
        updated_at=now_utc_iso(),
    )
    db.add(job)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(JobRun).where(
                JobRun.job_type == jt,
                JobRun.business_date == business_date,
                JobRun.scope_key == scope_key,
                JobRun.config_version == config_version,
            )
        )
        assert existing is not None
        return existing
    audit_service.append_event(
        db,
        action="job_enqueued",
        target_type="job",
        target_id=job.id,
        after={"job_type": jt, "business_date": business_date},
        request_id=request_id,
    )
    db.commit()
    return job


def claim_next(
    db: DBSession, settings: Settings, *, request_id: str | None = None
) -> JobRun | None:
    """条件领取（CAS）：选一个可领取任务，原子置 RUNNING + 设 lease。
    rowcount=1 才算领取成功 —— 保证同一 job_run 不被两执行器并发执行。"""
    now_iso = now_utc_iso()
    lease_until = (
        datetime.now(UTC) + timedelta(seconds=settings.job_lease_ttl_seconds)
    ).isoformat()

    candidate = db.scalar(
        select(JobRun)
        .where(_claimable_filter(now_iso))
        .order_by(JobRun.created_at)
        .limit(1)
    )
    if candidate is None:
        return None

    result = db.execute(
        update(JobRun)
        .where(JobRun.id == candidate.id, _claimable_filter(now_iso))
        .values(
            status=JobStatus.RUNNING.value,
            lease_until=lease_until,
            attempt=candidate.attempt + 1,
            started_at=candidate.started_at or now_iso,
            updated_at=now_iso,
        )
    )
    if (cast(CursorResult[Any], result).rowcount or 0) != 1:
        db.rollback()
        return None  # 被别人抢走
    audit_service.append_event(
        db,
        action="job_claimed",
        target_type="job",
        target_id=candidate.id,
        request_id=request_id,
    )
    db.commit()
    return repository.get_by_id(db, candidate.id)


def _set_transition(
    job: JobRun,
    target: JobStatus,
    *,
    error_code: str | None = None,
    result_ref: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    src = JobStatus(job.status)
    if not can_transition(src, target):
        raise InvalidTransitionError(f"{src.value} → {target.value} 非法")
    job.status = target.value
    job.updated_at = now_utc_iso()
    if target in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.PARTIAL, JobStatus.CANCELLED):
        job.completed_at = now_utc_iso()
        job.lease_until = None
    if error_code:
        job.error_code = error_code
    if result_ref:
        job.result_ref = result_ref
    for k, v in (extra or {}).items():
        setattr(job, k, v)


def complete(
    db: DBSession,
    job_id: str,
    *,
    result_ref: str | None = None,
    request_id: str | None = None,
) -> JobRun:
    job = repository.get_by_id(db, job_id)
    if job is None:
        raise JobNotFoundError(job_id)
    _set_transition(job, JobStatus.COMPLETED, result_ref=result_ref)
    audit_service.append_event(
        db, action="job_completed", target_type="job", target_id=job_id, request_id=request_id
    )
    db.commit()
    return job


def fail(
    db: DBSession,
    job_id: str,
    *,
    error_code: str,
    request_id: str | None = None,
) -> JobRun:
    job = repository.get_by_id(db, job_id)
    if job is None:
        raise JobNotFoundError(job_id)
    _set_transition(job, JobStatus.FAILED, error_code=error_code)
    audit_service.append_event(
        db, action="job_failed", target_type="job", target_id=job_id, request_id=request_id
    )
    db.commit()
    return job


def cancel(db: DBSession, job_id: str) -> JobRun:
    job = repository.get_by_id(db, job_id)
    if job is None:
        raise JobNotFoundError(job_id)
    _set_transition(job, JobStatus.CANCELLED)
    db.commit()
    return job
