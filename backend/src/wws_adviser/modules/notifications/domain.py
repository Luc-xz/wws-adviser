"""Notifications 领域：事件、payload hash、隐私脱敏。纯领域，禁框架 import。"""

import hashlib
import json
from enum import StrEnum
from typing import Any


class NotificationEvent(StrEnum):
    REPORT_COMPLETED = "report_completed"
    REPORT_FAILED = "report_failed"


def compute_payload_hash(payload: dict[str, Any]) -> str:
    """幂等键：sha256(排序 JSON)——与 stub_notifier 公式一致。"""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def mask_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """隐私模式（FR-NOTIFY-003）：锁屏可见内容不含标的代码/名称/金额/动作。

    仅保留事件类型与计数类摘要（如风险条数），登录后查看详情。
    """
    masked: dict[str, Any] = {"event_type": payload.get("event_type")}
    if "risk_breach_count" in payload:
        masked["risk_breach_count"] = payload["risk_breach_count"]
    if "degraded" in payload:
        masked["degraded"] = payload["degraded"]
    return masked
