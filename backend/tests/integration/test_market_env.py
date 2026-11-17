"""Market env service 集成测试：采集流水线 + 观测写入 + 读取侧聚合（ADR-0014）。"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from wws_adviser.infrastructure.market_env.stub_market_env import (
    StubIndexBarProvider,
    StubIndexQuoteProvider,
    StubSectorFlowProvider,
    stub_turnover_total,
)
from wws_adviser.modules.collections.models import IngestItem, SourceHealth
from wws_adviser.modules.market_env import service as market_env_service
from wws_adviser.modules.market_env.models import (
    IndexBar,
    IndexQuote,
    MarketEnvIndex,
    SectorBoard,
    SectorFlowSnapshot,
)
from wws_adviser.ports.market_env import RawIndexQuote, SectorKind


async def test_ingest_index_quotes_records_health_and_item(db_session) -> None:
    provider = StubIndexQuoteProvider(env="test")
    result = await market_env_service.ingest_index_quotes(db_session, provider=provider)
    assert result.ingested == 20  # 注册表 20 项全采（17 指数 + 3 美股期货）
    assert result.quality == "OK"
    # 注册表播种
    assert db_session.scalar(select(MarketEnvIndex).where(
        MarketEnvIndex.code == "cn_sh000001")) is not None
    # 快照落库 + 两市成交额汇总（上证综指 + 深证综指）
    assert db_session.query(IndexQuote).count() == 20
    assert market_env_service.market_turnover(db_session) == stub_turnover_total()
    # 观测：源健康成功 + 条目
    health = db_session.get(SourceHealth, "index_quote")
    assert health is not None and health.last_success_at
    item = db_session.scalar(
        select(IngestItem).where(IngestItem.category == "index_quote")
    )
    assert item is not None
    assert item.status == "OK" and item.rows_written == 20
    assert item.target_ref == "index:batch"


async def test_ingest_index_quotes_partial_parse_failure(db_session) -> None:
    """坏条目（价格非正）计失败不中断批次：条目 PARTIAL、质量 PARSE_FAILED。"""

    class OneBadProvider(StubIndexQuoteProvider):
        async def fetch_index_quotes(self, refs):
            quotes = await super().fetch_index_quotes(refs)
            bad = quotes[0]
            quotes[0] = RawIndexQuote(
                code=bad.code, source=bad.source, source_url=bad.source_url,
                market_time=bad.market_time, fetched_at=bad.fetched_at,
                received_at=bad.received_at, source_delay_class=bad.source_delay_class,
                price=Decimal("0"), change_pct=bad.change_pct,  # 价格非正 → 解析失败
            )
            return quotes

    result = await market_env_service.ingest_index_quotes(
        db_session, provider=OneBadProvider(env="test")
    )
    assert result.ingested == 19
    assert result.failed == 1
    assert result.quality == "PARSE_FAILED"
    item = db_session.scalar(
        select(IngestItem).where(IngestItem.category == "index_quote")
    )
    assert item is not None and item.status == "PARTIAL"


async def test_ingest_index_quotes_failure_records_observation(db_session) -> None:
    class ExplodingProvider:
        async def fetch_index_quotes(self, refs):
            raise RuntimeError("源不可达")

    with pytest.raises(RuntimeError):
        await market_env_service.ingest_index_quotes(
            db_session, provider=ExplodingProvider()  # type: ignore[arg-type]
        )
    health = db_session.get(SourceHealth, "index_quote")
    assert health is not None
    assert health.consecutive_failures == 1
    assert health.last_error_code == "RuntimeError"
    item = db_session.scalar(
        select(IngestItem).where(IngestItem.category == "index_quote")
    )
    assert item is not None and item.status == "FAILED"


async def test_ingest_index_bars_roundtrip(db_session) -> None:
    provider = StubIndexBarProvider(env="test")
    end = date.today()
    start = end - timedelta(days=60)
    result = await market_env_service.ingest_index_bars(
        db_session, provider=provider, code="cn_sh000001", start=start, end=end
    )
    assert result.ingested == 30 and result.quality == "OK"
    bars = market_env_service.repository.list_index_bars(db_session, "cn_sh000001")
    assert len(bars) == 30
    # 幂等：重采同区间不重复
    await market_env_service.ingest_index_bars(
        db_session, provider=provider, code="cn_sh000001", start=start, end=end
    )
    assert db_session.query(IndexBar).count() == 30
    health = db_session.get(SourceHealth, "index_bar")
    assert health is not None and health.last_success_at


async def test_ingest_index_bars_rejects_unregistered(db_session) -> None:
    with pytest.raises(ValueError):
        await market_env_service.ingest_index_bars(
            db_session, provider=StubIndexBarProvider(env="test"),
            code="xx_unknown", start=date.today(), end=date.today(),
        )


async def test_ingest_sector_flows_records_boards_and_snapshots(db_session) -> None:
    provider = StubSectorFlowProvider(env="test")
    result = await market_env_service.ingest_sector_flows(
        db_session, provider=provider, kind=SectorKind.INDUSTRY
    )
    assert result.ingested == 4 and result.quality == "OK"
    assert db_session.query(SectorBoard).count() == 4
    assert db_session.query(SectorFlowSnapshot).count() == 4
    # 最新一轮按主力净额降序（榜首为正净流入最大者；末位为净流出）
    latest = market_env_service.repository.latest_sector_flows(
        db_session, kind="industry"
    )
    assert len(latest) == 4
    assert Decimal(latest[0].net_main_inflow) > 0
    assert Decimal(latest[-1].net_main_inflow) < 0
    health = db_session.get(SourceHealth, "sector_flow")
    assert health is not None and health.last_success_at
    item = db_session.scalar(
        select(IngestItem).where(IngestItem.category == "sector_flow")
    )
    assert item is not None and item.target_ref == "sector:industry"


async def test_ingest_sector_flows_no_data(db_session) -> None:
    class EmptyProvider:
        async def fetch_sector_flows(self, kind):
            return []

    result = await market_env_service.ingest_sector_flows(
        db_session, provider=EmptyProvider(),  # type: ignore[arg-type]
        kind=SectorKind.CONCEPT,
    )
    assert result.ingested == 0 and result.quality == "MISSING"
    health = db_session.get(SourceHealth, "sector_flow")
    assert health is not None
    assert health.last_error_code == "NO_DATA"


def test_registry_refs_are_wellformed() -> None:
    """注册表不变量：code 唯一、分组合法、CN 指数均有东财 secid（日 K v1 仅 CN）。"""
    from wws_adviser.modules.market_env.domain import INDEX_REGISTRY, TURNOVER_INDEX_CODES

    codes = [r.code for r in INDEX_REGISTRY]
    assert len(codes) == len(set(codes))
    groups = {r.market_group for r in INDEX_REGISTRY}
    assert groups <= {"cn_broad", "cn_style", "overseas_us", "overseas_ap", "futures_us"}
    for r in INDEX_REGISTRY:
        if r.market_group.startswith("cn_"):
            assert "eastmoney" in r.symbol_map, f"{r.code} 缺东财 secid"
    for code in TURNOVER_INDEX_CODES:
        ref = next(r for r in INDEX_REGISTRY if r.code == code)
        assert ref.market_group == "cn_broad"
