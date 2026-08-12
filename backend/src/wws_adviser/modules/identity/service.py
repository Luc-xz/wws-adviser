"""身份服务：登录/登出/改密/当前用户 + 进程内登录限流。"""

import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.audit import service as audit_service
from wws_adviser.modules.identity import repository
from wws_adviser.modules.identity.domain import (
    AuthenticationError,
    RateLimitedError,
    generate_session_token,
    hash_password,
    hash_token,
    hash_user_id,
    verify_password,
)
from wws_adviser.modules.identity.models import Session as SessionRow
from wws_adviser.modules.identity.models import User

# 进程内登录失败限流：ip -> 失败时间戳队列。单 worker 保证一致。
_login_failures: defaultdict[str, deque[float]] = defaultdict(deque)


def reset_login_rate_limit() -> None:
    """测试用：清空限流状态。"""
    _login_failures.clear()


def _check_rate_limit(ip: str, settings: Settings) -> None:
    now = time.monotonic()
    window = settings.login_rate_limit_window_seconds
    q = _login_failures[ip]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= settings.login_rate_limit_max:
        raise RateLimitedError(f"登录失败次数过多，请 {window} 秒后重试")


def _record_failure(ip: str) -> None:
    _login_failures[ip].append(time.monotonic())


def login(
    db: DBSession,
    settings: Settings,
    *,
    username: str,
    password: str,
    ip: str,
    user_agent: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    _check_rate_limit(ip, settings)
    user = repository.get_user_by_username(db, username)
    if user is None or not verify_password(password, user.password_hash):
        _record_failure(ip)
        audit_service.append_event(
            db,
            action="login_failed",
            actor=username,
            target_type="user",
            request_id=request_id,
        )
        db.commit()
        raise AuthenticationError("用户名或密码错误")
    assert user is not None  # 通过上面校验，user 必非 None（mypy narrow）

    token = generate_session_token()
    expires_at = (
        datetime.now(UTC) + timedelta(days=settings.session_ttl_days)
    ).isoformat()
    sess = SessionRow(
        id=new_id(),
        user_id=user.id,
        token_hash=hash_token(token),
        issued_at=now_utc_iso(),
        expires_at=expires_at,
        user_agent_hash=hash_token(user_agent or ""),
    )
    repository.add_session(db, sess)
    audit_service.append_event(
        db,
        action="login_success",
        actor=user.username,
        target_type="user",
        target_id=user.id,
        request_id=request_id,
    )
    db.commit()
    return {
        "token": token,
        "session_id": sess.id,
        "user_id": user.id,
        "user_id_hash": hash_user_id(user.id),
        "expires_at": expires_at,
    }


def logout(db: DBSession, session_id: str, request_id: str | None = None) -> None:
    repository.revoke_session(db, session_id)
    audit_service.append_event(
        db, action="logout", target_type="session", target_id=session_id, request_id=request_id
    )
    db.commit()


def change_password(
    db: DBSession,
    *,
    user_id: str,
    old_password: str,
    new_password: str,
    current_session_id: str,
    request_id: str | None = None,
) -> None:
    user = repository.get_user_by_id(db, user_id)
    if user is None or not verify_password(old_password, user.password_hash):
        raise AuthenticationError("旧密码错误")
    assert user is not None
    user.password_hash = hash_password(new_password)
    user.updated_at = now_utc_iso()
    user.version += 1
    repository.revoke_other_sessions(db, user_id, current_session_id)
    audit_service.append_event(
        db,
        action="password_changed",
        actor=user.username,
        target_type="user",
        target_id=user_id,
        request_id=request_id,
    )
    db.commit()


def get_current_user(db: DBSession, token: str | None) -> User | None:
    """从会话令牌解析当前用户；无效/过期/撤销返回 None。"""
    if not token:
        return None
    sess = repository.get_session_by_token_hash(db, hash_token(token))
    if sess is None or sess.revoked_at is not None:
        return None
    if sess.expires_at < now_utc_iso():
        return None
    return repository.get_user_by_id(db, sess.user_id)


def get_session_id_by_token(db: DBSession, token: str | None) -> str | None:
    if not token:
        return None
    sess = repository.get_session_by_token_hash(db, hash_token(token))
    return sess.id if sess else None


def get_session_info(db: DBSession, token: str | None) -> dict[str, str] | None:
    user = get_current_user(db, token)
    if user is None:
        return None
    sess = repository.get_session_by_token_hash(db, hash_token(token or ""))
    if sess is None:
        return None
    return {"user_id_hash": hash_user_id(user.id), "expires_at": sess.expires_at}
