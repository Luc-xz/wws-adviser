"""initial: app_meta 表（证明空库迁移可建机制）

Phase 0 仅建 schema 元数据表；identity/audit/jobs 等业务表在波2 迁移加入。
索引命名遵循 ix_<table>_<cols>（见 2_DATA_MODEL_AND_STORAGE.md 索引约定）。

Revision ID: 0001
Revises:
Create Date: 2026-08-12
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_meta",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index("ix_app_meta_key", "app_meta", ["key"])
    op.execute(
        "INSERT INTO app_meta (key, value, updated_at) "
        "VALUES ('schema_version', '0', '1970-01-01T00:00:00Z')"
    )


def downgrade() -> None:
    op.drop_index("ix_app_meta_key", table_name="app_meta")
    op.drop_table("app_meta")
