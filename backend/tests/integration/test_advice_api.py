"""Advice API 集成测试：POST /assistant/intraday（登录 + CSRF + 幂等键 + 暂停语义）。"""

from fastapi.testclient import TestClient


def _login(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "pw12345"},
        headers={"Idempotency-Key": "login-advice-1"},
    )
    assert r.status_code == 200
    csrf = r.cookies.get("csrf_token")
    assert csrf
    return {"x-csrf-token": csrf, "Idempotency-Key": "intraday-1"}


def test_intraday_requires_auth(client: TestClient) -> None:
    # CSRF 中间件先于鉴权：凑齐 double-submit 对后，无会话 → 401
    r = client.post(
        "/api/v1/assistant/intraday", json={"code": "600519"},
        headers={"Idempotency-Key": "x", "x-csrf-token": "k"},
        cookies={"csrf_token": "k"},
    )
    assert r.status_code == 401


def test_intraday_requires_idempotency_key(migrated_client: TestClient) -> None:
    headers = _login(migrated_client)
    r = migrated_client.post("/api/v1/assistant/intraday", json={"code": "600519"},
                             headers={"x-csrf-token": headers["x-csrf-token"]})
    assert r.status_code == 400
    assert r.json()["code"] == "MISSING_IDEMPOTENCY_KEY"


def test_intraday_returns_suspend_without_calibrated_signal(migrated_client: TestClient) -> None:
    """当前无已校准信号 + 账本未对账 → 按规范返回暂停建议 + 原因（不静默）。"""
    headers = _login(migrated_client)
    r = migrated_client.post("/api/v1/assistant/intraday", json={"code": "600519"},
                             headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == "1"
    advice = body["advice"]
    assert advice["action"] == "suspend"
    assert advice["state"] == "degraded"
    assert advice["f_min"] is None and advice["f_max"] is None  # 暂停不携带区间
    assert "无已校准信号" in advice["reasons"]
    # 有效期语义：expires_at > valid_from
    assert advice["expires_at"] > advice["valid_from"]


def test_intraday_csrf_enforced(migrated_client: TestClient) -> None:
    headers = _login(migrated_client)
    r = migrated_client.post(
        "/api/v1/assistant/intraday", json={"code": "600519"},
        headers={"Idempotency-Key": headers["Idempotency-Key"]},  # 缺 CSRF 头
    )
    assert r.status_code == 403
