"""研究证据检索服务（Phase 3 波2，TECH §10.5 / FR-RES-004）。

检索策略（不引入独立向量数据库）：
1. 按标的/行业/文档类型/可信等级/时间做元数据过滤
2. SQLite FTS5 关键词检索（复用 documents 模块已有索引）
3. 按新鲜度、来源等级和匹配度排序
4. 对长文档按段落切片并保留定位信息（章节/行号）
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.documents import repository as documents_repository
from wws_adviser.modules.documents.models import Document, DocumentLink, Evidence
from wws_adviser.modules.instruments.models import Instrument

_logger = logging.getLogger(__name__)

# 可信等级排序权重（TECH §10.5 排序规则：来源等级 + 新鲜度）
_TRUST_WEIGHT = {"official": 3, "exchange": 3, "regulatory": 3, "news": 1, "blog": 0}
# 切片最大字符数（按段落切，超长段落再按句号切）
_SLICE_MAX_CHARS = 800


@dataclass(frozen=True)
class EvidenceSlice:
    """文档切片：一段可引用的原文 + 定位信息。"""

    evidence_id: str
    document_id: str
    title: str
    source: str
    source_url: str | None
    published_at: str | None
    trust_level: str
    slice_ref: str                  # "§3.2 L15" / "p.12" / "para:3"
    text: str                       # 切片原文
    content_hash: str               # 切片内容哈希（可复盘）
    score: float = 0.0              # 综合排序分


@dataclass(frozen=True)
class SearchResult:
    """一次检索的完整结果。"""

    query: str
    instrument_code: str | None
    total: int
    slices: list[EvidenceSlice] = field(default_factory=list)


def retrieve_evidence(
    db: DBSession,
    *,
    query: str,
    instrument_code: str | None = None,
    trust_levels: list[str] | None = None,
    since: str | None = None,
    max_results: int = 20,
) -> SearchResult:
    """检索证据：FTS5 关键词 → 元数据过滤 → 切片 → 排序。

    Args:
        query: 检索关键词（公司名/行业名/指标名）
        instrument_code: 限定标的（None = 全库）
        trust_levels: 可信等级过滤（None = 不过滤）
        since: ISO 日期，仅取此后的文档
        max_results: 最大返回切片数
    """
    # 1) FTS5 关键词检索
    docs = documents_repository.search_documents(db, query, limit=100)

    # 2) 元数据过滤
    if trust_levels:
        docs = [d for d in docs if d.trust_level in trust_levels]
    if since:
        docs = [d for d in docs if (d.published_at or "") >= since]
    if instrument_code:
        inst = db.scalar(select(Instrument).where(Instrument.code == instrument_code))
        if inst is not None:
            linked_ids = set(
                db.scalars(
                    select(DocumentLink.document_id).where(
                        DocumentLink.instrument_id == inst.id
                    )
                ).all()
            )
            docs = [d for d in docs if d.id in linked_ids or not linked_ids]

    # 3) 切片 + 评分
    all_slices: list[EvidenceSlice] = []
    for doc in docs:
        slices = slice_document(doc, query)
        all_slices.extend(slices)

    # 4) 排序（来源等级 + 新鲜度 + 关键词命中密度）
    all_slices.sort(key=lambda s: s.score, reverse=True)

    return SearchResult(
        query=query,
        instrument_code=instrument_code,
        total=len(all_slices),
        slices=all_slices[:max_results],
    )


def slice_document(doc: Document, query: str) -> list[EvidenceSlice]:
    """将文档按段落切片，保留定位信息，计算与查询的相关度。

    切片策略：按空行分段 → 超长段落按句号二次切 → 每片 ≤ _SLICE_MAX_CHARS。
    评分 = 可信等级权重 × (1 + 关键词密度 + 新鲜度加成)。
    """
    text = _load_document_text(doc)
    if not text:
        return []

    # 按段落切
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    # 超长段落按句号二次切
    chunks: list[tuple[int, str]] = []
    for para in paragraphs:
        if len(para) <= _SLICE_MAX_CHARS:
            chunks.append((len(chunks), para))
        else:
            sentences = re.split(r"(?<=[。．.!?！？])", para)
            buf = ""
            start_idx = len(chunks)
            for s in sentences:
                if len(buf) + len(s) > _SLICE_MAX_CHARS and buf:
                    chunks.append((start_idx, buf))
                    buf = s
                else:
                    buf += s
            if buf:
                chunks.append((start_idx, buf))

    # 关键词集合（用于密度计算）
    keywords = set(query.lower().split())
    if len(keywords) == 1 and len(query) > 2:
        # CJK 单词：按字切
        keywords = {query[i:i+2] for i in range(len(query) - 1)}

    trust_w = _TRUST_WEIGHT.get(doc.trust_level, 1)
    freshness = _freshness_bonus(doc.published_at)

    out: list[EvidenceSlice] = []
    for _idx, (para_idx, chunk) in enumerate(chunks):
        density = _keyword_density(chunk, keywords)
        if density == 0 and len(chunks) > 5:
            continue  # 大文档跳过无命中的段落
        score = trust_w * (1 + density + freshness)
        content_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()[:32]
        out.append(EvidenceSlice(
            evidence_id=new_id(),
            document_id=doc.id,
            title=doc.title,
            source=doc.source,
            source_url=doc.source_url,
            published_at=doc.published_at,
            trust_level=doc.trust_level,
            slice_ref=f"para:{para_idx + 1}",
            text=chunk,
            content_hash=content_hash,
            score=round(score, 3),
        ))
    return out


def _load_document_text(doc: Document) -> str | None:
    """从磁盘加载文档正文。text_path 优先，fallback title。"""
    if doc.text_path:
        try:
            from pathlib import Path
            p = Path(doc.text_path)
            if p.exists():
                return p.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            _logger.warning("读文档正文失败 %s: %s", doc.id, exc)
    return doc.title  # fallback：标题作为可用文本


def _keyword_density(text: str, keywords: set[str]) -> float:
    """关键词密度：命次数 / 文本长度（归一化 0-10）。"""
    if not keywords or not text:
        return 0.0
    lower = text.lower()
    hits = sum(lower.count(k) for k in keywords)
    return min(10.0, hits * 10.0 / max(len(lower), 1))


def _freshness_bonus(published_at: str | None) -> float:
    """新鲜度加成：30 天内 +0.5，90 天内 +0.2，更早 +0。"""
    if not published_at:
        return 0.0
    from datetime import date
    try:
        pub = date.fromisoformat(published_at[:10])
    except ValueError:
        return 0.0
    days = (date.today() - pub).days
    if days <= 30:
        return 0.5
    if days <= 90:
        return 0.2
    return 0.0


def persist_evidence(
    db: DBSession,
    slices: list[EvidenceSlice],
) -> list[str]:
    """将检索结果持久化为 Evidence 记录（供报告引用回查）。"""
    now = now_utc_iso()
    ids = []
    for s in slices:
        db.add(Evidence(
            id=s.evidence_id,
            document_id=s.document_id,
            slice_ref=s.slice_ref,
            trust_level=s.trust_level,
            content_hash=s.content_hash,
            created_at=now, updated_at=now,
        ))
        ids.append(s.evidence_id)
    db.commit()
    return ids
