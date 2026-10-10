import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="nigraan-test-")
# TEST_DATABASE_URL=postgresql://... runs the same suite against Postgres
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
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


def resolution_payload(client, case_id, outcome="false_alarm"):
    response = client.get(f"/api/v1/cases/{case_id}", headers=login(client, "rashid"))
    assert response.status_code == 200, response.text
    detail = response.json()
    return {"outcome": outcome, "note": "Reviewed the invoice, delivery records and independently verified the vendor.",
            "verification": {"result": "verified_legitimate" if outcome == "false_alarm" else "confirmed_issue",
                             "method": "documents", "checks": [item["id"] for item in detail["verification_plan"]["checklist"]],
                             "reference": "Signed delivery challan and vendor confirmation recorded in the case file."}}


@pytest.fixture(scope="session")
def demo_run(client):
    h = login(client, "rashid")
    reset = client.post("/api/v1/demo/reset", headers=h)
    assert reset.status_code == 200, reset.text
    h = login(client, "sana")
    r = client.post("/api/v1/demo/load-week", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["run_id"]
