"""身份领域：密码哈希（Argon2id）、会话令牌生成与哈希。纯领域，禁框架 import。"""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from wws_adviser.core.errors import DomainError

# argon2-cffi PasswordHasher 的审慎默认参数（见 ADR-0010）
_hasher = PasswordHasher()


class AuthenticationError(DomainError):
    code = "UNAUTHENTICATED"
    status = 401
    title = "认证失败"


class RateLimitedError(DomainError):
    code = "RATE_LIMITED"
    status = 429
    title = "请求过于频繁"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    return True


def generate_session_token() -> str:
    """高熵随机会话令牌（256bit，urlsafe）。明文交 cookie，DB 只存哈希。"""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_user_id(user_id: str) -> str:
    """给前端的 user_id_hash（不暴露原始 ULID）。"""
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:32]
