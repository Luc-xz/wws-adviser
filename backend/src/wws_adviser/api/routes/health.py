"""健康检查端点（见 TECHNICAL_ARCHITECTURE.md §16.1）。

- /health/live：进程存活，不触碰外部服务。
- /health/ready：DB 可写 + 迁移已应用；不可写时返回 503（反向代理据此排水）。
- /health/dependencies：数据源/模型/通知近况，仅认证用户可见（Phase 0 占位）。
"""

from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.engine import Engine

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
async def dependencies(request: Request) -> dict[str, object]:
    """依赖近况：clock_skew 为启动时 SNTP 测量结果；unknown = 未启用或 UDP 被拦。

    数据源/模型/通知的真实健康状态留待后续波次接入。
    """
    skew = getattr(request.app.state, "clock_skew", None)
    if skew is not None:
        clock: dict[str, object] = {
            "status": skew.status,
            "offset_seconds": skew.offset_seconds,
            "threshold_seconds": skew.threshold_seconds,
        }
    else:
        clock = {"status": "unknown", "offset_seconds": None, "threshold_seconds": None}
    return {"status": "ok", "clock_skew": clock}
