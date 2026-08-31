"""signals + signal_calibrations（Phase 2 波6 / FR-ANL-003）。

signals 为版本化信号定义；signal_calibrations 每信号版本一条最新校准结论
（p 区间/b/n_eff/校准状态/Platt 修正）。p 只在回测/校准服务内写入，
Decimal 以字符串存储（与 market_records 同约定）。

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-24
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signals",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("signal_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("signal_class", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("lookback_days", sa.Integer(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("cost_bps", sa.Integer(), nullable=False),
        sa.Column("universe", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("signal_id", "version", name="uq_signals_id_version"),
    )
    op.create_table(
        "signal_calibrations",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("signal_def_id", sa.String(length=26), nullable=False),
        sa.Column("signal_id", sa.Text(), nullable=False),
        sa.Column("signal_version", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("calibrated_on", sa.Text(), nullable=False),
        sa.Column("expires_on", sa.Text(), nullable=False),
        sa.Column("p_low", sa.Text(), nullable=False),
        sa.Column("p_mid", sa.Text(), nullable=False),
        sa.Column("p_high", sa.Text(), nullable=False),
        sa.Column("b", sa.Text(), nullable=False),
        sa.Column("n_eff", sa.Integer(), nullable=False),
        sa.Column("n_eff_oos", sa.Integer(), nullable=False),
        sa.Column("reliability_passed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("platt_a", sa.Float(), nullable=True),
        sa.Column("platt_b", sa.Float(), nullable=True),
        sa.Column("notes_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["signal_def_id"], ["signals.id"]),
        sa.UniqueConstraint("signal_def_id", "signal_version", name="uq_calibrations_def_version"),
    )
    op.create_index("ix_calibrations_state", "signal_calibrations", ["state"])


def downgrade() -> None:
    op.drop_index("ix_calibrations_state", table_name="signal_calibrations")
    op.drop_table("signal_calibrations")
    op.drop_table("signals")
