"""市场环境批次 B 集成测试：调度任务执行 + API 查询面 + 报告段注入（ADR-0014）。"""

from decimal import Decimal

from wws_adviser.core.config import Settings
from wws_adviser.core.time import business_date
from wws_adviser.infrastructure.market_env.stub_market_env import (
    StubIndexQuoteProvider,
    StubSectorFlowProvider,
)
from wws_adviser.modules.collections.models import SourceHealth
from wws_adviser.modules.identity import service as identity_service
from wws_adviser.modules.jobs import service as jobs_service
from wws_adviser.modules.jobs.domain import JobType
from wws_adviser.modules.jobs.models import JobRun
from wws_adviser.modules.market_env import service as env_service
from wws_adviser.modules.market_env.models import IndexBar, IndexQuote
from wws_adviser.modules.reports import executor as reports_executor
from wws_adviser.modules.reports.domain import render_markdown
from wws_adviser.ports.market_env import SectorKind

# 2026-11-21 为周六（非交易日，无日历记录时 weekday 兜底判定）
_SATURDAY = "2026-11-21"


async def _run_one(db_session, tmp_path, job_type: JobType, business_date: str,
                   scope_key: str = "default") -> JobRun:
    settings = Settings(env="test", data_dir=tmp_path, passkey_rp_id="t", passkey_origin="https://t")
    job = jobs_service.enqueue(
        db_session, settings, job_type=job_type, business_date=business_date, scope_key=scope_key
    )
    await reports_executor.run_due_jobs(db_session, settings, tmp_path)
    return db_session.get(JobRun, job.id)


async def test_market_env_intraday_job_runs_and_records(db_session, tmp_path) -> None:
    job = await _run_one(db_session, tmp_path, JobType.MARKET_ENV_INTRADAY,
                         business_date().isoformat(), scope_key="09:35")
    assert job is not None and job.status == "COMPLETED"
    assert job.result_ref and job.result_ref.startswith("env://q/")
    # 快照 20 项（17 指数 + 3 期货）+ 板块注册与快照（行业 4 + 概念 3 由 stub 提供）
    assert db_session.query(IndexQuote).count() == 20
    health = db_session.get(SourceHealth, "index_quote")
    assert health is not None and health.last_success_at
    assert db_session.get(SourceHealth, "sector_flow") is not None


async def test_market_env_intraday_same_slot_idempotent(db_session, tmp_path) -> None:
    """同日同时间槽重复入队 → 幂等返回既有任务（uq_job_runs_idem，不产生第二个批次）。"""
    settings = Settings(env="test", data_dir=tmp_path, passkey_rp_id="t", passkey_origin="https://t")
    bd = business_date().isoformat()
    j1 = jobs_service.enqueue(db_session, settings, job_type=JobType.MARKET_ENV_INTRADAY,
                              business_date=bd, scope_key="10:00")
    j2 = jobs_service.enqueue(db_session, settings, job_type=JobType.MARKET_ENV_INTRADAY,
                              business_date=bd, scope_key="10:00")
    assert j1.id == j2.id


async def test_market_env_job_skips_non_trading_day(db_session, tmp_path) -> None:
    job = await _run_one(db_session, tmp_path, JobType.OVERSEAS_MORNING, _SATURDAY)
    assert job is not None and job.status == "COMPLETED"
    assert job.result_ref == f"skipped://non_trading_day:{_SATURDAY}"
    assert db_session.query(IndexQuote).count() == 0


async def test_market_env_eod_job_ingests_bars(db_session, tmp_path) -> None:
    job = await _run_one(db_session, tmp_path, JobType.MARKET_ENV_EOD,
                         business_date().isoformat())
    assert job is not None and job.status == "COMPLETED"
    assert job.result_ref and "/bars/" in job.result_ref
    # CN 指数 10 个（海外/期货无日 K）；stub 日 K = 30 天窗口内的工作日数（≥18）
    per_index = len(env_service.repository.list_index_bars(db_session, "cn_sh000001"))
    assert per_index >= 18
    assert db_session.query(IndexBar).count() == 10 * per_index


async def test_overseas_job_quotes_only(db_session, tmp_path) -> None:
    job = await _run_one(db_session, tmp_path, JobType.OVERSEAS_MORNING,
                         business_date().isoformat())
    assert job is not None and job.status == "COMPLETED"
    assert job.result_ref == "env://quotes/20"
    assert db_session.query(IndexBar).count() == 0  # 不采日 K


