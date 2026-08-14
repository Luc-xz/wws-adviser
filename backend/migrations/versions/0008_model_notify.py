"""model_gateway + notifications + app_settings: model_profiles, model_calls, notifications, app_settings

建 4 表（波6 / 工作项 1.6）。model_profiles.key_ref 只存 env 变量名（密钥绝不落库，
8_SECURITY §5）；notifications 以 (channel,event_type,payload_hash) 幂等；app_settings
存非敏感可调项（/settings/* PATCH 持久化，写审计）。

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-14
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # —— model_profiles（路由 + 参数 + key 引用）——
    op.create_table(
        "model_profiles",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("key_ref", sa.Text(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("timeout", sa.Float(), nullable=True),
        sa.Column("retry", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("task_routes_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_model_profiles_name"),
    )

    # —— model_calls（调用审计；key 绝不出现）——
    op.create_table(
        "model_calls",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("job_run_id", sa.String(length=26), nullable=True),
        sa.Column("model_profile_id", sa.String(length=26), nullable=False),
        sa.Column("task_type", sa.Text(), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("prompt_hash", sa.Text(), nullable=False),
        sa.Column("input_evidence_ids_json", sa.Text(), nullable=True),
        sa.Column("started_at", sa.Text(), nullable=False),
        sa.Column("ended_at", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["job_run_id"], ["job_runs.id"], name="fk_model_calls_job_run_id"),
        sa.ForeignKeyConstraint(
            ["model_profile_id"], ["model_profiles.id"], name="fk_model_calls_model_profile_id"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_calls_job_run", "model_calls", ["job_run_id"])
    op.create_index(
        "ix_model_calls_profile_started", "model_calls", ["model_profile_id", "started_at"]
    )

    # —— notifications（幂等：channel+event_type+payload_hash）——
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_at", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "channel", "event_type", "payload_hash", name="uq_notifications_idem"
        ),
    )

    # —— app_settings（非敏感可调项，/settings/* PATCH 持久化）——
    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_table("notifications")
    op.drop_index("ix_model_calls_profile_started", table_name="model_calls")
    op.drop_index("ix_model_calls_job_run", table_name="model_calls")
    op.drop_table("model_calls")
    op.drop_table("model_profiles")
