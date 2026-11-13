"""source_health + ingest_items（采集可观测性，5_DATA §12 · 3_API §3.13/§3.17）。

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

# source_health：类别级 upsert（quote/bar/nav/calendar/document/news），
# 派生状态读取侧计算不落库；ingest_items：批次条目明细（append-only，不复制 payload）。


def upgrade() -> None:
    op.create_table(
        "source_health",
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("last_success_at", sa.Text(), nullable=True),
        sa.Column("last_failure_at", sa.Text(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.Text(), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("category"),
    )
    op.create_table(
        "ingest_items",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("run_id", sa.String(length=26), nullable=True),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("target_ref", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("rows_written", sa.Integer(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("data_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["job_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingest_items_run_category", "ingest_items", ["run_id", "category"])
    op.create_index("ix_ingest_items_category_status", "ingest_items", ["category", "status"])
    op.create_index("ix_ingest_items_created", "ingest_items", ["created_at"])
    op.create_index("ix_ingest_items_target", "ingest_items", ["target_ref"])


def downgrade() -> None:
    op.drop_index("ix_ingest_items_target", table_name="ingest_items")
    op.drop_index("ix_ingest_items_created", table_name="ingest_items")
    op.drop_index("ix_ingest_items_category_status", table_name="ingest_items")
    op.drop_index("ix_ingest_items_run_category", table_name="ingest_items")
    op.drop_table("ingest_items")
    op.drop_table("source_health")
