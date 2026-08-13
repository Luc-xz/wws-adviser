"""契约测试：bar/nav cassette 可加载（step 1）+ 喂解析层断言统一 schema（step 2）。

5_DATA_INGESTION_AND_QUALITY.md §9 的 6 步流程中，波2 落地 bar/nav 的 step 1（cassette
可加载、已脱敏）与 step 2（解析层满足统一 schema）；新鲜度/冲突留后续波次。
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from wws_adviser.modules.market_data.domain import parse_bars, parse_nav
from wws_adviser.ports.market_data import (
    BarRow,
    RawDataset,
    RawNAV,
    SourceDelayClass,
)

_CASSETTES = Path(__file__).parent / "cassettes" / "market_data"
_WRAPPER_FIELDS = [
    "source",
    "source_url",
    "market_time",
    "fetched_at",
    "received_at",
    "source_delay_class",
]


def _load(name: str) -> dict:
    return json.loads((_CASSETTES / name).read_text(encoding="utf-8"))


def test_bar_cassette_loadable_and_sanitized() -> None:
    data = _load("bar_ok.json")
    assert data["port"] == "BarProvider"
    assert data["sanitized"] is True
    resp = data["response"]
    for f in _WRAPPER_FIELDS:
        assert f in resp
    assert isinstance(resp["bars"], list) and resp["bars"]


def test_bar_cassette_parses_to_unified_schema() -> None:
    """step 2：cassette 原始响应经 parse_bars → 合法标准化日线。"""
    resp = _load("bar_ok.json")["response"]
    bars = [
        BarRow(
            date=date.fromisoformat(b["date"]),
            open=Decimal(b["open"]),
            high=Decimal(b["high"]),
            low=Decimal(b["low"]),
            close=Decimal(b["close"]),
            volume=Decimal(b["volume"]),
        )
        for b in resp["bars"]
    ]
    ds = RawDataset(
        source=resp["source"],
        source_url=resp["source_url"],
        market_time=resp["market_time"],
        fetched_at=resp["fetched_at"],
        received_at=resp["received_at"],
        source_delay_class=SourceDelayClass(resp["source_delay_class"]),
        bars=bars,
    )
    parsed = parse_bars(ds, price_scale=4, qty_scale=6)
    assert len(parsed) == 1
    assert parsed[0].close == Decimal("101.0000")
    assert parsed[0].low <= parsed[0].open <= parsed[0].high  # OHLC 合法


def test_nav_cassette_parses_to_unified_schema() -> None:
    resp = _load("nav_ok.json")["response"]
    raw = RawNAV(
        source=resp["source"],
        source_url=resp["source_url"],
        market_time=resp["market_time"],
        fetched_at=resp["fetched_at"],
        received_at=resp["received_at"],
        source_delay_class=SourceDelayClass(resp["source_delay_class"]),
        nav=Decimal(resp["nav"]),
        published_at=resp["published_at"],
    )
    parsed = parse_nav(raw, nav_scale=6)
    assert parsed.nav == Decimal("1.234567")
