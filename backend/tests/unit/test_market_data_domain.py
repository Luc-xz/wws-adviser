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


def test_akshare_secid_for() -> None:
    from wws_adviser.infrastructure.data_sources.akshare_quote import secid_for

    assert secid_for("SSE", "600519") == "1.600519"
    assert secid_for("SZSE", "000001") == "0.000001"
    assert secid_for("SSE", "510300") == "1.510300"
    assert secid_for("", "600519") == "1.600519"  # 市场缺失按前缀推断
    assert secid_for("", "300750") == "0.300750"


def test_akshare_payload_to_quote() -> None:
    from wws_adviser.infrastructure.data_sources.akshare_quote import payload_to_quote

    data = {"f43": 1307.78, "f170": 2.75, "f47": 31000, "f48": 4050000000}
    q = payload_to_quote(data, code="600519", market_time="t")
    assert q is not None
    assert q.price == Decimal("1307.78")
    assert q.change_pct == Decimal("2.75")
    # 停牌（无价占位 "-"）与空 data → None
    assert payload_to_quote({"f43": "-"}, code="600519", market_time="t") is None
    assert payload_to_quote(None, code="600519", market_time="t") is None


def test_akshare_modules_import_lazily() -> None:
    """模块导入不触发 akshare 导入（无 optional extra 也能 import）。"""
    sys.modules.pop("akshare", None)
    import wws_adviser.infrastructure.data_sources.akshare_bar  # noqa: F401
    import wws_adviser.infrastructure.data_sources.akshare_nav  # noqa: F401
    import wws_adviser.infrastructure.data_sources.akshare_quote  # noqa: F401

    assert "akshare" not in sys.modules


def test_tencent_quote_parsing() -> None:
    """腾讯实时行情文本解析：现价/昨收自算涨跌幅；停牌（价 0）→ None。"""
    from decimal import Decimal as D

    from wws_adviser.infrastructure.data_sources.akshare_quote import (
        tencent_symbol,
        tencent_text_to_quote,
    )

    sample = 'v_sh510500="1~中证500ETF南方~510500~7.825~7.726~7.732~3344444~..."'
    q = tencent_text_to_quote(sample, code="510500", market_time="t")
    assert q is not None
    assert q.price == D("7.825")
    assert q.source == "tencent"
    expected = (D("7.825") - D("7.726")) / D("7.726") * 100
    assert q.change_pct == expected
    # 停牌：现价 0 → None
    halted = 'v_sz159558="51~半导体E~159558~0.000~1.100~0.000~0~..."'
    assert tencent_text_to_quote(halted, code="159558", market_time="t") is None

    assert tencent_symbol("SSE", "510500") == "sh510500"
    assert tencent_symbol("SZSE", "159558") == "sz159558"
    assert tencent_symbol("", "600519") == "sh600519"


def test_tencent_bars_row_mapping() -> None:
    """腾讯日线行结构 → rows_to_dataset 中文列（日期/开收高低/量）。"""
    from wws_adviser.infrastructure.data_sources.akshare_bar import rows_to_dataset

    rows = [
        {"日期": "2026-08-25", "开盘": "7.663", "收盘": "7.726",
         "最高": "7.777", "最低": "7.594", "成交量": "3782961"},
    ]
    ds = rows_to_dataset(rows, source="tencent", source_url="tencent://bars/x")
    assert len(ds.bars) == 1
    b = ds.bars[0]
    assert b.date.isoformat() == "2026-08-25"
    assert b.open == Decimal("7.663") and b.close == Decimal("7.726")
    assert b.high == Decimal("7.777") and b.low == Decimal("7.594")


# —— 交易日兜底 + 日历同步（技术债清理）——


def test_weekday_trading_fallback() -> None:
    from datetime import date

    from wws_adviser.modules.market_data.domain import weekday_trading_fallback

    assert weekday_trading_fallback(date(2026, 8, 28)) is True   # 周五
    assert weekday_trading_fallback(date(2026, 8, 31)) is True   # 周一
    assert weekday_trading_fallback(date(2026, 8, 29)) is False  # 周六（实测误生成日）
    assert weekday_trading_fallback(date(2026, 8, 30)) is False  # 周日


def test_akshare_calendar_rows_to_days() -> None:
    from datetime import date

    from wws_adviser.infrastructure.data_sources.akshare_calendar import rows_to_days

    rows = [
        {"trade_date": "2026-08-28"},
        {"trade_date": date(2026, 8, 31)},   # akshare 可能返回 date 对象
        {"trade_date": "2026-08-31 00:00:00"},  # 带时间后缀
        {"trade_date": ""},                  # 空 → 跳过
        {"other": 1},                        # 缺列 → 跳过
    ]
    assert rows_to_days(rows) == [date(2026, 8, 28), date(2026, 8, 31)]


def test_calendar_sync_service_idempotent(db_session) -> None:
    from datetime import date

    from wws_adviser.modules.market_data import repository as md_repository
    from wws_adviser.modules.market_data import service as market_service

    start, end = date(2026, 8, 24), date(2026, 8, 31)  # 含周末 + 8/31 周一
    trading = [date(2026, 8, d) for d in (24, 25, 26, 27, 28, 31)]
    n1 = market_service.sync_trading_calendar(
        db_session, trading_days=trading, start=start, end=end
    )
    assert n1 == 8
    cal = md_repository.get_calendar(db_session, "2026-08-29")
    assert cal is not None and cal.is_trading_day is False   # 周六显式落库
    assert md_repository.get_calendar(db_session, "2026-08-31").is_trading_day is True
    # 幂等：重跑行数一致，无重复行
    n2 = market_service.sync_trading_calendar(
        db_session, trading_days=trading, start=start, end=end
    )
    assert n2 == 8
    assert len(list(db_session.query(md_repository.TradingCalendar).all())) == 8


def test_market_phase_state_machine() -> None:
    from datetime import datetime

    from wws_adviser.modules.market_data.domain import market_phase

    cases = [
        ("09:00", "pre_open", "09:15"),   # 盘前
        ("09:20", "auction", "09:30"),    # 集合竞价
        ("10:00", "open", "11:30"),       # 上午连续竞价
        ("12:00", "lunch_break", "13:00"),  # 午休
        ("14:30", "open", "15:00"),       # 下午连续竞价
        ("15:30", "closed", None),        # 收盘后（当日无边界）
    ]
    for t, phase, nxt in cases:
        now = datetime.fromisoformat(f"2026-09-02T{t}:00+08:00")
        assert market_phase(now, is_trading_day=True) == (phase, _t(nxt) if nxt else None), t
    # 非交易日：任何时刻都是 non_trading_day
    now = datetime.fromisoformat("2026-09-02T10:00:00+08:00")
    assert market_phase(now, is_trading_day=False) == ("non_trading_day", None)


def _t(s: str):
    from datetime import time

    h, m = s.split(":")
    return time(int(h), int(m))
