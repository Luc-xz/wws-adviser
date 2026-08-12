"""单 worker 守卫测试（1_REPO_STRUCTURE.md §7 必测项）。"""

import pytest

from wws_adviser.core.config import Settings
from wws_adviser.core.worker_guard import MultiWorkerError, enforce_single_worker


def test_prod_multi_worker_rejected(monkeypatch, tmp_path):
    """生产环境多 worker 必须拒绝启动。"""
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    settings = Settings(
        env="prod", data_dir=tmp_path, session_secret="real-prod-secret"
    )
    with pytest.raises(MultiWorkerError):
        enforce_single_worker(settings)


def test_non_prod_multi_worker_warns(monkeypatch, tmp_path, caplog):
    """非生产多 worker 仅告警，不抛错。"""
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    settings = Settings(env="dev", data_dir=tmp_path)
    enforce_single_worker(settings)  # 不抛
    assert any("多 worker" in r.getMessage() for r in caplog.records)


def test_single_worker_passes(monkeypatch, tmp_path):
    """单 worker（含生产）正常通过。"""
    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    settings = Settings(
        env="prod", data_dir=tmp_path, session_secret="real-prod-secret"
    )
    enforce_single_worker(settings)  # 不抛


def test_no_env_uses_expected_workers(tmp_path):
    """未设 WEB_CONCURRENCY 时用 expected_workers。"""
    settings = Settings(env="dev", data_dir=tmp_path, expected_workers=1)
    enforce_single_worker(settings)  # 不抛
