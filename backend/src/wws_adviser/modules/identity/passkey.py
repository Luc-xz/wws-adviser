"""Passkey 服务（Phase 3.5 P1，8_SECURITY §3）：WebAuthn 注册/登录仪式。

fido2 为 optional extra（`uv sync --extra passkey`）——懒加载，未装时给出明确指引。
challenge 一次性（校验即删）；登录成功签发与密码登录完全一致的会话 Cookie。
RP 未配置（WWSE_PASSKEY_RP_ID/ORIGIN）→ PasskeyDisabledError（端点 501）。
"""

import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.core.errors import DomainError
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.identity import repository
from wws_adviser.modules.identity.models import PasskeyChallenge, PasskeyCredential, User

CHALLENGE_TTL_SECONDS = 120


class PasskeyDisabledError(DomainError):
    def __init__(self) -> None:
        super().__init__("Passkey 未启用（需配置 WWSE_PASSKEY_RP_ID / WWSE_PASSKEY_ORIGIN）")


def _b64url(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64url(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return urlsafe_b64decode(data + pad)


def _server(settings: Settings) -> Any:
    """Fido2Server（懒加载 fido2——optional extra）。"""
    if not settings.passkey_rp_id or not settings.passkey_origin:
        raise PasskeyDisabledError()
    try:
        from fido2.server import Fido2Server
        from fido2.webauthn import PublicKeyCredentialRpEntity
    except ImportError as exc:  # pragma: no cover - 环境缺依赖的明确指引
        raise DomainError("fido2 未安装：uv sync --extra passkey") from exc

    rp = PublicKeyCredentialRpEntity(id=settings.passkey_rp_id, name="WWS Adviser")

    def _verify_origin(origin: str) -> bool:
        return origin == settings.passkey_origin

    return Fido2Server(rp, verify_origin=_verify_origin)


def _options_to_json(options: Any) -> dict[str, Any]:
    """fido2 options → JSON dict。

    fido2 的 webauthn 数据类本身是 Mapping（_JsonDataObject）：键 camelCase、
    bytes 经 __getitem__ 自动 b64url——按 Mapping 递归展开即可。
    """
    from collections.abc import Mapping

    def enc(v: Any) -> Any:
        if isinstance(v, Mapping):
            mapped: dict[str, Any] = {str(k): enc(v[k]) for k in v.keys()}
            return mapped
        if isinstance(v, (list, tuple)):
            return [enc(i) for i in v]
        if isinstance(v, bytes):
            return _b64url(v)
        if isinstance(v, (str, int, bool, type(None))):
            return v
        return str(v)

    result: dict[str, Any] = dict(enc(options))
    return result


def _store_challenge(
    db: DBSession, *, user_id: str | None, purpose: str, challenge: str
) -> None:
    """challenge 为 fido2 state 的 b64url 字符串，原样存取（比对与回放判定共用）。"""
    now = datetime.now(UTC)
    db.execute(delete(PasskeyChallenge).where(PasskeyChallenge.expires_at < now.isoformat()))
    db.add(PasskeyChallenge(
        id=new_id(), challenge=challenge, user_id=user_id, purpose=purpose,
        expires_at=(now + timedelta(seconds=CHALLENGE_TTL_SECONDS)).isoformat(),
        created_at=now_utc_iso(),
    ))
    db.commit()


def _consume_challenge(
    db: DBSession, *, challenge_b64: str, purpose: str
) -> PasskeyChallenge | None:
    """校验并删除（一次性）；命中返回行——user_id 可为 None（login 发现式凭据），
    不得用 None 判命中（会与未命中混淆）。"""
    row = db.scalar(
        select(PasskeyChallenge).where(
            PasskeyChallenge.challenge == challenge_b64, PasskeyChallenge.purpose == purpose
        )
    )
    if row is None:
        return None
    db.delete(row)
    if datetime.fromisoformat(row.expires_at) < datetime.now(UTC):
        db.commit()
        return None
    return row


# —— 注册仪式 ———


def register_begin(db: DBSession, settings: Settings, user: User) -> dict[str, Any]:
    options, state = _server(settings).register_begin(
        user={"id": user.id.encode(), "name": user.username, "displayName": user.username},
        resident_key_requirement="preferred",  # 发现式凭据：登录免用户名
    )
    challenge = state["challenge"]
    _store_challenge(db, user_id=user.id, purpose="register", challenge=challenge)
    return _options_to_json(options)


def register_complete(
    db: DBSession, settings: Settings, user: User, response: dict[str, Any], *, name: str
) -> PasskeyCredential:
    """校验注册响应（origin/challenge/格式），落凭据。重复 credential_id 幂等返回。"""
    challenge_b64 = _client_challenge_b64(response)
    challenge_row = _consume_challenge(db, challenge_b64=challenge_b64, purpose="register")
    if challenge_row is None or challenge_row.user_id != user.id:
        raise DomainError("challenge 无效或已过期，请重新发起注册")


    att_obj = _unb64url(response["response"]["attestationObject"])
    auth_data = _server(settings).register_complete(
        {"challenge": challenge_b64, "user_verification": None},
        {
            "id": _unb64url(response["id"]),
            "rawId": _unb64url(response.get("rawId") or response["id"]),
            "type": "public-key",
            "response": {
                "clientDataJSON": _unb64url(response["response"]["clientDataJSON"]),
                "attestationObject": att_obj,
            },
        },
    )
    cred_data = auth_data.credential_data
    assert cred_data is not None
    existing = db.scalar(
        select(PasskeyCredential).where(
            PasskeyCredential.credential_id == _b64url(cred_data.credential_id)
        )
    )
    if existing is not None:
        return existing
    row = PasskeyCredential(
        id=new_id(), user_id=user.id, name=name or "Passkey",
        credential_id=_b64url(cred_data.credential_id),
        attested_data=_b64url(bytes(cred_data)),
        sign_count=auth_data.counter,
        transports_json=json.dumps(response.get("transports") or []),
        created_at=now_utc_iso(), updated_at=now_utc_iso(),
    )
    db.add(row)
    db.commit()
    return row


def list_credentials(db: DBSession, user: User) -> list[PasskeyCredential]:
    return list(
        db.scalars(
            select(PasskeyCredential)
            .where(PasskeyCredential.user_id == user.id)
            .order_by(PasskeyCredential.created_at)
        ).all()
    )


# —— 登录仪式（发现式：无用户名，凭 credential 反查用户） ———


def login_begin(db: DBSession, settings: Settings) -> dict[str, Any]:
    options, state = _server(settings).authenticate_begin(user_verification="preferred")
    _store_challenge(db, user_id=None, purpose="login", challenge=state["challenge"])
    return _options_to_json(options)


def login_complete(
    db: DBSession, settings: Settings, response: dict[str, Any]
) -> tuple[PasskeyCredential, User]:
    """校验断言 → (凭据, 用户)。sign_count 单调防克隆；失败即整体拒绝。"""
    challenge_b64 = _client_challenge_b64(response)
    if _consume_challenge(db, challenge_b64=challenge_b64, purpose="login") is None:
        raise DomainError("challenge 无效或已过期，请重新发起登录")
    cred = db.scalar(
        select(PasskeyCredential).where(PasskeyCredential.credential_id == response["id"])
    )
    if cred is None:
        raise DomainError("凭据未注册")

    from fido2.webauthn import AttestedCredentialData

    user = db.scalar(select(User).where(User.id == cred.user_id))
    if user is None:
        raise DomainError("凭据所属用户不存在")

    cred_data = AttestedCredentialData(_unb64url(cred.attested_data))
    # authenticate_complete 校验断言（origin/challenge/签名）——返回值即凭据数据，无需再用
    _server(settings).authenticate_complete(
        {"challenge": challenge_b64, "user_verification": "preferred"},
        [cred_data],
        {
            "id": _unb64url(response["id"]),
            "rawId": _unb64url(response.get("rawId") or response["id"]),
            "type": "public-key",
            "response": {
                "clientDataJSON": _unb64url(response["response"]["clientDataJSON"]),
                "authenticatorData": _unb64url(response["response"]["authenticatorData"]),
                "signature": _unb64url(response["response"]["signature"]),
            },
        },
    )
    # 断言计数器：authenticatorData[33:37] 大端（authenticate_complete 返回凭据数据，不含它）
    auth_bytes = _unb64url(response["response"]["authenticatorData"])
    new_count = int.from_bytes(auth_bytes[33:37], "big")
    if new_count <= cred.sign_count:
        # 同步克隆信号：拒绝并要求重新注册（8_SECURITY §3 会话安全口径）
        raise DomainError("凭据计数器异常（可能被克隆），请删除后重新注册")
    cred.sign_count = new_count
    cred.last_used_at = now_utc_iso()
    cred.updated_at = now_utc_iso()
    db.commit()
    return cred, user


def delete_credential(db: DBSession, user: User, credential_id: str) -> None:
    row = db.scalar(
        select(PasskeyCredential).where(
            PasskeyCredential.credential_id == credential_id,
            PasskeyCredential.user_id == user.id,
        )
    )
    if row is None:
        raise DomainError("凭据不存在")
    db.delete(row)
    db.commit()


def _client_challenge_b64(response: dict[str, Any]) -> str:
    """从 clientDataJSON 提取 challenge（b64url，无需解码再编码）。"""
    import json as _json

    client_json = _unb64url(response["response"]["clientDataJSON"]).decode("utf-8")
    challenge: str = _json.loads(client_json)["challenge"]
    return challenge


__all__ = [
    "CHALLENGE_TTL_SECONDS",
    "PasskeyDisabledError",
    "register_begin",
    "register_complete",
    "list_credentials",
    "login_begin",
    "login_complete",
    "delete_credential",
    "repository",
]
