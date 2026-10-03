import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "data"


@pytest.fixture(scope="session", autouse=True)
def _env(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "test.db"
    os.environ["DATA_DIR"] = str(FIXTURES)
    os.environ["DATABASE_URL"] = f"sqlite:///{db}"
    os.environ["CURRENT_TERM"] = "FA26"
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["STATIC_DIR"] = str(tmp_path_factory.mktemp("static") / "missing")

    from app import models  # noqa: F401
    from app.models import Base, engine

    Base.metadata.create_all(engine)


@pytest.fixture
def catalog():
    from app.catalog.store import get_catalog

    return get_catalog()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def auth(client):
    import uuid

    code = f"T-{uuid.uuid4().hex[:8]}"
    token = client.post("/api/auth/login", json={"code": code}).json()["token"]
    return {"Authorization": f"Bearer {token}"}
