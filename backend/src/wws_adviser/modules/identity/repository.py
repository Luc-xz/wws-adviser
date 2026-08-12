"""身份仓储。"""

from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.identity.models import Session, User


def get_user_by_username(db: DBSession, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def get_user_by_id(db: DBSession, user_id: str) -> User | None:
    return db.get(User, user_id)


def get_session_by_token_hash(db: DBSession, token_hash: str) -> Session | None:
    return db.scalar(select(Session).where(Session.token_hash == token_hash))


def add_session(db: DBSession, session: Session) -> Session:
    db.add(session)
    db.flush()
    return session


def revoke_session(db: DBSession, session_id: str) -> None:
    db.execute(
        update(Session).where(Session.id == session_id).values(revoked_at=now_utc_iso())
    )


def revoke_other_sessions(db: DBSession, user_id: str, keep_session_id: str) -> int:
    """撤销该用户的其他未撤销会话（改密时）。返回受影响行数。"""
    result = db.execute(
        update(Session)
        .where(
            Session.user_id == user_id,
            Session.id != keep_session_id,
            Session.revoked_at.is_(None),
        )
        .values(revoked_at=now_utc_iso())
    )
    return cast(CursorResult[Any], result).rowcount or 0
