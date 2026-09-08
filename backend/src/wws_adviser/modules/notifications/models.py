"""Notifications ORM：notifications 表（波6，幂等 UNIQUE(channel,event_type,payload_hash)）。"""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from wws_adviser.core.db import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        sa.UniqueConstraint(
            "channel", "event_type", "payload_hash", name="uq_notifications_idem"
        ),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    channel: Mapped[str] = mapped_column(sa.Text, nullable=False)
    event_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    attempts: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    sent_at: Mapped[str | None] = mapped_column(sa.Text)
    error_code: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)


class PushSubscription(Base):
    """Web Push 订阅（Phase 3.5 P1）。endpoint 全局唯一；404/410 撤销。"""

    __tablename__ = "push_subscriptions"
    __table_args__ = (
        sa.UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
        sa.Index("ix_push_subscriptions_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    user_id: Mapped[str] = mapped_column(sa.String(26), sa.ForeignKey("users.id"), nullable=False)
    endpoint: Mapped[str] = mapped_column(sa.Text, nullable=False)
    p256dh: Mapped[str] = mapped_column(sa.Text, nullable=False)
    auth: Mapped[str] = mapped_column(sa.Text, nullable=False)
    revoked_at: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
