"""market_env 市场环境数据域五表（ADR-0014 / 2_DATA §6.8 / 5_DATA §13）。

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

# 纯新增表（无破坏性）：指数注册表 + 指数快照/日K 时序 + 板块注册/资金流快照。
# 外键 RESTRICT（防误删注册行导致时序孤儿）；回滚 = 五表全删（时序数据可重采）。


def upgrade() -> None:
    op.create_table(
        "market_env_indices",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("market_group", sa.Text(), nullable=False),
        sa.Column("symbol_map_json", sa.Text(), nullable=True),
        sa.Column("has_pre_post", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_table(
        "index_quotes",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("index_code", sa.Text(), nullable=False),
        sa.Column("market_time", sa.Text(), nullable=False),
        sa.Column("price", sa.Text(), nullable=False),
        sa.Column("change_pct", sa.Text(), nullable=False),
        sa.Column("volume", sa.Text(), nullable=True),
        sa.Column("amount", sa.Text(), nullable=True),
        sa.Column("pre_market_price", sa.Text(), nullable=True),
        sa.Column("pre_market_change_pct", sa.Text(), nullable=True),
        sa.Column("post_market_price", sa.Text(), nullable=True),
        sa.Column("post_market_change_pct", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.Text(), nullable=True),
        sa.Column("received_at", sa.Text(), nullable=True),
        sa.Column("source_delay_class", sa.Text(), nullable=True),
        sa.Column("quality_status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["index_code"], ["market_env_indices.code"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("index_code", "market_time", "source", name="uq_index_quotes_key"),
    )
    op.create_index(
        "ix_index_quotes_code_time", "index_quotes", ["index_code", "market_time"]
    )
    op.create_table(
        "index_bars",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("index_code", sa.Text(), nullable=False),
        sa.Column("business_date", sa.Text(), nullable=False),
        sa.Column("open", sa.Text(), nullable=True),
        sa.Column("high", sa.Text(), nullable=True),
        sa.Column("low", sa.Text(), nullable=True),
        sa.Column("close", sa.Text(), nullable=True),
        sa.Column("volume", sa.Text(), nullable=True),
        sa.Column("amount", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.Text(), nullable=True),
        sa.Column("quality_status", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["index_code"], ["market_env_indices.code"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "index_code", "business_date", "source", name="uq_index_bars_key"
        ),
    )
    op.create_index(
        "ix_index_bars_code_date", "index_bars", ["index_code", "business_date"]
    )
    op.create_table(
        "sector_boards",
        sa.Column("board_code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("board_code"),
    )
    op.create_table(
        "sector_flow_snapshots",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("board_code", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("snapshot_at", sa.Text(), nullable=False),
        sa.Column("change_pct", sa.Text(), nullable=True),
        sa.Column("turnover", sa.Text(), nullable=True),
        sa.Column("net_main_inflow", sa.Text(), nullable=True),
        sa.Column("leader_code", sa.Text(), nullable=True),
        sa.Column("leader_name", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("quality_status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["board_code"], ["sector_boards.board_code"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("board_code", "snapshot_at", "kind", name="uq_sector_flow_key"),
    )
    op.create_index(
        "ix_sector_flow_kind_time", "sector_flow_snapshots", ["kind", "snapshot_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_sector_flow_kind_time", table_name="sector_flow_snapshots")
    op.drop_table("sector_flow_snapshots")
    op.drop_table("sector_boards")
    op.drop_index("ix_index_bars_code_date", table_name="index_bars")
    op.drop_table("index_bars")
    op.drop_index("ix_index_quotes_code_time", table_name="index_quotes")
    op.drop_table("index_quotes")
    op.drop_table("market_env_indices")
