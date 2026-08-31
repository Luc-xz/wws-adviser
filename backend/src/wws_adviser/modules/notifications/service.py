"""Notifications 服务：幂等通知（UNIQUE 预查）→ 冷却窗口 → 发送 → 状态回写。

失败绝不外抛（FR-NOTIFY-001：通知失败不影响报告任务）；重试有上限（MVP 单次尝试，
失败记 error_code，补偿任务留硬化）。冷却窗口：同 channel+event_type 距上次成功
发送不足 cooldown 秒 → 抑制不发送（不同 payload 也拦，防事件风暴刷屏）。
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.notifications import repository
from wws_adviser.modules.notifications.domain import compute_payload_hash
from wws_adviser.modules.notifications.models import Notification
from wws_adviser.ports.notifier import NotificationChannel, NotificationResult, NotifierPort


def _within_cooldown(last_sent_at: str, now: datetime, cooldown_seconds: int) -> bool:
    """created_at(ISO) 距 now 不足冷却窗口 → True。解析失败视为不在窗口内。"""
    try:
        sent_at = datetime.fromisoformat(last_sent_at)
    except ValueError:
        return False
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=UTC)
    return (now - sent_at).total_seconds() < cooldown_seconds


async def notify(
    db: DBSession,
    settings: Settings,
    provider: NotifierPort,
    *,
    event_type: str,
    payload: dict[str, Any],
    channel: NotificationChannel = NotificationChannel.EMAIL,
) -> NotificationResult:
    """发送一条通知（幂等：同 channel+event+payload 已处理过 → 直接返回）。

    冷却开启时（settings.notification_cooldown_seconds>0），同 channel+event_type
    在窗口内的重复事件被抑制：sent=False + error_code="cooldown_suppressed" +
    suppressed_by_cooldown=True，不触达渠道、不落新行。
    """
    payload_hash = compute_payload_hash(payload)
    existing = repository.get_by_idem(db, channel.value, event_type, payload_hash)
    if existing is not None and existing.status in ("sent", "pending", "failed"):
        return NotificationResult(
            channel=channel, event_type=event_type, payload_hash=payload_hash,
            sent=existing.status == "sent", error_code=existing.error_code,
        )

    cooldown_seconds = settings.notification_cooldown_seconds
    if cooldown_seconds > 0:
        last_sent = repository.get_last_sent(db, channel.value, event_type)
        if last_sent is not None and _within_cooldown(
            last_sent.created_at, datetime.now(UTC), cooldown_seconds
        ):
            return NotificationResult(
                channel=channel, event_type=event_type, payload_hash=payload_hash,
                sent=False, error_code="cooldown_suppressed",
                suppressed_by_cooldown=True,
            )

    now = now_utc_iso()
    row = Notification(
        id=new_id(),
        channel=channel.value,
        event_type=event_type,
        payload_hash=payload_hash,
        status="pending",
        attempts=1,
        created_at=now,
        updated_at=now,
    )
    repository.insert_pending(db, row)
    db.commit()

    try:
        result = await provider.notify(channel, event_type, payload)
    except Exception as exc:  # noqa: BLE001 — 通知失败不外抛（FR-NOTIFY-001）
        repository.mark_failed(db, row.id, type(exc).__name__, now_utc_iso())
        db.commit()
        return NotificationResult(
            channel=channel, event_type=event_type, payload_hash=payload_hash,
            sent=False, error_code=type(exc).__name__,
        )

    if result.sent:
        repository.mark_sent(db, row.id, now_utc_iso())
    else:
        repository.mark_failed(db, row.id, result.error_code or "send_failed", now_utc_iso())
    db.commit()
    return result
