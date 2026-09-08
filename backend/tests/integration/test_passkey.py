"""Passkey 集成测试（Phase 3.5 P1）：进程内伪认证器走完注册/登录仪式。

伪认证器用 cryptography EC P-256 密钥构造 attestationObject（fmt=none）与
assertion 签名——完整校验 Fido2Server 的 challenge/origin/sign_count 链路。
"""

import hashlib
import json
import struct
from base64 import urlsafe_b64decode, urlsafe_b64encode

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

RP_ID = "test.local"
ORIGIN = "https://test.local"


def _b64u(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64u(data: str) -> bytes:
    return urlsafe_b64decode(data + "=" * (-len(data) % 4))


class FakeAuthenticator:
    """最小软认证器：ES256 签名、discoverable 凭据、单调 sign_count。"""

    def __init__(self) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        pub = self.key.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        self.credential_id = b"\x01" + hashlib.sha256(pub).digest()[:31]
        self.sign_count = 0

    def _cose_key(self) -> bytes:
        from fido2 import cbor  # cbor.encode

        nums = self.key.public_key().public_numbers()
        x, y = nums.x.to_bytes(32, "big"), nums.y.to_bytes(32, "big")
        return cbor.encode({1: 2, 3: -7, -1: 1, -2: x, -3: y})

    def _auth_data(self, *, attested: bool) -> bytes:
        rp_hash = hashlib.sha256(RP_ID.encode()).digest()
        flags = 0x05 | (0x40 if attested else 0)  # UP|UV (|AT)
        head = rp_hash + bytes([flags]) + struct.pack(">I", self.sign_count)
        if not attested:
            return head
        return (
            head + b"\x00" * 16 + struct.pack(">H", len(self.credential_id))
            + self.credential_id + self._cose_key()
        )

    def register(self, challenge: bytes) -> dict:
        from fido2 import cbor  # cbor.encode

        client_data = json.dumps(
            {"type": "webauthn.create", "challenge": _b64u(challenge), "origin": ORIGIN},
            separators=(",", ":"),
        ).encode()
        att_obj = cbor.encode({
            "fmt": "none", "attStmt": {}, "authData": self._auth_data(attested=True),
        })
        return {
            "id": _b64u(self.credential_id),
            "rawId": _b64u(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": _b64u(client_data),
                "attestationObject": _b64u(att_obj),
            },
        }

    def authenticate(self, challenge: bytes) -> dict:
        self.sign_count += 1
        client_data = json.dumps(
            {"type": "webauthn.get", "challenge": _b64u(challenge), "origin": ORIGIN},
            separators=(",", ":"),
        ).encode()
        auth_data = self._auth_data(attested=False)
        message = auth_data + hashlib.sha256(client_data).digest()
        signature = self.key.sign(message, ec.ECDSA(hashes.SHA256()))
        return {
            "id": _b64u(self.credential_id),
            "rawId": _b64u(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": _b64u(client_data),
                "authenticatorData": _b64u(auth_data),
                "signature": _b64u(signature),
            },
        }


def _login(client: TestClient, key: str) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "pw12345"},
        headers={"Idempotency-Key": key},
    )
    assert r.status_code == 200
    return {"x-csrf-token": r.cookies["csrf_token"], "Idempotency-Key": key}


def _challenge_of(options: dict) -> bytes:
    return _unb64u(options["publicKey"]["challenge"])


