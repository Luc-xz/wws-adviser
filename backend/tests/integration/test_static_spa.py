"""SPA history 回退集成测试：深链/刷新直达应用壳；API 与文件型 404 语义不变。"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wws_adviser.api.app import create_app
from wws_adviser.core.config import Settings

_SHELL = "<!doctype html><html><body>app-shell</body></html>"


@pytest.fixture
def spa_client(tmp_path: Path) -> Iterator[TestClient]:
    static_dir = tmp_path / "static"
    (static_dir / "assets").mkdir(parents=True)
    (static_dir / "index.html").write_text(_SHELL, encoding="utf-8")
    (static_dir / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    settings = Settings(
        env="test",
        data_dir=tmp_path / "data",
        static_dir=static_dir,
        passkey_rp_id="test.local",
        passkey_origin="https://test.local",
    )
    with TestClient(create_app(settings)) as c:
        yield c


def test_root_serves_index(spa_client: TestClient) -> None:
    r = spa_client.get("/")
    assert r.status_code == 200
    assert "app-shell" in r.text


def test_deep_link_falls_back_to_shell(spa_client: TestClient) -> None:
    """SPA history 模式：非文件型深链回退 index.html（刷新/外链直达）。"""
    for path in (
        "/transactions/new",
        "/reports/01M0RXMV",
        "/instruments/603823",
        "/settings/data-sources",
    ):
        r = spa_client.get(path)
        assert r.status_code == 200, path
        assert "app-shell" in r.text, path


def test_api_404_not_masked_by_shell(spa_client: TestClient) -> None:
    """未知 API 路径保持 404 且不返回 HTML（前端 fetch 的 404 语义不变）。"""
    r = spa_client.get("/api/v1/definitely-missing")
    assert r.status_code == 404
    assert "app-shell" not in r.text


def test_file_like_404_stays_404(spa_client: TestClient) -> None:
    """文件型路径（含扩展名）不回退——缺资源就该 404，不用 HTML 掩盖。"""
    r = spa_client.get("/assets/missing.js")
    assert r.status_code == 404


def test_real_asset_served(spa_client: TestClient) -> None:
    r = spa_client.get("/assets/app.js")
    assert r.status_code == 200
    assert "console.log" in r.text
