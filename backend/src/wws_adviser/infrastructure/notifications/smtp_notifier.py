"""SMTP 邮件通知适配器（NotifierPort）。

stdlib smtplib + asyncio.to_thread（零新依赖，阻塞发送移出事件循环）。587 STARTTLS/465 SSL
（8_SECURITY §12.2，避开云 VPS 25 端口封锁）。凭据经 env 引用；真实发送留 VPS 联调。
"""

import asyncio
import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any

from wws_adviser.ports.notifier import NotificationChannel, NotificationResult


def build_message(
    *, subject: str, body: str, from_addr: str, to_addr: str
) -> MIMEText:
    """构造邮件正文（纯函数可单测）。"""
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr(("WWS Adviser", from_addr))
    msg["To"] = to_addr
    return msg


def _send_sync(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    use_tls: bool,
    msg: MIMEText,
    to_addr: str,
) -> None:
    if port == 465:
        server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=15)
    else:
        server = smtplib.SMTP(host, port, timeout=15)
    try:
        if use_tls and port != 465:
            server.starttls()
        if user and password:
            server.login(user, password)
        server.send_message(msg, to_addrs=[to_addr])
    finally:
        server.quit()


class SMTPNotifierPort:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        key_ref: str,
        from_addr: str,
        to_addr: str,
        use_tls: bool = True,
        env: str = "dev",
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._key_ref = key_ref
        self._from = from_addr
        self._to = to_addr
        self._use_tls = use_tls
        self._env = env

    async def notify(
        self,
        channel: NotificationChannel,
        event_type: str,
        payload: dict[str, Any],
    ) -> NotificationResult:
        import hashlib
        import json

        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        subject = f"[WWS Adviser] {event_type}"
        body = "\n".join(f"{k}: {v}" for k, v in payload.items())
        msg = build_message(subject=subject, body=body, from_addr=self._from, to_addr=self._to)
        try:
            await asyncio.to_thread(
                _send_sync,
                host=self._host,
                port=self._port,
                user=self._user,
                password=os.environ.get(self._key_ref, ""),
                use_tls=self._use_tls,
                msg=msg,
                to_addr=self._to,
            )
        except Exception as exc:  # noqa: BLE001 — 发送失败记 error_code，不外抛
            return NotificationResult(
                channel=channel, event_type=event_type, payload_hash=payload_hash,
                sent=False, error_code=type(exc).__name__,
            )
        return NotificationResult(
            channel=channel, event_type=event_type, payload_hash=payload_hash, sent=True
        )
