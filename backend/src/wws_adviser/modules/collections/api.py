"""/api/v1/collections 端点：采集运行与健康（3_API §3.17，5_DATA §12）。

需登录（操作信息不公开，对齐技术架构 §16.1 依赖健康「仅认证用户可见详细信息」）。
只读，不校验 CSRF。
"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DBSession

from wws_adviser.api.dependencies import get_current_user, get_session, get_settings
from wws_adviser.core.config import Settings
from wws_adviser.core.errors import DomainError
from wws_adviser.modules.collections import service
from wws_adviser.modules.collections.schemas import (
    CollectionsHealthResponse,
    IngestItemListResponse,
    item_to_out,
    source_health_to_out,
)
from wws_adviser.modules.identity.models import User

router = APIRouter(prefix="/api/v1/collections", tags=["collections"])

DBDep = Annotated[DBSession, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


class InvalidCursorError(DomainError):
    code = "VALIDATION_ERROR"
    status = 400
    title = "无效分页游标"


@router.get("/health", response_model=CollectionsHealthResponse)
async def get_health(db: DBDep, user: UserDep, settings: SettingsDep) -> CollectionsHealthResponse:
    overview = service.health_overview(db, settings)
    sources = cast("list[dict[str, object]]", overview["sources"])
    return CollectionsHealthResponse(
        generated_at=str(overview["generated_at"]),
        sources=[source_health_to_out(s) for s in sources],
    )


@router.get("/items", response_model=IngestItemListResponse)
async def list_items(
    db: DBDep,
    user: UserDep,
    category: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> IngestItemListResponse:
    try:
        items, next_cursor = service.list_items_page(
            db,
            category=category,
            status=status,
            q=q,
            date_from=date_from,
            date_to=date_to,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise InvalidCursorError(str(exc)) from exc
    return IngestItemListResponse(items=[item_to_out(i) for i in items], next_cursor=next_cursor)
