"""push_subscriptions（Phase 3.5 P1，Web Push 订阅登记）。

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        # 推送端点（浏览器注册时由推送服务分配，全局唯一）
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column("revoked_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
    )
    op.create_index(
        "ix_push_subscriptions_user", "push_subscriptions", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_push_subscriptions_user", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
