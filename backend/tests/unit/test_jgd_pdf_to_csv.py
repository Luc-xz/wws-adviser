"""交割单 PDF→CSV 转换器测试：行解析、聚合去重、配对跳过、初始现金对账、
未单列费用补差、余额环种子、增量模式校验。"""

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "jgd_pdf_to_csv", Path(__file__).resolve().parents[2] / "scripts" / "jgd_pdf_to_csv.py"
)
jgd = importlib.util.module_from_spec(_spec)
sys.modules["jgd_pdf_to_csv"] = jgd
_spec.loader.exec_module(jgd)

parse_line = jgd.parse_line
convert = jgd.convert
assert_no_overlap = jgd.assert_no_overlap
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


# —— 未单列费用补差 ——


def test_unlisted_fee_patch_ties_replay_to_cash_delta() -> None:
    """现金流比 金额+费用 多 0.02（沪市过户费未单列）→ 补进手续费，回放逐分一致。"""
    rows = [_row(amount=Decimal("780.400"), cash_delta=Decimal("-780.520"))]
    result = convert(rows, final_cash=Decimal("219.480"))
    assert result.rows[0]["手续费"] == "0.120"
    assert any("补未单列费用 0.02" in n for n in result.fee_adjustments)
    assert Decimal(result.replay_check["回放现金合计"]) == Decimal("-780.52")


def test_sell_side_no_fee_patch_when_consistent() -> None:
    """卖出现金流=金额−费用（正常）不补差；差异为负（现金流比申报多）不修改。"""
    rows = [
        _row(op="证券卖出", amount=Decimal("780.400"), share_balance=Decimal(0),
             cash_delta=Decimal("780.300")),
        _row(op="证券卖出", amount=Decimal("790.000"), share_balance=Decimal(0),
             cash_delta=Decimal("790.400")),  # 现金流比申报多 0.10——数据异常不修改
    ]
    result = convert(rows, final_cash=Decimal("1000.000"))
    assert not any("补未单列费用" in n for n in result.fee_adjustments)
    assert any("数据异常" in n for n in result.fee_adjustments)


# —— 增量模式 ——


def test_incremental_skips_opening_synthesis() -> None:
    """服务器已有持仓：不做期初合成（合成即双计），期初衔接校验通过。"""
    rows = [_row(date="20260801", qty=Decimal(100), share_balance=Decimal(1100))]
    result = convert(rows, final_cash=Decimal("1000.000"),
                     initial_positions={"510500": Decimal(1000)})
    assert not any("期初持仓" in s for s in result.skipped)
    assert len(result.rows) == 1 and result.rows[0]["成交数量"] == "100"
    assert result.expected_finals["510500"] == ("500ETF", Decimal(1100))


def test_incremental_warns_on_opening_mismatch() -> None:
    rows = [_row(date="20260801", qty=Decimal(100), share_balance=Decimal(1100))]
    result = convert(rows, final_cash=Decimal("1000.000"),
                     initial_positions={"510500": Decimal(900)})
    assert any("期初 1000 ≠ 服务器持仓 900" in s for s in result.skipped)


def test_incremental_ring_seeded_by_server_position() -> None:
    """日内「卖 N→买回 N」余额环：服务器持仓作链头种子——先卖后买被正确还原
    （2026-08-26 515120 实测场景：6200 →卖2000→ 4200 →买2000→ 6200）。"""
    rows = [
        _row(date="20260826", code="515120", name="创新药", op="证券卖出",
             qty=Decimal(2000), price=Decimal("0.658"), amount=Decimal("1316.000"),
             share_balance=Decimal(4200), cash_delta=Decimal("1315.900")),
        _row(date="20260826", code="515120", name="创新药",
             qty=Decimal(2000), price=Decimal("0.650"), amount=Decimal("1300.000"),
             share_balance=Decimal(6200), cash_delta=Decimal("-1300.100")),
    ]
    result = convert(rows, final_cash=Decimal("1000.000"),
                     initial_positions={"515120": Decimal(6200)})
    day = [r for r in result.rows if r["成交日期"] == "20260826"]
    assert [r["操作"] for r in day] == ["卖出", "买入"]  # 种子定头：先卖后买
    assert result.final_holdings["515120"] == ("创新药", Decimal(6200))
    assert result.expected_finals["515120"] == ("创新药", Decimal(6200))
    assert not any("警告" in s for s in result.skipped)


