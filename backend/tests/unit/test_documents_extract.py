"""公告正文抽取测试（Phase 3 后续：PDF/HTML 魔数嗅探 + 纯函数抽取）。"""

from wws_adviser.modules.documents.domain import (
    extract_bytes_text,
    extract_pdf_text,
    extract_text,
    strip_html_text,
)
from wws_adviser.ports.document_source import RawDocument
from wws_adviser.ports.market_data import SourceDelayClass

_NOW = "2026-09-10T00:00:00Z"


def _mini_pdf(text: str) -> bytes:
    """构造最小合法 PDF（单页 Helvetica Tj），xref 偏移逐对象计算。"""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
    ]
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects.append(
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
        + stream + b"\nendstream"
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF"
    ).encode("ascii")
    return bytes(out)


def test_extract_pdf_text_roundtrip() -> None:
    pdf = _mini_pdf("Hello PDF 123")
    assert extract_pdf_text(pdf) == "Hello PDF 123"


def test_extract_bytes_text_pdf_sniff() -> None:
    assert "Hello PDF 123" in extract_bytes_text(_mini_pdf("Hello PDF 123"))


def test_extract_bytes_text_corrupt_pdf_returns_empty() -> None:
    assert extract_bytes_text(b"%PDF-1.4 broken garbage") == ""


def test_strip_html_text() -> None:
    html = (
        "<html><head><style>body{color:red}</style></head>"
        "<body><script>alert(1)</script>"
        "<p>营业收入&nbsp;增长 15%</p><div>净利润&nbsp;增长 20%</div>"
        "</body></html>"
    )
    text = strip_html_text(html)
    assert "营业收入 增长 15%" in text  # 实体还原 + 空白压缩
    assert "净利润 增长 20%" in text
    assert "alert" not in text and "color:red" not in text  # script/style 剥除
    assert text.count("\n") >= 1  # 块级标签换行


def test_extract_bytes_text_html_sniff() -> None:
    content = "<!DOCTYPE html><html><body><p>营业数据</p></body></html>".encode()
    assert extract_bytes_text(content) == "营业数据"


def test_extract_bytes_text_plain_utf8() -> None:
    assert extract_bytes_text("纯文本内容".encode()) == "纯文本内容"


def test_extract_text_prefers_raw_text() -> None:
    raw = RawDocument(
        source="akshare", source_url="https://x", market_time=_NOW, fetched_at=_NOW,
        received_at=_NOW, source_delay_class=SourceDelayClass.DELAYED,
        kind="announcement", title="t",
        content=_mini_pdf("Hello PDF 123"), text="显式文本优先",
    )
    assert extract_text(raw) == "显式文本优先"


def test_extract_text_from_pdf_content() -> None:
    raw = RawDocument(
        source="akshare", source_url="https://x", market_time=_NOW, fetched_at=_NOW,
        received_at=_NOW, source_delay_class=SourceDelayClass.DELAYED,
        kind="announcement", title="t",
        content=_mini_pdf("Hello PDF 123"), text="",
    )
    assert "Hello PDF 123" in extract_text(raw)
