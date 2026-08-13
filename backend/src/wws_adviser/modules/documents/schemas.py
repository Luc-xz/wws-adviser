"""Documents DTO。"""

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: str
    kind: str
    title: str
    issuer: str | None = None
    published_at: str | None = None
    source: str
    source_url: str | None = None
    trust_level: str
    quality_status: str
    local_path: str | None = None
    text_path: str | None = None


class DocumentListResponse(BaseModel):
    items: list[DocumentOut]
    # TODO(波后续): 游标分页（当前 limit 截断）


class DocumentSearchResponse(BaseModel):
    q: str
    items: list[DocumentOut]


class EvidenceOut(BaseModel):
    id: str
    document_id: str
    claim_text: str | None = None
    trust_level: str
    cited_at: str | None = None


class IngestResponse(BaseModel):
    discovered: int
    ingested: int
    skipped: int
