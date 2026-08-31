"""/api/v1/documents 端点：列表、详情、FTS 检索、证据详情、ops 采集（3_API §3.7）。

读端点公开（与 market 读端点一致）；POST /refresh 采集为写操作，需登录(CSRF) + Idempotency-Key。
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session as DBSession

from wws_adviser.api.dependencies import (
    get_document_provider,
    get_object_store,
    get_session,
)
from wws_adviser.core.errors import DomainError, MissingIdempotencyKeyError
from wws_adviser.modules.documents import service
from wws_adviser.modules.documents.domain import decode_cursor
from wws_adviser.modules.documents.models import Document, Evidence
from wws_adviser.modules.documents.schemas import (
    DocumentListResponse,
    DocumentOut,
    DocumentSearchResponse,
    EvidenceOut,
    IngestResponse,
)
from wws_adviser.ports.document_source import DocumentProvider, DocumentScope
from wws_adviser.ports.market_data import InstrumentRef
from wws_adviser.ports.object_store import ObjectStore

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

DBDep = Annotated[DBSession, Depends(get_session)]
StoreDep = Annotated[ObjectStore, Depends(get_object_store)]
ProviderDep = Annotated[DocumentProvider, Depends(get_document_provider)]


class DocumentNotFoundError(DomainError):
    code = "NOT_FOUND"
    status = 404
    title = "文档不存在"


class InvalidCursorError(DomainError):
    code = "INVALID_CURSOR"
    status = 400
    title = "无效分页游标"


def _require_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if not idempotency_key:
        raise MissingIdempotencyKeyError()
    return idempotency_key


def _to_out(d: Document) -> DocumentOut:
    return DocumentOut(
        id=d.id,
        kind=d.kind,
        title=d.title,
        issuer=d.issuer,
        published_at=d.published_at,
        source=d.source,
        source_url=d.source_url,
        trust_level=d.trust_level,
        quality_status=d.quality_status,
        local_path=d.local_path,
        text_path=d.text_path,
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    db: DBDep,
    kind: Annotated[str | None, Query()] = None,
    instrument_id: Annotated[str | None, Query()] = None,
    since: Annotated[str | None, Query()] = None,
    trust_level: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> DocumentListResponse:
    cursor_published_at: str | None = None
    cursor_document_id: str | None = None
    if cursor:
        try:
            cursor_published_at, cursor_document_id = decode_cursor(cursor)
        except ValueError as exc:
            raise InvalidCursorError(str(exc)) from exc
    page = service.list_documents_page(
        db,
        kind=kind,
        instrument_id=instrument_id,
        since=since,
        trust_level=trust_level,
        cursor_published_at=cursor_published_at,
        cursor_document_id=cursor_document_id,
        limit=limit,
    )
    return DocumentListResponse(
        items=[_to_out(d) for d in page.items], next_cursor=page.next_cursor
    )


@router.get("/search", response_model=DocumentSearchResponse)
async def search_documents(
    db: DBDep,
    q: Annotated[str, Query()],
    kind: Annotated[str | None, Query()] = None,
    limit: int = 50,
) -> DocumentSearchResponse:
    docs = service.search_documents(db, q, kind=kind, limit=limit)
    return DocumentSearchResponse(q=q, items=[_to_out(d) for d in docs])


@router.post("/refresh", response_model=IngestResponse)
async def refresh_documents(
    request: Request,
    db: DBDep,
    object_store: StoreDep,
    provider: ProviderDep,
    _key: Annotated[str, Depends(_require_idempotency_key)],
    code: Annotated[str | None, Query()] = None,
    market: Annotated[str, Query()] = "SSE",
    kind_filter: Annotated[str | None, Query(alias="kind")] = None,
) -> IngestResponse:
    instrument = (
        InstrumentRef(code=code, market=market, kind="stock") if code else None
    )
    scope = DocumentScope(instrument=instrument, kinds=[kind_filter] if kind_filter else None)
    since = datetime.min.replace(tzinfo=UTC)
    result = await service.ingest_documents(
        db,
        object_store=object_store,
        provider=provider,
        scope=scope,
        since=since,
        request_id=request.headers.get("x-request-id"),
    )
    return IngestResponse(
        discovered=result.discovered, ingested=result.ingested, skipped=result.skipped
    )


@router.get("/evidence/{evidence_id}", response_model=EvidenceOut)
async def get_evidence(evidence_id: str, db: DBDep) -> EvidenceOut:
    ev = service.get_evidence(db, evidence_id)
    if ev is None:
        raise DocumentNotFoundError(evidence_id)
    return _evidence_to_out(ev)


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: str, db: DBDep) -> DocumentOut:
    doc = service.get_document(db, document_id)
    if doc is None:
        raise DocumentNotFoundError(document_id)
    return _to_out(doc)


def _evidence_to_out(e: Evidence) -> EvidenceOut:
    return EvidenceOut(
        id=e.id,
        document_id=e.document_id,
        claim_text=e.claim_text,
        trust_level=e.trust_level,
        cited_at=e.cited_at,
    )
