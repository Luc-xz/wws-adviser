"""MWAC 持仓/盈亏计算确定性测试（波4 核心，AC-04「与测试基准一致」）。

固定 fixture 数值断言 qty/avg_cost/realized_pnl/cash——这是报告关键数值可追溯的基线。
"""

from decimal import Decimal

import pytest

from wws_adviser.modules.portfolio.domain import (
    PositionError,
    TransactionKind,
    TxnInput,
    compute_positions,
)

D = Decimal


def _txn(
    kind: TransactionKind,
    *,
    qty: str,
    price: str = "0",
    fee: str = "0",
    tax: str = "0",
    trade_at: str = "2026-08-10",
    instrument_id: str = "I1",
) -> TxnInput:
    from wws_adviser.modules.portfolio.domain import Direction

    return TxnInput(
        instrument_id=instrument_id,
        kind=kind,
        direction=Direction.IN,
        quantity=D(qty),
        price=D(price),
        fee=D(fee),
        tax=D(tax),
        trade_at=trade_at,
    )


def test_buy_capitalizes_fee_into_cost() -> None:
    r = compute_positions(
        [_txn(TransactionKind.BUY, qty="100", price="10", fee="5")], initial_cash=D("100000")
    )
    st = r.positions["I1"]
    assert st.qty == D("100")
    assert st.cost_basis == D("1005")  # 100*10 + 5
    assert st.avg_cost == D("10.05")
    assert r.cash == D("98995")  # 100000 - 1005


def test_mwac_avg_cost_unchanged_on_sell() -> None:
    txns = [
        _txn(TransactionKind.BUY, qty="100", price="10", fee="5", trade_at="2026-08-10"),
        _txn(TransactionKind.BUY, qty="100", price="12", fee="5", trade_at="2026-08-11"),
        _txn(TransactionKind.SELL, qty="100", price="13", fee="5", trade_at="2026-08-12"),
    ]
    r = compute_positions(txns, initial_cash=D("100000"))
    st = r.positions["I1"]
    # 加权 avg = (1005 + 1205) / 200 = 11.05
    assert st.avg_cost == D("11.05")
    # 卖 100：realized = 100*(13-11.05) - 5 = 190
    assert st.realized_pnl == D("190")
    assert st.qty == D("100")
    assert st.cost_basis == D("1105")  # 2210 - 100*11.05
    # 卖出后 avg_cost 不变（MWAC）
    assert st.avg_cost == D("11.05")
    # cash: 100000 - 1005 - 1205 + (1300-5) = 99085
    assert r.cash == D("99085")


def test_dividend_is_realized_income_no_position_change() -> None:
    txns = [
        _txn(TransactionKind.BUY, qty="100", price="10", trade_at="2026-08-10"),
        _txn(TransactionKind.DIVIDEND, qty="100", price="0.50", trade_at="2026-08-11"),
    ]
    r = compute_positions(txns, initial_cash=D("100000"))
    st = r.positions["I1"]
    assert st.qty == D("100")  # 不变
    assert st.cost_basis == D("1000")  # 不变
    assert st.realized_pnl == D("50")  # 100*0.50
    assert r.cash == D("99050")  # 100000 - 1000 + 50


def test_split_dilutes_avg_cost() -> None:
    txns = [
        _txn(TransactionKind.BUY, qty="100", price="10", trade_at="2026-08-10"),
        _txn(TransactionKind.SPLIT, qty="50", trade_at="2026-08-11"),  # 送股 50
    ]
    r = compute_positions(txns, initial_cash=D("100000"))
    st = r.positions["I1"]
    assert st.qty == D("150")
    assert st.cost_basis == D("1000")  # 不变
    assert st.avg_cost == D("1000") / D("150")  # 摊薄 ≈ 6.6667
    assert r.cash == D("99000")  # 仅 BUY 影响（100*10）


def test_fee_and_adjust_cash_only() -> None:
    txns = [
        _txn(TransactionKind.FEE, qty="0", price="0", fee="10", trade_at="2026-08-10"),
        _txn(TransactionKind.ADJUST, qty="1", price="200", trade_at="2026-08-11"),
    ]
    r = compute_positions(txns, initial_cash=D("100000"))
    assert r.positions.get("I1") is None or r.positions["I1"].qty == D("0")
    assert r.cash == D("100190")  # 100000 - 10 + 200


def test_subscribe_redeem_behave_like_buy_sell() -> None:
    txns = [
        _txn(TransactionKind.SUBSCRIBE, qty="100", price="1.5", fee="2", trade_at="2026-08-10"),
        _txn(TransactionKind.REDEEM, qty="40", price="1.8", fee="1", trade_at="2026-08-11"),
    ]
    r = compute_positions(txns, initial_cash=D("10000"))
    st = r.positions["I1"]
    assert st.qty == D("60")
    # cost_basis = 100*1.5+2 = 152；赎回 40 @ avg 1.52 → cost_basis -= 40*1.52=60.8 → 91.2
    assert st.cost_basis == D("152") - D("40") * (D("152") / D("100"))
    # realized = 40*(1.8-1.52) - 1 = 11.2 - 1 = 10.2
    assert st.realized_pnl == D("40") * (D("1.8") - D("152") / D("100")) - D("1")


def test_sell_more_than_holdings_raises() -> None:
    txns = [
        _txn(TransactionKind.BUY, qty="10", price="10", trade_at="2026-08-10"),
        _txn(TransactionKind.SELL, qty="20", price="11", trade_at="2026-08-11"),
    ]
    with pytest.raises(PositionError):
        compute_positions(txns, initial_cash=D("1000"))


def test_replay_is_idempotent() -> None:
    txns = [
        _txn(TransactionKind.BUY, qty="100", price="10", trade_at="2026-08-10"),
        _txn(TransactionKind.SELL, qty="30", price="12", trade_at="2026-08-11"),
        _txn(TransactionKind.DIVIDEND, qty="70", price="0.3", trade_at="2026-08-12"),
    ]
    r1 = compute_positions(txns, initial_cash=D("5000"))
    r2 = compute_positions(list(reversed(txns)), initial_cash=D("5000"))  # 打乱输入顺序
    assert r1.cash == r2.cash
    assert r1.positions["I1"].qty == r2.positions["I1"].qty
    assert r1.positions["I1"].realized_pnl == r2.positions["I1"].realized_pnl
