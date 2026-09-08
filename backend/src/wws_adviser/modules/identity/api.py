"""/api/v1/auth 端点。"""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response
from sqlalchemy.orm import Session as DBSession

from wws_adviser.api.dependencies import get_current_user, get_session, get_settings
from wws_adviser.core.config import Settings
from wws_adviser.core.errors import MissingIdempotencyKeyError
from wws_adviser.modules.identity import schemas, service
from wws_adviser.modules.identity.domain import AuthenticationError
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.identity.schemas import (
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    SessionInfo,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

SESSION_COOKIE = "wws_session"
CSRF_COOKIE = "csrf_token"

# 模块级依赖别名（避免 B008 + 去重）
DBDep = Annotated[DBSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionToken = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]


def _require_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if not idempotency_key:
        raise MissingIdempotencyKeyError()
    return idempotency_key


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DBDep,
    settings: SettingsDep,
    _key: Annotated[str, Depends(_require_idempotency_key)],
) -> LoginResponse:
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")
    request_id = request.headers.get("x-request-id")
    result = service.login(
        db,
        settings,
        username=body.username,
        password=body.password,
        ip=ip,
        user_agent=ua,
        request_id=request_id,
    )
    max_age = settings.session_ttl_days * 86400
    response.set_cookie(
        SESSION_COOKIE,
        result["token"],
        max_age=max_age,
        httponly=True,
        secure=settings.is_prod,
        samesite="lax",
    )
    response.set_cookie(
        CSRF_COOKIE,
        result["token"][:32],
        max_age=max_age,
        httponly=False,
        secure=settings.is_prod,
        samesite="lax",
    )
    return LoginResponse(
        user_id_hash=result["user_id_hash"], expires_at=result["expires_at"]
    )


@router.post("/logout")
async def logout(
    request: Request,
    db: DBDep,
    session_token: SessionToken = None,
) -> dict[str, str]:
    sid = service.get_session_id_by_token(db, session_token)
    if sid:
        service.logout(db, sid, request_id=request.headers.get("x-request-id"))
    return {"status": "ok"}


@router.get("/session", response_model=SessionInfo)
async def session_info(
    db: DBDep,
    session_token: SessionToken = None,
) -> SessionInfo:
    info = service.get_session_info(db, session_token)
    if info is None:
        raise AuthenticationError("未登录")
    return SessionInfo(**info)


@router.post("/password")
async def change_password(
    body: PasswordChangeRequest,
    request: Request,
    db: DBDep,
    user: Annotated[User, Depends(get_current_user)],
    session_token: SessionToken = None,
) -> dict[str, str]:
    sid = service.get_session_id_by_token(db, session_token)
    service.change_password(
        db,
        user_id=user.id,
        old_password=body.old_password,
        new_password=body.new_password,
        current_session_id=sid or "",
        request_id=request.headers.get("x-request-id"),
    )
    return {"status": "ok"}


# —— Passkey（Phase 3.5 P1；登录端点豁免 CSRF：仪式自带 challenge+origin 绑定） ——


@router.post("/passkey/register/options")
async def passkey_register_options(
    db: DBDep,
    settings: SettingsDep,
    user: Annotated[User, Depends(get_current_user)],
    _key: Annotated[str, Depends(_require_idempotency_key)],
) -> schemas.PasskeyCeremonyResponse:
    from wws_adviser.modules.identity import passkey as passkey_service

    options = passkey_service.register_begin(db, settings, user)
    return schemas.PasskeyCeremonyResponse(options=options)


@router.post("/passkey/register/verify")
async def passkey_register_verify(
    body: schemas.PasskeyRegisterVerifyRequest,
    db: DBDep,
    settings: SettingsDep,
    user: Annotated[User, Depends(get_current_user)],
    _key: Annotated[str, Depends(_require_idempotency_key)],
) -> schemas.PasskeyCredentialOut:
    from wws_adviser.modules.identity import passkey as passkey_service

    row = passkey_service.register_complete(
        db, settings, user, body.model_dump(), name=body.name
    )
    return schemas.PasskeyCredentialOut(
        id=row.credential_id, name=row.name, sign_count=row.sign_count,
        created_at=row.created_at, last_used_at=row.last_used_at,
    )


@router.get("/passkey/credentials")
async def passkey_list(
    db: DBDep,
    user: Annotated[User, Depends(get_current_user)],
) -> list[schemas.PasskeyCredentialOut]:
    from wws_adviser.modules.identity import passkey as passkey_service

    return [
        schemas.PasskeyCredentialOut(
            id=r.credential_id, name=r.name, sign_count=r.sign_count,
            created_at=r.created_at, last_used_at=r.last_used_at,
        )
        for r in passkey_service.list_credentials(db, user)
    ]


@router.delete("/passkey/credentials/{credential_id}")
async def passkey_delete(
    credential_id: str,
    db: DBDep,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    from wws_adviser.modules.identity import passkey as passkey_service

    passkey_service.delete_credential(db, user, credential_id)
    return {"status": "ok"}


@router.post("/passkey/login/options")
async def passkey_login_options(
    db: DBDep,
    settings: SettingsDep,
) -> schemas.PasskeyCeremonyResponse:
    from wws_adviser.modules.identity import passkey as passkey_service

    return schemas.PasskeyCeremonyResponse(options=passkey_service.login_begin(db, settings))


@router.post("/passkey/login/verify", response_model=schemas.LoginResponse)
async def passkey_login_verify(
    body: schemas.PasskeyLoginVerifyRequest,
    request: Request,
    response: Response,
    db: DBDep,
    settings: SettingsDep,
) -> schemas.LoginResponse:
    """Passkey 登录：校验断言 → 签发与密码登录一致的会话 Cookie。"""
    from wws_adviser.modules.identity import passkey as passkey_service

    _cred, user = passkey_service.login_complete(db, settings, body.model_dump())
    result = service.login_with_passkey(
        db, settings, user,
        request.headers.get("user-agent", ""),
        request_id=request.headers.get("x-request-id"),
    )
    max_age = settings.session_ttl_days * 86400
    response.set_cookie(
        SESSION_COOKIE, result["token"], max_age=max_age,
        httponly=True, secure=settings.is_prod, samesite="lax",
    )
    response.set_cookie(
        CSRF_COOKIE, result["token"][:32], max_age=max_age,
        httponly=False, secure=settings.is_prod, samesite="lax",
    )
    return schemas.LoginResponse(
        user_id_hash=result["user_id_hash"], expires_at=result["expires_at"]
    )