def test_ring_carries_previous_day_close_by_default() -> None:
    """默认模式跨日续接：前日链尾 4800 作次日环种子——环歧义不跨日传播
    （2026-08-31 515120 实测场景：4800 →卖2400→ 2400 →买2400→ 4800，
    旧版独立破环曾误报期末 2400）。"""
    d1 = _row(date="20260828", code="515120", name="创新药", qty=Decimal(800),
              price=Decimal("0.649"), amount=Decimal("519.200"),
              share_balance=Decimal(4800), cash_delta=Decimal("-519.300"))
    d2_sell = _row(date="20260831", code="515120", name="创新药", op="证券卖出",
                   qty=Decimal(2400), price=Decimal("0.630"), amount=Decimal("1512.000"),
                   share_balance=Decimal(2400), cash_delta=Decimal("1511.900"))
    d2_buy = _row(date="20260831", code="515120", name="创新药", qty=Decimal(2400),
                  price=Decimal("0.630"), amount=Decimal("1512.000"),
                  share_balance=Decimal(4800), cash_delta=Decimal("-1512.100"))
    result = convert([d2_sell, d2_buy, d1], final_cash=Decimal("1000.000"))
    assert result.final_holdings["515120"][1] == Decimal(4800)
    day2 = [r for r in result.rows if r["成交日期"] == "20260831"]
    assert [r["操作"] for r in day2] == ["卖出", "买入"]


def test_incremental_rejects_oversell() -> None:
    rows = [
        _row(date="20260801", op="证券卖出", qty=Decimal(200), amount=Decimal("1560.800"),
             share_balance=Decimal(800), cash_delta=Decimal("1560.700")),
    ]
    with pytest.raises(ValueError, match="负持仓"):
        convert(rows, final_cash=Decimal("1000.000"),
                initial_positions={"510500": Decimal(100)})


def test_incremental_cash_closure_with_tolerance_and_events() -> None:
    """现金闭合：服务器现金 + 回放 + 现金事件 = 交割单期末（容差吸收历史尾差）。"""
    rows = [
        _row(date="20260701", qty=Decimal(100), price=Decimal("1.000"),
             amount=Decimal("100.000"), share_balance=Decimal(100),
             cash_delta=Decimal("-100.100"), fee=Decimal("0.100")),
        _row(date="20260702", op="银行转证券", qty=Decimal(0), price=Decimal(0),
             amount=Decimal(0), share_balance=Decimal(0), cash_delta=Decimal("500.000"),
             fee=Decimal(0), fund_balance=Decimal("1399.900")),
    ]
    # 999.995（含 0.005 历史尾差）− 100.10 + 500 = 1399.895，残差 −0.005 ≤ 容差 → 通过
    result = convert(rows, final_cash=Decimal("1399.900"),
                     initial_positions={"510500": Decimal(100)},
                     server_cash=Decimal("999.995"))
    assert any("现金事件" in s for s in result.skipped)
    # 残差 −1.005 > 容差 → 拦截
    with pytest.raises(ValueError, match="现金闭合失败"):
        convert(rows, final_cash=Decimal("1399.900"),
                initial_positions={"510500": Decimal(100)},
                server_cash=Decimal("998.995"))


def test_incremental_expected_final_cross_checks_chain_anchor() -> None:
    """预期期末（服务器+净变动）与余额链锚点交叉校验；服务器独有代码一并报告。"""
    rows = [
        _row(date="20260801", code="159915", name="创业板", qty=Decimal(500),
             price=Decimal("3.420"), amount=Decimal("1710.000"),
             share_balance=Decimal(500), cash_delta=Decimal("-1710.100")),
    ]
    result = convert(rows, final_cash=Decimal("1000.000"),
                     initial_positions={"510500": Decimal(3000), "159915": Decimal(0)})
    assert result.expected_finals["159915"] == ("创业板", Decimal(500))
    assert result.expected_finals["510500"] == ("-", Decimal(3000))  # 窗口外代码不变


# —— 区间重叠拦截 ——


def test_overlap_guard_normalizes_date_formats() -> None:
    """服务器日期 YYYY-MM-DD 与 PDF 日期 YYYYMMDD 直接字符串比较恒判不重叠——
    必须统一格式后比较。"""
    rows = [_row(date="20260825")]
    # PDF 起点 0825 > 服务器最后 0824 → 通过（相邻区间）
    assert_no_overlap(rows, "2026-08-24")
    assert_no_overlap(rows, "2026-08-24T15:00:00+08:00")
    # 同日（含时间戳）→ 重叠
    with pytest.raises(ValueError, match="区间重叠"):
        assert_no_overlap(rows, "2026-08-25")
    with pytest.raises(ValueError, match="区间重叠"):
        assert_no_overlap(rows, "20260825")
    assert_no_overlap([], "2026-08-25")  # 空行集不拦截
