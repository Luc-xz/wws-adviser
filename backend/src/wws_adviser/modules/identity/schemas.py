"""身份 DTO。"""

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
