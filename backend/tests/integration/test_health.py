"""健康检查端点测试（TECHNICAL_ARCHITECTURE.md §16.1）。"""

from fastapi.testclient import TestClient


def test_live_returns_ok(client: TestClient):
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready_unmigrated_returns_503(client: TestClient):
    """未跑迁移时 alembic_version 表不存在 → ready 返回 503。"""
    r = client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["migration_applied"] is False


def test_dependencies_returns_ok(client: TestClient):
    r = client.get("/health/dependencies")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # test 环境不发起真实 SNTP → 固定 unknown（不依赖网络）
    assert body["clock_skew"]["status"] == "unknown"
    assert body["clock_skew"]["threshold_seconds"] == 5


def test_request_id_echoed(client: TestClient):
    """X-Request-ID 缺省时生成，提供时原样回显。"""
    r = client.get("/health/live", headers={"X-Request-ID": "req-abc-123"})
    assert r.headers["X-Request-ID"] == "req-abc-123"

    r2 = client.get("/health/live")
    assert r2.headers["X-Request-ID"]  # 自动生成，非空
