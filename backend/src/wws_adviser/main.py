"""应用入口。

lifespan 顺序（见 1_REPO_STRUCTURE.md §5、§7）：
    加载配置 → 结构化日志 → 单 worker 守卫 → 数据目录可写 → engine/session → scheduler 文件锁
迁移版本严格校验留给波5；Phase 0 由 CI migrate-check 保证空库可建、由 /health/ready 报告迁移状态。
"""

import logging
import threading
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
from wws_adviser.infrastructure.clock_sntp import measure_clock_skew
from wws_adviser.infrastructure.data_sources.stub_bar import StubBarProvider
from wws_adviser.infrastructure.data_sources.stub_document import StubDocumentProvider
from wws_adviser.infrastructure.data_sources.stub_nav import StubNAVProvider
from wws_adviser.infrastructure.data_sources.stub_quote import StubQuoteProvider
from wws_adviser.infrastructure.models.stub_model import StubModelPort
from wws_adviser.infrastructure.notifications.stub_notifier import StubNotifierPort
from wws_adviser.infrastructure.storage.local_object_store import LocalObjectStore

_logger = logging.getLogger(__name__)


def _build_document_provider(settings: Settings) -> object:
    """文档数据源选源：akshare（需 optional extra，懒加载）或 stub。"""
    if settings.document_source == "akshare":
        from wws_adviser.infrastructure.data_sources.akshare_document import (
            AKShareDocumentProvider,
        )

        _logger.info("文档数据源：akshare（真实调用需安装 optional extra）")
        return AKShareDocumentProvider(env=settings.env)
    return StubDocumentProvider(env=settings.env)


def _build_model_port(settings: Settings) -> object:
    """模型选源：openai-compatible（httpx，凭据经 env 引用）或 stub。"""
    if settings.model_source == "openai" and settings.model_base_url:
        from wws_adviser.infrastructure.models.openai_model import OpenAICompatibleModelPort

        _logger.info("模型源：openai-compatible %s", settings.model_base_url)
        return OpenAICompatibleModelPort(
            base_url=settings.model_base_url,
            model_name=settings.model_name,
            key_ref=settings.model_api_key_ref,
            timeout=settings.model_timeout,
            temperature=settings.model_temperature,
            env=settings.env,
        )
    return StubModelPort(env=settings.env)


def _build_notifier(settings: Settings) -> object:
    """通知选源：smtp（stdlib smtplib，凭据经 env 引用）或 stub。"""
    if settings.notifier_source == "smtp" and settings.smtp_host:
        from wws_adviser.infrastructure.notifications.smtp_notifier import SMTPNotifierPort

        _logger.info("通知渠道：smtp %s:%s", settings.smtp_host, settings.smtp_port)
        return SMTPNotifierPort(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user,
            key_ref=settings.smtp_key_ref,
            from_addr=settings.smtp_from_addr,
            to_addr=settings.smtp_to_addr,
            use_tls=settings.smtp_use_tls,
            env=settings.env,
        )
    return StubNotifierPort(env=settings.env)


def _start_executor_worker(app: FastAPI, settings: Settings) -> threading.Thread:
    """执行器常驻线程（6_MODEL §8.1：APScheduler 只入队，执行器领取 job_runs）。

    持 scheduler 锁的进程启动（单实例去重）；循环领取报告任务并执行（含通知）。
    测试环境不启动（tests 直接调用 run_due_jobs）。
    """
    import asyncio

    from wws_adviser.modules.reports import executor as reports_executor

    stop_event = threading.Event()

    def loop() -> None:
        while not stop_event.wait(settings.executor_poll_seconds):
            try:
                with app.state.session_factory() as db:
                    asyncio.run(
                        reports_executor.run_due_jobs(
                            db,
                            settings,
                            settings.data_dir,
                            model_port=getattr(app.state, "model_port", None),
                            notifier=getattr(app.state, "notifier", None),
                        )
                    )
            except Exception:  # noqa: BLE001 — 工作线程边界：单轮失败仅记日志续跑
                _logger.exception("执行器单轮处理失败（将继续）")

    t = threading.Thread(target=loop, name="report-executor", daemon=True)
    t.start()
    _logger.info("执行器线程已启动（每 %ss 轮询 job_runs）", settings.executor_poll_seconds)
    stop_events = getattr(app.state, "_executor_stops", [])
    stop_events.append(stop_event)
    app.state._executor_stops = stop_events  # noqa: SLF001 — lifespan 关闭信令
    return t


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
    app.state.document_provider = _build_document_provider(settings)
    app.state.model_port = _build_model_port(settings)
    app.state.notifier = _build_notifier(settings)
    app.state.object_store = LocalObjectStore(settings.data_dir)
    # clock-skew 校验（技术债清理）：偏移失真会让新鲜度门禁误判；失败降级 unknown。
    # test 环境不发起真实 SNTP（同执行器线程约定）。
    if settings.env != "test":
        skew = await measure_clock_skew(
            settings.clock_skew_ntp_host,
            threshold_seconds=settings.clock_skew_threshold_seconds,
        )
        if skew.status == "skew":
            _logger.warning(
                "系统时钟偏移 %+.3fs 超阈值 %ss——行情/报告新鲜度判定可能失真",
                skew.offset_seconds or 0.0,
                skew.threshold_seconds,
            )
        elif skew.status == "unknown":
            _logger.warning(
                "SNTP 时钟校验不可用（host=%s），偏移未知", settings.clock_skew_ntp_host
            )
    else:
        from wws_adviser.infrastructure.clock_sntp import ClockSkewReport

        skew = ClockSkewReport(
            offset_seconds=None, threshold_seconds=settings.clock_skew_threshold_seconds
        )
    app.state.clock_skew = skew
    app.state.scheduler_lock = acquire_scheduler_lock(settings)
    scheduler = None
    executor_started = False
    if app.state.scheduler_lock is not None:
        scheduler = create_scheduler(engine, settings)
        scheduler.start()
        app.state.scheduler = scheduler
        _logger.info("APScheduler 已启动（仅入队 job_runs，不执行业务）")
        if settings.env != "test":
            _start_executor_worker(app, settings)  # 领取执行（报告+通知），波8 常驻
            executor_started = True
    else:
        _logger.warning("未获 scheduler 锁，APScheduler 未启动（API 继续服务）")
    _logger.info("WWS Adviser 启动完成（env=%s）", settings.env)
    yield
    # 优雅关闭：先停执行器与 scheduler（长任务靠 lease 过期重领），再释放锁
    if executor_started:
        for stop_event in getattr(app.state, "_executor_stops", []):
            stop_event.set()
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    scheduler_lock: IO[str] | None = getattr(app.state, "scheduler_lock", None)
    if scheduler_lock is not None:
        scheduler_lock.close()
    engine.dispose()


settings = load_settings()
setup_logging(settings.log_level)
app = create_app(settings, lifespan=lifespan)
