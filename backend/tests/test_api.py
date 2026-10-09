"""Workflow guarantees through the HTTP API (segregation of duties, locks, roles)."""
from tests.conftest import login


def _run(client, run_id, who="bilal"):
    r = client.get(f"/api/v1/payment-runs/{run_id}", headers=login(client, who))
    assert r.status_code == 200, r.text
    return r.json()


def test_demo_week_scored_and_red_locked(client, demo_run):
    run = _run(client, demo_run)
    assert len(run["lines"]) == 40
    reds = [l for l in run["lines"] if l["decision"] == "blocked"]
    assert reds and all(l["status"] == "blocked" for l in reds)
    assert all(l["case"] and l["case"]["status"] == "open" for l in reds)
    cash = run["cash"]
    assert cash["with_nigraan"]["low_point"] >= cash["release_everything"]["low_point"]


def test_red_can_never_be_released(client, demo_run):
    run = _run(client, demo_run)
    red = next(l for l in run["lines"] if l["decision"] == "blocked")
    for who in ("bilal", "rashid"):
        r = client.post(f"/api/v1/payment-runs/{demo_run}/approve", headers=login(client, who),
                        json={"payment_ids": [red["id"]]})
        assert r.status_code == 409, r.text
        assert r.json()["code"] == "blocked_line"


def test_creator_cannot_approve_own_yellow(client, demo_run):
    run = _run(client, demo_run)
    yellow = next(l for l in run["lines"] if l["decision"] == "review")
    creator_email = {"Sana Iqbal": "sana", "Kashif Mehmood": "kashif", "Bilal Ahmed": "bilal",
                     "Haji Abdul Rashid": "rashid"}[yellow["created_by"]]
    if creator_email in ("sana", "kashif"):
        # accountants cannot release at all
        r = client.post(f"/api/v1/payment-runs/{demo_run}/approve", headers=login(client, creator_email),
                        json={"payment_ids": [yellow["id"]]})
        assert r.status_code == 403
    # the approver who entered a line can't approve it: make bilal the creator via a yellow line he enters
    from app.db import SessionLocal
    from app.models import Payment, User

    with SessionLocal() as db:
        bilal = db.query(User).filter(User.email == "bilal@bismillah.pk").one()
        p = db.get(Payment, yellow["id"])
        p.created_by = bilal.id
        db.commit()
    r = client.post(f"/api/v1/payment-runs/{demo_run}/approve", headers=login(client, "bilal"),
                    json={"payment_ids": [yellow["id"]]})
    assert r.status_code == 403 and r.json()["code"] == "same_user"
    r = client.post(f"/api/v1/payment-runs/{demo_run}/approve", headers=login(client, "rashid"),
                    json={"payment_ids": [yellow["id"]]})
    assert r.status_code == 200, r.text


def test_export_blocked_while_lines_open(client, demo_run):
    r = client.get(f"/api/v1/payment-runs/{demo_run}/export", headers=login(client, "rashid"))
    assert r.status_code == 409 and r.json()["code"] in ("open_lines", "nothing_to_export")


def test_wrong_role_forbidden(client, demo_run):
    sana = login(client, "sana")
    r = client.post(f"/api/v1/payment-runs/{demo_run}/approve-green", headers=sana)
    assert r.status_code == 403
    r = client.post("/api/v1/admin/retrain", headers=sana)
    assert r.status_code == 403
    case = client.get("/api/v1/cases?status=open", headers=sana).json()[0]
    r = client.post(f"/api/v1/cases/{case['id']}/resolve", headers=sana, json={"outcome": "false_alarm"})
    assert r.status_code == 403
    assert client.get("/api/v1/cases").status_code == 401


def test_full_release_flow_then_export(client, demo_run):
    rashid = login(client, "rashid")
    r = client.post(f"/api/v1/payment-runs/{demo_run}/approve-green", headers=rashid)
    assert r.status_code == 200, r.text
    run = _run(client, demo_run, "rashid")
    pending = [l for l in run["lines"] if l["status"] == "pending"]
    if pending:  # remaining yellows: hold them
        r = client.post(f"/api/v1/payment-runs/{demo_run}/hold", headers=rashid,
                        json={"payment_ids": [l["id"] for l in pending]})
        assert r.status_code == 200
    r = client.get(f"/api/v1/payment-runs/{demo_run}/export", headers=rashid)
    assert r.status_code == 200, r.text
    assert r.text.startswith("payment_id,value_date")
    blocked = {l["id"] for l in run["lines"] if l["decision"] == "blocked"}
    exported = {int(row.split(",")[0]) for row in r.text.strip().splitlines()[1:]}
    assert exported and not exported & blocked


def test_errors_have_envelope(client):
    r = client.post("/api/v1/auth/login", json={"email": "nobody@x.pk", "password": "x"})
    assert r.status_code == 401 and set(r.json()) >= {"code", "message"}
    r = client.get("/api/v1/cases/999999", headers=login(client, "bilal"))
    assert r.status_code == 404 and r.json()["code"] == "not_found"
