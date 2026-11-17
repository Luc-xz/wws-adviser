"""APScheduler 集成：只入队 job_runs，不执行业务（见 6_MODEL §8.1）。

Phase 0 注册 pre_market(08:30)/post_market(16:00) cron trigger，handler 只 enqueue 一个
stub job_run，证明"APScheduler 只入队"边界。真实 job handler 在 Phase 1+ 接报告流水线。
市场环境三任务（ADR-0014 / 5_DATA §13.5）：盘中每 5 分钟（scope_key=HH:MM——
uq_job_runs_idem 以 (job_type, business_date, scope_key) 为幂等键，盘中多次入队
必须以时间槽区分 scope_key，否则全天只会执行第一次）、15:25 日K、08:10 外围。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]

from wws_adviser.core.config import Settings
from wws_adviser.core.db import make_session_factory
from wws_adviser.core.time import SHANGHAI, business_date
from wws_adviser.modules.jobs import service as jobs_service
from wws_adviser.modules.jobs.domain import JobType

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


def _enqueue_stub(job_type: JobType, engine: "Engine", settings: Settings) -> None:
    """trigger 回调：开独立 session 入队一个 job_run，绝不触碰业务表。"""
    factory = make_session_factory(engine)
    with factory() as db:
        jobs_service.enqueue(
            db,
            settings,
            job_type=job_type,
            business_date=business_date().isoformat(),
            scope_key="default",
        )


def _enqueue_market_env_intraday(engine: "Engine", settings: Settings) -> None:
    """盘中任务：scope_key=HH:MM 时间槽（同日多次入队互不冲突，见模块 docstring）。"""
    factory = make_session_factory(engine)
    with factory() as db:
        jobs_service.enqueue(
            db,
            settings,
            job_type=JobType.MARKET_ENV_INTRADAY,
            business_date=business_date().isoformat(),
            scope_key=datetime.now(SHANGHAI).strftime("%H:%M"),
        )


def create_scheduler(engine: "Engine", settings: Settings) -> BackgroundScheduler:
    """构建调度器（不启动；由 main.py lifespan start/stop）。"""
    scheduler = BackgroundScheduler(timezone=SHANGHAI)

    def _pre_market() -> None:
        _enqueue_stub(JobType.PRE_MARKET, engine, settings)

    def _post_market() -> None:
        _enqueue_stub(JobType.POST_MARKET, engine, settings)

    def _calibration_scan() -> None:
        _enqueue_stub(JobType.CALIBRATION_SCAN, engine, settings)

    def _review_scan() -> None:
        _enqueue_stub(JobType.ADVICE_REVIEW, engine, settings)

    def _data_maintenance() -> None:
        _enqueue_stub(JobType.DATA_MAINTENANCE, engine, settings)

    scheduler.add_job(
        _pre_market,
        CronTrigger(hour=8, minute=30, timezone=SHANGHAI),
        id="pre_market",
    )
    scheduler.add_job(
        _post_market,
        CronTrigger(hour=16, minute=0, timezone=SHANGHAI),
        id="post_market",
    )
    # 校准扫描：开市前重跑（08:00），保证盘中建议用当日校准结论（FR-ANL-003）
    scheduler.add_job(
        _calibration_scan,
        CronTrigger(hour=8, minute=0, timezone=SHANGHAI),
        id="calibration_scan",
    )
    # 数据维护：持仓日线采集（15:20 赶在 16:00 收市后报告前拿到当日收盘价）
    scheduler.add_job(
        _data_maintenance,
        CronTrigger(hour=15, minute=20, timezone=SHANGHAI),
        id="data_maintenance",
    )
    # 建议评价回填：收市后报告（16:00）完成后，评价观察窗口已过的建议
    scheduler.add_job(
        _review_scan,
        CronTrigger(hour=16, minute=30, timezone=SHANGHAI),
        id="review",
    )
    # —— 市场环境（ADR-0014 / 5_DATA §13.5；非交易日在执行器侧过滤） ——
    def _market_env_intraday() -> None:
        _enqueue_market_env_intraday(engine, settings)

    def _market_env_eod() -> None:
        _enqueue_stub(JobType.MARKET_ENV_EOD, engine, settings)

    def _overseas_morning() -> None:
        _enqueue_stub(JobType.OVERSEAS_MORNING, engine, settings)

    scheduler.add_job(
        _market_env_intraday,
        CronTrigger(day_of_week="mon-fri", hour="9-14", minute="*/5", timezone=SHANGHAI),
        id="market_env_intraday",
    )
    # 15:00 收盘时点单独入队（与 9-14 点的 */5 覆盖衔接）
    scheduler.add_job(
        _market_env_intraday,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=0, timezone=SHANGHAI),
        id="market_env_intraday_close",
    )
    scheduler.add_job(
        _market_env_eod,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=25, timezone=SHANGHAI),
        id="market_env_eod",
    )
    scheduler.add_job(
        _overseas_morning,
        CronTrigger(day_of_week="mon-fri", hour=8, minute=10, timezone=SHANGHAI),
        id="overseas_morning",
    )
    return scheduler
