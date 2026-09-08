"""多源交叉验证领域纯函数测试（Phase 3.3，5_DATA §6）。"""

from decimal import Decimal

from wws_adviser.modules.market_data.domain import (
    compare_field,
    initial_status,
    trust_level,
)


def test_trust_level_registered_and_unknown() -> None:
    assert trust_level("exchange") == 1
    assert trust_level("akshare") == 3
    assert trust_level("stub") == 4  # 未注册源保守按 L4
    assert trust_level("whatever") == 4


def test_compare_field_pass_within_tolerance() -> None:
    cmp = compare_field("close", "100.0000", "100.0500", source_a="stub", source_b="exchange")
    assert cmp.outcome == "pass"  # 0.05% < 0.1% 容差
    assert cmp.winner == "exchange"  # 容差内也记录高等级源（读取侧选源依据）


def test_compare_field_fail_levels_differ_auto_resolved() -> None:
    cmp = compare_field("close", "100.0000", "106.0000", source_a="stub", source_b="exchange")
    assert cmp.outcome == "fail"
    assert cmp.winner == "exchange"  # L1 > L4 → 自动消解
    assert initial_status(cmp) == "RESOLVED"


def test_compare_field_fail_same_level_unresolved() -> None:
    cmp = compare_field("close", "100.0000", "106.0000", source_a="stub", source_b="aggregator")
    assert cmp.outcome == "fail"
    assert cmp.winner is None  # 同为 L4，无法消解
    assert initial_status(cmp) == "UNRESOLVED"


def test_compare_field_skip_when_missing() -> None:
    cmp = compare_field("close", "100.0000", None, source_a="stub", source_b="exchange")
    assert cmp.outcome == "skip"
    assert cmp.deviation_pct is None


def test_compare_field_zero_denominator() -> None:
    """双侧为 0（如停牌日量）不除零，视为一致。"""
    cmp = compare_field("volume", "0", "0", source_a="stub", source_b="exchange")
    assert cmp.outcome == "pass"
    assert cmp.deviation_pct == Decimal(0)
