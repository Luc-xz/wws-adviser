"""Documents 采集 + FTS5 检索闭环测试（stub DocumentProvider → object_store → FTS；AC-02）。"""

import asyncio
from datetime import UTC, datetime

from wws_adviser.infrastructure.data_sources.stub_document import StubDocumentProvider
from wws_adviser.infrastructure.storage.local_object_store import LocalObjectStore
from wws_adviser.modules.documents import service as docs_service
from wws_adviser.modules.instruments import service as instruments_service
from wws_adviser.ports.document_source import DocumentScope
from wws_adviser.ports.market_data import InstrumentRef


def _scope(code: str = "600519") -> DocumentScope:
    return DocumentScope(instrument=InstrumentRef(code=code, market="SSE", kind="stock"))


async def test_ingest_documents_content_addressed_and_fts(db_session, tmp_path) -> None:
    store = LocalObjectStore(tmp_path)
    provider = StubDocumentProvider(env="test")
    # 预置标的（document_links FK）
    inst = instruments_service.get_or_create_instrument(db_session, code="600519")
    db_session.commit()

    result = await docs_service.ingest_documents(
        db_session,
        object_store=store,
        provider=provider,
        scope=_scope("600519"),
        since=datetime.min.replace(tzinfo=UTC),
    )
    assert result.discovered == 1
    assert result.ingested == 1
    assert result.skipped == 0

    # 文档落库 + 内容寻址文件落盘
    docs = docs_service.list_documents(db_session, instrument_id=inst.id)
    assert len(docs) == 1
    d = docs[0]
    assert d.kind == "announcement"
    assert d.trust_level == "L1"
    assert d.content_sha256
    assert store.exists(d.local_path or "")
    assert store.exists(d.text_path or "")

    # FTS5 命中
    hits = docs_service.search_documents(db_session, "公告")
    assert len(hits) == 1
    assert hits[0].id == d.id
    # 无关词不命中
    assert docs_service.search_documents(db_session, "zzzznotfound") == []


async def test_ingest_dedup_by_content_sha256(db_session, tmp_path) -> None:
    store = LocalObjectStore(tmp_path)
    provider = StubDocumentProvider(env="test")
    instruments_service.get_or_create_instrument(db_session, code="600519")
    db_session.commit()
    since = datetime.min.replace(tzinfo=UTC)
    # 同一标的二次采集 → content_sha256 相同 → skipped
    await docs_service.ingest_documents(
        db_session, object_store=store, provider=provider, scope=_scope("600519"), since=since
    )
    r2 = await docs_service.ingest_documents(
        db_session, object_store=store, provider=provider, scope=_scope("600519"), since=since
    )
    assert r2.discovered == 1
    assert r2.ingested == 0
    assert r2.skipped == 1
    assert len(docs_service.list_documents(db_session)) == 1


def test_documents_http_endpoints(migrated_client) -> None:
    """HTTP：经 app.state stub 采集后，GET /documents、/search、/{id} 可读。"""
    app = migrated_client.app
    with app.state.session_factory() as db:
        instruments_service.get_or_create_instrument(db, code="600519")
        db.commit()
        asyncio.run(
            docs_service.ingest_documents(
                db,
                object_store=app.state.object_store,
                provider=app.state.document_provider,
                scope=_scope("600519"),
                since=datetime.min.replace(tzinfo=UTC),
            )
        )

    listing = migrated_client.get("/api/v1/documents").json()
    assert len(listing["items"]) == 1
    doc_id = listing["items"][0]["id"]
    assert listing["items"][0]["local_path"]

    detail = migrated_client.get(f"/api/v1/documents/{doc_id}").json()
    assert detail["id"] == doc_id
    assert detail["text_path"]

    search = migrated_client.get("/api/v1/documents/search", params={"q": "公告"}).json()
    assert len(search["items"]) == 1
    assert search["items"][0]["id"] == doc_id

    miss = migrated_client.get("/api/v1/documents/search", params={"q": "nomatch"}).json()
    assert miss["items"] == []
