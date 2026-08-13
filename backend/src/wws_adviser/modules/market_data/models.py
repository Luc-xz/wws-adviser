"""Market data ORM：trading_calendar、market_records、nav_records（波2，2_DATA_MODEL §6.4）。

OHLC/NAV/volume 存无损 decimal 字符串；SQLite 行为元数据索引 + 日线序列，完整历史另存
Parquet（2_DATA_MODEL §8）。intraday_quotes / data_conflicts 随后续波次引入。
"""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from wws_adviser.core.db import Base


class TradingCalendar(Base):
    __tablename__ = "trading_calendar"

    date: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    market: Mapped[str] = mapped_column(sa.Text, nullable=False)
    is_trading_day: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    session_schedule_json: Mapped[str | None] = mapped_column(sa.Text)
    calendar_version: Mapped[str | None] = mapped_column(sa.Text)


class MarketRecord(Base):
    __tablename__ = "market_records"
    __table_args__ = (
        sa.UniqueConstraint(
            "instrument_id",
            "business_date",
            "source",
            "adjustment_type",
            name="uq_market_records_key",
        ),
        sa.Index("ix_market_records_instrument_date", "instrument_id", "business_date"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(
        sa.String(26), sa.ForeignKey("instruments.id"), nullable=False
    )
    business_date: Mapped[str] = mapped_column(sa.Text, nullable=False)
    open: Mapped[str | None] = mapped_column(sa.Text)
    high: Mapped[str | None] = mapped_column(sa.Text)
    low: Mapped[str | None] = mapped_column(sa.Text)
    close: Mapped[str | None] = mapped_column(sa.Text)
    volume: Mapped[str | None] = mapped_column(sa.Text)
    amount: Mapped[str | None] = mapped_column(sa.Text)
    source: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(sa.Text)
    market_time: Mapped[str | None] = mapped_column(sa.Text)
    fetched_at: Mapped[str | None] = mapped_column(sa.Text)
    received_at: Mapped[str | None] = mapped_column(sa.Text)
    source_delay_class: Mapped[str | None] = mapped_column(sa.Text)
    quality_status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(sa.Text)
    adjustment_type: Mapped[str] = mapped_column(sa.Text, nullable=False, default="none")
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)


class NavRecord(Base):
    __tablename__ = "nav_records"
    __table_args__ = (
        sa.UniqueConstraint("instrument_id", "nav_date", "source", name="uq_nav_records_key"),
        sa.Index("ix_nav_records_instrument_date", "instrument_id", "nav_date"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(
        sa.String(26), sa.ForeignKey("instruments.id"), nullable=False
    )
    nav_date: Mapped[str] = mapped_column(sa.Text, nullable=False)
    nav: Mapped[str] = mapped_column(sa.Text, nullable=False)
    published_at: Mapped[str | None] = mapped_column(sa.Text)
    source: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(sa.Text)
    market_time: Mapped[str | None] = mapped_column(sa.Text)
    fetched_at: Mapped[str | None] = mapped_column(sa.Text)
    received_at: Mapped[str | None] = mapped_column(sa.Text)
    source_delay_class: Mapped[str | None] = mapped_column(sa.Text)
    quality_status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
