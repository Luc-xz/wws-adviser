"""Documents 仓储：文档元数据 CRUD + document_links + content_sha256 去重 + FTS5。

FTS5 documents_fts 为 contentless 虚拟表（content=''）：仅维护索引、不存正文。
create_fts_if_missing 供测试在 Base.metadata.create_all 之后补建虚拟表（生产由迁移建）。
"""

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as DBSession

from wws_adviser.modules.documents.models import Document, DocumentLink, Evidence


def _segment_cjk(s: str) -> str:
    """CJK 按字分词：在 CJK 字符两侧插空格，让 unicode61 按字建索引（FTS5 无内置中文分词）。"""
    import re

    return re.sub(r"([\u4e00-\u9fff])", r" \1 ", s)

_FTS5_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5("
    "title, body_text, content=''"
    ")"
)


def create_fts_if_missing(engine: Engine) -> None:
    """建 documents_fts 虚拟表（若不存在）。测试 fixture 用。"""
    with engine.begin() as conn:
        conn.execute(text(_FTS5_DDL))


def index_document_fts(
    db: DBSession, document_id: str, title: str, body_text: str
) -> None:
    """把一行文档索引进 contentless FTS5（正文不入库，仅进索引）。

    FTS5 rowid 必须为整数；用 documents 的隐式整数 rowid（PK 为 ULID 字符串，故表另有隐式 rowid）。
    """
    rid = db.execute(
        text("SELECT rowid FROM documents WHERE id = :id"), {"id": document_id}
    ).scalar()
    db.execute(
        text("INSERT INTO documents_fts (rowid, title, body_text) VALUES (:r, :t, :b)"),
        {"r": rid, "t": _segment_cjk(title), "b": _segment_cjk(body_text)},
    )


# —— documents ——


def get_by_sha256(db: DBSession, content_sha256: str) -> Document | None:
    return db.scalar(
        select(Document).where(Document.content_sha256 == content_sha256)
    )


def get_document(db: DBSession, document_id: str) -> Document | None:
    return db.get(Document, document_id)


def add_document(db: DBSession, doc: Document) -> Document:
    db.add(doc)
    db.flush()
    return doc


def add_link(db: DBSession, document_id: str, instrument_id: str, link_type: str) -> None:
    db.merge(
        DocumentLink(
            document_id=document_id, instrument_id=instrument_id, link_type=link_type
        )
    )


def list_documents(
    db: DBSession,
    *,
    kind: str | None = None,
    instrument_id: str | None = None,
    since: str | None = None,
    trust_level: str | None = None,
    limit: int = 50,
) -> list[Document]:
    stmt = select(Document)
    if kind is not None:
        stmt = stmt.where(Document.kind == kind)
    if since is not None:
        stmt = stmt.where(Document.published_at >= since)
    if trust_level is not None:
        stmt = stmt.where(Document.trust_level == trust_level)
    if instrument_id is not None:
        link_ids = select(DocumentLink.document_id).where(
            DocumentLink.instrument_id == instrument_id
        )
        stmt = stmt.where(Document.id.in_(link_ids))
    stmt = stmt.order_by(Document.published_at.desc(), Document.id.desc()).limit(limit)
    return list(db.scalars(stmt))


def list_documents_page(
    db: DBSession,
    *,
    kind: str | None = None,
    instrument_id: str | None = None,
    since: str | None = None,
    trust_level: str | None = None,
    cursor_published_at: str | None = None,
    cursor_document_id: str | None = None,
    limit: int = 50,
) -> tuple[list[Document], bool]:
    """keyset 分页：(COALESCE(published_at,''), id) 双键倒序，返回 (items, has_more)。

    NULL published_at 以 '' 参与排序与游标比较，保证游标序与排序序一致；
    多取一行判定 has_more，不暴露 offset。
    """
    stmt = select(Document)
    if kind is not None:
        stmt = stmt.where(Document.kind == kind)
    if since is not None:
        stmt = stmt.where(Document.published_at >= since)
    if trust_level is not None:
        stmt = stmt.where(Document.trust_level == trust_level)
    if instrument_id is not None:
        link_ids = select(DocumentLink.document_id).where(
            DocumentLink.instrument_id == instrument_id
        )
        stmt = stmt.where(Document.id.in_(link_ids))
    sort_key = func.coalesce(Document.published_at, "")
    if cursor_published_at is not None and cursor_document_id is not None:
        stmt = stmt.where(
            or_(
                sort_key < cursor_published_at,
                and_(sort_key == cursor_published_at, Document.id < cursor_document_id),
            )
        )
    stmt = stmt.order_by(sort_key.desc(), Document.id.desc()).limit(limit + 1)
    rows = list(db.scalars(stmt))
    return rows[:limit], len(rows) > limit


def search_documents(
    db: DBSession,
    q: str,
    *,
    kind: str | None = None,
    limit: int = 50,
) -> list[Document]:
    """FTS5 MATCH → 命中 rowid → join documents 隐式 rowid 回查元数据（可叠加 kind 过滤）。

    q 以引号包裹防 FTS 语法错/注入；CJK 按字分词后作短语查询。
    """
    import re

    seg = re.sub(r"\s+", " ", _segment_cjk(q).strip())
    safe = '"' + seg.replace('"', '""') + '"'
    ids = list(
        db.execute(
            text(
                "SELECT d.id FROM documents_fts f "
                "JOIN documents d ON d.rowid = f.rowid "
                "WHERE documents_fts MATCH :q"
            ),
            {"q": safe},
        ).scalars()
    )
    if not ids:
        return []
    stmt = select(Document).where(Document.id.in_(ids))
    if kind is not None:
        stmt = stmt.where(Document.kind == kind)
    stmt = stmt.order_by(Document.published_at.desc()).limit(limit)
    return list(db.scalars(stmt))


# —— evidence ——


def get_evidence(db: DBSession, evidence_id: str) -> Evidence | None:
    return db.get(Evidence, evidence_id)
