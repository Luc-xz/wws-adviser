"""StubNotifierPort：记录调用并返回成功（source="stub"），禁生产。"""

import hashlib
import json
from typing import Any

from wws_adviser.infrastructure import assert_not_prod
from wws_adviser.ports.notifier import (
    NotificationChannel,
    NotificationResult,
)


class StubNotifierPort:
    def __init__(self, *, env: str = "dev") -> None:
        assert_not_prod(env)
        self.calls: list[NotificationResult] = []

    async def notify(
        self,
        channel: NotificationChannel,
        event_type: str,
        payload: dict[str, Any],
    ) -> NotificationResult:
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        result = NotificationResult(
            channel=channel,
            event_type=event_type,
            payload_hash=payload_hash,
            sent=True,
        )
        self.calls.append(result)
        return result
