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


# —— 手动批次 + 列表/聚合（采集监控面板，5_DATA §12.2/§12.3） ——


def start_manual_run(
    db: DBSession,
    settings: Settings,
    *,
    job_type: str,
    business_date: str,
    scope_key: str,
    idempotency_key: str | None = None,
    request_id: str | None = None,
) -> JobRun:
    """非幂等手动批次：直接 RUNNING（lease_until=None 不入执行器领取范围）、逐次留痕。

    与 enqueue（幂等 UNIQUE 元组）互补：手动补采每次调用都应产生一行批次记录。
    同步执行方（refresh 端点）负责随后 complete/fail。
    """
    now = now_utc_iso()
    job = JobRun(
        id=new_id(),
        job_type=job_type,
        business_date=business_date,
        scope_key=scope_key,
        idempotency_key=idempotency_key,
        config_version=1,
        status=JobStatus.RUNNING.value,
        attempt=1,
        max_attempts=1,
        lease_until=None,
        started_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    audit_service.append_event(
        db,
        action="job_enqueued",
        target_type="job",
        target_id=job.id,
        after={"job_type": job_type, "business_date": business_date, "manual": True},
        request_id=request_id,
    )
    db.commit()
    return job


def list_runs(
    db: DBSession,
    *,
    job_type: str | None = None,
    status: str | None = None,
    business_date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    cursor_created_at: str | None = None,
    cursor_id: str | None = None,
    limit: int = 50,
) -> tuple[list[JobRun], bool]:
    """任务列表（created_at DESC, id DESC 键集分页，3_API §3.13 覆盖 §4 默认排序）。"""
    stmt = select(JobRun)
    filters: list[ColumnElement[bool]] = []
    if job_type is not None:
        filters.append(JobRun.job_type == job_type)
    if status is not None:
        filters.append(JobRun.status == status)
    if business_date is not None:
        filters.append(JobRun.business_date == business_date)
    if date_from is not None:
        filters.append(JobRun.business_date >= date_from)
    if date_to is not None:
        filters.append(JobRun.business_date <= date_to)
    if cursor_created_at is not None and cursor_id is not None:
        filters.append(
            (JobRun.created_at < cursor_created_at)
            | ((JobRun.created_at == cursor_created_at) & (JobRun.id < cursor_id))
        )
    if filters:
        stmt = stmt.where(*filters)
    rows = list(
        db.scalars(
            stmt.order_by(JobRun.created_at.desc(), JobRun.id.desc()).limit(limit + 1)
        ).all()
    )
    has_more = len(rows) > limit
    return rows[:limit], has_more


def run_stats(db: DBSession, *, window_days: int = 7) -> dict[str, object]:
    """窗口聚合：按状态计数、成功率、平均耗时、按类型连续失败（SET-08/DATA-01 共用）。

    成功率口径：(COMPLETED+PARTIAL) / (COMPLETED+PARTIAL+FAILED)；CANCELLED 与未终态不计。
    连续失败：窗口内按 created_at 倒序取各 job_type 的最新序列，遇非 FAILED 即止。
    """
    cutoff = (datetime.now(UTC) - timedelta(days=window_days)).isoformat()
    runs = list(
        db.scalars(
            select(JobRun).where(JobRun.created_at >= cutoff).order_by(JobRun.created_at.desc())
        ).all()
    )
    by_status: dict[str, int] = {}
    durations_ms: list[int] = []
    streak: dict[str, int] = {}
    streak_done: set[str] = set()  # 已遇非 FAILED 的类型，停止累计
    for run in runs:
        by_status[run.status] = by_status.get(run.status, 0) + 1
        if run.job_type not in streak_done:
            if run.status == JobStatus.FAILED.value:
                streak[run.job_type] = streak.get(run.job_type, 0) + 1
            else:
                streak_done.add(run.job_type)
        duration = _duration_ms(run)
        if duration is not None:
            durations_ms.append(duration)
    finished = (
        by_status.get(JobStatus.COMPLETED.value, 0)
        + by_status.get(JobStatus.PARTIAL.value, 0)
        + by_status.get(JobStatus.FAILED.value, 0)
    )
    succeeded = (
        by_status.get(JobStatus.COMPLETED.value, 0) + by_status.get(JobStatus.PARTIAL.value, 0)
    )
    consecutive_failures = {k: v for k, v in streak.items() if v > 0}
    return {
        "window_days": window_days,
        "total": len(runs),
        "by_status": by_status,
        "success_rate": round(succeeded / finished, 4) if finished else None,
        "avg_duration_ms": round(sum(durations_ms) / len(durations_ms)) if durations_ms else None,
        "consecutive_failures": consecutive_failures,
    }


def _duration_ms(run: JobRun) -> int | None:
    if not run.started_at or not run.completed_at:
        return None
    try:
        started = datetime.fromisoformat(run.started_at)
        completed = datetime.fromisoformat(run.completed_at)
    except ValueError:
        return None
    return max(0, int((completed - started).total_seconds() * 1000))
