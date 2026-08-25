"""Advice ORM：advice_records（Phase 2，FR-REV-003 建议时数据快照）。

每次盘中建议（含发布与降级）落一条：区间、原因链、完整调整轨迹与证据引用。
Decimal 字符串存储（与 market_records 同约定）。
"""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from wws_adviser.core.db import Base


class AdviceRecord(Base):
    __tablename__ = "advice_records"
    __table_args__ = (
        sa.Index("ix_advice_records_user_created", "user_id", "created_at"),
        sa.Index("ix_advice_records_signal", "signal_id"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    user_id: Mapped[str] = mapped_column(sa.String(26), sa.ForeignKey("users.id"), nullable=False)
    signal_id: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    code: Mapped[str] = mapped_column(sa.Text, nullable=False)
    action: Mapped[str] = mapped_column(sa.Text, nullable=False)
    state: Mapped[str] = mapped_column(sa.Text, nullable=False)
    valid_from: Mapped[str] = mapped_column(sa.Text, nullable=False)
    expires_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    f_min: Mapped[str | None] = mapped_column(sa.Text)
    f_max: Mapped[str | None] = mapped_column(sa.Text)
    value_min: Mapped[str | None] = mapped_column(sa.Text)
    value_max: Mapped[str | None] = mapped_column(sa.Text)
    suggested_lots: Mapped[int | None] = mapped_column(sa.Integer)
    reasons_json: Mapped[str | None] = mapped_column(sa.Text)
    trail_json: Mapped[str | None] = mapped_column(sa.Text)
    evidence_json: Mapped[str | None] = mapped_column(sa.Text)
    invalidated: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    row_version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
