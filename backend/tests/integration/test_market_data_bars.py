"""行情采集流水线 + /market/* 端点测试（stub 闭环；AC-02 日线口径）。

服务层用 db_session + StubBarProvider/StubNAVProvider 验证 ingest→Parquet→SQLite→query；
HTTP 层验证 GET /market/bars|nav|quality 端点。
"""

import asyncio
from datetime import date

from wws_adviser.infrastructure.data_sources.stub_bar import StubBarProvider
from wws_adviser.infrastructure.data_sources.stub_nav import StubNAVProvider
from wws_adviser.modules.instruments import service as instruments_service
from wws_adviser.modules.market_data import service as md_service


async def test_ingest_daily_bars_writes_parquet_and_index(db_session, tmp_path) -> None:
    inst = instruments_service.get_or_create_instrument(db_session, code="600519", name="贵州茅台")
    db_session.commit()

    result = await md_service.ingest_daily_bars(
        db_session,
        data_dir=tmp_path,
        instrument_id=inst.id,
        provider=StubBarProvider(env="test"),
        start=date(2026, 8, 10),  # 周一
        end=date(2026, 8, 14),  # 周五
    )
    assert result.quality == "OK"
    assert result.ingested > 0

    # Parquet 落盘
    files = list(tmp_path.rglob("part.parquet"))
    assert files, "日线 Parquet 未写入"

    # query 读回
    bars = md_service.query_bars(tmp_path, instrument_id=inst.id)
    assert len(bars) == result.ingested
    assert bars[0]["business_date"] == "2026-08-10"

    # SQLite 索引 + quality
    quality = md_service.market_quality(db_session, instrument_id=inst.id)
    assert any(q["series"] == "bar" and q["quality_status"] == "OK" for q in quality)


async def test_ingest_dedup_on_reingest(db_session, tmp_path) -> None:
    inst = instruments_service.get_or_create_instrument(db_session, code="600519")
    db_session.commit()
    provider = StubBarProvider(env="test")
    await md_service.ingest_daily_bars(
        db_session, data_dir=tmp_path, instrument_id=inst.id, provider=provider,
        start=date(2026, 8, 10), end=date(2026, 8, 12),
    )
    bars1 = md_service.query_bars(tmp_path, instrument_id=inst.id)
    # 重复采集同区间 → 不产生重复（UNIQUE upsert + Parquet 覆盖）
    await md_service.ingest_daily_bars(
        db_session, data_dir=tmp_path, instrument_id=inst.id, provider=provider,
        start=date(2026, 8, 10), end=date(2026, 8, 12),
    )
    bars2 = md_service.query_bars(tmp_path, instrument_id=inst.id)
    assert len(bars2) == len(bars1)


async def test_ingest_nav(db_session, tmp_path) -> None:
    inst = instruments_service.get_or_create_instrument(db_session, code="159915")
    db_session.commit()
    result = await md_service.ingest_nav(
        db_session, data_dir=tmp_path, instrument_id=inst.id,
        provider=StubNAVProvider(env="test"), as_of=date(2026, 8, 13),
    )
    assert result.quality == "OK"
    navs = md_service.query_nav(tmp_path, instrument_id=inst.id)
    assert len(navs) == 1
    assert navs[0]["nav_date"] == "2026-08-13"


def test_market_bars_nav_quality_http(migrated_client) -> None:
    """HTTP：经 app.state stub 采集后，GET /market/bars|nav|quality 可读。"""
    app = migrated_client.app
    settings = app.state.settings
    with app.state.session_factory() as db:
        inst = instruments_service.get_or_create_instrument(db, code="600519", name="贵州茅台")
        db.commit()
        iid = inst.id
        asyncio.run(
            md_service.ingest_daily_bars(
                db, data_dir=settings.data_dir, instrument_id=iid,
                provider=app.state.bar_provider, start=date(2026, 8, 10), end=date(2026, 8, 14),
            )
        )
        asyncio.run(
            md_service.ingest_nav(
                db, data_dir=settings.data_dir, instrument_id=iid,
                provider=app.state.nav_provider, as_of=date(2026, 8, 13),
            )
        )

    bars = migrated_client.get(f"/api/v1/market/bars/{iid}").json()
    assert bars["instrument_id"] == iid
    assert len(bars["bars"]) > 0
    assert bars["bars"][0]["close"]  # 非空

    nav = migrated_client.get(f"/api/v1/market/nav/{iid}").json()
    assert len(nav["navs"]) == 1

    quality = migrated_client.get("/api/v1/market/quality").json()
    series = {(e["series"], e["quality_status"]) for e in quality["items"]}
    assert ("bar", "OK") in series
    assert ("nav", "OK") in series

    state = migrated_client.get("/api/v1/market/state").json()
    # 状态机（Phase 2.1 补齐）：相位合法、交易日有值、恒有下一事件
    _PHASES = {"pre_open", "auction", "open", "lunch_break", "closed", "non_trading_day"}
    assert state["phase"] in _PHASES
    assert isinstance(state["is_trading_day"], bool)
    assert state["next_event_at"]


def test_market_state_endpoint_open(migrated_client) -> None:
    """GET /market/state 公开可读（无需登录）。"""
    r = migrated_client.get("/api/v1/market/state")
    assert r.status_code == 200
