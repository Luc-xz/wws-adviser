"""Web Push 测试（Phase 3.5 P1）：订阅登记 API + 发送扇出 + 真实 VAPID 签名链路。

pywebpush/py_vapid 在 dev 依赖组——测试走真实加密与签名（不发网络：httpx 桩）。
"""

from base64 import urlsafe_b64encode

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from wws_adviser.modules.notifications import push_repository
from wws_adviser.modules.notifications.models import PushSubscription

from .test_research_generation import _login


def _vapid_pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def _seed_user(db, user_id: str = "u1") -> str:
    """db_session 级测试的用户种子（push_subscriptions.user_id FK）。"""
    from wws_adviser.core.ids import new_id
    from wws_adviser.core.time import now_utc_iso
    from wws_adviser.modules.identity import domain as identity_domain
    from wws_adviser.modules.identity.models import User

    existing = db.get(User, user_id)
    if existing is not None:
        return user_id
    db.add(User(
        id=user_id, username=f"push-{new_id()}",
        password_hash=identity_domain.hash_password("pw12345"),
        created_at=now_utc_iso(), updated_at=now_utc_iso(), version=1,
    ))
    db.commit()
    return user_id


def _sub_keys() -> tuple[str, str]:
    """真实 P-256 公钥 + 16 字节 auth（http_ece 校验点格式，不能用假字节）。"""
    key = ec.generate_private_key(ec.SECP256R1())
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return (
        urlsafe_b64encode(pub).rstrip(b"=").decode(),
        urlsafe_b64encode(b"y" * 16).rstrip(b"=").decode(),
    )


def _sub_body(endpoint: str = "https://push.example/send/1") -> dict:
    p256dh, auth = _sub_keys()
    return {"endpoint": endpoint, "p256dh": p256dh, "auth": auth}


def _enable_vapid(client: TestClient) -> None:
    client.app.state.settings.push_vapid_private_pem = _vapid_pem()
    client.app.state.settings.push_vapid_subject = "mailto:me@example.com"


def test_vapid_public_and_subscribe(migrated_client: TestClient) -> None:
    """公钥下发（从 PEM 推导）+ 订阅幂等登记 + 解绑属主校验。"""
    from wws_adviser.infrastructure.notifications import web_push

    _enable_vapid(migrated_client)
    pem = migrated_client.app.state.settings.push_vapid_private_pem
    headers = _login(migrated_client)

    r = migrated_client.get("/api/v1/push/vapid-public", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True
    assert body["public_key"] == web_push.vapid_public_key_from_pem(pem)

    r1 = migrated_client.post(
        "/api/v1/push/subscriptions",
        json=_sub_body(),
        headers={**headers, "Idempotency-Key": "push-sub-1"},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["created"] is True

    # 同 endpoint 再次登记 → 幂等不新建
    r2 = migrated_client.post(
        "/api/v1/push/subscriptions",
        json=_sub_body(),
        headers={**headers, "Idempotency-Key": "push-sub-2"},
    )
    assert r2.status_code == 200
    assert r2.json()["created"] is False

    # 解绑（属主校验：二次删除 404）
    sub_id = r1.json()["id"]
    r3 = migrated_client.delete(
        f"/api/v1/push/subscriptions/{sub_id}",
        headers={**headers, "Idempotency-Key": "push-del-1"},
    )
    assert r3.status_code == 200
    r4 = migrated_client.delete(
        f"/api/v1/push/subscriptions/{sub_id}",
        headers={**headers, "Idempotency-Key": "push-del-2"},
    )
    assert r4.status_code >= 400


async def test_dispatch_push_signs_and_sends(db_session, tmp_path) -> None:
    """真实 VAPID 签名 + pywebpush 加密 + httpx 桩投递。"""
    from wws_adviser.core.config import Settings
    from wws_adviser.modules.notifications import service as notifications_service

    settings = Settings(
        env="test", data_dir=tmp_path,
        push_vapid_private_pem=_vapid_pem(),
        push_vapid_subject="mailto:me@example.com",
        notification_privacy_mode=True,
    )
    p256dh, auth = _sub_keys()
    push_repository.upsert(
        db_session, user_id=_seed_user(db_session), endpoint="https://push.example/send/1",
        p256dh=p256dh, auth=auth,
    )

    captured: dict = {}

    async def fake_post(url, content=None, headers=None):
        captured["url"] = url
        captured["body"] = content
        captured["headers"] = dict(headers or {})

        class _Resp:
            status_code = 201

        return _Resp()

    class _C:
        post = staticmethod(fake_post)

    sent = await notifications_service.dispatch_push(
        db_session, settings,
        event_type="research_completed",
        payload={"task_type": "company", "subject": "600519", "task_id": "t1"},
        push_client=_C(),
    )
    assert sent == 1
    # VAPID 头 + 加密 body（aes128gcm：16 字节 salt + 4 字节 rs=4096 + keyid…）
    assert captured["headers"]["Authorization"].startswith("vapid ")
    body: bytes = captured["body"]
    assert len(body) > 21
    assert int.from_bytes(body[16:20], "big") == 4096
    assert captured["headers"]["TTL"] == "60"


async def test_dispatch_push_gone_revokes(db_session, tmp_path) -> None:
    """推送服务 410 → 订阅软撤销，下次不再投递。"""
    from wws_adviser.core.config import Settings
    from wws_adviser.modules.notifications import service as notifications_service

    settings = Settings(
        env="test", data_dir=tmp_path,
        push_vapid_private_pem=_vapid_pem(),
        push_vapid_subject="mailto:me@example.com",
    )
    p256dh, auth = _sub_keys()
    row, _ = push_repository.upsert(
        db_session, user_id=_seed_user(db_session), endpoint="https://push.example/gone",
        p256dh=p256dh, auth=auth,
    )

    async def fake_post(url, content=None, headers=None):
        class _Gone:
            status_code = 410
        return _Gone()

    class _C:
        post = staticmethod(fake_post)

    await notifications_service.dispatch_push(
        db_session, settings, event_type="report_completed", payload={},
        push_client=_C(),
    )
    sub = db_session.get(PushSubscription, row.id)
    assert sub is not None and sub.revoked_at is not None


async def test_dispatch_push_not_configured_noop(db_session, tmp_path) -> None:
    """VAPID 未配置 → 不发送、订阅保留（配置后可推）。"""
    from wws_adviser.core.config import Settings
    from wws_adviser.modules.notifications import service as notifications_service

    settings = Settings(env="test", data_dir=tmp_path)
    p256dh, auth = _sub_keys()
    row, _ = push_repository.upsert(
        db_session, user_id=_seed_user(db_session), endpoint="https://push.example/x",
        p256dh=p256dh, auth=auth,
    )
    sent = await notifications_service.dispatch_push(
        db_session, settings, event_type="report_completed", payload={}
    )
    assert sent == 0
    sub = db_session.get(PushSubscription, row.id)
    assert sub is not None and sub.revoked_at is None
