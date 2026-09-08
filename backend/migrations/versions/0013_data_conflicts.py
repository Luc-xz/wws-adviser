"""data_conflicts（Phase 3 / 3.3 多源交叉验证，2_DATA_MODEL §6.7 · 5_DATA §6）。

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

# 每源一行保留原始值（market_records UNIQUE 含 source），本表只记字段级冲突。
# status：OPEN（待消解）/ RESOLVED（已选源）/ UNRESOLVED（无法消解，advice 持续 PAUSE）。


def upgrade() -> None:
    op.create_table(
        "data_conflicts",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("instrument_id", sa.String(length=26), nullable=False),
        sa.Column("business_date", sa.Text(), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("source_a", sa.Text(), nullable=False),
        sa.Column("source_b", sa.Text(), nullable=False),
        sa.Column("value_a", sa.Text(), nullable=False),
        sa.Column("value_b", sa.Text(), nullable=False),
        sa.Column("comparison", sa.Text(), nullable=False, server_default="fail"),
        sa.Column("resolved_by", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.UniqueConstraint(
            "instrument_id",
            "business_date",
            "field",
            "source_a",
            "source_b",
            name="uq_data_conflicts_key",
        ),
    )
    op.create_index(
        "ix_data_conflicts_instrument_status", "data_conflicts", ["instrument_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_data_conflicts_instrument_status", table_name="data_conflicts")
    op.drop_table("data_conflicts")
