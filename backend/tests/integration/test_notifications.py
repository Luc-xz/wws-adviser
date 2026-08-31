"""Notifications 服务测试：幂等 + 冷却窗口（技术债清理）。

用计数 Fake 渠道验证：冷却开启时同 channel+event_type 窗口内重复事件被抑制；
关闭（默认 0）时逐条发送；窗口过期后恢复发送。
"""

from datetime import UTC, datetime, timedelta

from wws_adviser.core.config import Settings
from wws_adviser.modules.notifications import service as notifications_service
from wws_adviser.ports.notifier import NotificationChannel, NotificationResult


class _CountingNotifier:
    """计数渠道：每次调用都成功并自增。"""

    def __init__(self) -> None:
        self.calls = 0

    async def notify(
        self,
        channel: NotificationChannel,
        event_type: str,
        payload: dict,
    ) -> NotificationResult:
        self.calls += 1
        return NotificationResult(
            channel=channel, event_type=event_type, payload_hash=f"p{self.calls}",
            sent=True,
        )


def _settings(tmp_path, cooldown_seconds: int) -> Settings:
    return Settings(
        env="test", data_dir=tmp_path, notification_cooldown_seconds=cooldown_seconds
    )


async def test_cooldown_suppresses_repeated_event(db_session, tmp_path) -> None:
    notifier = _CountingNotifier()
    s = _settings(tmp_path, cooldown_seconds=600)

    r1 = await notifications_service.notify(
        db_session, s, notifier, event_type="report.completed", payload={"n": 1}
    )
    assert r1.sent and not r1.suppressed_by_cooldown

    # 不同 payload、同事件类型，仍在冷却窗口 → 抑制，不触达渠道
    r2 = await notifications_service.notify(
        db_session, s, notifier, event_type="report.completed", payload={"n": 2}
    )
    assert not r2.sent and r2.suppressed_by_cooldown
    assert r2.error_code == "cooldown_suppressed"
    assert notifier.calls == 1


async def test_cooldown_disabled_by_default_sends_each(db_session, tmp_path) -> None:
    notifier = _CountingNotifier()
    s = _settings(tmp_path, cooldown_seconds=0)
    for n in (1, 2):
        await notifications_service.notify(
            db_session, s, notifier, event_type="report.completed", payload={"n": n}
        )
    assert notifier.calls == 2


async def test_cooldown_expires_and_sends_again(db_session, tmp_path) -> None:
    from wws_adviser.modules.notifications import repository

    notifier = _CountingNotifier()
    s = _settings(tmp_path, cooldown_seconds=600)
    await notifications_service.notify(
        db_session, s, notifier, event_type="report.completed", payload={"n": 1}
    )

    # 把唯一一条 sent 行的 created_at 回拨 700s → 出窗
    row = repository.get_last_sent(db_session, "email", "report.completed")
    assert row is not None
    stale = (datetime.now(UTC) - timedelta(seconds=700)).isoformat()
    row.created_at = stale
    row.updated_at = stale
    db_session.commit()

    r2 = await notifications_service.notify(
        db_session, s, notifier, event_type="report.completed", payload={"n": 2}
    )
    assert r2.sent and not r2.suppressed_by_cooldown
    assert notifier.calls == 2
