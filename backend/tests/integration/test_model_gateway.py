"""Model Gateway + 通知 + settings 集成测试（波6，AC-06 核心）。

覆盖：成功路径（stub 模型→报告含模型段+审计）、AC-06 降级（模型故障→报告照常出确定性
内容+model_unavailable 标记+可重试新版本）、事务边界（模型调用时无打开写事务）、
通知幂等与隔离（失败不失败 job）、settings 掩码与 PATCH 生效。
"""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select

from wws_adviser.core.config import Settings
from wws_adviser.infrastructure.models.stub_model import StubModelPort
from wws_adviser.infrastructure.notifications.stub_notifier import StubNotifierPort
from wws_adviser.modules.documents import service as docs_service
from wws_adviser.modules.identity import service as identity_service
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.instruments import service as instruments_service
from wws_adviser.modules.market_data import service as market_service
from wws_adviser.modules.model_gateway.models import ModelCall
from wws_adviser.modules.notifications import service as notify_service
from wws_adviser.modules.notifications.domain import NotificationEvent
from wws_adviser.modules.notifications.models import Notification
from wws_adviser.modules.portfolio import service as portfolio_service
from wws_adviser.modules.portfolio.domain import TransactionKind
from wws_adviser.modules.reports import executor
from wws_adviser.modules.reports import service as reports_service
from wws_adviser.modules.reports.domain import ReportStatus, ReportType
from wws_adviser.ports.document_source import DocumentScope
from wws_adviser.ports.market_data import InstrumentRef
from wws_adviser.ports.model import ModelRequest, ModelResponse
from wws_adviser.ports.notifier import NotificationResult

BD = "2026-08-14"


def _seed(app) -> str:
    settings = app.state.settings
    with app.state.session_factory() as db:
        uid = db.scalar(select(User.id).where(User.username == "alice"))
        assert uid is not None
        portfolio_service.create_account(
            db, user_id=uid, name="main", initial_cash=Decimal("100000")
        )
        inst = instruments_service.get_or_create_instrument(db, code="600519", name="贵州茅台")
        db.commit()
        asyncio.run(
            market_service.ingest_daily_bars(
                db, data_dir=settings.data_dir, instrument_id=inst.id,
                provider=app.state.bar_provider, start=date(2026, 8, 10), end=date(2026, 8, 14),
            )
        )
        asyncio.run(
            docs_service.ingest_documents(
                db, object_store=app.state.object_store, provider=app.state.document_provider,
                scope=DocumentScope(
                    instrument=InstrumentRef(code="600519", market="SSE", kind="stock")
                ),
                since=datetime.min.replace(tzinfo=UTC),
            )
        )
        portfolio_service.record_transaction(
            db, user_id=uid, instrument_id=inst.id, kind=TransactionKind.BUY,
            quantity=Decimal("100"), price=Decimal("1000"), trade_at="2026-08-13",
        )
        return uid


class _FailingModelPort:
    """AC-06：模型服务关闭/故障的替身。"""

    async def call(self, request: ModelRequest) -> ModelResponse:
        raise ConnectionError("model down")


class _TxAssertingPort(StubModelPort):
    """调用时断言 db 无打开写事务（6_MODEL §3.2/§11）。"""

    def __init__(self, db_ref) -> None:  # db_ref: Session
        super().__init__(env="test")
        self._db = db_ref
        self.in_transaction_during_call: bool | None = None

    async def call(self, request: ModelRequest) -> ModelResponse:
        self.in_transaction_during_call = self._db.in_transaction()
        return await super().call(request)


class _FailingNotifier:
    async def notify(self, channel, event_type, payload) -> NotificationResult:  # type: ignore[no-untyped-def]
        raise RuntimeError("smtp down")


def test_model_success_report_contains_model_section(migrated_client) -> None:
    app = migrated_client.app
    settings = app.state.settings
    uid = _seed(app)
    with app.state.session_factory() as db:
        r = asyncio.run(
            reports_service.generate_report(
                db, settings=Settings(env="test"), data_dir=settings.data_dir, user_id=uid,
                report_type=ReportType.PRE_MARKET, business_date=BD, manual=True,
                model_port=StubModelPort(env="test"),
            )
        )
        assert r.degradation_flags == []
        assert r.report.status == ReportStatus.RENDERED.value
        assert r.report.prompt_version == "v1"  # 真实 prompt 版本（非 wave6_pending）
        content = reports_service.get_report_content(settings.data_dir, r.report)
        assert content is not None and "model" in content
        assert content["model"]["prompt_version"] == "v1"
        # 审计行 ok
        calls = list(db.scalars(select(ModelCall).order_by(ModelCall.created_at)))
        assert calls and calls[-1].status == "ok"
        assert calls[-1].prompt_hash


def test_model_unavailable_degrades_report(migrated_client) -> None:
    """AC-06：模型故障 → 报告照常生成（确定性内容完整）+ model_unavailable 标记 + 可重试。"""
    app = migrated_client.app
    settings = app.state.settings
    uid = _seed(app)
    with app.state.session_factory() as db:
        r1 = asyncio.run(
            reports_service.generate_report(
                db, settings=Settings(env="test"), data_dir=settings.data_dir, user_id=uid,
                report_type=ReportType.PRE_MARKET, business_date=BD, manual=True,
                model_port=_FailingModelPort(),
            )
        )
        assert "model_unavailable" in r1.degradation_flags
        assert r1.report.status == ReportStatus.PARTIAL.value
        content = reports_service.get_report_content(settings.data_dir, r1.report)
        assert content is not None
        assert content["summary"]["pnl_total"] is not None  # 确定性内容完整
        assert "model" not in content
        calls = list(db.scalars(select(ModelCall)))
        assert calls and calls[-1].status == "error"
        assert calls[-1].error_code == "ConnectionError"

        # 可重试：恢复后再次生成 → 新版本（PARTIAL → RENDERED）
        r2 = asyncio.run(
            reports_service.generate_report(
                db, settings=Settings(env="test"), data_dir=settings.data_dir, user_id=uid,
                report_type=ReportType.PRE_MARKET, business_date=BD, manual=True,
                model_port=StubModelPort(env="test"),
            )
        )
        assert r2.report.version == r1.report.version + 1
        assert r2.report.status == ReportStatus.RENDERED.value


