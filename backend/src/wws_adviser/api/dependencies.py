"""依赖注入：唯一允许构造基础设施对象的地方（见 1_REPO_STRUCTURE.md §5）。

engine / session_factory 在 lifespan 创建并挂到 app.state；本模块从 app.state 取出注入。
"""

from collections.abc import Iterator
from typing import cast

from fastapi import Request
from sqlalchemy.orm import Session

from wws_adviser.core.config import Settings


def get_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)
