"""Documents ORM：documents、document_links、evidence（波3，2_DATA_MODEL §6.5）。

FTS5 虚拟表 documents_fts 无 ORM 模型（由迁移/测试以 raw SQL 建 + 维护）。
"""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from wws_adviser.core.db import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        sa.UniqueConstraint("content_sha256", name="uq_documents_content_sha256"),
        sa.Index("ix_documents_kind_published", "kind", "published_at"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    title: Mapped[str] = mapped_column(sa.Text, nullable=False)
    issuer: Mapped[str | None] = mapped_column(sa.Text)
    published_at: Mapped[str | None] = mapped_column(sa.Text)
    source: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(sa.Text)
    content_sha256: Mapped[str] = mapped_column(sa.Text, nullable=False)
    local_path: Mapped[str | None] = mapped_column(sa.Text)
    text_path: Mapped[str | None] = mapped_column(sa.Text)
    trust_level: Mapped[str] = mapped_column(sa.Text, nullable=False)
    fetched_at: Mapped[str | None] = mapped_column(sa.Text)
    quality_status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)


class DocumentLink(Base):
    __tablename__ = "document_links"
    __table_args__ = (sa.Index("ix_document_links_instrument", "instrument_id"),)

    document_id: Mapped[str] = mapped_column(
        sa.String(26), sa.ForeignKey("documents.id"), primary_key=True
    )
    instrument_id: Mapped[str] = mapped_column(
        sa.String(26), sa.ForeignKey("instruments.id"), primary_key=True
    )
    link_type: Mapped[str] = mapped_column(sa.Text, primary_key=True)


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (sa.Index("ix_evidence_document", "document_id"),)

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        sa.String(26), sa.ForeignKey("documents.id"), nullable=False
    )
    source_record_id: Mapped[str | None] = mapped_column(sa.Text)
    slice_ref: Mapped[str | None] = mapped_column(sa.Text)
    claim_text: Mapped[str | None] = mapped_column(sa.Text)
    cited_at: Mapped[str | None] = mapped_column(sa.Text)
    trust_level: Mapped[str] = mapped_column(sa.Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
