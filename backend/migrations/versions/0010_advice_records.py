"""advice_records：盘中建议记录（Phase 2 / FR-REV-003 数据快照）。

每次建议（发布/降级）一条：区间、原因链、调整轨迹与证据引用。
Decimal 字符串存储（与 market_records 同约定）。

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-24
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "advice_records",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("signal_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.Column("f_min", sa.Text(), nullable=True),
        sa.Column("f_max", sa.Text(), nullable=True),
        sa.Column("value_min", sa.Text(), nullable=True),
        sa.Column("value_max", sa.Text(), nullable=True),
        sa.Column("suggested_lots", sa.Integer(), nullable=True),
        sa.Column("reasons_json", sa.Text(), nullable=True),
        sa.Column("trail_json", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.Text(), nullable=True),
        sa.Column("invalidated", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_advice_records_user_created", "advice_records", ["user_id", "created_at"])
    op.create_index("ix_advice_records_signal", "advice_records", ["signal_id"])


def downgrade() -> None:
    op.drop_index("ix_advice_records_signal", table_name="advice_records")
    op.drop_index("ix_advice_records_user_created", table_name="advice_records")
    op.drop_table("advice_records")
