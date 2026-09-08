"""research_tasks + research_reports（Phase 3 / FR-RES-001~004）。

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_tasks",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("task_type", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("peer_codes_json", sa.Text(), nullable=True),
        sa.Column("time_span", sa.Text(), nullable=True),
        sa.Column("depth", sa.Text(), nullable=False, server_default="standard"),
        sa.Column("status", sa.Text(), nullable=False, server_default="PENDING"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("started_at", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.Text(), nullable=True),
        sa.Column("report_id", sa.String(length=26), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_research_tasks_user_created", "research_tasks", ["user_id", "created_at"])
    op.create_index("ix_research_tasks_status", "research_tasks", ["status"])

    op.create_table(
        "research_reports",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("task_id", sa.String(length=26), nullable=False),
        sa.Column("report_type", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("content_json_path", sa.Text(), nullable=True),
        sa.Column("content_md_path", sa.Text(), nullable=True),
        sa.Column("citations_json", sa.Text(), nullable=True),
        sa.Column("generation_config_json", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.id"]),
    )
    op.create_index("ix_research_reports_task", "research_reports", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_research_reports_task", table_name="research_reports")
    op.drop_table("research_reports")
    op.drop_index("ix_research_tasks_status", table_name="research_tasks")
    op.drop_index("ix_research_tasks_user_created", table_name="research_tasks")
    op.drop_table("research_tasks")
