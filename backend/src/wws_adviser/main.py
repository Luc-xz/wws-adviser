"""应用入口。

lifespan 顺序（见 1_REPO_STRUCTURE.md §5、§7）：
    加载配置 → 结构化日志 → 单 worker 守卫 → 数据目录可写 → engine/session → scheduler 文件锁
迁移版本严格校验留给波5；Phase 0 由 CI migrate-check 保证空库可建、由 /health/ready 报告迁移状态。
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import IO

from fastapi import FastAPI

from wws_adviser.api.app import create_app
from wws_adviser.core.config import Settings, load_settings
from wws_adviser.core.db import create_app_engine, make_session_factory
from wws_adviser.core.logging import setup_logging
from wws_adviser.core.scheduler import create_scheduler
from wws_adviser.core.worker_guard import enforce_single_worker

_logger = logging.getLogger(__name__)


def acquire_scheduler_lock(settings: Settings) -> IO[str] | None:
    """非阻塞获取 scheduler 文件锁；失败/平台不支持仅告警，不阻断 API。

    文件锁不是唯一正确性来源——最终防线是 DB 唯一约束（1_REPO_STRUCTURE.md §7）。
    """
    settings.locks_dir.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl  # unix-only
    except ImportError:
        _logger.warning(
            "平台无 fcntl（如 Windows），跳过 scheduler 文件锁；"
            "正确性以 DB 唯一约束为最终防线"
        )
        return None
    lock_file = open(settings.scheduler_lock_path, "w")  # noqa: SIM115
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
        return lock_file
    except OSError:
        _logger.warning("scheduler.lock 已被持有，不启动调度线程（API 继续服务）")
        lock_file.close()
        return None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    enforce_single_worker(settings)  # prod 多 worker 抛 MultiWorkerError，阻止启动
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_app_engine(settings)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.scheduler_lock = acquire_scheduler_lock(settings)
    scheduler = None
    if app.state.scheduler_lock is not None:
        scheduler = create_scheduler(engine, settings)
        scheduler.start()
        app.state.scheduler = scheduler
        _logger.info("APScheduler 已启动（仅入队 job_runs，不执行业务）")
    else:
        _logger.warning("未获 scheduler 锁，APScheduler 未启动（API 继续服务）")
    _logger.info("WWS Adviser 启动完成（env=%s）", settings.env)
    yield
    # 优雅关闭：先停 scheduler（不等待长任务，长任务靠 lease 过期重领），再释放锁
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    scheduler_lock: IO[str] | None = getattr(app.state, "scheduler_lock", None)
    if scheduler_lock is not None:
        scheduler_lock.close()
    engine.dispose()


settings = load_settings()
setup_logging(settings.log_level)
app = create_app(settings, lifespan=lifespan)
