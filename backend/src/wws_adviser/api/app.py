"""FastAPI 应用装配：路由、错误处理、CSRF + request_id 中间件。

中间件注册顺序（先注册=内层，后注册=外层）：csrf 先注册（内层），request_id 后注册
（外层）——这样 request_id 先执行设置 contextvar，csrf 内层返回 Problem Details 时能带上。
"""

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.types import Scope

from wws_adviser.api.errors import problem, register_exception_handlers
from wws_adviser.api.routes import health
from wws_adviser.core.config import Settings
from wws_adviser.core.logging import request_id_var
from wws_adviser.modules.advice.api import router as advice_router
from wws_adviser.modules.analytics.api import analytics_router, positions_router
from wws_adviser.modules.appsettings.api import router as settings_router
from wws_adviser.modules.documents.api import router as documents_router
from wws_adviser.modules.events.api import router as events_router
from wws_adviser.modules.identity.api import router as identity_router
from wws_adviser.modules.instruments.api import router as instruments_router
from wws_adviser.modules.market_data.api import market_router
from wws_adviser.modules.market_data.api import router as market_data_router
from wws_adviser.modules.notifications.push_api import router as push_router
from wws_adviser.modules.portfolio.api import router as portfolio_router
from wws_adviser.modules.reports.api import router as reports_router
from wws_adviser.modules.research.api import router as research_router


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
    app.include_router(events_router)
    app.include_router(portfolio_router)
    app.include_router(positions_router)
    app.include_router(analytics_router)
    app.include_router(reports_router)
    app.include_router(settings_router)
    app.include_router(advice_router)
    app.include_router(research_router)
    app.include_router(push_router)

    write_methods = frozenset({"POST", "PUT", "PATCH", "DELETE"})

    @app.middleware("http")
    async def csrf_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # 登录建立 session 前豁免（Passkey 登录仪式自带 challenge+origin 绑定）；
        # 其余写操作校验 double-submit CSRF token
        path = request.url.path
        if (
            request.method in write_methods
            and not path.startswith("/api/v1/auth/login")
            and not path.startswith("/api/v1/auth/passkey/login")
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

    # 同源静态（技术架构 §17.1）：配置了 WWSE_STATIC_DIR 且目录存在时挂载 PWA 产物
    # （最后挂载 → API 路由优先匹配；SPA history 回退见 SPAStaticFiles）。
    # 开发用 vite dev/proxy 不配。
    if settings.static_dir is not None and settings.static_dir.is_dir():
        app.mount("/", SPAStaticFiles(directory=settings.static_dir, html=True), name="pwa")

    return app


class SPAStaticFiles(StaticFiles):
    """SPA history 模式回退 + PWA 缓存策略头。

    - 回退：非文件型深链（如 /transactions/new）返回应用壳；`api/` 前缀与文件型
      路径（末段含扩展名分隔点）不回退——API 404 与缺资源 404 均不被 HTML 掩盖；
    - 缓存：hashed 资源（assets/）放行一年不可变；其余（index.html / sw.js /
      manifest）一律 no-cache 强制协商——否则浏览器启发式缓存会拖住 SW 更新，
      部署后用户长时间看到旧壳。
    """

    _IMMUTABLE = "public, max-age=31536000, immutable"
    _REVALIDATE = "no-cache"

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await self._response_with_fallback(path, scope)
        response.headers["Cache-Control"] = (
            self._IMMUTABLE if self._is_hashed_asset(path) else self._REVALIDATE
        )
        return response

    async def _response_with_fallback(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404 and self._should_fallback(path):
                return await super().get_response("index.html", scope)
            raise

    @staticmethod
    def _is_hashed_asset(path: str) -> bool:
        return path.replace("\\", "/").lstrip("/").startswith("assets/")

    @staticmethod
    def _should_fallback(path: str) -> bool:
        # StaticFiles 在 Windows 下以反斜杠连接路径，统一分隔符后判断
        normalized = path.replace("\\", "/").lstrip("/")
        if normalized.startswith("api/"):
            return False
        last_segment = normalized.rsplit("/", 1)[-1]
        return "." not in last_segment