def test_scheduler_registers_market_env_jobs(tmp_path) -> None:
    from wws_adviser.core.db import create_app_engine
    from wws_adviser.core.scheduler import create_scheduler

    settings = Settings(env="test", data_dir=tmp_path, passkey_rp_id="t", passkey_origin="https://t")
    engine = create_app_engine(settings)
    try:
        scheduler = create_scheduler(engine, settings)
        ids = {job.id for job in scheduler.get_jobs()}
        assert {"market_env_intraday", "market_env_intraday_close", "market_env_eod",
                "overseas_morning"} <= ids
    finally:
        try:
            scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001 — 未 start 的 scheduler shutdown 会抛错，无资源需释放
            pass
        engine.dispose()


# —— 报告段 / 模型上下文 ——


async def test_report_section_and_markdown(db_session) -> None:
    await env_service.ingest_index_quotes(
        db_session, provider=StubIndexQuoteProvider(env="test")
    )
    await env_service.ingest_sector_flows(
        db_session, provider=StubSectorFlowProvider(env="test"), kind=SectorKind.INDUSTRY
    )
    section = env_service.build_report_section(db_session)
    assert section is not None
    assert section["market_turnover"] == "900000000000"
    assert len(section["cn_indices"]) == 10
    assert len(section["futures"]) == 3
    md = render_markdown({"header": {"report_type": "pre_market", "business_date": "2026-11-16"},
                          "summary": {}, "market_env": section})
    assert "## 市场环境" in md
    assert "两市成交额" in md and "9000.00亿" in md
    assert "美股期货(盘前参考)" in md


def test_report_section_none_when_no_data(db_session) -> None:
    assert env_service.build_report_section(db_session) is None


def test_masked_context_optional_market_env() -> None:
    from wws_adviser.modules.model_gateway.domain import build_masked_context

    base = dict(report_type="pre_market", business_date="2026-11-16",
                summary={}, risk=[], positions=[], snapshot_refs={})
    ctx = build_masked_context(**base)
    assert "market_env" not in ctx
    ctx2 = build_masked_context(**base, market_env={"cn_indices": []})
    assert ctx2["market_env"] == {"cn_indices": []}


# —— API 查询面（3_API §3.18） ——


def _login(client) -> None:
    identity_service.reset_login_rate_limit()
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "pw12345"},
        headers={"Idempotency-Key": "login-market-env"},
    )
    assert r.status_code == 200


def test_market_env_api_requires_login(client) -> None:
    assert client.get("/api/v1/market-env/overview").status_code == 401
    assert client.get("/api/v1/market-env/indices").status_code == 401


def test_market_env_overview_and_detail_endpoints(migrated_client) -> None:
    import asyncio

    _login(migrated_client)
    app = migrated_client.app
    with app.state.session_factory() as db:
        asyncio.run(env_service.ingest_index_quotes(
            db, provider=StubIndexQuoteProvider(env="test")
        ))
        asyncio.run(env_service.ingest_sector_flows(
            db, provider=StubSectorFlowProvider(env="test"),
            kind=SectorKind.INDUSTRY,
        ))

    r = migrated_client.get("/api/v1/market-env/overview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["cn_indices"]) == 10
    assert body["market_turnover"] == "900000000000"
    assert body["active_sectors"] and body["net_inflow_top"] and body["net_outflow_top"]
    assert len(body["futures"]) == 3
    assert body["freshness"]["cn_quote_age_seconds"] is not None

    r = migrated_client.get("/api/v1/market-env/indices", params={"group": "futures_us"})
    assert r.status_code == 200
    assert {i["code"] for i in r.json()} == {"fut_es", "fut_nq", "fut_ym"}

    r = migrated_client.get("/api/v1/market-env/indices/cn_sh000001/bars")
    assert r.status_code == 200
    assert r.json()["items"] == []

    r = migrated_client.get("/api/v1/market-env/indices/xx_unknown/bars")
    assert r.status_code == 404

    r = migrated_client.get("/api/v1/market-env/sectors/flows",
                            params={"kind": "industry", "top": 2})
    assert r.status_code == 200
    flows = r.json()
    assert len(flows) == 2
    assert flows[0]["board_name"]  # 中文板块名（sector_boards 反查）
    assert Decimal(flows[0]["net_main_inflow"]) > Decimal(flows[-1]["net_main_inflow"])

    r = migrated_client.get("/api/v1/market-env/sectors/flows", params={"kind": "bad"})
    assert r.status_code == 422
