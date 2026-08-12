"""依赖注入：唯一允许构造基础设施对象的地方（见 1_REPO_STRUCTURE.md §5）。

engine / session_factory 在 lifespan 创建并挂到 app.state；本模块从 app.state 取出注入。
"""

from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from wws_adviser.core.config import Settings
from wws_adviser.modules.identity import service as identity_service
from wws_adviser.modules.identity.domain import AuthenticationError
from wws_adviser.modules.identity.models import User


def get_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_current_user(request: Request, db: Annotated[Session, Depends(get_session)]) -> User:
    """从 wws_session cookie 解析当前用户；未登录抛 AuthenticationError(401)。"""
    token = request.cookies.get("wws_session")
    user = identity_service.get_current_user(db, token)
    if user is None:
        raise AuthenticationError("未登录")
    return user
