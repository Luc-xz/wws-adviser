"""Portfolio ORM：accounts、transactions（波1，2_DATA_MODEL §6.2）。

金额（cash/fee/tax）存定标整数分 + *_scale 列；price/quantity 存无损 decimal 字符串。
position_snapshots / pending_transactions / reconciliation_adjustments 随后续波次引入。
"""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from wws_adviser.core.db import Base


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (sa.Index("ix_accounts_user_id", "user_id"),)

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    user_id: Mapped[str] = mapped_column(sa.String(26), sa.ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    currency: Mapped[str] = mapped_column(sa.Text, nullable=False, default="CNY")
    initial_cash_minor: Mapped[int | None] = mapped_column(sa.Integer)
    initial_cash_scale: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=2)
    current_cash_minor: Mapped[int | None] = mapped_column(sa.Integer)
    current_cash_scale: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=2)
    total_assets: Mapped[str | None] = mapped_column(sa.Text)  # decimal 字符串（波4 计算）
    reconciled: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    reconciled_at: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        sa.UniqueConstraint("external_ref", name="uq_transactions_external_ref"),
        sa.UniqueConstraint("fingerprint", name="uq_transactions_fingerprint"),
        sa.Index("ix_transactions_account_trade", "account_id", "trade_at"),
        sa.Index("ix_transactions_instrument_trade", "instrument_id", "trade_at"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        sa.String(26), sa.ForeignKey("accounts.id"), nullable=False
    )
    instrument_id: Mapped[str] = mapped_column(
        sa.String(26), sa.ForeignKey("instruments.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    direction: Mapped[str] = mapped_column(sa.Text, nullable=False)
    quantity: Mapped[str] = mapped_column(sa.Text, nullable=False)  # 无损 decimal 字符串
    price: Mapped[str] = mapped_column(sa.Text, nullable=False)  # 无损 decimal 字符串
    fee_minor: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    fee_scale: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=2)
    tax_minor: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    tax_scale: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=2)
    trade_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    external_ref: Mapped[str | None] = mapped_column(sa.Text)  # UNIQUE（多 NULL 允许）
    fingerprint: Mapped[str] = mapped_column(sa.Text, nullable=False)
    note: Mapped[str | None] = mapped_column(sa.Text)
    deleted_at: Mapped[str | None] = mapped_column(sa.Text)  # 软删除
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
