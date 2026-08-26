"""交割单 PDF→CSV 转换器测试：行解析、聚合去重、配对跳过、初始现金对账。"""

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "jgd_pdf_to_csv", Path(__file__).resolve().parents[2] / "scripts" / "jgd_pdf_to_csv.py"
)
jgd = importlib.util.module_from_spec(_spec)
sys.modules["jgd_pdf_to_csv"] = jgd
_spec.loader.exec_module(jgd)

parse_line = jgd.parse_line
convert = jgd.convert
JgdRow = jgd.JgdRow


def _row(**kw) -> JgdRow:
    base = dict(date="20260801", code="510500", name="500ETF", op="证券买入",
                qty=Decimal(100), price=Decimal("7.804"), amount=Decimal("780.400"),
                share_balance=Decimal(100), cash_delta=Decimal("-780.500"),
                fee=Decimal("0.100"), tax=Decimal(0), fund_balance=Decimal("1000.000"))
    base.update(kw)
    return JgdRow(**base)


# —— 行解析 ——


def test_parse_line_standard_trade() -> None:
    r = parse_line(
        "20260824 510500 500ETF 证券买入 100 7.804 780.400 1100 -780.500 0.100 0.000 31152.660"
    )
    assert r is not None
    assert (r.date, r.code, r.op) == ("20260824", "510500", "证券买入")
    assert r.qty == 100 and r.price == Decimal("7.804")
    assert r.fee == Decimal("0.100") and r.tax == 0
    assert r.fund_balance == Decimal("31152.660")


def test_parse_line_without_fund_balance() -> None:
    r = parse_line("20260824 510500 500ETF 证券买入 300 7.715 2314.500 1600 -2314.620 0.120 0.000")
    assert r is not None
    assert r.fee == Decimal("0.120") and r.fund_balance is None


def test_parse_line_rejects_non_data() -> None:
    assert parse_line("交割单") is None
    assert parse_line("营业部名: l_xc_hsy_7 第1页/总51页") is None
    assert parse_line("20260723 银行转证券 0 0.000 0.000 0 10000.000 0.000 -0.000 24677.") is None


def test_parse_line_negative_price_fields() -> None:
    r = parse_line(
        "20260818 000636 风华高科 证券卖出 100 63.450 6345.000 0 6336.830 5.000 3.170 29264.470"
    )
    assert r is not None
    assert r.cash_delta == Decimal("6336.830") and r.tax == Decimal("3.170")


# —— 聚合去重 ——


def test_duplicate_fills_aggregated() -> None:
    """同日同价两笔 100 股 → 聚合为一行 200 股、费用求和（指纹唯一）。"""
    rows = [
        _row(qty=Decimal(100), fee=Decimal("0.100")),
        _row(qty=Decimal(100), fee=Decimal("0.100")),
    ]
    result = convert(rows, final_cash=Decimal("1000.000"))
    assert len(result.rows) == 1
    assert result.rows[0]["成交数量"] == "200"
    assert result.rows[0]["手续费"] == "0.200"


def test_different_prices_not_aggregated() -> None:
    rows = [
        _row(price=Decimal("7.804")),
        _row(price=Decimal("7.754")),
    ]
    assert len(convert(rows).rows) == 2


# —— 特殊业务 ——


def test_split_maps_to_zero_cost() -> None:
    rows = [
        _row(date="20260701", qty=Decimal(2000), price=Decimal("0.700"),
             amount=Decimal("1400.000"), share_balance=Decimal(2000),
             cash_delta=Decimal("-1400.100")),
        _row(date="20260709", op="ETF份额分拆", qty=Decimal(2000), price=Decimal(0),
             amount=Decimal(0), cash_delta=Decimal(0), fee=Decimal(0),
             share_balance=Decimal(4000)),
    ]
    result = convert(rows, final_cash=Decimal("100.000"))
    split_row = next(r for r in result.rows if r["操作"] == "拆股")
    assert split_row["成交价格"] == "0" and split_row["成交数量"] == "2000"
    assert not any("期初持仓" in s2 for s2 in result.skipped)  # 拆股前持仓来自窗口内买入
    # 拆股不影响现金：初始现金 = 期末现金 − 买入流出
    assert result.initial_cash == Decimal("100.00") + Decimal("1400.10")


