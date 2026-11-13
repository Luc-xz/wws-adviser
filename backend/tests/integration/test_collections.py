"""采集可观测性测试（5_DATA §12）：source_health/ingest_items 写入、jobs 列表/聚合、
/api/v1/jobs* 与 /api/v1/collections/* 端点（stub 闭环；采集监控面板波1）。"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from wws_adviser.core.config import Settings
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.infrastructure.data_sources.stub_bar import StubBarProvider
from wws_adviser.infrastructure.data_sources.stub_document import StubDocumentProvider
from wws_adviser.infrastructure.storage.local_object_store import LocalObjectStore
from wws_adviser.modules.collections import service as collections_service
from wws_adviser.modules.collections.models import IngestItem, SourceHealth
from wws_adviser.modules.documents import service as docs_service
from wws_adviser.modules.identity import service as identity_service
from wws_adviser.modules.instruments import service as instruments_service
from wws_adviser.modules.jobs import service as jobs_service
from wws_adviser.modules.market_data import service as md_service
from wws_adviser.ports.document_source import DocumentScope
from wws_adviser.ports.market_data import InstrumentRef, RawDataset, SourceDelayClass


def _settings(tmp_path) -> Settings:
    return Settings(
        env="test", data_dir=tmp_path, passkey_rp_id="test.local", passkey_origin="https://test.local"
    )


class _BoomBarProvider:
    """源不可用 stub（5_DATA §9 契约测试方法：注入失败路径）。"""

    async def fetch_daily_bars(self, instrument, start: date, end: date) -> RawDataset:
        raise RuntimeError("source down")


class _EmptyBarProvider:
    """源返回空数据集（主备源均未命中）。"""

    async def fetch_daily_bars(self, instrument, start: date, end: date) -> RawDataset:
        now = now_utc_iso()
        return RawDataset(
            source="stub",
            source_url="stub://empty",
            market_time=now,
            fetched_at=now,
            received_at=now,
            source_delay_class=SourceDelayClass.END_OF_DAY,
        )


def _items_of(db, run_id: str) -> list[IngestItem]:
    return list(db.scalars(select(IngestItem).where(IngestItem.run_id == run_id)).all())


def _overview_by_cat(db, settings) -> dict:
    sources = collections_service.health_overview(db, settings)["sources"]
    return {s["category"]: s for s in sources}


# —— 服务层：日线采集观测 ——


async def test_ingest_bars_records_health_and_item(db_session, tmp_path) -> None:
    inst = instruments_service.get_or_create_instrument(db_session, code="600519", name="贵州茅台")
    db_session.commit()
    # run_id 必须指向真实 job_runs 行（ingest_items.run_id FK）——对齐生产路径
    run_id = jobs_service.start_manual_run(
        db_session, _settings(tmp_path), job_type="ingest_manual",
        business_date="2026-11-13", scope_key="bars:600519",
    ).id

    result = await md_service.ingest_daily_bars(
        db_session, data_dir=tmp_path, instrument_id=inst.id,
        provider=StubBarProvider(env="test"),
        start=date(2026, 8, 10), end=date(2026, 8, 14), run_id=run_id,
    )
    assert result.quality == "OK"

    health = db_session.get(SourceHealth, "bar")
    assert health is not None
    assert health.consecutive_failures == 0
    assert health.last_success_at is not None

    items = _items_of(db_session, run_id)
    assert len(items) == 1
    it = items[0]
    assert (it.category, it.status, it.action) == ("bar", "OK", "ingested")
    assert it.rows_written == result.ingested
    assert it.data_ref == f"market:{inst.id}:2026-08-10-2026-08-14"
    assert it.duration_ms is not None and it.duration_ms >= 0
    assert "600519" in it.display_name


async def test_ingest_bars_failure_records_observation(db_session, tmp_path) -> None:
    inst = instruments_service.get_or_create_instrument(db_session, code="600519")
    db_session.commit()
    run_id = jobs_service.start_manual_run(
        db_session, _settings(tmp_path), job_type="ingest_manual",
        business_date="2026-11-13", scope_key="bars:600519",
    ).id

    with pytest.raises(RuntimeError, match="source down"):
        await md_service.ingest_daily_bars(
            db_session, data_dir=tmp_path, instrument_id=inst.id,
            provider=_BoomBarProvider(),
            start=date(2026, 8, 10), end=date(2026, 8, 14), run_id=run_id,
        )

    health = db_session.get(SourceHealth, "bar")
    assert health is not None
    assert health.consecutive_failures == 1
    assert health.last_error_code == "RuntimeError"

    items = _items_of(db_session, run_id)
    assert len(items) == 1
    assert items[0].status == "FAILED"
    assert items[0].error_code == "RuntimeError"


async def test_ingest_bars_no_data_records_missing(db_session, tmp_path) -> None:
    inst = instruments_service.get_or_create_instrument(db_session, code="600519")
    db_session.commit()

    result = await md_service.ingest_daily_bars(
        db_session, data_dir=tmp_path, instrument_id=inst.id,
        provider=_EmptyBarProvider(),
        start=date(2026, 8, 10), end=date(2026, 8, 14),
    )
    assert result.quality == "MISSING"
    assert result.ingested == 0

    health = db_session.get(SourceHealth, "bar")
    assert health is not None
    assert health.last_error_code == "NO_DATA"
    items = list(db_session.scalars(select(IngestItem).where(IngestItem.category == "bar")).all())
    assert len(items) == 1
    assert items[0].action == "failed" and items[0].error_code == "NO_DATA"


# —— 服务层：源健康派生 + 新闻缺口 ——


def test_health_overview_derivation_and_news_gap(db_session, tmp_path) -> None:
    settings = _settings(tmp_path)

    overview = collections_service.health_overview(db_session, settings)
    by_cat = {s["category"]: s for s in overview["sources"]}
    # 无任何记录：全部 no_data；news 恒为未配置真实源（FR-DATA-005 仅 stub）
    assert by_cat["bar"]["status"] == "no_data"
    assert by_cat["news"]["status"] == "no_data"
    assert by_cat["news"]["configured"] is False
    assert by_cat["bar"]["configured"] is True

    # 连败派生：1 次 → degraded（默认阈值 1）；累计 5 次 → unavailable
    collections_service.record_source_failure(
        db_session, "bar", error_code="E", error_message="x"
    )
    db_session.commit()
    by_cat = _overview_by_cat(db_session, settings)
    assert by_cat["bar"]["status"] == "degraded"
    assert by_cat["bar"]["consecutive_failures"] == 1

    for _ in range(4):
        collections_service.record_source_failure(
            db_session, "bar", error_code="E", error_message="x"
        )
    db_session.commit()
    by_cat = _overview_by_cat(db_session, settings)
    assert by_cat["bar"]["status"] == "unavailable"

    # 成功清零 → ok
    collections_service.record_source_success(db_session, "bar")
    db_session.commit()
    by_cat = _overview_by_cat(db_session, settings)
    assert by_cat["bar"]["status"] == "ok"
    assert by_cat["bar"]["consecutive_failures"] == 0


# —— 服务层：公告条目（ingested / skipped） ——


async def test_documents_ingest_items_and_skip(db_session, tmp_path) -> None:
    store = LocalObjectStore(tmp_path)
    provider = StubDocumentProvider(env="test")
    instruments_service.get_or_create_instrument(db_session, code="600519")
    db_session.commit()
    scope = DocumentScope(instrument=InstrumentRef(code="600519", market="SSE", kind="stock"))
    since = datetime.min.replace(tzinfo=UTC)

    run1 = jobs_service.start_manual_run(
        db_session, _settings(tmp_path), job_type="ingest_manual",
        business_date="2026-11-13", scope_key="docs:600519",
    ).id
    await docs_service.ingest_documents(
        db_session, object_store=store, provider=provider, scope=scope, since=since, run_id=run1,
    )
    items1 = _items_of(db_session, run1)
    assert len(items1) == 1
    assert items1[0].category == "document"
    assert (items1[0].action, items1[0].status) == ("ingested", "OK")
    assert items1[0].data_ref is not None and items1[0].data_ref.startswith("doc:")

    # 同标的二次采集 → sha256 命中 → SKIPPED 条目
    run2 = jobs_service.start_manual_run(
        db_session, _settings(tmp_path), job_type="ingest_manual",
        business_date="2026-11-13", scope_key="docs:600519:2",
    ).id
    r2 = await docs_service.ingest_documents(
        db_session, object_store=store, provider=provider, scope=scope, since=since, run_id=run2,
    )
    assert r2.skipped == 1
    items2 = _items_of(db_session, run2)
    assert len(items2) == 1
    assert (items2[0].action, items2[0].status) == ("skipped", "SKIPPED")


# —— 服务层：保留清理 ——


def test_prune_ingest_items_by_retention(db_session, tmp_path) -> None:
    old = IngestItem(
        id=new_id(), run_id=None, category="bar", action="failed", status="FAILED",
        target_ref="instrument:x", display_name="旧条目",
        created_at="2020-01-01T00:00:00+00:00",
    )
    fresh = IngestItem(
        id=new_id(), run_id=None, category="bar", action="ingested", status="OK",
        target_ref="instrument:y", display_name="新条目", created_at=now_utc_iso(),
    )
    db_session.add_all([old, fresh])
    db_session.commit()

    pruned = collections_service.prune_ingest_items(db_session, _settings(tmp_path))
    assert pruned == 1
    remaining = list(db_session.scalars(select(IngestItem)).all())
    assert [i.id for i in remaining] == [fresh.id]


# —— 服务层：手动批次 + 列表/聚合 ——


def test_start_manual_run_not_claimable(db_session, tmp_path) -> None:
    settings = _settings(tmp_path)
    job = jobs_service.start_manual_run(
        db_session, settings, job_type="ingest_manual",
        business_date="2026-11-13", scope_key="bars:x",
    )
    assert job.status == "RUNNING"
    assert job.lease_until is None  # 不入执行器领取范围（5_DATA §12.2）
    assert job.attempt == 1 and job.max_attempts == 1
    assert jobs_service.claim_next(db_session, settings) is None


def test_list_runs_filters_and_stats(db_session, tmp_path) -> None:
    settings = _settings(tmp_path)
    j1 = jobs_service.start_manual_run(
        db_session, settings, job_type="ingest_manual",
        business_date="2026-11-13", scope_key="bars:a",
    )
    jobs_service.complete(db_session, j1.id, result_ref="bars://3/0")
    j2 = jobs_service.start_manual_run(
        db_session, settings, job_type="ingest_manual",
        business_date="2026-11-13", scope_key="bars:b",
    )
    jobs_service.fail(db_session, j2.id, error_code="RuntimeError")

    failed_runs, _ = jobs_service.list_runs(db_session, status="FAILED")
    assert [r.id for r in failed_runs] == [j2.id]

    all_runs, _ = jobs_service.list_runs(db_session)
    assert len(all_runs) == 2  # created_at 倒序：最新在前

    stats = jobs_service.run_stats(db_session, window_days=7)
    assert stats["total"] == 2
    assert stats["by_status"]["COMPLETED"] == 1
    assert stats["by_status"]["FAILED"] == 1
    assert stats["success_rate"] == 0.5
    assert stats["consecutive_failures"].get("ingest_manual") == 1


# —— HTTP 层 ——


def _login(client) -> None:
    identity_service.reset_login_rate_limit()
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "pw12345"},
        headers={"Idempotency-Key": "login-collections"},
    )
    assert r.status_code == 200


def test_collections_requires_login(client) -> None:
    assert client.get("/api/v1/collections/health").status_code == 401
    assert client.get("/api/v1/jobs").status_code == 401


def test_manual_refresh_then_panel_drilldown(migrated_client) -> None:
    """手动补采 job 化 → 任务列表 → 批次条目 → 源健康 → 跨批次检索 → 聚合（面板主链路）。"""
    _login(migrated_client)
    app = migrated_client.app
    with app.state.session_factory() as db:
        inst = instruments_service.get_or_create_instrument(db, code="600519", name="贵州茅台")
        db.commit()
        inst_id = inst.id

    csrf = {"X-CSRF-Token": migrated_client.cookies.get("csrf_token", "")}
    r = migrated_client.post(
        f"/api/v1/market/bars/{inst_id}/refresh",
        params={"start_date": "2026-08-10", "end_date": "2026-08-14"},
        headers={**csrf, "Idempotency-Key": "refresh-bars-panel"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ingested"] > 0
    job_id = body["job_run_id"]
    assert job_id

    # 任务列表：手动批次可见，result_ref 解析摘要 + 条目计数
    r = migrated_client.get("/api/v1/jobs", params={"job_type": "ingest_manual"})
    assert r.status_code == 200
    jobs = r.json()["items"]
    job = next(j for j in jobs if j["id"] == job_id)
    assert job["status"] == "COMPLETED"
    assert job["result_summary"]["kind"] == "bars"
    assert job["item_counts"].get("OK") == 1

    # 批次条目明细
    r = migrated_client.get(f"/api/v1/jobs/{job_id}/items")
    assert r.status_code == 200
    item_rows = r.json()["items"]
    assert len(item_rows) == 1
    assert item_rows[0]["status"] == "OK"
    assert item_rows[0]["data_ref"].startswith("market:")

    # 无效游标 → 400
    r = migrated_client.get(
        f"/api/v1/jobs/{job_id}/items", params={"cursor": "not-base64!!"}
    )
    assert r.status_code == 400

    # 源健康 + 数据集覆盖
    r = migrated_client.get("/api/v1/collections/health")
    assert r.status_code == 200
    by_cat = {s["category"]: s for s in r.json()["sources"]}
    assert by_cat["bar"]["status"] == "ok"
    assert by_cat["bar"]["latest_data"]["latest_business_date"] == "2026-08-14"
    assert by_cat["news"]["status"] == "no_data"
    assert by_cat["news"]["configured"] is False

    # 跨批次条目检索（display_name 模糊）
    r = migrated_client.get("/api/v1/collections/items", params={"q": "600519"})
    assert r.status_code == 200
    assert any(i["run_id"] == job_id for i in r.json()["items"])

    # 窗口聚合
    r = migrated_client.get("/api/v1/jobs/stats")
    assert r.status_code == 200
    assert r.json()["total"] >= 1
    assert r.json()["by_status"].get("COMPLETED", 0) >= 1
