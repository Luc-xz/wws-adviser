"""闭环测试：stub QuoteProvider → market_data domain → API（Phase 0 退出条件 4）。

GET /api/v1/market-data/quotes/{code} 经 stub 适配器 → RawQuote → parse_quote → QuoteOut，
证明"端口 + 占位适配器可跑通一条 stub 数据→领域→API 闭环"（10_MILESTONE_PLAN 退出条件）。
"""


def test_quote_closed_loop_returns_stub_data(migrated_client) -> None:
    r = migrated_client.get("/api/v1/market-data/quotes/600519")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == "600519"
    assert body["source"] == "stub"  # 数据来自 stub 适配器，证明端口抽象生效
    assert body["price"] == "100.0000"  # 波2：parse_quote 按 price_scale=4 校正
    assert body["change_pct"] == "1.2300"
    assert body["market_time"]


def test_market_state_endpoint(migrated_client) -> None:
    """市场状态机：phase 合法、is_trading_day 有值（空日历走 weekday 兜底）、
    next_event_at 始终有下一事件（当日边界或次日 09:15）。"""
    r = migrated_client.get("/api/v1/market/state")
    assert r.status_code == 200
    body = r.json()
    _PHASES = {"pre_open", "auction", "open", "lunch_break", "closed", "non_trading_day"}
    assert body["phase"] in _PHASES
    assert isinstance(body["is_trading_day"], bool)
    assert body["next_event_at"]  # 永远给出下一事件（SSE/前端节奏依赖）
