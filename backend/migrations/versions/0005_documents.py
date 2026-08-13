"""documents: documents, document_links, evidence, documents_fts(FTS5)

建文档/证据表 + FTS5 contentless 虚拟表（波3 / 工作项 1.3）。列类型遵循全局约定：
id=CHAR(26) ULID、时间为 UTC ISO 8601 TEXT。documents_fts 用 contentless 模式
（content=''）：body_text 仅在采集时 INSERT 进索引、不落 documents 列，正文存 text_path
文件（2_DATA_MODEL §2「文档正文不进 SQLite」+ §6.5 FTS 外部内容）。

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-13
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_FTS5_DDL = (
    "CREATE VIRTUAL TABLE documents_fts USING fts5("
    "title, body_text, content=''"
    ")"
)


def upgrade() -> None:
    # —— documents ——
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("issuer", sa.Text(), nullable=True),
        sa.Column("published_at", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column("local_path", sa.Text(), nullable=True),
        sa.Column("text_path", sa.Text(), nullable=True),
        sa.Column("trust_level", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.Text(), nullable=True),
        sa.Column("quality_status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_sha256", name="uq_documents_content_sha256"),
    )
    op.create_index("ix_documents_kind_published", "documents", ["kind", "published_at"])

    # —— document_links（标的关联，复合主键）——
    op.create_table(
        "document_links",
        sa.Column("document_id", sa.String(length=26), nullable=False),
        sa.Column("instrument_id", sa.String(length=26), nullable=False),
        sa.Column("link_type", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name="fk_document_links_document_id"
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["instruments.id"], name="fk_document_links_instrument_id"
        ),
        sa.PrimaryKeyConstraint("document_id", "instrument_id", "link_type"),
    )
    op.create_index("ix_document_links_instrument", "document_links", ["instrument_id"])

    # —— evidence ——
    op.create_table(
        "evidence",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("document_id", sa.String(length=26), nullable=False),
        sa.Column("source_record_id", sa.Text(), nullable=True),
        sa.Column("slice_ref", sa.Text(), nullable=True),
        sa.Column("claim_text", sa.Text(), nullable=True),
        sa.Column("cited_at", sa.Text(), nullable=True),
        sa.Column("trust_level", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], name="fk_evidence_document_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_document", "evidence", ["document_id"])

    # —— documents_fts（FTS5 contentless）——
    op.execute(_FTS5_DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS documents_fts")
    op.drop_index("ix_evidence_document", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index("ix_document_links_instrument", table_name="document_links")
    op.drop_table("document_links")
    op.drop_index("ix_documents_kind_published", table_name="documents")
    op.drop_table("documents")
