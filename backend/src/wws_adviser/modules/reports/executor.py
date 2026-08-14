"""Reports 执行器：领取 PRE_MARKET/POST_MARKET job_runs → 生成报告 → 完成/失败 → 通知。

独立于 scheduler（APScheduler 只入队，6_MODEL §8.1）；MVP 单进程顺序执行。
通知在报告终态后发送，失败绝不失败报告 job（FR-NOTIFY-001）。
"""

import logging
from pathlib import Path

from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.core.time import business_date as today_str
from wws_adviser.modules.jobs import service as jobs_service
from wws_adviser.modules.jobs.domain import JobType
from wws_adviser.modules.jobs.models import JobRun
from wws_adviser.modules.notifications import service as notifications_service
from wws_adviser.modules.notifications.domain import NotificationEvent
from wws_adviser.modules.reports.domain import ReportType
from wws_adviser.modules.reports.service import NotTradingDayError, generate_report
from wws_adviser.ports.model import ModelPort
from wws_adviser.ports.notifier import NotifierPort

_logger = logging.getLogger(__name__)

_REPORT_JOBS = {JobType.PRE_MARKET.value, JobType.POST_MARKET.value}


def _user_id_for_job(db: DBSession) -> str:
    """MVP 单用户：取第一个用户（多用户随后续波次按 scope_key 路由）。"""
    from sqlalchemy import select

    from wws_adviser.modules.identity.models import User

    uid = db.scalar(select(User.id).limit(1))
    if uid is None:
        raise RuntimeError("无用户，无法执行报告任务")
    return uid


async def _notify_report_event(
    db: DBSession,
    settings: Settings,
    notifier: NotifierPort | None,
    *,
    event_type: str,
    payload: dict[str, object],
) -> None:
    """发送通知；任何失败只记日志（FR-NOTIFY-001）。"""
    if notifier is None:
        return
    try:
        await notifications_service.notify(
            db, settings, notifier, event_type=event_type, payload=payload
        )
    except Exception as exc:  # noqa: BLE001 — 通知绝不影响报告任务
        _logger.warning("通知发送失败（不影响报告任务）: %s", exc)


async def run_due_jobs(
    db: DBSession,
    settings: Settings,
    data_dir: Path,
    *,
    model_port: ModelPort | None = None,
    notifier: NotifierPort | None = None,
) -> int:
    """循环领取并执行报告任务，返回执行（含跳过）的任务数。"""
    executed = 0
    while True:
        job = jobs_service.claim_next(db, settings)
        if job is None:
            break
        executed += 1
        if job.job_type not in _REPORT_JOBS:
            jobs_service.complete(db, job.id)
            continue
        report_type = (
            ReportType.PRE_MARKET
            if job.job_type == JobType.PRE_MARKET.value
            else ReportType.POST_MARKET
        )
        try:
            result = await generate_report(
                db,
                settings=settings,
                data_dir=data_dir,
                user_id=_user_id_for_job(db),
                report_type=report_type,
                business_date=job.business_date,
                job_run_id=job.id,
                model_port=model_port,
            )
            jobs_service.complete(db, job.id, result_ref=f"report://{result.report.id}")
            await _notify_report_event(
                db, settings, notifier,
                event_type=NotificationEvent.REPORT_COMPLETED.value,
                payload={
                    "report_type": report_type.value,
                    "business_date": job.business_date,
                    "report_id": result.report.id,
                    "risk_breach_count": 0,
                    "degraded": bool(result.degradation_flags),
                },
            )
        except NotTradingDayError as exc:
            # 非交易日：任务本身正常完成（无报告产出），结果引用注明跳过
            jobs_service.complete(db, job.id, result_ref=f"skipped://{exc.detail}")
        except Exception as exc:  # noqa: BLE001 — 执行器边界：任何失败记 error_code 不外抛
            _logger.warning("报告任务失败 job=%s: %s", job.id, exc)
            jobs_service.fail(db, job.id, error_code=type(exc).__name__)
            await _notify_report_event(
                db, settings, notifier,
                event_type=NotificationEvent.REPORT_FAILED.value,
                payload={"report_type": report_type.value, "business_date": job.business_date},
            )
    return executed


def enqueue_report_job(
    db: DBSession,
    settings: Settings,
    *,
    report_type: ReportType,
    business_date: str | None = None,
) -> JobRun:
    """入队一个报告任务（幂等：UNIQUE 冲突返回已存在）。"""
    bd = business_date or today_str().isoformat()
    return jobs_service.enqueue(
        db, settings, job_type=JobType(report_type.value), business_date=bd, scope_key="default"
    )
