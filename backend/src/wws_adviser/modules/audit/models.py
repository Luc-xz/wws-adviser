"""AuditEvent ORM（audit_events 表，append-only）。"""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from wws_adviser.core.db import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        sa.Index("ix_audit_events_target", "target_type", "target_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    actor: Mapped[str | None] = mapped_column(sa.Text)
    action: Mapped[str] = mapped_column(sa.Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(sa.Text)
    target_id: Mapped[str | None] = mapped_column(sa.Text)
    before_summary_json: Mapped[str | None] = mapped_column(sa.Text)
    after_summary_json: Mapped[str | None] = mapped_column(sa.Text)
    request_id: Mapped[str | None] = mapped_column(sa.Text)
    job_id: Mapped[str | None] = mapped_column(sa.Text)
    occurred_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
