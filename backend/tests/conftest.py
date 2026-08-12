"""共享 fixtures。"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from wws_adviser.api.app import create_app
from wws_adviser.core.config import Settings
from wws_adviser.main import lifespan


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(env="test", data_dir=tmp_path)


@pytest.fixture
def app(settings):
    return create_app(settings, lifespan=lifespan)


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_session(tmp_path):
    """已建表（Base.metadata.create_all）的 DB session，供 service 层测试。"""
    from wws_adviser.core.db import Base, create_app_engine, make_session_factory
    from wws_adviser.modules.audit import models as _audit_models  # noqa: F401
    from wws_adviser.modules.identity import models as _identity_models  # noqa: F401
    from wws_adviser.modules.jobs import models as _jobs_models  # noqa: F401

    s = Settings(env="test", data_dir=tmp_path)
    engine = create_app_engine(s)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def migrated_client(tmp_path) -> Iterator[TestClient]:
    """已建表 + 预置测试用户(alice/pw12345) 的 HTTP client。"""
    from fastapi.testclient import TestClient

    from wws_adviser.api.app import create_app
    from wws_adviser.core.db import Base, create_app_engine, make_session_factory
    from wws_adviser.core.ids import new_id
    from wws_adviser.core.time import now_utc_iso
    from wws_adviser.main import lifespan
    from wws_adviser.modules.audit import models as _a  # noqa: F401
    from wws_adviser.modules.identity import domain  # noqa: F401
    from wws_adviser.modules.identity import models as identity_models
    from wws_adviser.modules.jobs import models as _j  # noqa: F401

    settings = Settings(env="test", data_dir=tmp_path)
    engine = create_app_engine(settings)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as db:
        db.add(
            identity_models.User(
                id=new_id(),
                username="alice",
                password_hash=domain.hash_password("pw12345"),
                created_at=now_utc_iso(),
                updated_at=now_utc_iso(),
                version=1,
            )
        )
        db.commit()
    engine.dispose()

    app = create_app(settings, lifespan=lifespan)
    with TestClient(app) as c:
        yield c
