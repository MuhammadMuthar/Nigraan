"""Money, invoice lifecycle and export/forecast guarantees through the real API."""
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select

from app.db import SessionLocal, engine
from app.errors import ApiError
from app.models import Case, Company, Invoice, Payment, PaymentRun, RiskScore, User, Vendor
from app.services.cash.service import CashInputs
from app.services.payment_runs import utcnow
from app.services import payment_runs
from tests.conftest import login, resolution_payload


@pytest.fixture
def invoice(client):
    with SessionLocal() as db:
        company = db.execute(select(Company)).scalars().first()
        vendor = db.execute(select(Vendor).where(Vendor.status == "active")).scalars().first()
        user = db.execute(select(User).where(User.email == "sana@bismillah.pk")).scalars().one()
        number = f"REG-{uuid4().hex[:12]}"
        inv = Invoice(vendor_id=vendor.id, invoice_no=number, invoice_no_norm=number,
                      invoice_date=company.as_of_date, due_date=company.as_of_date + timedelta(days=4),
                      received_at=utcnow(), subtotal=10_000, tax=500, total=10_500,
                      status="received", source="csv", created_by=user.id)
        db.add(inv)
        db.commit()
        return inv.id


@pytest.mark.parametrize("value", [-1, "NaN", "Infinity", "-Infinity", "0.001", "92233720368547759",
                                 "1e999999", "1e-999999"])
def test_invoice_money_rejects_invalid_values_without_writing(client, invoice, value):
    headers = login(client, "sana")
    before = client.get(f"/api/v1/invoices/{invoice}", headers=headers).json()
    response = client.patch(f"/api/v1/invoices/{invoice}", headers=headers, json={"total": value})
    assert response.status_code == 422, response.text
    assert client.get(f"/api/v1/invoices/{invoice}", headers=headers).json() == before


def test_invoice_patch_requires_reconciled_total_and_preserves_exact_paisa(client, invoice):
    headers = login(client, "sana")
    response = client.patch(f"/api/v1/invoices/{invoice}", headers=headers,
                            json={"invoice_no": "REG-EDITED", "invoice_date": "2026-10-12", "due_date": "2026-10-16"})
    assert response.status_code == 200, response.text
    assert response.json()["invoice_no"] == "REG-EDITED" and response.json()["due_date"] == "2026-10-16"
    response = client.patch(f"/api/v1/invoices/{invoice}", headers=headers, json={"total": "106.00"})
    assert response.status_code == 422 and response.json()["code"] == "amount_mismatch"
    assert client.get(f"/api/v1/invoices/{invoice}", headers=headers).json()["total"] == 10_500
    response = client.patch(f"/api/v1/invoices/{invoice}", headers=headers,
                            json={"subtotal": "100.01", "tax": "5.02", "total": "105.03"})
    assert response.status_code == 200, response.text
    assert (response.json()["subtotal"], response.json()["tax"], response.json()["total"]) == (10_001, 502, 10_503)
    response = client.patch(f"/api/v1/invoices/{invoice}", headers=headers,
                            json={"subtotal": "1e2", "tax": "5e0", "total": "1.05e2",
                                  "lines": [{"description": "Scientific amount", "qty": 1,
                                             "unit_price": "1e2", "amount": "1e2"}]})
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 10_500 and response.json()["lines"][0]["amount"] == 10_000
    response = client.patch(f"/api/v1/invoices/{invoice}", headers=headers,
                            json={"subtotal": "0e999999", "tax": "0e-999999", "total": "0.0000"})
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 0


def test_invoice_lines_require_nonnegative_exact_money_and_subtotal(client, invoice):
    headers = login(client, "sana")
    line = {"description": "Regression item", "qty": 1, "unit_price": "100.00", "amount": "100.00"}
    for invalid in ({"qty": "Infinity"}, {"unit_price": -1}, {"amount": "100.001"}, {"amount": "90.00"}):
        response = client.patch(f"/api/v1/invoices/{invoice}", headers=headers,
                                json={"lines": [line | invalid]})
        assert response.status_code == 422, response.text
    response = client.patch(f"/api/v1/invoices/{invoice}", headers=headers, json={"lines": [line]})
    assert response.status_code == 200, response.text
    assert response.json()["lines"][0]["amount"] == 10_000


