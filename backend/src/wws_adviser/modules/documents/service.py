"""Documents 服务：公告/新闻采集流水线 + 查询。

事务边界在此。采集 = discover→download→内容寻址存储(sha256)→content_sha256 去重→
insert documents + document_links + FTS5 索引→audit→commit。
"""

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.audit import service as audit_service
from wws_adviser.modules.collections import service as collections_service
from wws_adviser.modules.documents import repository
from wws_adviser.modules.documents.domain import (
    DocKind,
    NormalizedDocument,
    default_trust,
    encode_cursor,
    parse_document,
)
from wws_adviser.modules.documents.models import Document, Evidence
from wws_adviser.modules.instruments import service as instruments_service
from wws_adviser.ports.document_source import DocumentProvider, DocumentScope
from wws_adviser.ports.object_store import ObjectStore


@dataclass(frozen=True)
class IngestResult:
    discovered: int
    ingested: int
    skipped: int
    updated: int = 0


def _category_of_kind(kind: str | None) -> str:
    """文档类型 → 观测类别（news 单列——FR-DATA-005 仅 stub，面板如实区分）。"""
    return "news" if kind == DocKind.NEWS.value else "document"


async def ingest_documents(
    db: DBSession,
    *,
    object_store: ObjectStore,
    provider: DocumentProvider,
    scope: DocumentScope,
    since: datetime,
    request_id: str | None = None,
    run_id: str | None = None,
) -> IngestResult:
    """公告/新闻采集：discover→download→内容寻址→去重→入库→FTS→观测（5_DATA §12）。

    每篇文档一条 ingest_items（ingested/updated/skipped_dup）；单篇失败整批上抛
    （与既有语义一致：批次不落半程），失败观测先 rollback 再单独提交。
    """
    code = scope.instrument.code if scope.instrument is not None else None
    display_scope = f"{code} 公告" if code else "公告采集"
    instrument_id: str | None = None
    if scope.instrument is not None:
        inst = instruments_service.get_or_create_instrument(
            db, code=scope.instrument.code, market=scope.instrument.market
        )
        instrument_id = inst.id

    try:
        refs = await provider.discover(scope, since)
    except Exception as exc:  # noqa: BLE001 — 源失败先落观测再上抛
        collections_service.record_failure(
            db, category="document", run_id=run_id, target_ref=f"scope:{code or 'all'}",
            display_name=f"{display_scope}（发现阶段）", error_code=type(exc).__name__,
            error_message=str(exc),
        )
        raise

    ingested = 0
    skipped = 0
    updated = 0
    for ref in refs:
        t0 = time.perf_counter()
        display = f"{code} {ref.title}" if code else ref.title
        try:
            raw = await provider.download(ref)
            norm = parse_document(raw)
            content_sha = hashlib.sha256(raw.content).hexdigest()
            dup = repository.get_by_sha256(db, content_sha)
            if dup is not None:
                skipped += 1
                collections_service.record_item(
                    db, category=_category_of_kind(ref.kind), run_id=run_id,
                    target_ref=f"document:{content_sha[:12]}", display_name=display,
                    action="skipped", status="SKIPPED", source=raw.source,
                    duration_ms=int((time.perf_counter() - t0) * 1000),
                    data_ref=f"doc:{dup.id}",
                )
                continue
            # 同源同 URL 已存在（标题占位 → 真实正文等场景）：原行就地升级，防同公告重复入库
            existing = repository.get_by_source_url(db, raw.source, ref.source_url)
            if existing is not None:
                old_text: str | None = None
                if existing.text_path:
                    try:
                        old_text = object_store.get(existing.text_path).decode("utf-8")
                    except Exception:  # noqa: BLE001 — 原文不可得则跳 FTS 删除（宁陈旧不损坏）
                        old_text = None
                old_title = existing.title
                local_path = object_store.put(raw.content, kind=ref.kind, ext="bin")
                text_path = object_store.put(norm.text.encode("utf-8"), kind="text", ext="txt")
                now = now_utc_iso()
                existing.local_path = local_path
                existing.text_path = text_path
                existing.content_sha256 = content_sha
                existing.fetched_at = raw.fetched_at
                existing.updated_at = now
                existing.version = (existing.version or 1) + 1
                repository.reindex_document_fts(
                    db, existing.id, existing.title, norm.text,
                    old_title=old_title, old_body=old_text,
                )
                updated += 1
                collections_service.record_item(
                    db, category=_category_of_kind(ref.kind), run_id=run_id,
                    target_ref=f"document:{content_sha[:12]}", display_name=display,
                    action="updated", status="OK", rows_written=1, source=raw.source,
                    duration_ms=int((time.perf_counter() - t0) * 1000),
                    data_ref=f"doc:{existing.id}",
                )
                continue
            local_path = object_store.put(raw.content, kind=ref.kind, ext="bin")
            text_path = object_store.put(norm.text.encode("utf-8"), kind="text", ext="txt")
            now = now_utc_iso()
            doc = Document(
                id=new_id(),
                kind=ref.kind,
                title=ref.title,
                issuer=None,
                published_at=ref.published_at,
                source=raw.source,
                source_url=ref.source_url,
                content_sha256=content_sha,
                local_path=local_path,
                text_path=text_path,
                trust_level=default_trust(ref.kind).value,
                fetched_at=raw.fetched_at,
                quality_status="OK",
                created_at=now,
                updated_at=now,
                version=1,
            )
            repository.add_document(db, doc)
            if instrument_id is not None:
                repository.add_link(db, doc.id, instrument_id, "subject")
            repository.index_document_fts(db, doc.id, doc.title, norm.text)
            collections_service.record_item(
                db, category=_category_of_kind(ref.kind), run_id=run_id,
                target_ref=f"document:{content_sha[:12]}", display_name=display,
                action="ingested", status="OK", rows_written=1, source=raw.source,
                duration_ms=int((time.perf_counter() - t0) * 1000),
                data_ref=f"doc:{doc.id}",
            )
            ingested += 1
        except Exception as exc:  # noqa: BLE001 — 单篇失败整批上抛，观测已落
            collections_service.record_failure(
                db, category=_category_of_kind(ref.kind), run_id=run_id,
                target_ref=f"document:{ref.source_url}", display_name=display,
                error_code=type(exc).__name__, error_message=str(exc),
                duration_ms=int((time.perf_counter() - t0) * 1000),
            )
            raise

    collections_service.record_source_success(db, "document")
    audit_service.append_event(
        db,
        action="documents_ingested",
        target_type="document",
        after={
            "discovered": len(refs), "ingested": ingested,
            "skipped": skipped, "updated": updated,
        },
        request_id=request_id,
    )
    db.commit()
    return IngestResult(
        discovered=len(refs), ingested=ingested, skipped=skipped, updated=updated
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
    return repository.list_documents(
        db,
        kind=kind,
        instrument_id=instrument_id,
        since=since,
        trust_level=trust_level,
        limit=limit,
    )


@dataclass(frozen=True)
class DocumentPage:
    items: list[Document]
    next_cursor: str | None  # null = 已到末页


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
) -> DocumentPage:
    """游标分页列表。有下一页时以最后一行的排序键编 next_cursor。"""
    items, has_more = repository.list_documents_page(
        db,
        kind=kind,
        instrument_id=instrument_id,
        since=since,
        trust_level=trust_level,
        cursor_published_at=cursor_published_at,
        cursor_document_id=cursor_document_id,
        limit=limit,
    )
    next_cursor = (
        encode_cursor(published_at=items[-1].published_at, document_id=items[-1].id)
        if has_more and items
        else None
    )
    return DocumentPage(items=items, next_cursor=next_cursor)


def get_document(db: DBSession, document_id: str) -> Document | None:
    return repository.get_document(db, document_id)


def search_documents(
    db: DBSession, q: str, *, kind: str | None = None, limit: int = 50
) -> list[Document]:
    return repository.search_documents(db, q, kind=kind, limit=limit)


def get_evidence(db: DBSession, evidence_id: str) -> Evidence | None:
    return repository.get_evidence(db, evidence_id)


__all__ = [
    "DocumentPage",
    "IngestResult",
    "NormalizedDocument",
    "get_document",
    "get_evidence",
    "ingest_documents",
    "list_documents",
    "list_documents_page",
    "search_documents",
]
