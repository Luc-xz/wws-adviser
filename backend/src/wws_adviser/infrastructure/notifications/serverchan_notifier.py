"""Server 酱（sc3.ft07/sctapi）通知适配器（NotifierPort；PRD §20.1 保留渠道）。

SENDKEY 半敏感——只经 env 引用名注入，绝不落日志/审计。
表单字段：title=摘要行，desp=Markdown 正文。仅处理 SERVER_CHAN 渠道。
"""

import hashlib
import json
import os
from typing import TYPE_CHECKING, Any

from wws_adviser.ports.notifier import NotificationChannel, NotificationResult

if TYPE_CHECKING:
    import httpx

DEFAULT_API_BASE = "https://sctapi.ftqq.com"


def build_form(event_type: str, payload: dict[str, Any]) -> dict[str, str]:
    """事件+载荷 → Server酱表单（title 摘要 + desp Markdown 正文，纯函数可单测）。"""
    title = f"[WWS Adviser] {event_type}"
    desp = "\n".join(f"- **{k}**: {v}" for k, v in payload.items())
    return {"title": title, "desp": desp}


def _payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _fail(
    channel: NotificationChannel,
    event_type: str,
    payload_hash: str,
    error_code: str,
) -> NotificationResult:
    return NotificationResult(
        channel=channel, event_type=event_type, payload_hash=payload_hash,
        sent=False, error_code=error_code,
    )


class ServerChanNotifierPort:
    def __init__(
        self,
        *,
        sendkey_ref: str,
        api_base: str = DEFAULT_API_BASE,
        env: str = "dev",
        transport: "httpx.AsyncBaseTransport | None" = None,
    ) -> None:
        self._sendkey_ref = sendkey_ref
        self._api_base = api_base.rstrip("/")
        self._env = env
        self._transport = transport  # 测试注 MockTransport；生产走真实连接池

    async def notify(
        self,
        channel: NotificationChannel,
        event_type: str,
        payload: dict[str, Any],
    ) -> NotificationResult:
        payload_hash = _payload_hash(payload)
        if channel is not NotificationChannel.SERVER_CHAN:
            return _fail(channel, event_type, payload_hash, "channel_mismatch")
        sendkey = os.environ.get(self._sendkey_ref, "")
        if not sendkey:
            return _fail(channel, event_type, payload_hash, "missing_sendkey_env")
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0, transport=self._transport) as client:
                resp = await client.post(
                    f"{self._api_base}/{sendkey}.send", data=build_form(event_type, payload)
                )
                resp.raise_for_status()
                code = int(resp.json().get("code", "-1"))
        except Exception as exc:  # noqa: BLE001 — 发送失败记 error_code，不外抛
            return _fail(channel, event_type, payload_hash, type(exc).__name__)
        if code != 0:
            return _fail(channel, event_type, payload_hash, f"serverchan_code_{code}")
        return NotificationResult(
            channel=channel, event_type=event_type, payload_hash=payload_hash, sent=True
        )
