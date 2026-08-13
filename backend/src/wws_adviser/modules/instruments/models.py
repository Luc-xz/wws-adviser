"""Instrument ORM（instruments 表）。"""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from wws_adviser.core.db import Base


class Instrument(Base):
    __tablename__ = "instruments"
    __table_args__ = (
        sa.UniqueConstraint("market", "code", name="uq_instruments_market_code"),
        sa.Index("ix_instruments_name", "name"),
        sa.Index("ix_instruments_industry", "industry"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    code: Mapped[str] = mapped_column(sa.Text, nullable=False)
    market: Mapped[str] = mapped_column(sa.Text, nullable=False)
    kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    industry: Mapped[str | None] = mapped_column(sa.Text)
    sector: Mapped[str | None] = mapped_column(sa.Text)
    lot_size: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=100)
    price_scale: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=2)
    qty_scale: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=2)
    tradable: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, default="active")
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
