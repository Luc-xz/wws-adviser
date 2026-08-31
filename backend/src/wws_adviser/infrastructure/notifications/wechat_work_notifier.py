"""企业微信群机器人通知适配器（NotifierPort；PRD §20.1 保留渠道按需启用）。

webhook URL 内嵌 key（半敏感）——只经 env 引用名注入，绝不落日志/审计。
群机器人无独立标题字段：首行 [WWS Adviser] event_type 作摘要行。
仅处理 WECHAT_WORK 渠道；未配置/非本渠道一律返回失败结果，不外抛。
"""

import hashlib
import json
import os
from typing import TYPE_CHECKING, Any

from wws_adviser.ports.notifier import NotificationChannel, NotificationResult

if TYPE_CHECKING:
    import httpx


def build_request_body(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """事件+载荷 → 群机器人 text 消息体（纯函数可单测）。"""
    body = "\n".join(f"{k}: {v}" for k, v in payload.items())
    content = f"[WWS Adviser] {event_type}\n{body}".strip()
    return {"msgtype": "text", "text": {"content": content}}


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


class WeChatWorkNotifierPort:
    def __init__(
        self,
        *,
        webhook_ref: str,
        env: str = "dev",
        transport: "httpx.AsyncBaseTransport | None" = None,
    ) -> None:
        self._webhook_ref = webhook_ref
        self._env = env
        self._transport = transport  # 测试注 MockTransport；生产走真实连接池

    async def notify(
        self,
        channel: NotificationChannel,
        event_type: str,
        payload: dict[str, Any],
    ) -> NotificationResult:
        payload_hash = _payload_hash(payload)
        if channel is not NotificationChannel.WECHAT_WORK:
            return _fail(channel, event_type, payload_hash, "channel_mismatch")
        webhook_url = os.environ.get(self._webhook_ref, "")
        if not webhook_url:
            return _fail(channel, event_type, payload_hash, "missing_webhook_env")
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0, transport=self._transport) as client:
                resp = await client.post(
                    webhook_url, json=build_request_body(event_type, payload)
                )
                resp.raise_for_status()
                errcode = int(resp.json().get("errcode", "-1"))
        except Exception as exc:  # noqa: BLE001 — 发送失败记 error_code，不外抛
            return _fail(channel, event_type, payload_hash, type(exc).__name__)
        if errcode != 0:
            return _fail(channel, event_type, payload_hash, f"wechat_work_errcode_{errcode}")
        return NotificationResult(
            channel=channel, event_type=event_type, payload_hash=payload_hash, sent=True
        )
