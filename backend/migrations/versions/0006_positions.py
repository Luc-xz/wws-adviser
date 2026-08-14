"""positions: position_snapshots

建持仓快照表（波4 / 工作项 1.4）。移动加权平均成本法（MWAC）的每日快照：数量/可用、
avg_cost/realized_pnl/unrealized_pnl/market_value 为定标整数分（+ *_scale 列），quantity/weight
为无损 decimal 字符串。算法版本列保证可复现/可追溯（技术架构 §9.1、2_DATA_MODEL §6.2）。

reconciliation_adjustments（对账流）随后续波次引入。

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-13
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "position_snapshots",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("account_id", sa.String(length=26), nullable=False),
        sa.Column("instrument_id", sa.String(length=26), nullable=False),
        sa.Column("business_date", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Text(), nullable=False),
        sa.Column("available_qty", sa.Text(), nullable=False),
        sa.Column("avg_cost_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_cost_scale", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("realized_pnl_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("realized_pnl_scale", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("unrealized_pnl_minor", sa.Integer(), nullable=True),
        sa.Column("unrealized_pnl_scale", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("market_value_minor", sa.Integer(), nullable=True),
        sa.Column("market_value_scale", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("weight", sa.Text(), nullable=True),
        sa.Column("cost_method_version", sa.Text(), nullable=False),
        sa.Column("snapshot_algo_version", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], name="fk_position_snapshots_account_id"),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["instruments.id"], name="fk_position_snapshots_instrument_id"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id", "instrument_id", "business_date", name="uq_position_snapshots_key"
        ),
    )
    op.create_index(
        "ix_position_snapshots_account_date", "position_snapshots", ["account_id", "business_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_position_snapshots_account_date", table_name="position_snapshots")
    op.drop_table("position_snapshots")
