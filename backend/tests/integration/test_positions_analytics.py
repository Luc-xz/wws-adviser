"""持仓/估值/风险/归因 端点 + 快照重建一致性测试（波4，AC-04）。

经 portfolio 服务建交易（触发 rebuild_snapshots）+ market_data 注入 close →
GET /positions、/analytics/{summary,risk,attribution}、/positions/history。
"""

import asyncio
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from wws_adviser.modules.identity import service as identity_service
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.instruments import service as instruments_service
from wws_adviser.modules.market_data import service as market_service
from wws_adviser.modules.portfolio import service as portfolio_service
from wws_adviser.modules.portfolio.domain import TransactionKind


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


def _seed(migrated_client) -> str:
    """建账户 + 标的 + 行情 + 一笔大额买入（触发 single_cap）。返回 instrument_id。"""
    app = migrated_client.app
    settings = app.state.settings
    with app.state.session_factory() as db:
        alice = db.scalar(select(User).where(User.username == "alice"))
        assert alice is not None
        portfolio_service.create_account(
            db, user_id=alice.id, name="main", initial_cash=Decimal("100000")
        )
        inst = instruments_service.get_or_create_instrument(
            db, code="600519", name="贵州茅台"
        )
        inst.industry = "白酒"
        db.commit()
        asyncio.run(
            market_service.ingest_daily_bars(
                db, data_dir=settings.data_dir, instrument_id=inst.id,
                provider=app.state.bar_provider, start=date(2026, 8, 10), end=date(2026, 8, 14),
            )
        )
        portfolio_service.record_transaction(
            db, user_id=alice.id, instrument_id=inst.id, kind=TransactionKind.BUY,
            quantity=Decimal("600"), price=Decimal("100"), fee=Decimal("5"),
            tax=Decimal("0"), trade_at="2026-08-13",
        )
        return inst.id


def test_positions_with_market_value_and_weight(migrated_client) -> None:
    inst_id = _seed(migrated_client)
    _login(migrated_client)

    r = migrated_client.get("/api/v1/positions")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    p = body["items"][0]
    assert p["instrument_id"] == inst_id
    assert p["market_value"]  # 有 close → 有市值
    assert p["weight"]
    assert p["freshness"] != "missing"
    assert float(body["total_assets"]) > 0


def test_analytics_summary_risk_attribution(migrated_client) -> None:
    _seed(migrated_client)
    _login(migrated_client)

    summary = migrated_client.get("/api/v1/analytics/summary").json()
    assert float(summary["total_assets"]) > 0
    assert "note" in summary  # volatility 等样本不足标记

    risk = migrated_client.get("/api/v1/analytics/risk").json()
    # 单一持仓 600 股 @100 = 60000，占 total_assets 比例 > single_cap(0.30)
    rules = {b["rule"] for b in risk["breaches"]}
    assert "single_cap" in rules

    attr = migrated_client.get("/api/v1/analytics/attribution").json()
    assert len(attr["by_instrument"]) == 1
    assert attr["by_industry"][0]["industry"] == "白酒"


def test_positions_history_after_rebuild(migrated_client) -> None:
    inst_id = _seed(migrated_client)
    _login(migrated_client)

    hist = migrated_client.get(
        "/api/v1/positions/history", params={"instrument_id": inst_id}
    ).json()
    # 至少一条快照（BUY 那天）
    assert len(hist["items"]) >= 1
    assert hist["items"][0]["instrument_id"] == inst_id


def test_rebuild_consistency_after_new_transaction(migrated_client) -> None:
    """新增交易后快照重建：持仓数量与回放一致。"""
    inst_id = _seed(migrated_client)
    app = migrated_client.app
    with app.state.session_factory() as db:
        alice = db.scalar(select(User).where(User.username == "alice"))
        assert alice is not None
        # 再买一笔（不同日期）→ 触发 rebuild
        portfolio_service.record_transaction(
            db, user_id=alice.id, instrument_id=inst_id, kind=TransactionKind.BUY,
            quantity=Decimal("100"), price=Decimal("110"), fee=Decimal("5"),
            tax=Decimal("0"), trade_at="2026-08-14",
        )
        state = portfolio_service.get_position_state(
            db, portfolio_service.get_user_account(db, alice.id).id
        )
    # 回放后总持仓 = 600 + 100 = 700
    assert state.positions[inst_id].qty == Decimal("700")
