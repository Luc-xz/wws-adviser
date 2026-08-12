"""FastAPI 应用装配：路由、错误处理、request_id 中间件。

lifespan 由 main.py 注入（含启动校验）；create_app 不含 lifespan，便于测试。
"""

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from uuid import uuid4

from fastapi import FastAPI, Request, Response

from wws_adviser.api.errors import register_exception_handlers
from wws_adviser.api.routes import health
from wws_adviser.core.config import Settings
from wws_adviser.core.logging import request_id_var


def create_app(
    settings: Settings,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
) -> FastAPI:
    app = FastAPI(
        title="WWS Adviser",
        version="0.1.0",
        description="个人投资顾问（模块化单体）",
        lifespan=lifespan,
    )
    app.state.settings = settings

    register_exception_handlers(app)
    app.include_router(health.router)

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get("X-Request-ID") or str(uuid4())
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response

    return app
