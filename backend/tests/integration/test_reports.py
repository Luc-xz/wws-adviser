"""报告流水线集成测试（波5）：幂等/完整路径/降级/版本递进/executor/HTTP。

对应 6_MODEL §11 不变量：同 (type,date) 不产生重复报告；PARTIAL 补算新版本旧版保留；
executor 领取执行 job_runs；状态以 SQLite 为准。
"""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select

from wws_adviser.core.config import Settings
from wws_adviser.modules.documents import service as docs_service
from wws_adviser.modules.identity import service as identity_service
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.instruments import service as instruments_service
from wws_adviser.modules.jobs.domain import JobStatus
from wws_adviser.modules.market_data import service as market_service
from wws_adviser.modules.portfolio import service as portfolio_service
from wws_adviser.modules.portfolio.domain import TransactionKind
from wws_adviser.modules.reports import executor
from wws_adviser.modules.reports import service as reports_service
from wws_adviser.modules.reports.domain import ReportStatus, ReportType
from wws_adviser.ports.document_source import DocumentScope
from wws_adviser.ports.market_data import InstrumentRef


def _login(client) -> None:
    identity_service.reset_login_rate_limit()
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "pw12345"},
        headers={"Idempotency-Key": "login"},
    )
    assert r.status_code == 200


def _csrf(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("csrf_token", "")}


def _user_id(db) -> str:
    uid = db.scalar(select(User.id).where(User.username == "alice"))
    assert uid is not None
    return uid


