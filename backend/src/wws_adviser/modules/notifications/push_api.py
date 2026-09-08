"""/api/v1/push 端点（Phase 3.5 P1）：VAPID 公钥 + 订阅登记/解绑。

订阅属用户态写操作（登录 + CSRF + Idempotency-Key）；公钥为公开配置读。
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from wws_adviser.api.dependencies import get_current_user, get_session, get_settings
from wws_adviser.core.config import Settings
from wws_adviser.core.errors import DomainError, MissingIdempotencyKeyError
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.notifications import push_repository

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/push", tags=["push"])

DBDep = Annotated[DBSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _require_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if not idempotency_key:
        raise MissingIdempotencyKeyError()
    return idempotency_key


class SubscribeRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


class SubscribeOut(BaseModel):
    id: str
    created: bool


@router.get("/vapid-public")
async def vapid_public(settings: SettingsDep) -> dict[str, str | bool | None]:
    """订阅用公钥（applicationServerKey）；未配置 → configured=false（前端隐藏入口）。"""
    from wws_adviser.infrastructure.notifications import web_push

    key: str | None = settings.push_vapid_public_key_b64 or None
    if not key and settings.push_vapid_private_pem:
        try:
            key = web_push.vapid_public_key_from_pem(settings.push_vapid_private_pem)
        except DomainError:
            key = None
    return {"public_key": key, "configured": web_push.vapid_configured(settings)}


@router.post("/subscriptions", response_model=SubscribeOut)
async def subscribe(
    body: SubscribeRequest,
    db: DBDep,
    settings: SettingsDep,
    user: Annotated[User, Depends(get_current_user)],
    _key: Annotated[str, Depends(_require_idempotency_key)],
) -> SubscribeOut:
    from wws_adviser.infrastructure.notifications import web_push

    if not web_push.vapid_configured(settings):
        raise DomainError("Web Push 未配置（VAPID）")
    row, created = push_repository.upsert(
        db, user_id=user.id, endpoint=body.endpoint,
        p256dh=body.p256dh, auth=body.auth,
    )
    return SubscribeOut(id=row.id, created=created)


@router.delete("/subscriptions/{sub_id}")
async def unsubscribe(
    sub_id: str,
    db: DBDep,
    user: Annotated[User, Depends(get_current_user)],
    _key: Annotated[str, Depends(_require_idempotency_key)],
) -> dict[str, str]:
    if not push_repository.delete(db, sub_id, user.id):
        raise DomainError("订阅不存在")
    return {"status": "ok"}
