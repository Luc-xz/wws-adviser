"""审计 DTO。"""

from typing import Any

from pydantic import BaseModel


class AuditEventCreate(BaseModel):
    action: str
    actor: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    before_summary: dict[str, Any] | None = None
    after_summary: dict[str, Any] | None = None
    request_id: str | None = None
    job_id: str | None = None
