import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="nigraan-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["DEMO_MODE"] = "true"
os.environ["AUTO_SEED"] = "true"
os.environ["JWT_SECRET"] = "test-secret"
os.environ.pop("GEMINI_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def login(client, who: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": f"{who}@bismillah.pk", "password": "nigraan-demo"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def demo_run(client):
    h = login(client, "sana")
    client.post("/api/v1/demo/reset", headers=h)
    h = login(client, "sana")
    r = client.post("/api/v1/demo/load-week", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["run_id"]