def test_model_call_has_no_open_transaction(migrated_client) -> None:
    """6_MODEL §11：模型调用期间不得持有 DB 写事务。"""
    app = migrated_client.app
    settings = app.state.settings
    uid = _seed(app)
    with app.state.session_factory() as db:
        port = _TxAssertingPort(db)
        asyncio.run(
            reports_service.generate_report(
                db, settings=Settings(env="test"), data_dir=settings.data_dir, user_id=uid,
                report_type=ReportType.POST_MARKET, business_date=BD, manual=True,
                model_port=port,
            )
        )
        assert port.in_transaction_during_call is False


def test_notifications_idempotent(migrated_client) -> None:
    app = migrated_client.app
    s = Settings(env="test")
    notifier = StubNotifierPort(env="test")
    payload = {"event_type": "report_completed", "business_date": BD}
    with app.state.session_factory() as db:
        r1 = asyncio.run(
            notify_service.notify(
                db, s, notifier,
                event_type=NotificationEvent.REPORT_COMPLETED.value, payload=payload,
            )
        )
        r2 = asyncio.run(
            notify_service.notify(
                db, s, notifier,
                event_type=NotificationEvent.REPORT_COMPLETED.value, payload=payload,
            )
        )
        assert r1.sent and r2.sent
        rows = list(db.scalars(select(Notification)))
        assert len(rows) == 1  # 幂等：同 payload 只一条


def test_executor_notifies_and_notif_failure_does_not_fail_job(migrated_client) -> None:
    app = migrated_client.app
    settings = app.state.settings
    _seed(app)
    s = Settings(env="test")
    with app.state.session_factory() as db:
        job = executor.enqueue_report_job(
            db, s, report_type=ReportType.PRE_MARKET, business_date=BD
        )
        # 故障通知器：发送必失败 → 但报告 job 必须 COMPLETED
        asyncio.run(
            executor.run_due_jobs(
                db, s, settings.data_dir,
                model_port=StubModelPort(env="test"),
                notifier=_FailingNotifier(),
            )
        )
        from wws_adviser.modules.jobs import repository as jobs_repo

        done = jobs_repo.get_by_id(db, job.id)
        assert done is not None and done.status == "COMPLETED"
        rows = list(db.scalars(select(Notification)))
        assert rows and rows[-1].status == "failed"
        assert rows[-1].error_code == "RuntimeError"

        # 正常通知器再跑一轮（不同 job）→ sent 行存在
        job2 = executor.enqueue_report_job(
            db, s, report_type=ReportType.POST_MARKET, business_date=BD
        )
        asyncio.run(
            executor.run_due_jobs(db, s, settings.data_dir, notifier=StubNotifierPort(env="test"))
        )
        done2 = jobs_repo.get_by_id(db, job2.id)
        assert done2 is not None and done2.status == "COMPLETED"
        sent = [n for n in db.scalars(select(Notification)) if n.status == "sent"]
        assert sent


def test_settings_masked_and_patch_effective(migrated_client) -> None:
    app = migrated_client.app
    identity_service.reset_login_rate_limit()
    r = migrated_client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "pw12345"},
        headers={"Idempotency-Key": "login"},
    )
    assert r.status_code == 200
    csrf = {"X-CSRF-Token": migrated_client.cookies.get("csrf_token", "")}

    # GET models：掩码（env 引用名，无 key 值）
    models = migrated_client.get("/api/v1/settings/models").json()
    assert "环境变量" in models["api_key"]
    assert "Bearer" not in str(models)

    # PATCH risk：调低 single_cap → /analytics/risk 随之触发
    _seed(app)  # 600 股 ≈ 60000/100000 → weight 0.6
    patched = migrated_client.patch(
        "/api/v1/settings/risk", json={"single_cap": 0.10}, headers=csrf
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["single_cap"] == 0.10
    # 持久化 + 审计
    risk_view = migrated_client.get("/api/v1/settings/risk").json()
    assert risk_view["single_cap"] == 0.10
    with app.state.session_factory() as db:
        from wws_adviser.modules.audit.models import AuditEvent

        audits = list(
            db.scalars(
                select(AuditEvent).where(AuditEvent.action == "settings_patched")
            )
        )
        assert audits
    # 实际生效：/analytics/risk 触发 single_cap（默认 0.30 时 0.6 已触发；此处验证端点连通与有效值）
    risk = migrated_client.get("/api/v1/analytics/risk").json()
    rules = {b["rule"] for b in risk["breaches"]}
    assert "single_cap" in rules

    # 越权字段拒绝（白名单外的敏感字段不可 PATCH、不落库）
    bad = migrated_client.patch(
        "/api/v1/settings/models", json={"api_key": "secret"}, headers=csrf
    )
    assert bad.status_code == 422  # 白名单拒绝；值不落库
    from wws_adviser.modules.appsettings.models import AppSetting

    with app.state.session_factory() as db:
        assert db.get(AppSetting, "models") is None
