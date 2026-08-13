"""Documents 服务：公告/新闻采集流水线 + 查询。

事务边界在此。采集 = discover→download→内容寻址存储(sha256)→content_sha256 去重→
insert documents + document_links + FTS5 索引→audit→commit。
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.audit import service as audit_service
from wws_adviser.modules.documents import repository
from wws_adviser.modules.documents.domain import (
    NormalizedDocument,
    default_trust,
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


async def ingest_documents(
    db: DBSession,
    *,
    object_store: ObjectStore,
    provider: DocumentProvider,
    scope: DocumentScope,
    since: datetime,
    request_id: str | None = None,
) -> IngestResult:
    refs = await provider.discover(scope, since)
    instrument_id: str | None = None
    if scope.instrument is not None:
        inst = instruments_service.get_or_create_instrument(
            db, code=scope.instrument.code, market=scope.instrument.market
        )
        instrument_id = inst.id

    ingested = 0
    skipped = 0
    for ref in refs:
        raw = await provider.download(ref)
        norm = parse_document(raw)
        content_sha = hashlib.sha256(raw.content).hexdigest()
        if repository.get_by_sha256(db, content_sha) is not None:
            skipped += 1
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
            source_url=raw.source_url,
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
        ingested += 1

    audit_service.append_event(
        db,
        action="documents_ingested",
        target_type="document",
        after={"discovered": len(refs), "ingested": ingested, "skipped": skipped},
        request_id=request_id,
    )
    db.commit()
    return IngestResult(discovered=len(refs), ingested=ingested, skipped=skipped)


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


def get_document(db: DBSession, document_id: str) -> Document | None:
    return repository.get_document(db, document_id)


def search_documents(
    db: DBSession, q: str, *, kind: str | None = None, limit: int = 50
) -> list[Document]:
    return repository.search_documents(db, q, kind=kind, limit=limit)


def get_evidence(db: DBSession, evidence_id: str) -> Evidence | None:
    return repository.get_evidence(db, evidence_id)


__all__ = [
    "IngestResult",
    "NormalizedDocument",
    "get_document",
    "get_evidence",
    "ingest_documents",
    "list_documents",
    "search_documents",
]
