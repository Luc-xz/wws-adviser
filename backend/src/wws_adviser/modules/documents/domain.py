"""Documents 领域：可信等级、文档类型、文本抽取、解析。纯领域，禁框架 import。

公告/网页/新闻属不可信输入（技术架构 §17）；文本抽取按字节魔数嗅探：
PDF 走 pypdf（pdf extra 懒加载），HTML 剥标签，未知格式 UTF-8 容错解码。
"""

import base64
import html as html_lib
import re
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO

from wws_adviser.ports.document_source import RawDocument


class TrustLevel(StrEnum):
    """可信等级（PRD §9.5 / 5_DATA §6）。"""

    L1 = "L1"  # 交易所/监管/官方披露
    L2 = "L2"  # 授权行情/专业供应商
    L3 = "L3"  # 可信新闻/协会
    L4 = "L4"  # 聚合转载
    L5 = "L5"  # 社交媒体


class DocKind(StrEnum):
    ANNOUNCEMENT = "announcement"
    REPORT = "report"
    NEWS = "news"


# 按文档类型的默认可信等级（无显式来源分级时）
_DEFAULT_TRUST: dict[str, TrustLevel] = {
    DocKind.ANNOUNCEMENT.value: TrustLevel.L1,
    DocKind.REPORT.value: TrustLevel.L2,
    DocKind.NEWS.value: TrustLevel.L3,
}


def default_trust(kind: str) -> TrustLevel:
    return _DEFAULT_TRUST.get(kind, TrustLevel.L4)


@dataclass(frozen=True)
class NormalizedDocument:
    kind: str
    title: str
    text: str
    source: str
    source_url: str
    published_at: str


def extract_text(raw: RawDocument) -> str:
    """抽取纯文本：raw.text 优先；否则按 content 魔数嗅探（PDF→pypdf，HTML→剥标签）。"""
    if raw.text:
        return raw.text
    return extract_bytes_text(raw.content)


def extract_bytes_text(content: bytes) -> str:
    """原始字节 → 纯文本（魔数嗅探；未知格式按 UTF-8 容错解码）。"""
    if content[:5] == b"%PDF-":
        pdf_text = extract_pdf_text(content)
        return pdf_text if pdf_text else ""
    head = content[:512].lstrip().lower()
    if head.startswith((b"<!doctype html", b"<html")) or b"<body" in head:
        return strip_html_text(content.decode("utf-8", errors="replace"))
    return content.decode("utf-8", errors="replace")


def extract_pdf_text(content: bytes) -> str | None:
    """PDF 字节 → 文本（pypdf 懒加载，未安装/解析失败返回 None——退占位不阻断采集）。"""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(BytesIO(content))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception:  # noqa: BLE001 — 损坏 PDF 不阻断采集
        return None


_RE_SCRIPT_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_RE_BLOCK_BREAK = re.compile(r"<(?:br|/p|/div|/tr|/li|/h[1-6])\b[^>]*>", re.IGNORECASE)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_WS = re.compile("[ \t\f\v\xa0]+")


def strip_html_text(html: str) -> str:
    """HTML → 纯文本：去 script/style、块级标签换行、剥标签、还原实体、压空白。"""
    text = _RE_SCRIPT_STYLE.sub(" ", html)
    text = _RE_BLOCK_BREAK.sub("\n", text)
    text = _RE_TAG.sub(" ", text)
    text = html_lib.unescape(text)
    lines = [_RE_WS.sub(" ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def parse_document(raw: RawDocument) -> NormalizedDocument:
    """RawDocument → 标准化文档（含抽取文本）。"""
    return NormalizedDocument(
        kind=raw.kind,
        title=raw.title,
        text=extract_text(raw),
        source=raw.source,
        source_url=raw.source_url,
        published_at="",  # published_at 在 DocumentRef 上，由 service 注入
    )


# —— 游标分页（keyset：published_at desc + id desc 稳定序，offset 在插入下会漂移）——


def encode_cursor(*, published_at: str | None, document_id: str) -> str:
    """排序键 → 不透明游标（base64url）。客户端原样回传，无需理解内容。"""
    raw = f"{published_at or ''}|{document_id}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> tuple[str, str]:
    """游标 → (published_at, document_id)。格式非法抛 ValueError（API 层转 400）。

    published_at 为 NULL 的文档以 '' 参与编码，与仓储侧 COALESCE 排序口径一致。
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
    except Exception as exc:
        raise ValueError(f"游标不是合法 base64url: {exc}") from exc
    if "|" not in raw:
        raise ValueError("游标缺少分隔符")
    published_at, _, document_id = raw.rpartition("|")
    if not document_id:
        raise ValueError("游标缺少 id 段")
    return published_at, document_id
