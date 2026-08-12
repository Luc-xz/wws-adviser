"""健康检查端点（见 TECHNICAL_ARCHITECTURE.md §16.1）。

- /health/live：进程存活，不触碰外部服务。
- /health/ready：DB 可写 + 迁移已应用；不可写时返回 503（反向代理据此排水）。
- /health/dependencies：数据源/模型/通知近况，仅认证用户可见（Phase 0 占位）。
"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.engine import Engine

from wws_adviser.api.dependencies import get_settings
from wws_adviser.core.config import Settings
from wws_adviser.core.db import check_db_writable

router = APIRouter(prefix="/health", tags=["health"])


def _engine(request: Request) -> Engine:
    return cast(Engine, request.app.state.engine)


def _migration_applied(engine: Engine) -> bool:
    """alembic_version 表存在且有版本记录。"""
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        return version is not None
    except Exception:
        # 表不存在或查询失败 = 未迁移
        return False


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    engine = _engine(request)
    db_ok = check_db_writable(engine)
    migrated = _migration_applied(engine)
    healthy = db_ok and migrated
    body: dict[str, object] = {
        "status": "ok" if healthy else "fail",
        "db_writable": db_ok,
        "migration_applied": migrated,
    }
    return JSONResponse(status_code=200 if healthy else 503, content=body)


@router.get("/dependencies")
async def dependencies(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    # Phase 0 占位；波3 起接入数据源/模型/通知的真实健康状态
    return {"status": "ok", "env": settings.env, "phase": "0"}