def test_dividend_qty_zero_synthesizes() -> None:
    rows = [_row(op="红利入账", qty=Decimal(0), price=Decimal(0), amount=Decimal("6.000"),
                 cash_delta=Decimal("6.000"), fee=Decimal(0), share_balance=Decimal(0))]
    result = convert(rows, final_cash=Decimal("106.000"))
    assert result.rows[0]["操作"] == "分红"
    assert result.rows[0]["成交数量"] == "1"
    assert result.rows[0]["成交价格"] == "6.000000"
    assert result.initial_cash == Decimal("100.00")


def test_share_transfer_paired_with_subscription_skipped() -> None:
    """股份转入与 5 日内申购配对 → 跳过（避免双计持仓）。"""
    rows = [
        _row(date="20260616", code="501312", name="海外科技", op="上证LOF申购",
             qty=Decimal(42), price=Decimal("2.321"), amount=Decimal("97.460"),
             cash_delta=Decimal("-97.580"), fee=Decimal("0.120")),
        _row(date="20260616", code="501312", name="海外科技", op="股份转入",
             qty=Decimal(42), price=Decimal("2.391"), amount=Decimal("98.650"),
             cash_delta=Decimal(0), fee=Decimal(0), share_balance=Decimal(85)),
    ]
    result = convert(rows, final_cash=Decimal("1000.000"))
    transfers = [r for r in result.rows if r["证券代码"] == "501312"]
    assert len(transfers) == 1 and transfers[0]["操作"] == "买入"  # 只有申购行
    assert any("股份转入" in s for s in result.skipped)


def test_unpaired_share_transfer_imported_with_warning() -> None:
    rows = [_row(op="股份转入", qty=Decimal(500), price=Decimal("0.000"), amount=Decimal(0),
                 cash_delta=Decimal(0), fee=Decimal(0), share_balance=Decimal(500))]
    result = convert(rows, final_cash=Decimal("100.000"))
    assert any("警告" in s and "股份转入" in s for s in result.skipped)
    assert result.rows[0]["操作"] == "买入" and result.rows[0]["成交价格"] == "0.000"


def test_cash_events_folded_into_initial_cash() -> None:
    """银行转账等现金事件不导入，但初始现金吸收其影响（回放对齐期末余额）。"""
    rows = [
        _row(date="20260701", qty=Decimal(100), price=Decimal("1.000"),
             cash_delta=Decimal("-100.100"), fee=Decimal("0.100")),
        _row(date="20260702", op="银行转证券", qty=Decimal(0), price=Decimal(0),
             amount=Decimal(0), share_balance=Decimal(0), cash_delta=Decimal("30000.000"),
             fee=Decimal(0), fund_balance=Decimal("30900.000")),
    ]
    result = convert(rows, final_cash=Decimal("30900.000"))
    assert len(result.rows) == 1  # 只有买入
    # 回放：-(100×1.000+0.1) = -100.10（与发生金额 -100.100 一致）；期末 30900
    assert result.initial_cash == Decimal("31000.10")


# —— 对账 ——


def test_initial_cash_reconciles_replay_to_final() -> None:
    """初始现金 + 回放现金增量 = 交割单期末资金余额（核心对账不变式）。"""
    rows = [
        _row(date="20260301", qty=Decimal(100), price=Decimal("2.000"),
             cash_delta=Decimal("-200.100"), fee=Decimal("0.100"), share_balance=Decimal(100)),
        _row(date="20260401", op="证券卖出", qty=Decimal(50), price=Decimal("2.500"),
             amount=Decimal("125.000"), share_balance=Decimal(50),
             cash_delta=Decimal("124.900"), fee=Decimal("0.100"), fund_balance=Decimal("1024.800")),
    ]
    result = convert(rows, final_cash=Decimal("1024.800"))
    replay = Decimal(result.replay_check["回放现金合计"])
    assert result.initial_cash + replay == Decimal("1024.80")


def test_final_holdings_anchor() -> None:
    rows = [
        _row(date="20260301", share_balance=Decimal(100)),
        _row(date="20260401", share_balance=Decimal(60)),
        _row(date="20260401", code="159558", name="半导体E", share_balance=Decimal(2600)),
    ]
    result = convert(rows)
    assert result.final_holdings["510500"] == ("500ETF", Decimal(60))
    assert result.final_holdings["159558"] == ("半导体E", Decimal(2600))


