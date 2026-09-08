"""Web Push 发送（Phase 3.5 P1）：pywebpush/py_vapid（optional extra）+ httpx 直发。

VAPID 签名（py_vapid）与载荷加密（WebPusher.encode，RFC 8291 aes128gcm）全委托库——
不自实现密码学；httpx 负责投递，便于测试与超时控制。
VAPID 未配置 → not_configured（不发送不报错）；端点 404/410 → gone（订阅应撤销）。
"""

import json
import logging
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Any
from urllib.parse import urlparse

from wws_adviser.core.errors import DomainError

_logger = logging.getLogger(__name__)

_GONE_CODES = {404, 410}


def vapid_configured(settings: Any) -> bool:
    return bool(settings.push_vapid_private_pem and settings.push_vapid_subject)


def vapid_public_key_from_pem(private_key_pem: str) -> str:
    """PEM 私钥 → 未压缩 P-256 公钥点 b64url（订阅时 applicationServerKey 用）。"""
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    key = _load_ec_key(private_key_pem)
    pub = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return urlsafe_b64encode(pub).rstrip(b"=").decode("ascii")


def _load_ec_key(pem_or_raw_b64: str) -> Any:
    """配置里的 VAPID 私钥：PEM 或 b64url 原始 EC 私钥，统一装载。"""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    if "-----BEGIN" in pem_or_raw_b64:
        key = serialization.load_pem_private_key(pem_or_raw_b64.encode(), password=None)
    else:
        raw = urlsafe_b64decode(pem_or_raw_b64 + "=" * (-len(pem_or_raw_b64) % 4))
        key = ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise DomainError("VAPID 私钥须为 EC P-256")
    return key


def _vapid_key_string(settings_key: str) -> str:
    """py_vapid.from_string 只认 b64url raw / DER——PEM 归一化为 b64url raw。"""
    if "-----BEGIN" not in settings_key:
        return settings_key
    key = _load_ec_key(settings_key)
    # cryptography 的 Raw 序列化不支持 EC——手动取 32 字节私有值
    raw = key.private_numbers().private_value.to_bytes(32, "big")
    return urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


async def send_web_push(
    httpx_client: Any,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    payload: dict[str, Any],
    settings: Any,
) -> str:
    """加密并投递一条推送。返回 sent / not_configured / gone / error[:reason]。

    payload 将 JSON 序列化后加密（隐私脱敏在上游完成——本函数不做脱敏）。
    """
    if not vapid_configured(settings):
        return "not_configured"
    try:
        from py_vapid import Vapid
        from pywebpush import WebPusher
    except ImportError:  # pragma: no cover - 环境缺依赖的明确指引
        _logger.warning("pywebpush 未安装（uv sync --extra webpush），推送跳过")
        return "not_configured"

    try:
        vv = Vapid.from_string(_vapid_key_string(settings.push_vapid_private_pem))
        u = urlparse(endpoint)
        claims: dict[str, Any] = {
            "aud": f"{u.scheme}://{u.netloc}",
            "exp": int(time.time()) + 12 * 3600,
            "sub": settings.push_vapid_subject,
        }
        vapid_headers = vv.sign(claims)
        pusher = WebPusher({"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}})
        encoded = pusher.encode(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
            content_encoding="aes128gcm",
        )
        headers = {
            "TTL": "60",
            "Content-Type": "application/octet-stream",
            **{str(k): str(v) for k, v in vapid_headers.items()},
            **{
                str(k): (v.decode() if isinstance(v, bytes) else str(v))
                for k, v in encoded.items()
                if k != "body"
            },
        }
        resp = await httpx_client.post(endpoint, content=encoded["body"], headers=headers)
        if resp.status_code in _GONE_CODES:
            return "gone"
        if resp.status_code >= 400:
            return f"error:http_{resp.status_code}"
        return "sent"
    except Exception as exc:  # noqa: BLE001 — 推送失败绝不外抛（FR-NOTIFY-001）
        _logger.warning(
            "Web Push 投递失败 endpoint=%s…: %s: %s", endpoint[:40], type(exc).__name__, exc
        )
        return "error"
