"""Money, invoice lifecycle and export/forecast guarantees through the real API."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Company, Invoice, Payment, PaymentRun, RiskScore, User, Vendor
from app.services.cash.service import CashInputs
from app.services.payment_runs import utcnow
from tests.conftest import login


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


@pytest.mark.parametrize("value", [-1, "NaN", "Infinity", "-Infinity", "0.001", "92233720368547759"])
def test_invoice_money_rejects_invalid_values_without_writing(client, invoice, value):
    headers = login(client, "sana")
    before = client.get(f"/api/v1/invoices/{invoice}", headers=headers).json()
    response = client.patch(f"/api/v1/invoices/{invoice}", headers=headers, json={"total": value})
    assert response.status_code == 422, response.text
    assert client.get(f"/api/v1/invoices/{invoice}", headers=headers).json() == before


def test_invoice_patch_requires_reconciled_total_and_preserves_exact_paisa(client, invoice):
    headers = login(client, "sana")
    response = client.patch(f"/api/v1/invoices/{invoice}", headers=headers, json={"total": "106.00"})
    assert response.status_code == 422 and response.json()["code"] == "amount_mismatch"
    assert client.get(f"/api/v1/invoices/{invoice}", headers=headers).json()["total"] == 10_500
    response = client.patch(f"/api/v1/invoices/{invoice}", headers=headers,
                            json={"subtotal": "100.01", "tax": "5.02", "total": "105.03"})
    assert response.status_code == 200, response.text
    assert (response.json()["subtotal"], response.json()["tax"], response.json()["total"]) == (10_001, 502, 10_503)


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