def test_same_day_rows_in_chronological_order() -> None:
    """同日内按股票余额链排序：余额衔接决定先后（不依赖 PDF 行序）。

    夹具（行序故意打乱）：0→600（买 600）→100（卖 500）——链头=买入（before=0），
    唯一序 buy→sell，无期初合成。
    """
    rows = [
        _row(date="20260717", op="证券卖出", qty=Decimal(500), price=Decimal("0.722"),
             amount=Decimal("361.000"), share_balance=Decimal(100),
             cash_delta=Decimal("360.900")),
        _row(date="20260717", qty=Decimal(600), price=Decimal("0.747"),
             amount=Decimal("448.200"), share_balance=Decimal(600),
             cash_delta=Decimal("-448.300")),
    ]
    result = convert(rows, final_cash=Decimal("100.000"))
    same_day = [r for r in result.rows if r["成交日期"] == "20260717"]
    assert [r["操作"] for r in same_day] == ["买入", "卖出"]
    assert not any("期初持仓" in s2 for s2 in result.skipped)


def test_opening_position_synthesized_from_share_balance() -> None:
    """首行即卖出且窗口前已有持仓：由股票余额列反推期初数量并合成买入行。

    159892 实测场景：7/17 先卖 500（余额 0）再买 500（余额 500）——
    卖出的 500 来自窗口前，交割单内无来源行。
    """
    # 真实 159892 场景：日内 0→500→0 无法与"先卖(期初500)后买回"区分（余额环）——
    # 环回退 PDF 行序。此夹具行序为买在前，链给 buy→sell，无需期初。
    rows = [
        _row(date="20260717", code="159892", name="恒生生物", qty=Decimal(500),
             price=Decimal("0.747"), amount=Decimal("373.500"),
             share_balance=Decimal(500), cash_delta=Decimal("-373.600")),
        _row(date="20260717", code="159892", name="恒生生物", op="证券卖出",
             qty=Decimal(500), price=Decimal("0.722"), amount=Decimal("361.000"),
             share_balance=Decimal(0), cash_delta=Decimal("360.900")),
    ]
    result = convert(rows, final_cash=Decimal("1000.000"))
    # buy→sell 链序，无期初合成
    assert not any("期初持仓" in s2 for s2 in result.skipped)


def test_opening_when_chain_head_is_sell() -> None:
    """链头判定为卖出（before=500 不在任何 after 中）→ 期初合成 500。"""
    rows = [
        _row(date="20260717", code="159892", name="恒生生物", op="证券卖出",
             qty=Decimal(500), price=Decimal("0.722"), amount=Decimal("361.000"),
             share_balance=Decimal(100), cash_delta=Decimal("360.900")),
        _row(date="20260718", code="159892", name="恒生生物", qty=Decimal(100),
             price=Decimal("0.750"), amount=Decimal("75.000"),
             share_balance=Decimal(200), cash_delta=Decimal("-75.100")),
    ]
    result = convert(rows, final_cash=Decimal("1000.000"))
    # 首行卖出 after=100 → before=600 期初；次日买入 100 → 200 链接成功
    assert any("期初持仓 600" in s2 for s2 in result.skipped)
    same_code = [r for r in result.rows if r["证券代码"] == "159892"]
    kinds = [r["操作"] for r in same_code]
    # 期初合成买入 → 卖出 → 当日买入：三行，期初行在最前
    assert kinds[0] == "买入" and same_code[0]["成交数量"] == "600"
    assert "卖出" in kinds and kinds.count("买入") == 2
    assert any("期初持仓" in s for s in result.skipped)
    # 期末现金不变式：初始 + 回放 = 1000（虚拟购入成本被初始现金吸收）
    replay = Decimal(result.replay_check["回放现金合计"])
    assert result.initial_cash + replay == Decimal("1000.00")


def test_no_opening_position_when_balance_matches_activity() -> None:
    """首行买入且余额=数量：无期初持仓，不合成。"""
    rows = [_row(qty=Decimal(100), share_balance=Decimal(100))]
    result = convert(rows, final_cash=Decimal("100.000"))
    assert not any("期初持仓" in s for s in result.skipped)
    assert len(result.rows) == 1
