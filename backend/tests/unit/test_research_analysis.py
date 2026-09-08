"""确定性分析测试：指标表 + 可比公司 + 估值情景（Phase 3 波3）。"""

from decimal import Decimal

from wws_adviser.modules.research.analysis import (
    build_comparable_table,
    build_metric_table,
    build_valuation_scenarios,
    compute_yoy,
    historical_percentile,
)

# —— 指标表 ——


def test_build_metric_table_basic() -> None:
    raw = {
        "营业收入": {"value": "100.5", "prior": "85.2", "unit": "亿元"},
        "净利润": {"value": "20.1", "prior": "18.5", "unit": "亿元"},
        "ROE": {"value": "15.3", "unit": "%"},  # 无上年 → yoy None
    }
    rows = build_metric_table(raw)
    assert len(rows) == 3
    rev = next(r for r in rows if r.name == "营业收入")
    assert rev.value == Decimal("100.5")
    assert rev.yoy_change == Decimal("17.96")  # (100.5-85.2)/85.2*100
    roe = next(r for r in rows if r.name == "ROE")
    assert roe.yoy_change is None


def test_compute_yoy_edge_cases() -> None:
    assert compute_yoy(Decimal("110"), Decimal("100")) == Decimal("10")
    assert compute_yoy(Decimal("90"), Decimal("100")) == Decimal("-10")
    assert compute_yoy(None, Decimal("100")) is None
    assert compute_yoy(Decimal("100"), None) is None
    assert compute_yoy(Decimal("100"), Decimal("0")) is None


def test_build_metric_table_missing_values() -> None:
    raw = {"指标A": {"value": None, "unit": "x"}, "指标B": {"value": "abc", "unit": "y"}}
    rows = build_metric_table(raw)
    assert rows[0].value is None
    assert rows[1].value is None  # 非数字 → None


# —— 可比公司 ——


def test_comparable_table_median_and_percentile() -> None:
    peers = [
        ("600519", "贵州茅台", Decimal("25.0")),
        ("000858", "五粮液", Decimal("20.0")),
        ("000568", "泸州老窖", Decimal("22.0")),
        ("002304", "洋河股份", Decimal("18.0")),
    ]
    row = build_comparable_table(
        "PE", "600519", "贵州茅台", Decimal("25.0"), peers,
    )
    assert row.median == Decimal("21.0")  # sorted: 18,20,22,25 → (20+22)/2
    assert row.percentile == Decimal("75")  # 3/4 below → 75th


def test_comparable_table_no_data() -> None:
    row = build_comparable_table("PE", "X", "标的", None, [])
    assert row.median is None
    assert row.percentile is None


# —— 估值情景 ——


def test_valuation_scenarios_pe() -> None:
    result = build_valuation_scenarios(
        current_price=Decimal("50"),
        method="pe",
        base_metric=Decimal("2.5"),    # 预测 EPS
        bull_multiple=Decimal("30"),
        base_multiple=Decimal("20"),
        bear_multiple=Decimal("12"),
    )
    assert len(result.scenarios) == 3
    bull = result.scenarios[0]
    assert bull.implied_value == Decimal("75")  # 30 × 2.5
    assert bull.upside_pct == Decimal("50")     # (75-50)/50*100
    bear = result.scenarios[2]
    assert bear.implied_value == Decimal("30")
    assert bear.upside_pct == Decimal("-40")


def test_valuation_scenarios_missing_inputs() -> None:
    result = build_valuation_scenarios(
        current_price=Decimal("50"), method="pe",
        base_metric=None, bull_multiple=Decimal("30"),
        base_multiple=None, bear_multiple=Decimal("12"),
    )
    assert all(s.implied_value is None for s in result.scenarios)


# —— 历史分位 ——


def test_historical_percentile() -> None:
    history = [Decimal(x) for x in ("10", "12", "15", "18", "20", "25", "30")]
    assert historical_percentile(Decimal("22"), history) == Decimal("71.43")  # 5/7
    assert historical_percentile(Decimal("10"), history) == Decimal("0")
    assert historical_percentile(Decimal("35"), history) == Decimal("100")
    assert historical_percentile(None, history) is None
    assert historical_percentile(Decimal("15"), []) is None