def test_unconfirmed_draft_cannot_score_or_join_a_run(client, invoice):
    with SessionLocal() as db:
        inv = db.get(Invoice, invoice)
        inv.status = "draft"
        inv.extraction_json = {"fields": {"invoice_no": inv.invoice_no, "invoice_date": None, "total": 105}}
        db.commit()
    headers = login(client, "sana")
    response = client.post(f"/api/v1/invoices/{invoice}/score", headers=headers)
    assert response.status_code == 409 and response.json()["code"] == "confirmation_required"
    response = client.post("/api/v1/payment-runs", headers=headers, json={"invoice_ids": [invoice]})
    assert response.status_code == 409 and response.json()["code"] == "invoice_not_open"
    response = client.patch(f"/api/v1/invoices/{invoice}", headers=headers, json={"confirm": True})
    assert response.status_code == 422 and response.json()["field"] == "invoice_date"
    response = client.patch(f"/api/v1/invoices/{invoice}", headers=headers,
                            json={"confirm": True, "invoice_date": "2026-10-12"})
    assert response.status_code == 200 and response.json()["status"] == "received"
    response = client.post(f"/api/v1/invoices/{invoice}/score", headers=headers)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("status", ["paid", "scheduled", "rejected"])
def test_nonopen_invoice_cannot_be_scheduled_again(client, invoice, status):
    with SessionLocal() as db:
        db.get(Invoice, invoice).status = status
        db.commit()
        before = db.scalar(select(func.count(PaymentRun.id)))
    headers = login(client, "sana")
    response = client.post("/api/v1/payment-runs", headers=headers, json={"invoice_ids": [invoice]})
    assert response.status_code == 409 and response.json()["code"] == "invoice_not_open"
    assert client.post(f"/api/v1/invoices/{invoice}/score", headers=headers).status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count(PaymentRun.id))) == before
        assert db.scalar(select(func.count(Payment.id)).where(Payment.invoice_id == invoice)) == 0


def test_duplicate_invoice_ids_rejected_before_creating_a_run(client, invoice):
    with SessionLocal() as db:
        before = db.scalar(select(func.count(PaymentRun.id)))
    response = client.post("/api/v1/payment-runs", headers=login(client, "sana"),
                           json={"invoice_ids": [invoice, invoice]})
    assert response.status_code == 422 and response.json()["code"] == "duplicate_invoice"
    with SessionLocal() as db:
        assert db.scalar(select(func.count(PaymentRun.id))) == before
        assert db.get(Invoice, invoice).status == "received"


@pytest.mark.skipif(engine.dialect.name != "sqlite", reason="Reproduces SQLite's ignored SELECT FOR UPDATE")
def test_concurrent_run_requests_claim_an_invoice_once(client, invoice, monkeypatch):
    barrier = Barrier(2)
    with SessionLocal() as db:
        owner_id = db.execute(select(User.id).where(User.email == "rashid@bismillah.pk")).scalar_one()
        value_date = db.get(Invoice, invoice).due_date

    def align_reads(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT payments.invoice_id") and " IN " in statement and invoice in parameters:
            barrier.wait(timeout=5)

    event.listen(engine, "after_cursor_execute", align_reads)
    monkeypatch.setattr(payment_runs, "score_payments", lambda *args, **kwargs: [])

    def submit(_):
        with SessionLocal() as db:
            try:
                payment_runs.create_run(db, db.get(User, owner_id), value_date, [invoice])
                return 201
            except ApiError as exc:
                assert exc.code == "invoice_not_open"
                return exc.status

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(submit, [0, 1]))
    finally:
        event.remove(engine, "after_cursor_execute", align_reads)
    assert sorted(outcomes) == [201, 409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Payment.id)).where(Payment.invoice_id == invoice)) == 1


def test_concurrent_export_only_emits_bank_instructions_once(client, invoice, monkeypatch):
    response = client.post("/api/v1/payment-runs", headers=login(client, "sana"), json={"invoice_ids": [invoice]})
    assert response.status_code == 201, response.text
    run_id, line_id = response.json()["id"], response.json()["lines"][0]["id"]
    with SessionLocal() as db:
        owner_id = db.execute(select(User.id).where(User.email == "rashid@bismillah.pk")).scalar_one()
        p = db.get(Payment, line_id)
        p.status, p.approved_by, p.approved_at = "approved", owner_id, utcnow()
        db.commit()
    # Both callers load the old open run and approved lines before either starts export.
    barrier = Barrier(2)

    def submit(_):
        with SessionLocal() as db:
            run = db.get(PaymentRun, run_id)
            assert run.status == "open" and run.payments[0].status == "approved"
            owner = db.get(User, owner_id)
            barrier.wait(timeout=5)
            try:
                csv = payment_runs.export_csv(db, run, owner)
                assert len(csv.strip().splitlines()) == 2
                return 200
            except ApiError as exc:
                assert exc.code == "run_closed"
                return exc.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(submit, [0, 1]))
    assert sorted(outcomes) == [200, 409]
    with SessionLocal() as db:
        assert db.get(PaymentRun, run_id).status == "exported"
        assert db.get(Payment, line_id).status == "exported"


