"""审计仓储（只 INSERT，无 UPDATE 路径 —— append-only 由接口形态保证）。"""

from sqlalchemy.orm import Session

from wws_adviser.modules.audit.models import AuditEvent


def append(session: Session, event: AuditEvent) -> AuditEvent:
    session.add(event)
    session.flush()
    return event
