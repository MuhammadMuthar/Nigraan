"""Recorded investigations and combined-vendor approval controls through the API."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.models import Case, CaseEvent, Company, Invoice, Payment, PaymentRun, RiskScore, User, Vendor
from app.services.payment_runs import utcnow
from app.services.runtime import runtime
from tests.conftest import login, resolution_payload


@pytest.fixture
def controlled_run(client):
    created = []

    def make(amounts=(10_000,), decisions=("blocked",)):
        with SessionLocal() as db:
            company = db.execute(select(Company)).scalars().first()
            vendor = db.execute(select(Vendor).where(Vendor.status == "active")).scalars().first()
            user = db.execute(select(User).where(User.email == "sana@bismillah.pk")).scalars().one()
            run = PaymentRun(company_id=company.id, name="Review control regression", run_date=company.as_of_date,
                             status="open", created_by=user.id, created_at=utcnow(), is_live=True)
            db.add(run)
            db.flush()
            payment_ids, case_ids = [], []
            for amount, decision in zip(amounts, decisions):
                number = f"REVIEW-{uuid4().hex[:12]}"
                inv = Invoice(vendor_id=vendor.id, invoice_no=number, invoice_no_norm=number,
                              invoice_date=company.as_of_date, due_date=company.as_of_date + timedelta(days=4),
                              received_at=utcnow(), subtotal=amount, tax=0, total=amount,
                              status="scheduled", source="csv", created_by=user.id)
                db.add(inv)
                db.flush()
                payment = Payment(run_id=run.id, invoice_id=inv.id, vendor_id=vendor.id,
                                  bank_account_id=vendor.bank_accounts[0].id, amount=amount, created_by=user.id,
                                  created_at=utcnow(), pay_date=company.as_of_date,
                                  status="blocked" if decision == "blocked" else "pending")
                db.add(payment)
                db.flush()
                score = RiskScore(payment_id=payment.id, score=90 if decision == "blocked" else 45,
                                  decision=decision, reasons_json=[], engine_scores_json={},
                                  evidence_json={}, trace_json=[], model_version="regression", created_at=utcnow())
                db.add(score)
                db.flush()
                if decision == "blocked":
                    case = Case(payment_id=payment.id, risk_score_id=score.id, status="open", source="auto",
                                opened_at=utcnow(), amount=amount, fraud_type="ANOMALY")
                    db.add(case)
                    db.flush()
                    case_ids.append(case.id)
                payment_ids.append(payment.id)
            db.commit()
            created.append(run.id)
            runtime.bump()
            return {"run": run.id, "payments": payment_ids, "cases": case_ids}

    yield make
    with SessionLocal() as db:
        for run_id in created:
            payments = list(db.execute(select(Payment).where(Payment.run_id == run_id)).scalars())
            ids = [payment.id for payment in payments]
            invoice_ids = [payment.invoice_id for payment in payments]
            case_ids = list(db.execute(select(Case.id).where(Case.payment_id.in_(ids))).scalars())
            db.execute(delete(CaseEvent).where(CaseEvent.case_id.in_(case_ids)))
            db.execute(delete(Case).where(Case.id.in_(case_ids)))
            db.execute(delete(RiskScore).where(RiskScore.payment_id.in_(ids)))
            db.execute(delete(Payment).where(Payment.id.in_(ids)))
            db.execute(delete(Invoice).where(Invoice.id.in_(invoice_ids)))
            db.execute(delete(PaymentRun).where(PaymentRun.id == run_id))
        db.commit()
        runtime.bump()


@pytest.mark.parametrize("change", [
    {"note": None}, {"note": "   \n  "}, {"note": "checked"}, {"verification": None},
    {"verification.checks": []}, {"verification.reference": " "},
    {"verification.result": "confirmed_issue"},
])
def test_resolution_requires_complete_supported_verification(client, controlled_run, change):
    data = controlled_run()
    case_id = data["cases"][0]
    body = resolution_payload(client, case_id)
    for key, value in change.items():
        if key.startswith("verification."):
            body["verification"][key.split(".")[1]] = value
        else:
            body[key] = value
    response = client.post(f"/api/v1/cases/{case_id}/resolve", headers=login(client, "rashid"), json=body)
    assert response.status_code == 422, response.text
    with SessionLocal() as db:
        assert db.get(Case, case_id).status == "open"
        assert db.get(Payment, data["payments"][0]).status == "blocked"
        assert db.get(Payment, data["payments"][0]).override_by is None


@pytest.mark.parametrize("clearer,other", [("bilal", "rashid"), ("rashid", "bilal")])
def test_case_clearer_cannot_approve_the_recovered_payment(client, controlled_run, clearer, other):
    data = controlled_run()
    case_id, payment_id = data["cases"][0], data["payments"][0]
    response = client.post(f"/api/v1/cases/{case_id}/resolve", headers=login(client, clearer),
                           json=resolution_payload(client, case_id))
    assert response.status_code == 200, response.text
    response = client.post(f"/api/v1/payment-runs/{data['run']}/approve", headers=login(client, clearer),
                           json={"payment_ids": [payment_id]})
    assert response.status_code == 403 and response.json()["code"] == "same_clearer", response.text
    detail = client.get(f"/api/v1/cases/{case_id}", headers=login(client, other)).json()
    recorded = detail["verification_plan"]["recorded_result"]
    assert recorded["result"] == "verified_legitimate"
    assert recorded["by"] and recorded["at"]
    assert recorded["reference"].startswith("Signed delivery")
    assert any(event["detail"].get("verification") for event in detail["events"])
    response = client.post(f"/api/v1/payment-runs/{data['run']}/approve", headers=login(client, other),
                           json={"payment_ids": [payment_id]})
    assert response.status_code == 200, response.text


def test_confirmed_fraud_retains_rejection_and_recorded_verification(client, controlled_run):
    data = controlled_run()
    case_id = data["cases"][0]
    body = resolution_payload(client, case_id, "confirmed_fraud")
    response = client.post(f"/api/v1/cases/{case_id}/resolve", headers=login(client, "bilal"), json=body)
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        payment = db.get(Payment, data["payments"][0])
        assert payment.status == "rejected" and payment.invoice.status == "rejected"
        assert payment.override_by is None


def test_split_vendor_commitment_requires_owner_before_either_line_is_approved(client, controlled_run):
    data = controlled_run((46_000_000, 46_000_000), ("review", "review"))
    approver, owner = login(client, "bilal"), login(client, "rashid")
    detail = client.get(f"/api/v1/payment-runs/{data['run']}", headers=approver).json()
    assert all(line["vendor_commitment_amount"] == 92_000_000 and line["requires_owner_approval"]
               for line in detail["lines"])
    for payment_id in data["payments"]:
        response = client.post(f"/api/v1/payment-runs/{data['run']}/approve", headers=approver,
                               json={"payment_ids": [payment_id]})
        assert response.status_code == 403 and response.json()["code"] == "over_limit", response.text
    response = client.post(f"/api/v1/payment-runs/{data['run']}/approve", headers=owner,
                           json={"payment_ids": data["payments"]})
    assert response.status_code == 200, response.text


def test_approve_green_skips_combined_over_limit_vendor_and_preserves_atomic_approval(client, controlled_run):
    data = controlled_run((46_000_000, 46_000_000), ("allow", "allow"))
    response = client.post(f"/api/v1/payment-runs/{data['run']}/approve-green", headers=login(client, "bilal"))
    assert response.status_code == 200, response.text
    assert response.json()["approved"] == []
    assert {item["id"] for item in response.json()["skipped"]} == set(data["payments"])
    assert all("combined vendor" in item["reason"] for item in response.json()["skipped"])
    with SessionLocal() as db:
        assert all(db.get(Payment, pid).status == "pending" for pid in data["payments"])


def test_exported_commitment_counts_but_held_rejected_and_settled_do_not(client, controlled_run):
    data = controlled_run((30_000_000, 30_000_000, 46_000_000, 46_000_000, 46_000_000), ("allow",) * 5)
    with SessionLocal() as db:
        for payment_id, status in zip(data["payments"][1:], ("exported", "held", "rejected", "released")):
            db.get(Payment, payment_id).status = status
        db.commit()
    approver = login(client, "bilal")
    response = client.post(f"/api/v1/payment-runs/{data['run']}/approve", headers=approver,
                           json={"payment_ids": [data["payments"][0]]})
    assert response.status_code == 403 and response.json()["code"] == "over_limit", response.text
    with SessionLocal() as db:
        db.get(Payment, data["payments"][1]).status = "released"
        db.commit()
    response = client.post(f"/api/v1/payment-runs/{data['run']}/approve", headers=approver,
                           json={"payment_ids": [data["payments"][0]]})
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("source,status,expected_pattern,expected_name", [
    ("auto", "open", "ANOMALY", "Unusual payment"),
    ("historical", "confirmed_fraud", "F7", "Out-of-hours payment"),
])
def test_case_and_summary_repair_stale_auto_pattern_without_rewriting_historical_label(
        client, controlled_run, source, status, expected_pattern, expected_name):
    from app.services.summary import _evidence

    data = controlled_run()
    case_id, payment_id = data["cases"][0], data["payments"][0]
    with SessionLocal() as db:
        case = db.get(Case, case_id)
        case.fraud_type, case.source, case.status = "F7", source, status
        score = db.execute(select(RiskScore).where(RiskScore.payment_id == payment_id)).scalars().one()
        score.reasons_json = [{"text": "Paid 1 day after the invoice", "engine": "risk_model",
                               "feature": "days_since_invoice_date"}]
        score.engine_scores_json = {"fraud_type": "F7"}
        score.evidence_json = {"features": {"days_since_invoice_date": 1, "is_night": 0}}
        db.commit()
        evidence = _evidence(case, score)
        assert evidence["suspected_pattern"] == expected_name
        assert evidence["reasons"] == ["Paid 1 day after the invoice"]
        assert case.fraud_type == "F7"  # Read-time correction preserves the stored audit record.
    headers = login(client, "rashid")
    detail = client.get(f"/api/v1/cases/{case_id}", headers=headers).json()
    assert detail["fraud_type"] == expected_pattern
    assert detail["fraud_type_name"] == expected_name
    for lang in ("en", "ur"):
        response = client.get(f"/api/v1/cases/{case_id}/summary?lang={lang}", headers=headers)
        assert response.status_code == 200, response.text
        summary = response.json()
        assert summary["mode"] == "template"
        assert summary["evidence"]["suspected_pattern"] == expected_name
        assert expected_name.lower() in summary["text"]
        if source == "auto":
            assert "out-of-hours" not in summary["text"]
