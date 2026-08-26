"""Documents 领域：可信等级、文档类型、文本抽取、解析。纯领域，禁框架 import。

公告/网页/新闻属不可信输入（技术架构 §17）；文本抽取 MVP 直取 raw.text 或解码 content，
结构化 PDF/HTML 解析留后续波次。
"""

import base64
from dataclasses import dataclass
from enum import StrEnum

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
    """抽取纯文本：优先 raw.text；否则解码 content（MVP；PDF/HTML 解析留后续）。"""
    if raw.text:
        return raw.text
    return raw.content.decode("utf-8", errors="replace")


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
