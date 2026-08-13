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
from wws_adviser.infrastructure.data_sources.stub_bar import StubBarProvider
from wws_adviser.infrastructure.data_sources.stub_document import StubDocumentProvider
from wws_adviser.infrastructure.data_sources.stub_nav import StubNAVProvider
from wws_adviser.infrastructure.data_sources.stub_quote import StubQuoteProvider
from wws_adviser.infrastructure.models.stub_model import StubModelPort
from wws_adviser.infrastructure.notifications.stub_notifier import StubNotifierPort
from wws_adviser.infrastructure.storage.local_object_store import LocalObjectStore

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
        # getattr 规避 attr-defined 检查：fcntl 是 unix-only，typeshed stub 在 Linux/Windows
        # 加载行为不同（Linux 加载→attr 已知，Windows 不加载→attr 未知），用 getattr 统一为 Any。
        _flock = getattr(fcntl, "flock")  # noqa: B009
        _flock(lock_file.fileno(), getattr(fcntl, "LOCK_EX") | getattr(fcntl, "LOCK_NB"))  # noqa: B009
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
    # 端口适配器（唯一构造点，见 1_REPO_STRUCTURE §5）。行情数据源按配置选 akshare/stub；
    # akshare 为 optional extra，适配器模块懒加载 akshare（未装也能导入，调用时才需）。
    if settings.market_data_source == "akshare":
        from wws_adviser.infrastructure.data_sources.akshare_bar import AKShareBarProvider
        from wws_adviser.infrastructure.data_sources.akshare_nav import AKShareNAVProvider
        from wws_adviser.infrastructure.data_sources.akshare_quote import AKShareQuoteProvider

        app.state.quote_provider = AKShareQuoteProvider(env=settings.env)
        app.state.bar_provider = AKShareBarProvider(env=settings.env)
        app.state.nav_provider = AKShareNAVProvider(env=settings.env)
        _logger.info("行情数据源：akshare（真实调用需安装 optional extra）")
    else:
        app.state.quote_provider = StubQuoteProvider(env=settings.env)
        app.state.bar_provider = StubBarProvider(env=settings.env)
        app.state.nav_provider = StubNAVProvider(env=settings.env)
    app.state.document_provider = StubDocumentProvider(env=settings.env)
    app.state.model_port = StubModelPort(env=settings.env)
    app.state.notifier = StubNotifierPort(env=settings.env)
    app.state.object_store = LocalObjectStore(settings.data_dir)
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
