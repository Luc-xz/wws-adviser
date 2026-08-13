"""Instruments 领域纯函数测试（无 DB）。"""

import pytest

from wws_adviser.modules.instruments.domain import (
    InstrumentKind,
    Market,
    infer_instrument_kind,
    infer_market,
    validate_scale,
)


@pytest.mark.parametrize(
    "code,expected",
    [
        ("600519", Market.SSE),
        ("510300", Market.SSE),  # ETF
        ("000001", Market.SZSE),
        ("300750", Market.SZSE),
        ("159915", Market.SZSE),  # ETF
        ("", Market.SSE),  # 空代码默认 SSE
    ],
)
def test_infer_market(code: str, expected: Market) -> None:
    assert infer_market(code) is expected


@pytest.mark.parametrize(
    "code,expected",
    [
        ("600519", InstrumentKind.STOCK),
        ("510300", InstrumentKind.ETF),
        ("159915", InstrumentKind.ETF),
        ("300750", InstrumentKind.STOCK),
    ],
)
def test_infer_instrument_kind(code: str, expected: InstrumentKind) -> None:
    assert infer_instrument_kind(code) is expected


def test_validate_scale_bounds() -> None:
    assert validate_scale(2) == 2
    with pytest.raises(ValueError):
        validate_scale(-1)
    with pytest.raises(ValueError):
        validate_scale(9)
