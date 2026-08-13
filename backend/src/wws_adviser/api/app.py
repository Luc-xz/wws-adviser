"""FastAPI 应用装配：路由、错误处理、CSRF + request_id 中间件。

中间件注册顺序（先注册=内层，后注册=外层）：csrf 先注册（内层），request_id 后注册
（外层）——这样 request_id 先执行设置 contextvar，csrf 内层返回 Problem Details 时能带上。
"""

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from uuid import uuid4

from fastapi import FastAPI, Request, Response

from wws_adviser.api.errors import problem, register_exception_handlers
from wws_adviser.api.routes import health
from wws_adviser.core.config import Settings
from wws_adviser.core.logging import request_id_var
from wws_adviser.modules.documents.api import router as documents_router
from wws_adviser.modules.identity.api import router as identity_router
from wws_adviser.modules.instruments.api import router as instruments_router
from wws_adviser.modules.market_data.api import market_router
from wws_adviser.modules.market_data.api import router as market_data_router
from wws_adviser.modules.portfolio.api import router as portfolio_router


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
    app.include_router(identity_router)
    app.include_router(market_data_router)
    app.include_router(market_router)
    app.include_router(instruments_router)
    app.include_router(documents_router)
    app.include_router(portfolio_router)

    write_methods = frozenset({"POST", "PUT", "PATCH", "DELETE"})

    @app.middleware("http")
    async def csrf_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # 登录建立 session 前豁免；其余写操作校验 double-submit CSRF token
        if (
            request.method in write_methods
            and not request.url.path.startswith("/api/v1/auth/login")
        ):
            cookie_tok = request.cookies.get("csrf_token")
            header_tok = request.headers.get("x-csrf-token")
            if not cookie_tok or cookie_tok != header_tok:
                return problem("FORBIDDEN", "CSRF 校验失败", status=403)
        return await call_next(request)

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
