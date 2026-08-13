"""portfolio: instruments, accounts, transactions

建 3 张业务表（波1 / 工作项 1.1）。列类型遵循全局约定：id=CHAR(26) ULID、时间为 UTC
ISO 8601 TEXT、金额（cash/fee/tax）为定标整数分 + *_scale 列、price/quantity 为无损
decimal 字符串（SQLite 无原生 DECIMAL）。索引命名 ix_<table>_<cols>。

position_snapshots / pending_transactions / reconciliation_adjustments 随后续波次引入。

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-13
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # —— instruments（标的参考表，波1 建基础列）——
    op.create_table(
        "instruments",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("market", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("industry", sa.Text(), nullable=True),
        sa.Column("sector", sa.Text(), nullable=True),
        sa.Column("lot_size", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("price_scale", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("qty_scale", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("tradable", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market", "code", name="uq_instruments_market_code"),
    )
    op.create_index("ix_instruments_name", "instruments", ["name"])
    op.create_index("ix_instruments_industry", "instruments", ["industry"])

    # —— accounts（每用户单账户 MVP）——
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default="CNY"),
        sa.Column("initial_cash_minor", sa.Integer(), nullable=True),
        sa.Column("initial_cash_scale", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("current_cash_minor", sa.Integer(), nullable=True),
        sa.Column("current_cash_scale", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("total_assets", sa.Text(), nullable=True),
        sa.Column("reconciled", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("reconciled_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_accounts_user_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"])

    # —— transactions ——
    op.create_table(
        "transactions",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("account_id", sa.String(length=26), nullable=False),
        sa.Column("instrument_id", sa.String(length=26), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Text(), nullable=False),
        sa.Column("price", sa.Text(), nullable=False),
        sa.Column("fee_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fee_scale", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("tax_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tax_scale", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("trade_at", sa.Text(), nullable=False),
        sa.Column("external_ref", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], name="fk_transactions_account_id"),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["instruments.id"], name="fk_transactions_instrument_id"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_ref", name="uq_transactions_external_ref"),
        sa.UniqueConstraint("fingerprint", name="uq_transactions_fingerprint"),
    )
    op.create_index("ix_transactions_account_trade", "transactions", ["account_id", "trade_at"])
    op.create_index(
        "ix_transactions_instrument_trade", "transactions", ["instrument_id", "trade_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_instrument_trade", table_name="transactions")
    op.drop_index("ix_transactions_account_trade", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index("ix_accounts_user_id", table_name="accounts")
    op.drop_table("accounts")
    op.drop_index("ix_instruments_industry", table_name="instruments")
    op.drop_index("ix_instruments_name", table_name="instruments")
    op.drop_table("instruments")
