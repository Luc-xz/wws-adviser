"""Market data 领域纯函数 + akshare 行映射测试（无 DB、无网络）。"""

import sys
from datetime import date
from decimal import Decimal

import pytest

from wws_adviser.modules.market_data.domain import (
    BarParseError,
    QualityStatus,
    assign_quality_status,
    is_daily_complete,
    parse_bars,
    parse_nav,
)
from wws_adviser.ports.market_data import (
    BarRow,
    RawDataset,
    RawNAV,
    SourceDelayClass,
)


def _ds(bars: list[BarRow]) -> RawDataset:
    return RawDataset(
        source="stub",
        source_url="u",
        market_time="t",
        fetched_at="t",
        received_at="t",
        source_delay_class=SourceDelayClass.END_OF_DAY,
        bars=bars,
    )


def test_parse_bars_valid_and_quantize() -> None:
    bars = [
        BarRow(
            date=date(2026, 8, 13),
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            volume=Decimal("1000"),
        )
    ]
    out = parse_bars(_ds(bars), price_scale=2, qty_scale=0)
    assert len(out) == 1
    assert out[0].close == Decimal("101.00")  # 量化到 2 位
    assert out[0].open == Decimal("100.00")
    assert out[0].volume == Decimal("1000")  # qty_scale=0


def test_parse_bars_ohlc_illegal_raises() -> None:
    bars = [
        BarRow(  # open(100) > high(99) 非法
            date=date(2026, 8, 13),
            open=Decimal("100"),
            high=Decimal("99"),
            low=Decimal("98"),
            close=Decimal("99"),
            volume=Decimal("1000"),
        )
    ]
    with pytest.raises(BarParseError):
        parse_bars(_ds(bars))


def test_parse_nav_quantize() -> None:
    raw = RawNAV(
        source="stub",
        source_url="u",
        market_time="t",
        fetched_at="t",
        received_at="t",
        source_delay_class=SourceDelayClass.END_OF_DAY,
        nav=Decimal("1.234567"),
        published_at="2026-08-13",
    )
    out = parse_nav(raw, nav_scale=6)
    assert out.nav == Decimal("1.234567")


def test_assign_quality_status() -> None:
    d = date(2026, 8, 13)
    assert (
        assign_quality_status(latest_bar_date=None, expected_trading_day=d)
        is QualityStatus.MISSING
    )
    assert (
        assign_quality_status(latest_bar_date=d, expected_trading_day=d) is QualityStatus.OK
    )
    assert (
        assign_quality_status(latest_bar_date=date(2026, 8, 10), expected_trading_day=d)
        is QualityStatus.DELAYED
    )


def test_is_daily_complete() -> None:
    assert is_daily_complete(date(2026, 8, 13), date(2026, 8, 13)) is True
    assert is_daily_complete(None, date(2026, 8, 13)) is False
    assert is_daily_complete(date(2026, 8, 12), date(2026, 8, 13)) is False


# —— akshare 行映射纯函数 ——


def test_akshare_rows_to_dataset() -> None:
    from wws_adviser.infrastructure.data_sources.akshare_bar import rows_to_dataset

    rows = [
        {
            "日期": "2026-08-13",
            "开盘": "100",
            "最高": "102",
            "最低": "99",
            "收盘": "101",
            "成交量": "1000",
        }
    ]
    ds = rows_to_dataset(rows, source="akshare", source_url="u")
    assert ds.source == "akshare"
    assert len(ds.bars) == 1
    assert ds.bars[0].close == Decimal("101")
    assert ds.bars[0].date == date(2026, 8, 13)


def test_akshare_rows_to_nav_picks_as_of() -> None:
    from wws_adviser.infrastructure.data_sources.akshare_nav import rows_to_nav

    rows = [
        {"净值日期": "2026-08-12", "单位净值": "1.10"},
        {"净值日期": "2026-08-13", "单位净值": "1.234567"},
    ]
    nav = rows_to_nav(rows, source="akshare", source_url="u", as_of=date(2026, 8, 13))
    assert nav.nav == Decimal("1.234567")
    assert nav.published_at == "2026-08-13"


def test_akshare_rows_to_quote_filters_code() -> None:
    from wws_adviser.infrastructure.data_sources.akshare_quote import rows_to_quote

    rows = [
        {"代码": "600519", "最新价": "1800.50", "涨跌幅": "1.23", "成交量": "10000"},
        {"代码": "000001", "最新价": "11.20", "涨跌幅": "0.5", "成交量": "100"},
    ]
    q = rows_to_quote(rows, code="600519", market_time="t")
    assert q is not None
    assert q.price == Decimal("1800.50")
    assert q.change_pct == Decimal("1.23")
    assert rows_to_quote(rows, code="999999", market_time="t") is None


def test_akshare_modules_import_lazily() -> None:
    """模块导入不触发 akshare 导入（无 optional extra 也能 import）。"""
    sys.modules.pop("akshare", None)
    import wws_adviser.infrastructure.data_sources.akshare_bar  # noqa: F401
    import wws_adviser.infrastructure.data_sources.akshare_nav  # noqa: F401
    import wws_adviser.infrastructure.data_sources.akshare_quote  # noqa: F401

    assert "akshare" not in sys.modules
