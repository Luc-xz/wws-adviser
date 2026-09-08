"""多源冲突集成测试（Phase 3.3）：两源超容差 → data_conflicts + 质量/建议降级 + API 消解。

- 等级可分（L1 vs L4）→ 自动 RESOLVED，质量保持 OK
- 同等级（L4 vs L4）→ UNRESOLVED，两侧记录 CONFLICT，advice data_conflict 降级
- 人工消解端点（SET-02）：选源落库 + 幂等 + 解除降级
"""

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.instruments import service as instruments_service
from wws_adviser.modules.market_data import repository as md_repository
from wws_adviser.modules.market_data import service as md_service
from wws_adviser.modules.market_data.models import DataConflict, MarketRecord
from wws_adviser.ports.market_data import (
    BarRow,
    InstrumentRef,
    RawDataset,
    SourceDelayClass,
)

from .test_research_generation import _login


class _ShiftedBarProvider:
    """第二数据源：合成日线整体偏移 pct（构造超容差差异），source 名可配。"""

    def __init__(self, *, source: str, pct: Decimal) -> None:
        self._source = source
        self._pct = pct

    async def fetch_daily_bars(
        self, instrument: InstrumentRef, start: date, end: date
    ) -> RawDataset:
        now = now_utc_iso()
        base = Decimal(100 + sum(ord(c) for c in instrument.code) % 100)
        bars: list[BarRow] = []
        cur = start
        while cur <= end:
            if cur.weekday() < 5:
                close = (base + Decimal((cur - start).days)) * (1 + self._pct)
                bars.append(
                    BarRow(
                        date=cur,
                        open=close - Decimal("1"),
                        high=close + Decimal("1"),
                        low=close - Decimal("2"),
                        close=close,
                        volume=Decimal("1000"),
                    )
                )
            cur += timedelta(days=1)
        return RawDataset(
            source=self._source,
            source_url=f"{self._source}://bars/{instrument.code}",
            market_time=now,
            fetched_at=now,
            received_at=now,
            source_delay_class=SourceDelayClass.END_OF_DAY,
            bars=bars,
        )


async def _ingest_two_sources(db, tmp_path, inst_id: str, second: _ShiftedBarProvider) -> None:
    """先采 stub 基线，再采第二源（偏移）。"""
    from wws_adviser.infrastructure.data_sources.stub_bar import StubBarProvider

    await md_service.ingest_daily_bars(
        db, data_dir=tmp_path, instrument_id=inst_id,
        provider=StubBarProvider(env="test"),
        start=date(2026, 8, 10), end=date(2026, 8, 11),
    )
    await md_service.ingest_daily_bars(
        db, data_dir=tmp_path, instrument_id=inst_id, provider=second,
        start=date(2026, 8, 10), end=date(2026, 8, 11),
    )


async def test_levels_differ_auto_resolves(db_session, tmp_path) -> None:
    """L1（exchange）vs L4（stub）超容差 → RESOLVED 记录胜出源，质量保持 OK。"""
    inst = instruments_service.get_or_create_instrument(db_session, code="600519", name="茅台")
    db_session.commit()
    await _ingest_two_sources(
        db_session, tmp_path, inst.id, _ShiftedBarProvider(source="exchange", pct=Decimal("0.05"))
    )

    rows = list(db_session.scalars(select(DataConflict)).all())
    assert rows, "超容差未写 data_conflicts"
    close_rows = [r for r in rows if r.field == "close"]
    assert close_rows
    assert all(r.status == "RESOLVED" for r in rows)
    assert all(r.resolved_by == "auto:trust_level:exchange" for r in rows)
    # 等级可分 → 不污染质量
    assert not md_repository.has_open_conflict(db_session, inst.id)
    recs = list(
        db_session.scalars(
            select(MarketRecord).where(MarketRecord.instrument_id == inst.id)
        ).all()
    )
    assert all(r.quality_status == "OK" for r in recs)


