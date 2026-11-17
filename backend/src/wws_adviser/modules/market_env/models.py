"""Market env ORM：市场环境数据域五表（ADR-0014 / 2_DATA_MODEL §6.8）。

研究上下文数据域，与持仓域物理隔离（不关联 instruments）。点位/比例/金额按
2_DATA §5 精度规则存无损 decimal 字符串。
"""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from wws_adviser.core.db import Base


class MarketEnvIndex(Base):
    """指数注册表（代码为规范代码 PK；symbol 映射 JSON 由领域注册表播种 upsert）。"""

    __tablename__ = "market_env_indices"

    code: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    market_group: Mapped[str] = mapped_column(sa.Text, nullable=False)
    symbol_map_json: Mapped[str | None] = mapped_column(sa.Text)
    has_pre_post: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)


class IndexQuote(Base):
    """指数快照时序（append + 同键 upsert；两市成交额读取侧由 amount 汇总）。"""

    __tablename__ = "index_quotes"
    __table_args__ = (
        sa.UniqueConstraint("index_code", "market_time", "source", name="uq_index_quotes_key"),
        sa.Index("ix_index_quotes_code_time", "index_code", "market_time"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    index_code: Mapped[str] = mapped_column(
        sa.Text, sa.ForeignKey("market_env_indices.code"), nullable=False
    )
    market_time: Mapped[str] = mapped_column(sa.Text, nullable=False)
    price: Mapped[str] = mapped_column(sa.Text, nullable=False)
    change_pct: Mapped[str] = mapped_column(sa.Text, nullable=False)
    volume: Mapped[str | None] = mapped_column(sa.Text)
    amount: Mapped[str | None] = mapped_column(sa.Text)
    pre_market_price: Mapped[str | None] = mapped_column(sa.Text)
    pre_market_change_pct: Mapped[str | None] = mapped_column(sa.Text)
    post_market_price: Mapped[str | None] = mapped_column(sa.Text)
    post_market_change_pct: Mapped[str | None] = mapped_column(sa.Text)
    source: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(sa.Text)
    fetched_at: Mapped[str | None] = mapped_column(sa.Text)
    received_at: Mapped[str | None] = mapped_column(sa.Text)
    source_delay_class: Mapped[str | None] = mapped_column(sa.Text)
    quality_status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)


class IndexBar(Base):
    """指数日 K（SQLite 直存，量小不引 Parquet——2_DATA §6.8 注）。"""

    __tablename__ = "index_bars"
    __table_args__ = (
        sa.UniqueConstraint("index_code", "business_date", "source", name="uq_index_bars_key"),
        sa.Index("ix_index_bars_code_date", "index_code", "business_date"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    index_code: Mapped[str] = mapped_column(
        sa.Text, sa.ForeignKey("market_env_indices.code"), nullable=False
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
    fetched_at: Mapped[str | None] = mapped_column(sa.Text)
    quality_status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)


class SectorBoard(Base):
    """板块注册（行业/概念；每次采集 upsert，东财板块代码漂移由本表吸收）。"""

    __tablename__ = "sector_boards"

    board_code: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)


class SectorFlowSnapshot(Base):
    """板块资金流快照时序（append + 同键 upsert）。"""

    __tablename__ = "sector_flow_snapshots"
    __table_args__ = (
        sa.UniqueConstraint("board_code", "snapshot_at", "kind", name="uq_sector_flow_key"),
        sa.Index("ix_sector_flow_kind_time", "kind", "snapshot_at"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    board_code: Mapped[str] = mapped_column(
        sa.Text, sa.ForeignKey("sector_boards.board_code"), nullable=False
    )
    kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    snapshot_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    change_pct: Mapped[str | None] = mapped_column(sa.Text)
    turnover: Mapped[str | None] = mapped_column(sa.Text)
    net_main_inflow: Mapped[str | None] = mapped_column(sa.Text)
    leader_code: Mapped[str | None] = mapped_column(sa.Text)
    leader_name: Mapped[str | None] = mapped_column(sa.Text)
    source: Mapped[str] = mapped_column(sa.Text, nullable=False)
    quality_status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
