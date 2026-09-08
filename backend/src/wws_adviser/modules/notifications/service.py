"""Notifications 服务：幂等通知（UNIQUE 预查）→ 冷却窗口 → 发送 → 状态回写。

失败绝不外抛（FR-NOTIFY-001：通知失败不影响报告任务）；重试有上限（MVP 单次尝试，
失败记 error_code，补偿任务留硬化）。冷却窗口：同 channel+event_type 距上次成功
发送不足 cooldown 秒 → 抑制不发送（不同 payload 也拦，防事件风暴刷屏）。
"""

from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.notifications import repository
from wws_adviser.modules.notifications.domain import compute_payload_hash, mask_payload
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
    await dispatch_push(db, settings, event_type=event_type, payload=payload)
    return result


# —— Web Push 扇出（Phase 3.5 P1）：通知事件同步推到全部活跃订阅 ——

_PUSH_TITLES = {
    "report_completed": "报告已完成",
    "report_failed": "报告生成失败",
    "research_completed": "研究任务已完成",
    "research_failed": "研究任务失败",
    "hard_risk_breach": "硬风险限制触发",
}


async def dispatch_push(
    db: DBSession,
    settings: Settings,
    *,
    event_type: str,
    payload: dict[str, Any],
    push_client: Any | None = None,
) -> int:
    """向该用户全部活跃 Web Push 订阅投递（隐私模式→脱敏）；失败逐条吞掉。

    返回成功条数。VAPID 未配置 → 0（订阅仍保留，配置后可推送）。
    push_client 供测试注入 httpx 桩；缺省自建短连接 client。
    """
    from wws_adviser.modules.notifications import push_repository

    subs = push_repository.list_active(db, user_id=payload.get("user_id"))
    if not subs:
        return 0
    visible = (
        mask_payload(payload) if settings.notification_privacy_mode else payload
    )
    title = _PUSH_TITLES.get(event_type, "通知")
    push_payload: dict[str, Any] = {"title": title, "event_type": event_type, **visible}

    sent = 0
    if push_client is not None:
        sent = await _push_all(push_client, settings, subs, push_payload, db)
    else:
        async with httpx.AsyncClient(timeout=15.0) as client:
            sent = await _push_all(client, settings, subs, push_payload, db)
    return sent


async def _push_all(
    client: Any, settings: Settings, subs: list[Any], push_payload: dict[str, Any], db: DBSession
) -> int:
    from wws_adviser.infrastructure.notifications import web_push
    from wws_adviser.modules.notifications import push_repository

    sent = 0
    for sub in subs:
        outcome = await web_push.send_web_push(
            client,
            endpoint=sub.endpoint, p256dh=sub.p256dh, auth=sub.auth,
            payload=push_payload, settings=settings,
        )
        if outcome == "sent":
            sent += 1
        elif outcome == "gone":
            push_repository.revoke(db, sub.id)
    return sent