def test_bank_export_does_not_claim_settlement_or_increase_forecast(client, invoice):
    headers = login(client, "sana")
    with SessionLocal() as db:
        value_date = db.get(Invoice, invoice).due_date
    response = client.post("/api/v1/payment-runs", headers=headers,
                           json={"invoice_ids": [invoice], "run_date": value_date.isoformat()})
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]
    line_id = response.json()["lines"][0]["id"]
    # Isolate the export lifecycle from model classification, covered by the scoring suite.
    with SessionLocal() as db:
        score = db.execute(select(RiskScore).where(RiskScore.payment_id == line_id).order_by(RiskScore.id.desc())).scalars().first()
        score.decision, score.score = "allow", 10
        db.get(Payment, line_id).status = "pending"
        db.commit()
    owner = login(client, "rashid")
    assert client.post(f"/api/v1/payment-runs/{run_id}/approve", headers=owner,
                       json={"payment_ids": [line_id]}).status_code == 200
    before = client.get("/api/v1/cash/projection", headers=owner).json()["projection"]
    before_selected = client.get(f"/api/v1/cash/projection?run_id={run_id}", headers=owner).json()["projection"]
    response = client.get(f"/api/v1/payment-runs/{run_id}/export", headers=owner)
    assert response.status_code == 200, response.text
    assert ",105.00," in response.text
    after = client.get("/api/v1/cash/projection", headers=owner).json()["projection"]
    after_selected = client.get(f"/api/v1/cash/projection?run_id={run_id}", headers=owner).json()["projection"]
    assert after == before
    assert after_selected == before_selected
    with SessionLocal() as db:
        assert db.get(Invoice, invoice).status == "scheduled"
        assert db.get(Payment, line_id).status == "exported"
        assert db.get(PaymentRun, run_id).status == "exported"
        ci = CashInputs(db, db.get(PaymentRun, run_id))
        for mode in ("nigraan", "all", "green_only"):
            matching = [f for f in ci.base_flows() + ci.line_flows(mode) if f.ref == f"payment:{line_id}"]
            assert len(matching) == 1 and matching[0].amount == -10_500
    assert client.post("/api/v1/payment-runs", headers=headers, json={"invoice_ids": [invoice]}).status_code == 409
    assert client.post(f"/api/v1/invoices/{invoice}/score", headers=headers).status_code == 409
    assert client.get(f"/api/v1/payment-runs/{run_id}/export", headers=owner).status_code == 409
    assert client.post(f"/api/v1/payment-runs/{run_id}/approve-green", headers=owner).status_code == 409
    assert client.post(f"/api/v1/payment-runs/{run_id}/hold", headers=owner,
                       json={"payment_ids": [line_id]}).status_code == 409


def test_future_recorded_payment_is_projected_once_until_value_date(client, invoice):
    response = client.post("/api/v1/payment-runs", headers=login(client, "sana"), json={"invoice_ids": [invoice]})
    assert response.status_code == 201, response.text
    line_id, run_id = response.json()["lines"][0]["id"], response.json()["id"]
    with SessionLocal() as db:
        c = db.execute(select(Company)).scalars().first()
        p = db.get(Payment, line_id)
        p.status, p.pay_date = "released", c.as_of_date + timedelta(days=3)
        p.invoice.status = "paid"
        db.commit()
        ci = CashInputs(db, db.get(PaymentRun, run_id))
        matching = [f for f in ci.base_flows() + ci.line_flows("nigraan") if f.ref == f"payment:{line_id}"]
        assert len(matching) == 1 and matching[0].amount == -10_500
        p.pay_date = c.as_of_date - timedelta(days=1)
        db.commit()
        ci = CashInputs(db, db.get(PaymentRun, run_id))
        assert not any(f.ref == f"payment:{line_id}" for f in ci.base_flows() + ci.line_flows("nigraan"))


