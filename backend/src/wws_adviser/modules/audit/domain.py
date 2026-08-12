"""审计动作枚举（纯领域，禁框架 import）。"""

from enum import StrEnum


class AuditAction(StrEnum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    PASSWORD_CHANGED = "password_changed"
    SESSION_REVOKED = "session_revoked"
    JOB_ENQUEUED = "job_enqueued"
    JOB_CLAIMED = "job_claimed"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
