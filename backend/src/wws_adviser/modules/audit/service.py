"""审计服务：append_event 是唯一的审计写入入口（无更新路径 → append-only）。"""

import json
from typing import Any

from sqlalchemy.orm import Session

from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.audit.models import AuditEvent
from wws_adviser.modules.audit.repository import append


def append_event(
    session: Session,
    *,
    action: str,
    actor: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    request_id: str | None = None,
    job_id: str | None = None,
) -> AuditEvent:
    """记一条审计事件。before/after 以 JSON 字符串存 TEXT 列（敏感值应先脱敏）。"""
    event = AuditEvent(
        id=new_id(),
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_summary_json=(
            json.dumps(before, ensure_ascii=False) if before is not None else None
        ),
        after_summary_json=(
            json.dumps(after, ensure_ascii=False) if after is not None else None
        ),
        request_id=request_id,
        job_id=job_id,
        occurred_at=now_utc_iso(),
    )
    return append(session, event)
