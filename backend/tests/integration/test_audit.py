"""Audit append-only 测试（1_REPO_STRUCTURE.md §8）。"""

from sqlalchemy import select

from wws_adviser.modules.audit import service as audit_service
from wws_adviser.modules.audit.models import AuditEvent


def test_append_event_inserts_row(db_session):
    audit_service.append_event(
        db_session, action="login_failed", actor="x", target_type="user", after={"v": 1}
    )
    db_session.commit()
    rows = db_session.scalars(select(AuditEvent)).all()
    assert len(rows) == 1
    assert rows[0].action == "login_failed"
    assert rows[0].after_summary_json is not None


def test_append_only_no_update_interface(db_session):
    """append_event 只 INSERT；更新走"新事件"，原事件不可变。"""
    audit_service.append_event(db_session, action="job_completed", target_id="j1", after={"v": 1})
    db_session.commit()
    # 同 target 再记一条新事件（不改原事件）
    audit_service.append_event(db_session, action="job_completed", target_id="j1", after={"v": 2})
    db_session.commit()
    rows = db_session.scalars(select(AuditEvent).where(AuditEvent.target_id == "j1")).all()
    assert len(rows) == 2
    assert {r.after_summary_json for r in rows} == {'{"v": 1}', '{"v": 2}'}
