"""identity/audit/jobs: users, sessions, audit_events, job_runs

建 4 张业务表（波2）。列类型遵循全局约定：id=CHAR(26) ULID、时间为 UTC ISO 8601 TEXT、
JSON 列用 TEXT 存字符串（SQLite 无原生 JSON 类型）。索引命名 ix_<table>_<cols>。

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-12
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # —— users ——
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )

    # —— sessions ——
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("issued_at", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.Column("revoked_at", sa.Text(), nullable=True),
        sa.Column("user_agent_hash", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_sessions_user_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    # —— audit_events（append-only，应用层 enforce 无 UPDATE 路径）——
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("actor", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=True),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column("before_summary_json", sa.Text(), nullable=True),
        sa.Column("after_summary_json", sa.Text(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("job_id", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_events_target",
        "audit_events",
        ["target_type", "target_id", "occurred_at"],
    )

    # —— job_runs ——
    op.create_table(
        "job_runs",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("business_date", sa.Text(), nullable=False),
        sa.Column("scope_key", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_until", sa.Text(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.Text(), nullable=True),
        sa.Column("started_at", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.Text(), nullable=True),
        sa.Column("result_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_type",
            "business_date",
            "scope_key",
            "config_version",
            name="uq_job_runs_idem",
        ),
    )
    op.create_index("ix_job_runs_status_lease", "job_runs", ["status", "lease_until"])
    op.create_index("ix_job_runs_idempotency_key", "job_runs", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_job_runs_idempotency_key", table_name="job_runs")
    op.drop_index("ix_job_runs_status_lease", table_name="job_runs")
    op.drop_table("job_runs")
    op.drop_index("ix_audit_events_target", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("users")
