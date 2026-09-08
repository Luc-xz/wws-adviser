"""身份 DTO。"""

from typing import Any

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    user_id_hash: str
    expires_at: str


class SessionInfo(BaseModel):
    user_id_hash: str
    expires_at: str


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str


# —— Passkey（Phase 3.5 P1）——


class PasskeyCeremonyResponse(BaseModel):
    """注册/登录 options 响应：WebAuthn 标准结构（bytes 字段 b64url 化）。"""

    options: dict[str, Any]


class PasskeyRegisterVerifyRequest(BaseModel):
    """navigator.credentials.create() 的 JSON 序列化（b64url 字段原样透传）。"""

    id: str
    rawId: str
    type: str = "public-key"
    response: dict[str, Any]
    transports: list[str] | None = None
    name: str = "Passkey"


class PasskeyLoginVerifyRequest(BaseModel):
    """navigator.credentials.get() 的 JSON 序列化。"""

    id: str
    rawId: str
    type: str = "public-key"
    response: dict[str, Any]


class PasskeyCredentialOut(BaseModel):
    id: str          # credential_id（b64url）
    name: str
    sign_count: int
    created_at: str
    last_used_at: str | None = None
