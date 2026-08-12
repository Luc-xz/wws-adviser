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
    assert body["price"] == "100.00"
    assert body["change_pct"] == "1.23"
    assert body["market_time"]
