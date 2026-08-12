"""Identity auth 端点测试：登录/限流/CSRF/改密（8_SECURITY §3）。"""

from wws_adviser.modules.identity import service


def _login(client, username="alice", password="pw12345", key="k1"):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={"Idempotency-Key": key},
    )


def test_login_success_sets_cookies(migrated_client):
    service.reset_login_rate_limit()
    r = _login(migrated_client)
    assert r.status_code == 200
    assert "user_id_hash" in r.json()
    assert "wws_session" in migrated_client.cookies
    assert "csrf_token" in migrated_client.cookies


def test_login_wrong_password(migrated_client):
    service.reset_login_rate_limit()
    assert _login(migrated_client, password="wrong").status_code == 401


def test_login_rate_limited_after_5(migrated_client):
    service.reset_login_rate_limit()
    for i in range(5):
        r = _login(migrated_client, password="wrong", key=f"fail{i}")
        assert r.status_code == 401
    assert _login(migrated_client, password="wrong", key="fail6").status_code == 429


def test_login_missing_idempotency_key(migrated_client):
    r = migrated_client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "pw12345"}
    )
    assert r.status_code == 400  # MISSING_IDEMPOTENCY_KEY


def test_session_info_requires_login(migrated_client):
    assert migrated_client.get("/api/v1/auth/session").status_code == 401


def test_session_info_after_login(migrated_client):
    service.reset_login_rate_limit()
    _login(migrated_client)
    r = migrated_client.get("/api/v1/auth/session")
    assert r.status_code == 200
    assert "user_id_hash" in r.json()


def test_csrf_protects_writes(migrated_client):
    service.reset_login_rate_limit()
    _login(migrated_client)
    # logout 缺 X-CSRF-Token → 403
    assert migrated_client.post("/api/v1/auth/logout").status_code == 403
    # 带正确 CSRF → 200
    csrf = migrated_client.cookies.get("csrf_token")
    r = migrated_client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200


def test_change_password(migrated_client):
    service.reset_login_rate_limit()
    _login(migrated_client, key="c1")
    csrf = migrated_client.cookies.get("csrf_token")
    r = migrated_client.post(
        "/api/v1/auth/password",
        json={"old_password": "pw12345", "new_password": "newpw789"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    # 旧密码失败
    service.reset_login_rate_limit()
    assert _login(migrated_client, password="pw12345", key="c2").status_code == 401
    # 新密码成功
    service.reset_login_rate_limit()
    assert _login(migrated_client, password="newpw789", key="c3").status_code == 200