def test_passkey_register_and_login_flow(migrated_client: TestClient) -> None:
    headers = _login(migrated_client, "pk-1")

    # 注册仪式
    r1 = migrated_client.post(
        "/api/v1/auth/passkey/register/options",
        headers={**headers, "Idempotency-Key": "pk-reg-opt-1"},
    )
    assert r1.status_code == 200, r1.text
    options = r1.json()["options"]

    authr = FakeAuthenticator()
    reg_resp = authr.register(_challenge_of(options))
    r2 = migrated_client.post(
        "/api/v1/auth/passkey/register/verify",
        json={**reg_resp, "name": "我的手机"},
        headers={**headers, "Idempotency-Key": "pk-reg-verify-1"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["name"] == "我的手机"
    assert r2.json()["sign_count"] == 0

    # 凭据列表可见
    r3 = migrated_client.get("/api/v1/auth/passkey/credentials", headers=headers)
    assert r3.status_code == 200
    assert len(r3.json()) == 1

    # 登录仪式（登出后用凭据登录，无需密码）
    assert migrated_client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    r4 = migrated_client.post("/api/v1/auth/passkey/login/options")
    assert r4.status_code == 200, r4.text
    login_options = r4.json()["options"]

    assertion = authr.authenticate(_challenge_of(login_options))
    r5 = migrated_client.post("/api/v1/auth/passkey/login/verify", json=assertion)
    assert r5.status_code == 200, r5.text
    assert r5.json()["user_id_hash"]

    # 会话可用（session 端点回显）+ sign_count 递增落库（GET 不需 CSRF）
    r6 = migrated_client.get("/api/v1/auth/session")
    assert r6.status_code == 200
    assert r6.json()["user_id_hash"] == r5.json()["user_id_hash"]

    r7 = migrated_client.get("/api/v1/auth/passkey/credentials")
    assert r7.status_code == 200, r7.text
    assert r7.json()[0]["sign_count"] == 1


def test_passkey_challenge_single_use_and_replay(migrated_client: TestClient) -> None:
    """challenge 一次性：重放同一断言被拒。"""
    headers = _login(migrated_client, "pk-2")
    options = migrated_client.post(
        "/api/v1/auth/passkey/register/options",
        headers={**headers, "Idempotency-Key": "pk-reg-opt-2"},
    ).json()["options"]
    authr = FakeAuthenticator()
    reg = authr.register(_challenge_of(options))
    r1 = migrated_client.post(
        "/api/v1/auth/passkey/register/verify",
        json=reg,
        headers={**headers, "Idempotency-Key": "pk-reg-verify-2"},
    )
    assert r1.status_code == 200

    login_options = migrated_client.post(
        "/api/v1/auth/passkey/login/options"
    ).json()["options"]
    assertion = authr.authenticate(_challenge_of(login_options))
    ok = migrated_client.post("/api/v1/auth/passkey/login/verify", json=assertion)
    assert ok.status_code == 200
    # 重放：challenge 已消费 → 拒绝（即便签名本身有效）
    replay = migrated_client.post("/api/v1/auth/passkey/login/verify", json=assertion)
    assert replay.status_code >= 400


def test_passkey_clone_detection(migrated_client: TestClient) -> None:
    """sign_count 不前进（克隆信号）→ 拒绝。"""
    headers = _login(migrated_client, "pk-3")
    options = migrated_client.post(
        "/api/v1/auth/passkey/register/options",
        headers={**headers, "Idempotency-Key": "pk-reg-opt-3"},
    ).json()["options"]
    authr = FakeAuthenticator()
    reg = authr.register(_challenge_of(options))
    migrated_client.post(
        "/api/v1/auth/passkey/register/verify",
        json=reg,
        headers={**headers, "Idempotency-Key": "pk-reg-verify-3"},
    )

    lo = migrated_client.post("/api/v1/auth/passkey/login/options").json()["options"]
    ok = migrated_client.post(
        "/api/v1/auth/passkey/login/verify", json=authr.authenticate(_challenge_of(lo))
    )
    assert ok.status_code == 200

    # 克隆：不递增 sign_count 直接签（计数器停在已存值）
    lo2 = migrated_client.post("/api/v1/auth/passkey/login/options").json()["options"]
    bad = authr.authenticate(_challenge_of(lo2))
    auth_bytes = bytearray(_unb64u(bad["response"]["authenticatorData"]))
    auth_bytes[33:37] = struct.pack(">I", 1)  # 计数器改为 1（≤ 已存的 1）
    bad_auth = bytes(auth_bytes)
    msg = bad_auth + hashlib.sha256(
        _unb64u(bad["response"]["clientDataJSON"])
    ).digest()
    bad["response"]["authenticatorData"] = _b64u(bad_auth)
    bad["response"]["signature"] = _b64u(authr.key.sign(msg, ec.ECDSA(hashes.SHA256())))
    r = migrated_client.post("/api/v1/auth/passkey/login/verify", json=bad)
    assert r.status_code >= 400
