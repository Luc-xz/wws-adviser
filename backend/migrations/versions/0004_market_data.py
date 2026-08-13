"""market_data: trading_calendar, market_records, nav_records

建 3 张行情表（波2 / 工作项 1.2）。列类型遵循全局约定：id=CHAR(26) ULID、时间为 UTC
ISO 8601 TEXT、OHLC/NAV/volume 为无损 decimal 字符串（SQLite 行为元数据索引 + 日线序列；
完整历史另存 Parquet，见 2_DATA_MODEL §8）。索引命名 ix_<table>_<cols>。

intraday_quotes（盘中）随 Phase 2.1 引入；data_conflicts（多源）随 Phase 3.3 引入。

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-13
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # —— trading_calendar（交易日历，date 为主键）——
    op.create_table(
        "trading_calendar",
        sa.Column("date", sa.Text(), nullable=False),
        sa.Column("market", sa.Text(), nullable=False),
        sa.Column("is_trading_day", sa.Boolean(), nullable=False),
        sa.Column("session_schedule_json", sa.Text(), nullable=True),
        sa.Column("calendar_version", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("date"),
    )

    # —— market_records（日线元数据索引；OHLC 无损 decimal 串）——
    op.create_table(
        "market_records",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("instrument_id", sa.String(length=26), nullable=False),
        sa.Column("business_date", sa.Text(), nullable=False),
        sa.Column("open", sa.Text(), nullable=True),
        sa.Column("high", sa.Text(), nullable=True),
        sa.Column("low", sa.Text(), nullable=True),
        sa.Column("close", sa.Text(), nullable=True),
        sa.Column("volume", sa.Text(), nullable=True),
        sa.Column("amount", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("market_time", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.Text(), nullable=True),
        sa.Column("received_at", sa.Text(), nullable=True),
        sa.Column("source_delay_class", sa.Text(), nullable=True),
        sa.Column("quality_status", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=True),
        sa.Column("adjustment_type", sa.Text(), nullable=False, server_default="none"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["instruments.id"], name="fk_market_records_instrument_id"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "business_date",
            "source",
            "adjustment_type",
            name="uq_market_records_key",
        ),
    )
    op.create_index(
        "ix_market_records_instrument_date", "market_records", ["instrument_id", "business_date"]
    )

    # —— nav_records（基金净值）——
    op.create_table(
        "nav_records",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("instrument_id", sa.String(length=26), nullable=False),
        sa.Column("nav_date", sa.Text(), nullable=False),
        sa.Column("nav", sa.Text(), nullable=False),
        sa.Column("published_at", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("market_time", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.Text(), nullable=True),
        sa.Column("received_at", sa.Text(), nullable=True),
        sa.Column("source_delay_class", sa.Text(), nullable=True),
        sa.Column("quality_status", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["instruments.id"], name="fk_nav_records_instrument_id"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instrument_id", "nav_date", "source", name="uq_nav_records_key"),
    )
    op.create_index(
        "ix_nav_records_instrument_date", "nav_records", ["instrument_id", "nav_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_nav_records_instrument_date", table_name="nav_records")
    op.drop_table("nav_records")
    op.drop_index("ix_market_records_instrument_date", table_name="market_records")
    op.drop_table("market_records")
    op.drop_table("trading_calendar")