def test_false_alarm_after_export_recovers_live_line_without_duplicate_instructions(client, invoice):
    with SessionLocal() as db:
        original = db.get(Invoice, invoice)
        number = f"RECOVERY-{uuid4().hex[:10]}"
        other = Invoice(vendor_id=original.vendor_id, invoice_no=number, invoice_no_norm=number,
                        invoice_date=original.invoice_date, due_date=original.due_date,
                        received_at=utcnow(), subtotal=10_000, tax=500, total=10_500,
                        status="received", source="csv", created_by=original.created_by)
        db.add(other)
        db.commit()
        other_id, value_date = other.id, other.due_date
    response = client.post("/api/v1/payment-runs", headers=login(client, "sana"),
                           json={"invoice_ids": [invoice, other_id], "run_date": value_date.isoformat()})
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]
    with SessionLocal() as db:
        lines = {p.invoice_id: p for p in db.get(PaymentRun, run_id).payments}
        green, red = lines[invoice], lines[other_id]
        green_id, red_id = green.id, red.id
        scores = {s.payment_id: s for s in db.execute(select(RiskScore).where(RiskScore.payment_id.in_([green_id, red_id]))).scalars()}
        scores[green_id].decision, scores[green_id].score, green.status = "allow", 10, "pending"
        scores[red_id].decision, scores[red_id].score, red.status = "blocked", 90, "blocked"
        case = db.execute(select(Case).where(Case.payment_id == red_id)).scalars().first()
        if case is None:
            case = Case(payment_id=red_id, risk_score_id=scores[red_id].id, status="open", source="auto",
                        opened_at=utcnow(), amount=red.amount)
            db.add(case)
        db.commit()
        case_id = case.id
    owner = login(client, "rashid")
    assert client.post(f"/api/v1/payment-runs/{run_id}/approve", headers=owner,
                       json={"payment_ids": [green_id]}).status_code == 200
    before = client.get("/api/v1/cash/projection", headers=owner).json()["projection"]
    first_export = client.get(f"/api/v1/payment-runs/{run_id}/export", headers=owner)
    assert first_export.status_code == 200, first_export.text
    assert len(first_export.text.strip().splitlines()) == 2
    assert client.get("/api/v1/cash/projection", headers=owner).json()["projection"] == before
    response = client.post(f"/api/v1/cases/{case_id}/resolve", headers=owner, json=resolution_payload(client, case_id))
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        assert db.get(PaymentRun, run_id).status == "open"
        assert db.get(Payment, green_id).status == "exported"
        assert db.get(Payment, red_id).status == "pending"
        assert db.get(Payment, red_id).override_decision == "review"
    # A different approver reviews the recovered instruction; prior exports cannot be held/approved again.
    approver = login(client, "bilal")
    assert client.post(f"/api/v1/payment-runs/{run_id}/approve", headers=approver,
                       json={"payment_ids": [green_id]}).status_code == 409
    assert client.post(f"/api/v1/payment-runs/{run_id}/approve", headers=approver,
                       json={"payment_ids": [red_id]}).status_code == 200
    before_second = client.get("/api/v1/cash/projection", headers=owner).json()["projection"]
    second_export = client.get(f"/api/v1/payment-runs/{run_id}/export", headers=owner)
    assert second_export.status_code == 200, second_export.text
    rows = second_export.text.strip().splitlines()
    assert len(rows) == 2 and int(rows[1].split(",")[0]) == red_id
    assert client.get("/api/v1/cash/projection", headers=owner).json()["projection"] == before_second
    with SessionLocal() as db:
        ci = CashInputs(db, db.get(PaymentRun, run_id))
        flows = ci.base_flows() + ci.line_flows("nigraan")
        for payment_id in (green_id, red_id):
            assert sum(f.ref == f"payment:{payment_id}" for f in flows) == 1


def test_false_alarm_does_not_reopen_a_historical_run(client, invoice):
    response = client.post("/api/v1/payment-runs", headers=login(client, "sana"), json={"invoice_ids": [invoice]})
    assert response.status_code == 201, response.text
    run_id, line_id = response.json()["id"], response.json()["lines"][0]["id"]
    with SessionLocal() as db:
        run = db.get(PaymentRun, run_id)
        run.is_live, run.status = False, "exported"
        p = db.get(Payment, line_id)
        p.status, p.invoice.status = "released", "paid"
        score = db.execute(select(RiskScore).where(RiskScore.payment_id == line_id).order_by(RiskScore.id.desc())).scalars().first()
        case = db.execute(select(Case).where(Case.payment_id == line_id)).scalars().first()
        if case is None:
            case = Case(payment_id=line_id, risk_score_id=score.id, status="open", source="historical",
                        opened_at=utcnow(), amount=p.amount)
            db.add(case)
        db.commit()
        case_id = case.id
    response = client.post(f"/api/v1/cases/{case_id}/resolve", headers=login(client, "rashid"),
                           json=resolution_payload(client, case_id))
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        assert db.get(PaymentRun, run_id).status == "exported"
        assert db.get(Payment, line_id).status == "released"
        assert db.get(Invoice, invoice).status == "paid"
