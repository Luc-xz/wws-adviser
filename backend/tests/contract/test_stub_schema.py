"""契约测试：stub 满足统一 schema（step 6）+ cassette 骨架可加载（step 1）。

5_DATA_INGESTION_AND_QUALITY.md §9 的 6 步流程中，波 3 落地 step 1（cassette 骨架）
与 step 6（stub 满足 schema）；解析/突变/新鲜度/冲突留 Phase 1 接真实适配器。
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from wws_adviser.infrastructure.data_sources.stub_quote import StubQuoteProvider
from wws_adviser.ports.market_data import InstrumentRef, RawQuote, SourceDelayClass

_CASSETTES = Path(__file__).parent / "cassettes"
_WRAPPER_FIELDS = [
    "source",
    "source_url",
    "market_time",
    "fetched_at",
    "received_at",
    "source_delay_class",
]


async def test_stub_quote_satisfies_unified_schema() -> None:
    """step 6：stub 返回的合成 RawQuote 满足统一 schema。"""
    provider = StubQuoteProvider(env="test")
    quotes = await provider.fetch_quotes(
        [InstrumentRef(code="600519", market="SSE", kind="stock")]
    )
    assert len(quotes) == 1
    q: RawQuote = quotes[0]
    assert q.source == "stub"
    for f in _WRAPPER_FIELDS:
        assert getattr(q, f) not in (None, ""), f"缺 wrapper 字段 {f}"
    assert isinstance(q.source_delay_class, SourceDelayClass)
    assert isinstance(q.price, Decimal)
    assert isinstance(q.change_pct, Decimal)


def test_stub_quote_rejects_prod() -> None:
    with pytest.raises(RuntimeError):
        StubQuoteProvider(env="prod")


def test_cassette_quote_ok_loadable_and_sanitized() -> None:
    """step 1：cassette 骨架可解析、已脱敏、含 6 wrapper 字段。"""
    data = json.loads(
        (_CASSETTES / "market_data" / "quote_ok.json").read_text(encoding="utf-8")
    )
    assert data["port"] == "QuoteProvider"
    assert data["sanitized"] is True
    for f in _WRAPPER_FIELDS:
        assert f in data["response"]
