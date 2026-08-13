"""Documents 领域纯函数 + akshare 行映射测试（无 DB、无网络）。"""

import sys

from wws_adviser.modules.documents.domain import (
    DocKind,
    TrustLevel,
    default_trust,
    extract_text,
    parse_document,
)
from wws_adviser.ports.document_source import RawDocument
from wws_adviser.ports.market_data import SourceDelayClass


def _raw(text: str | None = "正文", content: bytes | None = None) -> RawDocument:
    return RawDocument(
        source="stub",
        source_url="stub://ann/600519",
        market_time="t",
        fetched_at="t",
        received_at="t",
        source_delay_class=SourceDelayClass.DELAYED,
        kind="announcement",
        title="测试公告",
        content=content if content is not None else b"\xe5\x8e\x9f\xe6\x96\x87",  # "原文"
        text=text,
    )


def test_trust_level_ordering_and_default() -> None:
    assert default_trust("announcement") is TrustLevel.L1
    assert default_trust("report") is TrustLevel.L2
    assert default_trust("news") is TrustLevel.L3
    assert default_trust("unknown") is TrustLevel.L4
    # 枚举可排序（L1 最高）
    assert TrustLevel.L1 < TrustLevel.L5


def test_extract_text_prefers_raw_text() -> None:
    assert extract_text(_raw(text="显式文本")) == "显式文本"


def test_extract_text_falls_back_to_content() -> None:
    raw = _raw(text=None, content="备份解码".encode())
    assert extract_text(raw) == "备份解码"


def test_parse_document() -> None:
    norm = parse_document(_raw(text="正文内容"))
    assert norm.kind == "announcement"
    assert norm.title == "测试公告"
    assert norm.text == "正文内容"


def test_akshare_rows_to_document_ref() -> None:
    from wws_adviser.infrastructure.data_sources.akshare_document import rows_to_document_ref

    rows = [
        {
            "公告标题": "关于分红",
            "公告时间": "2026-08-13",
            "网址": "http://x/1",
            "公告类型": "announcement",
        },
        {"公告标题": "", "公告时间": "2026-08-12"},  # 无标题 → 跳过
    ]
    refs = rows_to_document_ref(rows)
    assert len(refs) == 1
    assert refs[0].title == "关于分红"
    assert refs[0].published_at == "2026-08-13"
    assert refs[0].source_url == "http://x/1"


def test_akshare_module_imports_lazily() -> None:
    sys.modules.pop("akshare", None)
    import wws_adviser.infrastructure.data_sources.akshare_document  # noqa: F401

    assert "akshare" not in sys.modules


def test_dockind_enum() -> None:
    assert DocKind.ANNOUNCEMENT.value == "announcement"
