"""APScheduler 集成：只入队 job_runs，不执行业务（见 6_MODEL §8.1）。

Phase 0 注册 pre_market(08:30)/post_market(16:00) cron trigger，handler 只 enqueue 一个
stub job_run，证明"APScheduler 只入队"边界。真实 job handler 在 Phase 1+ 接报告流水线。
"""

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


def create_scheduler(engine: "Engine", settings: Settings) -> BackgroundScheduler:
    """构建调度器（不启动；由 main.py lifespan start/stop）。"""
    scheduler = BackgroundScheduler(timezone=SHANGHAI)

    def _pre_market() -> None:
        _enqueue_stub(JobType.PRE_MARKET, engine, settings)

    def _post_market() -> None:
        _enqueue_stub(JobType.POST_MARKET, engine, settings)

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
    # 数据维护：持仓日线采集（15:20 赶在 16:00 收市后报告前拿到当日收盘价）
    scheduler.add_job(
        _data_maintenance,
        CronTrigger(hour=15, minute=20, timezone=SHANGHAI),
        id="data_maintenance",
    )
    return scheduler
