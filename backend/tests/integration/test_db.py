"""SQLite 存储层测试：PRAGMA、可写性、备份一致性、迁移空库可建。"""

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from wws_adviser.core.backup import backup_database
from wws_adviser.core.config import Settings
from wws_adviser.core.db import check_db_writable, create_app_engine


def test_sqlite_pragmas(tmp_path):
    settings = Settings(env="test", data_dir=tmp_path)
    engine = create_app_engine(settings)
    with engine.connect() as conn:
        assert str(conn.execute(text("PRAGMA journal_mode")).scalar()).lower() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000
    engine.dispose()


def test_db_writable(tmp_path):
    settings = Settings(env="test", data_dir=tmp_path)
    engine = create_app_engine(settings)
    assert check_db_writable(engine) is True
    engine.dispose()


def test_backup_produces_consistent_copy(tmp_path):
    src = tmp_path / "app.db"
    conn = sqlite3.connect(str(src))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1),(2),(3)")
    conn.commit()
    conn.close()

    dest = tmp_path / "backup" / "app.db.bak"
    returned = backup_database(src, dest)
    assert returned == dest
    assert dest.exists()

    conn2 = sqlite3.connect(str(dest))
    assert conn2.execute("SELECT count(*) FROM t").fetchone()[0] == 3
    conn2.close()


def test_migration_empty_db_runnable(tmp_path, monkeypatch):
    """alembic upgrade head 从空库可建（Phase 0 退出条件 + CI migrate-check）。"""
    monkeypatch.setenv("WWSE_DATA_DIR", str(tmp_path))
    backend_dir = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(backend_dir)

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(backend_dir / "alembic.ini"))
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{(tmp_path / 'app.db').as_posix()}")
    table_names = inspect(engine).get_table_names()
    engine.dispose()

    assert "app_meta" in table_names
    assert "alembic_version" in table_names


def test_health_ready_green_after_migration(tmp_path, monkeypatch):
    """迁移后 /health/ready 应返回 200。"""
    monkeypatch.setenv("WWSE_DATA_DIR", str(tmp_path))
    backend_dir = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(backend_dir)

    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(backend_dir / "alembic.ini")), "head")

    # 迁移已落 tmp_path，重新加载 app 指向同一 data_dir
    from fastapi.testclient import TestClient

    from wws_adviser.api.app import create_app
    from wws_adviser.core.config import load_settings
    from wws_adviser.main import lifespan

    settings = load_settings(env="test", data_dir=tmp_path)
    app = create_app(settings, lifespan=lifespan)
    with TestClient(app) as client:
        r = client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["migration_applied"] is True
