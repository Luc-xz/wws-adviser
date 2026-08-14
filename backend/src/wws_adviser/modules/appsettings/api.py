"""/api/v1/settings/{risk,models,notifications} 端点（3_API §3.14 子集，波6）。

GET 掩码视图；PATCH 白名单字段持久化 + 审计（CSRF 中间件全局生效）。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as DBSession

from wws_adviser.api.dependencies import get_current_user, get_session, get_settings
from wws_adviser.core.config import Settings
from wws_adviser.modules.appsettings import service
from wws_adviser.modules.identity.models import User

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

DBDep = Annotated[DBSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
UserDep = Annotated[User, Depends(get_current_user)]

_SECTIONS = ("risk", "models", "notifications")


@router.get("/{section}")
async def get_settings_section(
    section: str, db: DBDep, settings: SettingsDep, user: UserDep
) -> dict[str, object]:
    if section not in _SECTIONS:
        raise service.SettingsValidationError(f"未知 settings section: {section}")
    return service.masked_view(db, settings, section)


@router.patch("/{section}")
async def patch_settings_section(
    section: str,
    request: Request,
    patch: dict[str, object],
    db: DBDep,
    settings: SettingsDep,
    user: UserDep,
) -> dict[str, object]:
    if section not in _SECTIONS:
        raise service.SettingsValidationError(f"未知 settings section: {section}")
    service.patch_section(
        db,
        user_id=user.id,
        section=section,
        patch=patch,
        request_id=request.headers.get("x-request-id"),
    )
    return service.masked_view(db, settings, section)
