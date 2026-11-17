"""DirectIndexQuoteProvider 降级链单测（腾讯主源 + 新浪补位/兜底，5_DATA §13.2）。

monkeypatch 模块级 _fetch_* 函数（不发真实网络请求）；新浪响应取自线上实录 cassette。
"""

import json
import pathlib

import pytest

import wws_adviser.infrastructure.market_env.direct_index_quote as direct_mod
from wws_adviser.infrastructure.market_env.direct_index_quote import (
    DirectIndexQuoteProvider,
)
from wws_adviser.modules.market_env.domain import INDEX_REGISTRY


def _cassette_text(name: str) -> str:
    return json.loads(
        (
            pathlib.Path(__file__).parent.parent
            / "contract"
            / "cassettes"
            / "market_env"
            / name
        ).read_text(encoding="utf-8")
    )["response"]["text"]


# 新浪兜底需同时覆盖指数族与期货族：合并两份实录 cassette
_SINA_TEXT = _cassette_text("sina_global_ok.json") + "\n" + _cassette_text("sina_futures_ok.json")


def _patch(monkeypatch, tencent_exc: Exception | None, sina_text: str | None) -> None:
    def fake_tencent(symbols):
        if tencent_exc is not None:
            raise tencent_exc
        return ""

    def fake_sina(symbols):
        if sina_text is None:
            raise RuntimeError("sina down")
        return sina_text

    monkeypatch.setattr(direct_mod, "_fetch_tencent_sync", fake_tencent)
    monkeypatch.setattr(direct_mod, "_fetch_sina_sync", fake_sina)


async def test_sina_fills_codes_without_tencent_symbol(monkeypatch) -> None:
    """日经/KOSPI 无腾讯代码 → 新浪补位；腾讯未失败时不越权兜底其覆盖的指数。"""
    _patch(monkeypatch, tencent_exc=None, sina_text=_SINA_TEXT)
    provider = DirectIndexQuoteProvider(env="test")
    quotes = await provider.fetch_index_quotes(list(INDEX_REGISTRY))
    codes = {q.code for q in quotes}
    assert {"jp_n225", "kr_kospi"} <= codes
    assert "hk_hsi" not in codes  # 腾讯正常时美股/港股不走新浪


async def test_tencent_failure_falls_back_to_sina(monkeypatch) -> None:
    """腾讯整批失败 → 新浪有映射的指数兜底（美股/港股/亚市 7 项）。"""
    _patch(monkeypatch, tencent_exc=RuntimeError("tencent reset"), sina_text=_SINA_TEXT)
    provider = DirectIndexQuoteProvider(env="test")
    quotes = await provider.fetch_index_quotes(list(INDEX_REGISTRY))
    codes = {q.code for q in quotes}
    assert {"hk_hsi", "hk_hstech", "us_dji", "us_ixic", "us_inx", "jp_n225", "kr_kospi",
            "fut_es", "fut_nq", "fut_ym"} <= codes
    assert all(q.source == "sina" for q in quotes)


async def test_both_sources_fail_raises_primary(monkeypatch) -> None:
    """主备全失败 → 上抛主源异常（可审计），不吞不抛兜底异常。"""
    _patch(monkeypatch, tencent_exc=RuntimeError("tencent reset"), sina_text=None)
    provider = DirectIndexQuoteProvider(env="test")
    with pytest.raises(RuntimeError, match="tencent reset"):
        await provider.fetch_index_quotes(list(INDEX_REGISTRY))
