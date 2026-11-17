"""契约测试：market_env 四源 cassette（5_DATA §9 step 1/2/3 + §13.6）。

- step 1：cassette 可加载、已脱敏（三份线上实录 + 一份 niuone 格式钉住）；
- step 2：cassette 喂适配器 parse 阶段 → 统一 schema（RawIndexQuote/RawSectorFlow/RawDataset）；
- step 3：schema 突变（删字段/改类型）→ 结构化 MarketEnvParseError，不抛不透明异常。
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from wws_adviser.infrastructure.market_env._parsing import (
    MarketEnvParseError,
    normalize_market_time,
)
from wws_adviser.infrastructure.market_env.eastmoney_index_bar import (
    parse_eastmoney_kline_payload,
)
from wws_adviser.infrastructure.market_env.eastmoney_sector_flow import (
    parse_eastmoney_clist_payload,
)
from wws_adviser.infrastructure.market_env.sina_index_quote import parse_sina_global_text
from wws_adviser.infrastructure.market_env.tencent_index_quote import (
    parse_tencent_index_text,
)
from wws_adviser.modules.market_env.domain import INDEX_REGISTRY, parse_index_quote
from wws_adviser.ports.market_env import SectorKind

_CASSETTES = Path(__file__).parent / "cassettes" / "market_env"


def _load(name: str) -> dict:
    return json.loads((_CASSETTES / name).read_text(encoding="utf-8"))


# —— step 1：可加载 + 已脱敏 ——


@pytest.mark.parametrize(
    ("name", "port"),
    [
        ("tencent_index_quotes_ok.json", "IndexQuoteProvider"),
        ("sina_global_ok.json", "IndexQuoteProvider"),
        ("eastmoney_index_kline_ok.json", "IndexBarProvider"),
        ("eastmoney_sector_flow_ok.json", "SectorFlowProvider"),
        ("sina_futures_ok.json", "IndexQuoteProvider"),
    ],
)
def test_cassette_loadable_and_sanitized(name: str, port: str) -> None:
    data = _load(name)
    assert data["port"] == port
    assert data["sanitized"] is True
    assert data["recorded"]
    assert "text" in data["response"] or "payload" in data["response"]


# —— step 2：cassette → 统一 schema ——


def test_tencent_cassette_parses_to_unified_schema() -> None:
    text = _load("tencent_index_quotes_ok.json")["response"]["text"]
    quotes = parse_tencent_index_text(text, list(INDEX_REGISTRY))
    assert len(quotes) == 10  # 10 个注册 symbol 全命中
    by_code = {q.code: q for q in quotes}
    # A 股：斜杠三元组成交额（元）被采信
    sh = by_code["cn_sh000001"]
    assert sh.price == Decimal("3602.57")
    assert sh.amount == Decimal("706214352273")
    assert sh.market_time == "2026-11-16 16:06:27"  # 14 位紧凑 → 归一
    assert sh.change_pct == pytest.approx(Decimal("-0.8739"), abs=Decimal("0.001"))
    # 美股：USD 币种位不冒充成交额；时间带横杠归一
    dji = by_code["us_dji"]
    assert dji.amount == Decimal("0")
    assert dji.market_time == "2026-11-13 16:43:26"
    # 港股：斜杠时间归一
    assert by_code["hk_hsi"].market_time == "2026/11/16 15:51:27".replace("/", "-")
    # 全部过领域标准化（价格非正抛错的路径不触发）
    for q in quotes:
        nq = parse_index_quote(q)
        assert nq.price > 0


def test_sina_cassette_parses_to_unified_schema() -> None:
    text = _load("sina_global_ok.json")["response"]["text"]
    quotes = parse_sina_global_text(text, list(INDEX_REGISTRY))
    by_code = {q.code: q for q in quotes}
    assert set(by_code) == {"hk_hsi", "hk_hstech", "kr_kospi", "jp_n225",
                            "us_dji", "us_ixic", "us_inx"}  # 空 b_N225 被跳过
    assert by_code["hk_hsi"].price == Decimal("23749.129")
    assert by_code["kr_kospi"].market_time == "2026-11-16 14:32:50"
    assert by_code["jp_n225"].price == Decimal("44946.64")  # int_ 族仅 4 字段
    assert by_code["us_dji"].market_time == "2026-11-14 05:43:43"


def test_eastmoney_kline_cassette_parses_to_unified_schema() -> None:
    payload = _load("eastmoney_index_kline_ok.json")["response"]["payload"]
    ds = parse_eastmoney_kline_payload(payload, source_url="eastmoney://index-bars/cn_sh000001")
    assert ds.source == "eastmoney"
    assert len(ds.bars) == 5
    first = ds.bars[0]
    # klines 行序为 日期,开,收,高,低,量——按位映射不可颠倒
    assert first.date == date(2026, 11, 10)
    assert first.open == Decimal("3682.04")
    assert first.close == Decimal("3663.72")
    assert first.high == Decimal("3683.73")
    assert first.low == Decimal("3660.72")
    assert all(b.low <= b.high for b in ds.bars)


def test_eastmoney_sector_flow_cassette_parses_to_unified_schema() -> None:
    payload = _load("eastmoney_sector_flow_ok.json")["response"]["payload"]
    flows = parse_eastmoney_clist_payload(
        payload, kind=SectorKind.INDUSTRY, source_url="eastmoney://sector-flows/industry"
    )
    assert len(flows) == 3
    bank = flows[0]
    assert bank.board_code == "BK0475"
    assert bank.net_main_inflow == Decimal("3567000000.0")
    assert bank.leader_name == "工商银行"
    assert bank.market_time  # f124 unix 秒 → 上海时区
    # 缺失值 "-" → 0/None，不冒充数据
    semi = flows[1]
    assert semi.leader_name is None
    assert flows[2].change_pct == Decimal("0")
    for f in flows:
        assert isinstance(f.source, str)


# —— step 3：schema 突变 → 结构化解析错误（不抛不透明异常） ——


def test_tencent_mutation_short_row_skipped_not_crash() -> None:
    text = 'v_sh000001="1~上证指数~000001";\n'  # 行被截断
    assert parse_tencent_index_text(text, list(INDEX_REGISTRY)) == []


def test_sina_mutation_unregistered_symbol_ignored() -> None:
    text = 'var hq_str_gb_unknown="x";\n'
    assert parse_sina_global_text(text, list(INDEX_REGISTRY)) == []


def test_eastmoney_kline_mutation_raises_typed_error() -> None:
    payload = _load("eastmoney_index_kline_ok.json")["response"]["payload"]
    payload["data"]["klines"] = ["2026-11-16,bad"]  # 字段不足
    with pytest.raises(MarketEnvParseError):
        parse_eastmoney_kline_payload(payload, source_url="x")
    del payload["data"]["klines"]  # 节点消失
    with pytest.raises(MarketEnvParseError):
        parse_eastmoney_kline_payload(payload, source_url="x")


def test_eastmoney_sector_flow_mutation_raises_typed_error() -> None:
    payload = _load("eastmoney_sector_flow_ok.json")["response"]["payload"]
    del payload["data"]["diff"]
    with pytest.raises(MarketEnvParseError):
        parse_eastmoney_clist_payload(payload, kind=SectorKind.CONCEPT, source_url="x")
    payload["data"]["diff"] = [{"f14": "无名板块"}]  # 缺 f12
    with pytest.raises(MarketEnvParseError):
        parse_eastmoney_clist_payload(payload, kind=SectorKind.CONCEPT, source_url="x")


# —— 共享时间归一助手 ——


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("20261116155127", "2026-11-16 15:51:27"),
        ("2026-11-13 16:43:26", "2026-11-13 16:43:26"),
        ("2026/11/16 15:36:28", "2026-11-16 15:36:28"),
        ("2026-11-16,14:32:50", "2026-11-16 14:32:50"),
        ("", None),
    ],
)
def test_normalize_market_time(raw: str, expected: str | None) -> None:
    assert normalize_market_time(raw) == expected


def test_sina_futures_cassette_parses_to_unified_schema() -> None:
    """美股指数期货（盘前参考，hf_ 族）：涨跌幅以 最新/昨结 自算。"""
    text = _load("sina_futures_ok.json")["response"]["text"]
    quotes = parse_sina_global_text(text, list(INDEX_REGISTRY))
    by_code = {q.code: q for q in quotes}
    assert set(by_code) == {"fut_es", "fut_nq", "fut_ym"}
    es = by_code["fut_es"]
    assert es.price == Decimal("7560.925")
    # (7560.925 - 7583.000) / 7583.000 * 100 ≈ -0.2913
    assert es.change_pct == pytest.approx(Decimal("-0.2913"), abs=Decimal("0.001"))
    assert es.market_time == "2026-11-16 17:36:09"
    assert by_code["fut_ym"].price == Decimal("52478.900")
