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
            if job.job_type == JobType.ADVICE_REVIEW.value:
                try:
                    from wws_adviser.modules.advice import evaluation_service

                    result = evaluation_service.review_due_advices(db, settings)
                    jobs_service.complete(
                        db, job.id, result_ref=f"advice_review://{result.get('reviewed', 0)}"
                    )
                except Exception as exc:  # noqa: BLE001 — 执行器边界：失败记 error_code
                    _logger.warning("建议评价任务失败 job=%s: %s", job.id, exc)
                    jobs_service.fail(db, job.id, error_code=type(exc).__name__)
                continue
            if job.job_type == JobType.CALIBRATION_SCAN.value:
                try:
                    result = _run_calibration_scan(db, settings)
                    jobs_service.complete(
                        db, job.id,
                        result_ref=f"calibration://{result.get('instruments', 0)}",
                    )
                except Exception as exc:  # noqa: BLE001 — 执行器边界：失败记 error_code
                    _logger.warning("校准任务失败 job=%s: %s", job.id, exc)
                    jobs_service.fail(db, job.id, error_code=type(exc).__name__)
                continue
            if job.job_type == JobType.DATA_MAINTENANCE.value:
                try:
                    maint = await _run_data_maintenance(db, settings)
                    ok_n, fail_n = maint.get("ok", 0), maint.get("failed", 0)
                    jobs_service.complete(
                        db, job.id, result_ref=f"bars://{ok_n}/{fail_n}"
                    )
                except Exception as exc:  # noqa: BLE001 — 执行器边界：失败记 error_code
                    _logger.warning("数据维护任务失败 job=%s: %s", job.id, exc)
                    jobs_service.fail(db, job.id, error_code=type(exc).__name__)
                continue
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


def _run_calibration_scan(db: DBSession, settings: Settings) -> dict[str, object]:
    """校准扫描任务体（Phase 2 波6）：信号回测 → OOS 门禁 → 校准记录落库。"""
    from wws_adviser.modules.analytics import calibration_service

    return calibration_service.run_calibration_scan(db, settings)

async def _run_data_maintenance(db: DBSession, settings: Settings) -> dict[str, int]:
    """数据维护任务体：持仓日线批量采集 + 交易日历同步（均幂等，重采安全）。

    15:20 调度赶在 16:00 收市后报告前拿到当日收盘价；单标的失败不中断批次。
    日历同步失败不影响日线采集（报告侧尚有 weekday 兜底，但节假日识别依赖本同步）。
    """
    from datetime import timedelta as _td

    from wws_adviser.core.time import business_date as _bd
    from wws_adviser.infrastructure.data_sources.akshare_bar import AKShareBarProvider
    from wws_adviser.infrastructure.data_sources.akshare_calendar import AKShareCalendarProvider
    from wws_adviser.modules.market_data import service as market_service

    if settings.market_data_source != "akshare":
        return {"ok": 0, "failed": 0}
    results = await market_service.ingest_bars_for_holdings(
        db, data_dir=settings.data_dir,
        provider=AKShareBarProvider(env=settings.env),
        request_id=f"data-maintenance-{_bd().isoformat()}",
    )
    ok = sum(1 for v in results.values() if v == "OK")
    try:
        today = _bd()
        cal_rows = await market_service.sync_trading_calendar_from_provider(
            db,
            provider=AKShareCalendarProvider(env=settings.env),
            start=today - _td(days=365),
            end=today + _td(days=400),
        )
        _logger.info("交易日历同步完成：%s 行（近一年 + 未来 400 天）", cal_rows)
    except Exception as exc:  # noqa: BLE001 — 日历失败不阻塞采集结果
        _logger.warning("交易日历同步失败（不影响日线采集）: %s", exc)
    return {"ok": ok, "failed": len(results) - ok}


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