def _seed_full(app, *, with_market: bool = True, with_docs: bool = True) -> str:
    """建账户+标的+交易（+可选行情/公告）。返回 instrument_id。"""
    settings = app.state.settings
    with app.state.session_factory() as db:
        uid = _user_id(db)
        portfolio_service.create_account(
            db, user_id=uid, name="main", initial_cash=Decimal("100000")
        )
        inst = instruments_service.get_or_create_instrument(db, code="600519", name="贵州茅台")
        db.commit()
        if with_market:
            asyncio.run(
                market_service.ingest_daily_bars(
                    db, data_dir=settings.data_dir, instrument_id=inst.id,
                    provider=app.state.bar_provider,
                    start=date(2026, 8, 10), end=date(2026, 8, 14),
                )
            )
        if with_docs:
            asyncio.run(
                docs_service.ingest_documents(
                    db,
                    object_store=app.state.object_store,
                    provider=app.state.document_provider,
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
        return inst.id


BD = "2026-08-14"


def test_generate_complete_report_idempotent(migrated_client) -> None:
    app = migrated_client.app
    settings = app.state.settings
    _seed_full(app)
    with app.state.session_factory() as db:
        uid = _user_id(db)
        s = Settings(env="test")

        r1 = asyncio.run(reports_service.generate_report(
            db, settings=s, data_dir=settings.data_dir, user_id=uid,
            report_type=ReportType.PRE_MARKET, business_date=BD, manual=True,
        ))
        assert r1.report.status == ReportStatus.RENDERED.value
        assert r1.degradation_flags == []
        # 文件三件套落盘
        assert (settings.data_dir / r1.report.manifest_path).exists()
        assert (settings.data_dir / r1.report.content_json_path).exists()
        assert (settings.data_dir / r1.report.content_md_path).exists()

        # 幂等：二次生成返回同一报告（RENDERED → 不重复）
        r2 = asyncio.run(reports_service.generate_report(
            db, settings=s, data_dir=settings.data_dir, user_id=uid,
            report_type=ReportType.PRE_MARKET, business_date=BD, manual=True,
        ))
        assert r2.report.id == r1.report.id
        assert r2.report.version == r1.report.version
        # 冻结快照唯一（同 purpose 不重复冻结）
        assert r1.report.analysis_snapshot_id == r2.report.analysis_snapshot_id


def test_generate_degraded_without_market_data(migrated_client) -> None:
    """AC-02/AC-04：缺行情 → PARTIAL + market_data_missing；仍含确定性摘要。"""
    app = migrated_client.app
    settings = app.state.settings
    _seed_full(app, with_market=False)  # 无行情（有公告）
    with app.state.session_factory() as db:
        uid = _user_id(db)
        r = asyncio.run(reports_service.generate_report(
            db, settings=Settings(env="test"), data_dir=settings.data_dir, user_id=uid,
            report_type=ReportType.POST_MARKET, business_date=BD, manual=True,
        ))
        assert r.report.status == ReportStatus.PARTIAL.value
        assert "market_data_missing" in r.degradation_flags
        content = reports_service.get_report_content(settings.data_dir, r.report)
        assert content is not None
        # 仍含确定性摘要（AC-04：数据未就绪时不错误计算，但不缺席确定性内容）
        assert content["summary"]["pnl_total"] is not None


def test_generate_degraded_without_documents(migrated_client) -> None:
    """AC-02：公告源失败/无公告 → documents_unavailable 标记。"""
    app = migrated_client.app
    settings = app.state.settings
    _seed_full(app, with_docs=False)  # 有行情、无公告
    with app.state.session_factory() as db:
        uid = _user_id(db)
        r = asyncio.run(reports_service.generate_report(
            db, settings=Settings(env="test"), data_dir=settings.data_dir, user_id=uid,
            report_type=ReportType.PRE_MARKET, business_date=BD, manual=True,
        ))
        assert "documents_unavailable" in r.degradation_flags
        assert r.report.status == ReportStatus.PARTIAL.value


def test_partial_upgrades_to_new_version(migrated_client) -> None:
    """PARTIAL → 补数据再生成 → version+1，旧版保留（6_MODEL §6）。"""
    app = migrated_client.app
    settings = app.state.settings
    _seed_full(app, with_docs=False)  # 先无公告 → PARTIAL v1
    with app.state.session_factory() as db:
        uid = _user_id(db)
        s = Settings(env="test")
        r1 = asyncio.run(reports_service.generate_report(
            db, settings=s, data_dir=settings.data_dir, user_id=uid,
            report_type=ReportType.PRE_MARKET, business_date=BD, manual=True,
        ))
        assert r1.report.status == ReportStatus.PARTIAL.value
        assert r1.report.version == 1

        # 补公告（ingest_documents 需在独立会话提交后再生成）
        db.close()
    with app.state.session_factory() as db:
        asyncio.run(
            docs_service.ingest_documents(
                db, object_store=app.state.object_store, provider=app.state.document_provider,
                scope=DocumentScope(
                    instrument=InstrumentRef(code="600519", market="SSE", kind="stock")
                ),
                since=datetime.min.replace(tzinfo=UTC),
            )
        )
    with app.state.session_factory() as db:
        uid2 = _user_id(db)
        r2 = asyncio.run(reports_service.generate_report(
            db, settings=Settings(env="test"), data_dir=settings.data_dir, user_id=uid2,
            report_type=ReportType.PRE_MARKET, business_date=BD, manual=True,
        ))
        assert r2.report.version == 2  # 新版本
        assert r2.report.status == ReportStatus.RENDERED.value
        assert r2.report.id != r1.report.id  # 旧版保留（不同行）
        from wws_adviser.modules.reports import repository as reports_repo

        assert reports_repo.get_report(db, r1.report.id) is not None


def test_executor_runs_enqueued_job(migrated_client) -> None:
    """enqueue → run_due_jobs 领取执行 → job COMPLETED + 报告产出。"""
    app = migrated_client.app
    settings = app.state.settings
    _seed_full(app)
    with app.state.session_factory() as db:
        job = executor.enqueue_report_job(
            db, Settings(env="test"), report_type=ReportType.PRE_MARKET, business_date=BD
        )
        assert job.status == JobStatus.PENDING.value
        n = asyncio.run(executor.run_due_jobs(db, Settings(env="test"), settings.data_dir))
        assert n >= 1
        from wws_adviser.modules.jobs import repository as jobs_repo

        done = jobs_repo.get_by_id(db, job.id)
        assert done is not None
        assert done.status == JobStatus.COMPLETED.value
        assert (done.result_ref or "").startswith("report://")


def test_executor_skips_pre_market_on_non_trading_day(migrated_client) -> None:
    """非交易日：PRE_MARKET 自动生成跳过（job 正常完成，result_ref=skipped://）。"""
    app = migrated_client.app
    settings = app.state.settings
    _seed_full(app)
    NON_TD = "2026-08-16"  # 周日
    with app.state.session_factory() as db:
        from wws_adviser.modules.market_data import repository as md_repo
        from wws_adviser.modules.market_data.models import TradingCalendar

        md_repo.upsert_calendar_row(
            db, TradingCalendar(date=NON_TD, market="SSE", is_trading_day=False)
        )
        db.commit()
        job = executor.enqueue_report_job(
            db, Settings(env="test"), report_type=ReportType.PRE_MARKET, business_date=NON_TD
        )
        asyncio.run(executor.run_due_jobs(db, Settings(env="test"), settings.data_dir))
        from wws_adviser.modules.jobs import repository as jobs_repo

        done = jobs_repo.get_by_id(db, job.id)
        assert done is not None
        assert done.status == JobStatus.COMPLETED.value
        assert (done.result_ref or "").startswith("skipped://")
        # 手动触发则放行（manual=True）
        r = asyncio.run(reports_service.generate_report(
            db, settings=Settings(env="test"), data_dir=settings.data_dir,
            user_id=_user_id(db), report_type=ReportType.PRE_MARKET,
            business_date=NON_TD, manual=True,
        ))
        assert r.report.status in (ReportStatus.RENDERED.value, ReportStatus.PARTIAL.value)


def test_reports_http_endpoints(migrated_client) -> None:
    app = migrated_client.app
    _seed_full(app)
    _login(migrated_client)
    csrf = _csrf(migrated_client)

    gen = migrated_client.post(
        "/api/v1/reports/generate",
        json={"report_type": "pre_market", "business_date": BD},
        headers={**csrf, "Idempotency-Key": "gen1"},
    )
    assert gen.status_code == 200, gen.text
    body = gen.json()
    assert body["job_run_id"]
    assert body["report"]["status"] in ("RENDERED", "PARTIAL")
    assert body["report"]["content"]["header"]["report_type"] == "pre_market"
    report_id = body["report"]["id"]

    # 缺 Idempotency-Key（带 CSRF）→ 400；无 CSRF 则 403（中间件先行）
    no_csrf = migrated_client.post(
        "/api/v1/reports/generate", json={"report_type": "pre_market", "business_date": BD}
    )
    assert no_csrf.status_code == 403
    no_key = migrated_client.post(
        "/api/v1/reports/generate",
        json={"report_type": "pre_market", "business_date": BD},
        headers=csrf,
    )
    assert no_key.status_code == 400

    listing = migrated_client.get("/api/v1/reports", params={"business_date": BD}).json()
    assert any(i["id"] == report_id for i in listing["items"])

    detail = migrated_client.get(f"/api/v1/reports/{report_id}").json()
    assert detail["content"]["header"]["business_date"] == BD

    md = migrated_client.get(f"/api/v1/reports/{report_id}/render", params={"format": "md"})
    assert md.status_code == 200
    assert "开市前报告" in md.text

    job = migrated_client.get(f"/api/v1/jobs/{body['job_run_id']}").json()
    assert job["id"] == body["job_run_id"]