async def test_same_level_unresolved_degrades(db_session, tmp_path) -> None:
    """L4 vs L4 超容差 → UNRESOLVED + 两侧 CONFLICT + 建议 data_conflict 降级。"""
    inst = instruments_service.get_or_create_instrument(db_session, code="600519", name="茅台")
    db_session.commit()
    await _ingest_two_sources(
        db_session, tmp_path, inst.id, _ShiftedBarProvider(source="aggregator", pct=Decimal("0.05"))
    )

    rows = list(db_session.scalars(select(DataConflict)).all())
    assert rows
    assert all(r.status == "UNRESOLVED" for r in rows)
    assert md_repository.has_open_conflict(db_session, inst.id)

    recs = list(
        db_session.scalars(
            select(MarketRecord).where(MarketRecord.instrument_id == inst.id)
        ).all()
    )
    conflicted = [r for r in recs if r.quality_status == "CONFLICT"]
    assert {r.source for r in conflicted} == {"stub", "aggregator"}  # 两侧都标

    # 建议链路：上下文不洁 → DEGRADED + data_conflict（build_intraday_advice 纯函数）
    from wws_adviser.modules.advice.domain import (
        AdviceAction,
        AdviceState,
        DegradedReason,
        IntradayContext,
        build_intraday_advice,
    )

    advice = build_intraday_advice(
        IntradayContext(
            code="600519", signal_id="", quote_fresh=True, tradable=True,
            ledger_reconciled=True, market_data_clean=False, kelly_accepted=True,
        ),
        advice_id="a1", valid_from="2026-09-08T01:00:00Z", expires_at="2026-09-08T01:10:00Z",
    )
    assert advice.state == AdviceState.DEGRADED
    assert advice.action == AdviceAction.SUSPEND
    assert DegradedReason.DATA_CONFLICT.value in advice.reasons


async def test_single_source_never_conflicts(db_session, tmp_path) -> None:
    """单源重复采集不触发冲突（无第二源可比）。"""
    from wws_adviser.infrastructure.data_sources.stub_bar import StubBarProvider

    inst = instruments_service.get_or_create_instrument(db_session, code="600519")
    db_session.commit()
    for _ in range(2):
        await md_service.ingest_daily_bars(
            db_session, data_dir=tmp_path, instrument_id=inst.id,
            provider=StubBarProvider(env="test"),
            start=date(2026, 8, 10), end=date(2026, 8, 11),
        )
    assert list(db_session.scalars(select(DataConflict)).all()) == []


def test_conflicts_api_list_and_resolve(migrated_client: TestClient, tmp_path) -> None:
    """GET /market/conflicts 列表 + POST resolve 消解（幂等）+ 解除建议降级。"""
    app = migrated_client.app
    headers = _login(migrated_client)
    with app.state.session_factory() as db:
        inst = instruments_service.get_or_create_instrument(db, code="600519", name="茅台")
        db.commit()
        asyncio.run(_ingest_two_sources(
            db, tmp_path, inst.id,
            _ShiftedBarProvider(source="aggregator", pct=Decimal("0.05")),
        ))

    r = migrated_client.get("/api/v1/market/conflicts", headers=headers)
    assert r.status_code == 200
    items = r.json()["items"]
    assert items
    assert all(i["status"] == "UNRESOLVED" for i in items)
    conflict_id = items[0]["id"]

    # 非法 winner 拒绝
    r_bad = migrated_client.post(
        f"/api/v1/market/conflicts/{conflict_id}/resolve",
        json={"winner": "not_a_source"},
        headers={**headers, "Idempotency-Key": "resolve-bad-1"},
    )
    assert r_bad.status_code >= 400

    # 人工消解（逐条：字段级冲突一行一消）
    for i, item in enumerate(items):
        r2 = migrated_client.post(
            f"/api/v1/market/conflicts/{item['id']}/resolve",
            json={"winner": "aggregator", "note": "人工核对选聚合源"},
            headers={**headers, "Idempotency-Key": f"resolve-ok-{i}"},
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "RESOLVED"
        assert "aggregator" in (r2.json()["resolved_by"] or "")

    # 幂等：重复消解不报错、状态不变
    r3 = migrated_client.post(
        f"/api/v1/market/conflicts/{conflict_id}/resolve",
        json={"winner": "aggregator", "note": "人工核对选聚合源"},
        headers={**headers, "Idempotency-Key": "resolve-ok-again"},
    )
    assert r3.status_code == 200
    assert r3.json()["status"] == "RESOLVED"

    # 全部消解后建议恢复通道（无 open 冲突）
    with app.state.session_factory() as db:
        assert not md_repository.has_open_conflict(db, inst.id)

    # 状态过滤
    r4 = migrated_client.get(
        "/api/v1/market/conflicts", params={"status": "UNRESOLVED"}, headers=headers
    )
    assert r4.status_code == 200
    unresolved_ids = [i["id"] for i in r4.json()["items"]]
    assert conflict_id not in unresolved_ids
