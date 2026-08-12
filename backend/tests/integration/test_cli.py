"""CLI create-user 测试（首个用户 provisioning，8_SECURITY §3）。"""

import pytest

from wws_adviser.cli import create_user


def _prepare_db(tmp_path, monkeypatch):
    monkeypatch.setenv("WWSE_DATA_DIR", str(tmp_path))
    from wws_adviser.core.config import load_settings
    from wws_adviser.core.db import Base, create_app_engine
    from wws_adviser.modules.audit import models as _a  # noqa: F401
    from wws_adviser.modules.identity import models as _i  # noqa: F401
    from wws_adviser.modules.jobs import models as _j  # noqa: F401

    s = load_settings()
    engine = create_app_engine(s)
    Base.metadata.create_all(engine)
    engine.dispose()


def test_create_user_success(tmp_path, monkeypatch):
    _prepare_db(tmp_path, monkeypatch)
    create_user("bob", "secret123")  # 不抛即成功


def test_create_user_duplicate_rejected(tmp_path, monkeypatch):
    _prepare_db(tmp_path, monkeypatch)
    create_user("bob", "secret123")
    with pytest.raises(SystemExit):
        create_user("bob", "other456")
