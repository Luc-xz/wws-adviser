"""通知端口。幂等键 UNIQUE(channel, event_type, payload_hash)（6_MODEL §10）。

MVP 渠道：email SMTP；保留企业微信/Server 酱 可插拔（技术架构 §6.11）。
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


class NotificationChannel(StrEnum):
    EMAIL = "email"
    WECHAT_WORK = "wechat_work"
    SERVER_CHAN = "server_chan"


@dataclass(frozen=True)
class NotificationResult:
    channel: NotificationChannel
    event_type: str
    payload_hash: str
    sent: bool
    error_code: str | None = None
    # 冷却窗口内被抑制（未触达渠道）；sent=False 且 error_code="cooldown_suppressed"
    suppressed_by_cooldown: bool = False


class NotifierPort(Protocol):
    async def notify(
        self,
        channel: NotificationChannel,
        event_type: str,
        payload: dict[str, Any],
    ) -> NotificationResult: ...
