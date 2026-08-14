"""Notifications 仓储：幂等预查 + 状态更新。"""

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.modules.notifications.models import Notification


def get_by_idem(
    db: DBSession, channel: str, event_type: str, payload_hash: str
) -> Notification | None:
    return db.scalar(
        select(Notification).where(
            Notification.channel == channel,
            Notification.event_type == event_type,
            Notification.payload_hash == payload_hash,
        )
    )


def insert_pending(db: DBSession, n: Notification) -> Notification:
    db.add(n)
    db.flush()
    return n


def mark_sent(db: DBSession, notification_id: str, sent_at: str) -> None:
    n = db.get(Notification, notification_id)
    if n is None:
        return
    n.status = "sent"
    n.sent_at = sent_at
    n.updated_at = sent_at


def mark_failed(db: DBSession, notification_id: str, error_code: str, at: str) -> None:
    n = db.get(Notification, notification_id)
    if n is None:
        return
    n.status = "failed"
    n.error_code = error_code
    n.updated_at = at
