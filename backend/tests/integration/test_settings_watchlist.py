"""自选（watchlist）API 测试：GET/PUT + 校验 + 审计（技术债清理：PORT 自选 Tab）。"""

from wws_adviser.modules.appsettings import service as appsettings_service
from wws_adviser.modules.identity import service as identity_service


def _login(client) -> None:
    identity_service.reset_login_rate_limit()
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "pw12345"},
        headers={"Idempotency-Key": "login-watchlist"},
    )
    assert r.status_code == 200


def test_watchlist_default_empty_and_put_roundtrip(migrated_client) -> None:
    _login(migrated_client)
    r0 = migrated_client.get("/api/v1/settings/watchlist")
    assert r0.status_code == 200
    assert r0.json() == {"codes": []}

    csrf = {"X-CSRF-Token": migrated_client.cookies.get("csrf_token", "")}
    r1 = migrated_client.put(
        "/api/v1/settings/watchlist",
        json={"codes": ["600519", "510300", "600519"]},
        headers=csrf,
    )
    assert r1.status_code == 200
    # 保序去重
    assert r1.json() == {"codes": ["600519", "510300"]}

    r2 = migrated_client.get("/api/v1/settings/watchlist")
    assert r2.json() == {"codes": ["600519", "510300"]}


def test_watchlist_rejects_invalid_code(migrated_client) -> None:
    _login(migrated_client)
    csrf = {"X-CSRF-Token": migrated_client.cookies.get("csrf_token", "")}
    r = migrated_client.put(
        "/api/v1/settings/watchlist", json={"codes": ["60051A"]}, headers=csrf
    )
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


def test_watchlist_requires_auth(client) -> None:
    r = client.get("/api/v1/settings/watchlist")
    assert r.status_code == 401


def test_watchlist_service_roundtrip(db_session) -> None:
    codes = appsettings_service.set_watchlist(
        db_session, user_id="u1", codes=["000001", "000001", "600519"]
    )
    assert codes == ["000001", "600519"]
    assert appsettings_service.get_watchlist(db_session) == ["000001", "600519"]
