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
