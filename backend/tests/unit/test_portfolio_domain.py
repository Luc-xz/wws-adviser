"""Portfolio 领域纯函数测试：定点整数、指纹、方向、游标、CSV 解析（无 DB）。"""

from decimal import Decimal

import pytest

from wws_adviser.modules.portfolio.domain import (
    Direction,
    TransactionKind,
    compute_fingerprint,
    decode_cursor,
    encode_cursor,
    from_scaled_int,
    kind_to_direction,
    parse_csv_rows,
    to_scaled_int,
)

# —— 定点整数 ——


@pytest.mark.parametrize(
    "value,expected",
    [
        (Decimal("1.50"), 150),
        (Decimal("0"), 0),
        (Decimal("12.345"), 1234),  # quantize 到 2 位（银行家舍入：5 舍到偶）
        (Decimal("100"), 10000),
    ],
)
def test_to_scaled_int(value: Decimal, expected: int) -> None:
    assert to_scaled_int(value) == expected


def test_scaled_int_roundtrip() -> None:
    for v in ["0", "1.50", "99.99", "1234.56", "0.01"]:
        d = Decimal(v)
        assert from_scaled_int(to_scaled_int(d)) == d.quantize(Decimal("0.01"))


# —— 指纹 ——


def test_fingerprint_deterministic() -> None:
    kwargs = dict(
        market="SSE", code="600519", kind=TransactionKind.BUY, direction=Direction.IN,
        quantity=Decimal("100"), price=Decimal("1800.50"), fee=Decimal("5.00"),
        trade_at="2026-08-13",
    )
    assert compute_fingerprint(**kwargs) == compute_fingerprint(**kwargs)


def test_fingerprint_invariant_to_quantity_formatting() -> None:
    """'100' 与 '100.000000' 应产生同一指纹（量化保证）。"""
    base = dict(
        market="SSE", code="600519", kind=TransactionKind.BUY, direction=Direction.IN,
        price=Decimal("1800.50"), fee=Decimal("5.00"), trade_at="2026-08-13",
    )
    fp1 = compute_fingerprint(quantity=Decimal("100"), **base)
    fp2 = compute_fingerprint(quantity=Decimal("100.000000"), **base)
    assert fp1 == fp2


def test_fingerprint_differs_on_key_change() -> None:
    base = dict(
        market="SSE", code="600519",
        quantity=Decimal("100"), price=Decimal("1800.50"), fee=Decimal("5.00"),
        trade_at="2026-08-13",
    )
    fp_buy = compute_fingerprint(
        kind=TransactionKind.BUY, direction=Direction.IN, **base
    )
    fp_sell = compute_fingerprint(
        kind=TransactionKind.SELL, direction=Direction.OUT, **base
    )
    assert fp_buy != fp_sell


# —— 方向 ——


@pytest.mark.parametrize(
    "kind,expected",
    [
        (TransactionKind.BUY, Direction.IN),
        (TransactionKind.SELL, Direction.OUT),
        (TransactionKind.SUBSCRIBE, Direction.IN),
        (TransactionKind.REDEEM, Direction.OUT),
        (TransactionKind.DIVIDEND, Direction.IN),
        (TransactionKind.FEE, Direction.OUT),
    ],
)
def test_kind_to_direction(kind: TransactionKind, expected: Direction) -> None:
    assert kind_to_direction(kind) is expected


# —— 游标 ——


def test_cursor_roundtrip() -> None:
    cursor = encode_cursor("2026-08-13", "01J")
    assert decode_cursor(cursor) == ("2026-08-13", "01J")


# —— CSV 解析 ——


def test_parse_valid_csv() -> None:
    text = (
        "成交日期,证券代码,证券名称,买卖方向,成交数量,成交价格,手续费,印花税\n"
        "2026-08-13,600519,贵州茅台,买入,100,1800.50,5.00,1.80\n"
        "2026-08-12,000001,平安银行,卖出,200,11.20,2.00,2.24\n"
    )
    rows, errors = parse_csv_rows(text, market_for_code=lambda c: "SSE")
    assert errors == []
    assert len(rows) == 2
    assert rows[0].code == "600519"
    assert rows[0].kind is TransactionKind.BUY
    assert rows[0].direction is Direction.IN
    assert rows[1].kind is TransactionKind.SELL
    assert rows[1].fee == Decimal("2.00")


def test_parse_date_formats() -> None:
    for d in ("2026-08-13", "2026/08/13", "20260813", "2026.08.13"):
        text = f"成交日期,证券代码,买卖方向,成交数量,成交价格\n{d},600519,买入,100,1800\n"
        rows, errors = parse_csv_rows(text)
        assert errors == [], (d, errors)
        assert rows[0].trade_at == "2026-08-13"


def test_parse_missing_required_column() -> None:
    text = "证券代码,买卖方向,成交数量,成交价格\n600519,买入,100,1800\n"  # 缺成交日期
    rows, errors = parse_csv_rows(text)
    assert rows == []
    assert len(errors) == 1
    assert "trade_date" in errors[0].message


def test_parse_bad_number_and_unknown_direction() -> None:
    text = (
        "成交日期,证券代码,买卖方向,成交数量,成交价格\n"
        "2026-08-13,600519,换股,100,1800\n"  # 未知方向
        "2026-08-13,600519,买入,abc,1800\n"  # 非法数量
    )
    rows, errors = parse_csv_rows(text)
    assert rows == []
    assert len(errors) == 2
    msgs = " ".join(e.message for e in errors)
    assert "换股" in msgs
    assert "abc" in msgs or "数值格式错误" in msgs


def test_parse_within_batch_duplicate() -> None:
    """同一批次内两行指纹相同 → 后者记为错误（不导入重复）。"""
    text = (
        "成交日期,证券代码,买卖方向,成交数量,成交价格,手续费\n"
        "2026-08-13,600519,买入,100,1800.50,5.00\n"
        "2026-08-13,600519,买入,100,1800.50,5.00\n"
    )
    rows, errors = parse_csv_rows(text)
    assert len(rows) == 1
    assert len(errors) == 1
    assert "重复" in errors[0].message


def test_parse_empty_file() -> None:
    rows, errors = parse_csv_rows("")
    assert rows == []
    assert len(errors) == 1


def test_parse_fee_optional() -> None:
    """手续费/印花税列缺失时默认 0。"""
    text = "成交日期,证券代码,买卖方向,成交数量,成交价格\n2026-08-13,600519,买入,100,1800\n"
    rows, errors = parse_csv_rows(text)
    assert errors == []
    assert rows[0].fee == Decimal("0")
    assert rows[0].tax == Decimal("0")
