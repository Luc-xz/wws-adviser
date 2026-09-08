"""研究任务通知测试（FR-NOTIFY-002「异步研究报告完成」，Phase 3 收尾①）。

- 成功 → research_completed 通知（payload 不含标的名，FR-NOTIFY-003 隐私口径）
- 失败 → research_failed 通知
- 通知渠道抛异常 → 任务状态不受影响（FR-NOTIFY-001）
"""

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select

from wws_adviser.modules.notifications.models import Notification
from wws_adviser.modules.research import service as research_service
from wws_adviser.ports.notifier import NotificationChannel, NotificationResult

from .test_research_generation import _login, _seed_doc


class _CrashNotifier:
    """渠道异常边界：notify 必抛（验证 FR-NOTIFY-001）。"""

    async def notify(self, channel, event_type, payload) -> NotificationResult:
        raise RuntimeError("channel down")


def _notifications(db, event_type: str) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(Notification.event_type == event_type)
        ).all()
    )


def _run(app, *, model_port=None, notifier=None) -> None:
    from wws_adviser.modules.research import executor as research_executor

    with app.state.session_factory() as db:
        asyncio.run(research_executor.run_pending(
            db, app.state.settings, app.state.settings.data_dir,
            model_port=model_port or app.state.model_port,
            notifier=notifier if notifier is not None else app.state.notifier,
        ))


def test_research_completed_sends_notification(migrated_client: TestClient) -> None:
    app = migrated_client.app
    with app.state.session_factory() as db:
        _seed_doc(
            db, title="600519贵州茅台2026年半年报",
            text="600519 贵州茅台营业收入增长15%，净利润增长20%。",
        )
        db.commit()

    headers = _login(migrated_client)
    r = migrated_client.post(
        "/api/v1/research/tasks",
        json={"task_type": "company", "subject": "600519", "depth": "quick"},
        headers={**headers, "Idempotency-Key": "notify-ok-1"},
    )
    task_id = r.json()["id"]

    _run(app)

    with app.state.session_factory() as db:
        rows = _notifications(db, "research_completed")
        assert len(rows) == 1
        assert rows[0].status == "sent"
        assert rows[0].channel == NotificationChannel.EMAIL.value
        # 幂等键含 task_id → 重跑不重复通知
        task = research_service.get_task(db, task_id)
        assert task is not None and task.status == "COMPLETED"


def test_research_completed_payload_has_no_subject(migrated_client: TestClient) -> None:
    """隐私口径：通知 payload 不含标的代码/名称（FR-NOTIFY-003 默认开启）。"""
    app = migrated_client.app

    class _RecordingNotifier:
        def __init__(self) -> None:
            self.payloads: list[dict] = []

        async def notify(self, channel, event_type, payload) -> NotificationResult:
            self.payloads.append(dict(payload))
            return NotificationResult(
                channel=channel, event_type=event_type, payload_hash="x", sent=True
            )

    notifier = _RecordingNotifier()
    with app.state.session_factory() as db:
        _seed_doc(db, title="600519贵州茅台公告", text="600519 贵州茅台公告内容。")
        db.commit()

    headers = _login(migrated_client)
    migrated_client.post(
        "/api/v1/research/tasks",
        json={"task_type": "company", "subject": "600519", "depth": "quick"},
        headers={**headers, "Idempotency-Key": "notify-priv-1"},
    )

    _run(app, notifier=notifier)
    assert len(notifier.payloads) == 1
    p = notifier.payloads[0]
    assert set(p) == {"task_type", "task_id", "report_id"}
    assert "600519" not in str(p.values())


def test_research_failed_sends_notification(migrated_client: TestClient) -> None:
    """零证据诚实失败 → research_failed 通知 + 任务 FAILED。"""
    app = migrated_client.app
    headers = _login(migrated_client)
    r = migrated_client.post(
        "/api/v1/research/tasks",
        json={"task_type": "company", "subject": "000000", "depth": "quick"},
        headers={**headers, "Idempotency-Key": "notify-fail-1"},
    )
    task_id = r.json()["id"]

    _run(app)

    with app.state.session_factory() as db:
        rows = _notifications(db, "research_failed")
        assert len(rows) == 1
        task = research_service.get_task(db, task_id)
        assert task is not None and task.status == "FAILED"


def test_notification_failure_never_fails_task(migrated_client: TestClient) -> None:
    """渠道宕机 → 任务照常完成（FR-NOTIFY-001）。"""
    app = migrated_client.app
    with app.state.session_factory() as db:
        _seed_doc(db, title="600519贵州茅台公告", text="600519 贵州茅台公告内容。")
        db.commit()

    headers = _login(migrated_client)
    r = migrated_client.post(
        "/api/v1/research/tasks",
        json={"task_type": "company", "subject": "600519", "depth": "quick"},
        headers={**headers, "Idempotency-Key": "notify-crash-1"},
    )
    task_id = r.json()["id"]

    _run(app, notifier=_CrashNotifier())

    with app.state.session_factory() as db:
        task = research_service.get_task(db, task_id)
        assert task is not None
        assert task.status == "COMPLETED"
        assert task.report_id
