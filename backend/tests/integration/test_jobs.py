"""Jobs 服务测试：幂等入队 + claim CAS + lease 过期重领 + 状态机（6_MODEL §8/§11）。"""

import time

import pytest
from sqlalchemy import select

from wws_adviser.core.config import Settings
from wws_adviser.modules.jobs import service as jobs_service
from wws_adviser.modules.jobs.domain import JobStatus, JobType
from wws_adviser.modules.jobs.models import JobRun


def _settings() -> Settings:
    return Settings(env="test")


def test_enqueue_idempotent_returns_existing(db_session):
    s = _settings()
    j1 = jobs_service.enqueue(
        db_session, s, job_type=JobType.STUB, business_date="2026-08-12", scope_key="d"
    )
    j2 = jobs_service.enqueue(
        db_session, s, job_type=JobType.STUB, business_date="2026-08-12", scope_key="d"
    )
    assert j1.id == j2.id  # UNIQUE 冲突返回已存在，不创建第二个
    rows = list(db_session.scalars(select(JobRun)))
    assert len(rows) == 1


def test_claim_sets_running_and_lease(db_session):
    s = _settings()
    jobs_service.enqueue(
        db_session, s, job_type=JobType.STUB, business_date="2026-08-12", scope_key="d"
    )
    claimed = jobs_service.claim_next(db_session, s)
    assert claimed is not None
    assert claimed.status == JobStatus.RUNNING.value
    assert claimed.lease_until is not None
    assert claimed.attempt == 1


def test_claim_cas_no_concurrent(db_session):
    """两 executor 抢同一任务，只一个成功（CAS rowcount）。"""
    s = _settings()
    jobs_service.enqueue(
        db_session, s, job_type=JobType.STUB, business_date="2026-08-12", scope_key="d"
    )
    c1 = jobs_service.claim_next(db_session, s)
    c2 = jobs_service.claim_next(db_session, s)  # RUNNING 且 lease 未过期 → 无可领取
    assert c1 is not None
    assert c2 is None


def test_lease_expiry_reclaimable(db_session):
    """租约到期后可重新领取并完成（Phase 0 退出条件 3）。"""
    s = _settings()
    s.job_lease_ttl_seconds = 0
    jobs_service.enqueue(
        db_session, s, job_type=JobType.STUB, business_date="2026-08-12", scope_key="d"
    )
    c1 = jobs_service.claim_next(db_session, s)
    assert c1 is not None
    time.sleep(0.02)  # 确保 now_iso 越过 lease
    c2 = jobs_service.claim_next(db_session, s)
    assert c2 is not None
    assert c2.attempt == 2  # 重领 attempt 递增
    done = jobs_service.complete(db_session, c2.id)
    assert done.status == JobStatus.COMPLETED.value


def test_complete_and_fail(db_session):
    s = _settings()
    j = jobs_service.enqueue(
        db_session, s, job_type=JobType.STUB, business_date="2026-08-12", scope_key="d"
    )
    jobs_service.claim_next(db_session, s)
    done = jobs_service.complete(db_session, j.id, result_ref="report://x")
    assert done.status == JobStatus.COMPLETED.value
    assert done.result_ref == "report://x"

    j2 = jobs_service.enqueue(
        db_session, s, job_type=JobType.STUB, business_date="2026-08-12", scope_key="d2"
    )
    jobs_service.claim_next(db_session, s)
    failed = jobs_service.fail(db_session, j2.id, error_code="MODEL_UNAVAILABLE")
    assert failed.status == JobStatus.FAILED.value
    assert failed.error_code == "MODEL_UNAVAILABLE"


def test_invalid_transition_rejected(db_session):
    s = _settings()
    j = jobs_service.enqueue(
        db_session, s, job_type=JobType.STUB, business_date="2026-08-12", scope_key="d"
    )
    with pytest.raises(jobs_service.InvalidTransitionError):
        jobs_service.complete(db_session, j.id)  # PENDING → COMPLETED 非法


def test_scheduler_enqueue_only_viapoints():
    """APScheduler handler 只调 enqueue，不触碰业务表 —— 边界由 create_scheduler 结构保证。"""
    # create_scheduler 注册的 job 只入队，不 import 业务模块（结构性边界检查）
    import inspect

    from wws_adviser.core import scheduler as sched_mod

    text = inspect.getsource(sched_mod)
    assert "reports" not in text and "advice" not in text
