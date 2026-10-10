"""Case detail and resolution. Outcomes become training labels for the next retrain."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Case, CaseEvent, Payment, RiskScore, User, Vendor
from app.money import fmt_rs
from app.schemas.requests import VerificationIn
from app.services.payment_runs import audit, utcnow
from app.services.runtime import runtime
from app.services.scoring.scorer import FRAUD_TYPES, suspected_type


def suspected_case_type(case: Case, score: RiskScore | None) -> str | None:
    # Human-confirmed historical labels remain intact. Automatic suspicion must be
    # supported by the model evidence shown in the same investigation.
    if case.source == "auto" and score is not None:
        return suspected_type(score.reasons_json or [], score.decision, (score.evidence_json or {}).get("features"))
    return case.fraud_type


def case_row(c: Case, users: dict[int, str]) -> dict:
    p = c.payment
    return {
        "id": c.id, "status": c.status, "fraud_type": c.fraud_type, "fraud_type_name": FRAUD_TYPES.get(c.fraud_type or ""),
        "source": c.source, "opened_at": c.opened_at.isoformat() + "Z",
        "resolved_at": c.resolved_at.isoformat() + "Z" if c.resolved_at else None, "resolved_by": users.get(c.resolved_by),
        "amount": int(c.amount), "amount_fmt": fmt_rs(int(c.amount)), "payment_id": p.id, "vendor": p.vendor.name,
        "vendor_id": p.vendor_id, "invoice_no": p.invoice.invoice_no, "run_id": p.run_id,
    }


def case_detail(db: Session, case: Case, user: User) -> dict:
    audit(db, user, "view_case", "case", case.id)
    db.add(CaseEvent(case_id=case.id, at=utcnow(), user_id=user.id, kind="viewed", detail_json={}))
    db.commit()
    db.refresh(case)
    users = dict(db.execute(select(User.id, User.name)).all())
    p: Payment = case.payment
    scores = db.execute(select(RiskScore).where(RiskScore.payment_id == p.id).order_by(RiskScore.id)).scalars().all()
    s = scores[-1] if scores else None
    ctx = runtime.scoring_context(db)
    graph = ctx.graph.neighbourhood(p.vendor_id, pd.Timestamp(p.created_at).value)
    inv = p.invoice
    out = case_row(case, users)
    pattern = suspected_case_type(case, s)
    out["fraud_type"], out["fraud_type_name"] = pattern, FRAUD_TYPES.get(pattern or "")
    out.update({
        "payment": {"id": p.id, "amount": int(p.amount), "status": p.status, "created_by": users.get(p.created_by),
                    "created_at": p.created_at.isoformat() + "Z", "pay_date": p.pay_date.isoformat(),
                    "bank_name": p.bank_account.bank_name, "bank_last4": p.bank_account.iban_last4,
                    "override": p.override_decision, "override_by": users.get(p.override_by),
                    "override_by_id": p.override_by, "created_by_id": p.created_by},
        "invoice": {"id": inv.id, "invoice_no": inv.invoice_no, "invoice_date": inv.invoice_date.isoformat(),
                    "due_date": inv.due_date.isoformat(), "total": int(inv.total), "tax": int(inv.tax),
                    "source": inv.source, "file_name": inv.file_name,
                    "lines": [{"description": l.description, "qty": l.qty, "unit_price": int(l.unit_price),
                               "amount": int(l.amount)} for l in inv.lines]},
        "vendor_info": _vendor_info(p.vendor),
        "score": None if s is None else {
            "score": s.score, "decision": s.decision, "reasons": s.reasons_json, "engines": s.engine_scores_json,
            "evidence": s.evidence_json, "trace": s.trace_json, "model_version": s.model_version,
            "scored_at": s.created_at.isoformat() + "Z"},
        "score_history": [{"score": x.score, "decision": x.decision, "model_version": x.model_version,
                           "at": x.created_at.isoformat() + "Z"} for x in scores],
        "graph": graph,
        "events": [{"at": e.at.isoformat() + "Z", "user": users.get(e.user_id), "kind": e.kind, "detail": e.detail_json}
                   for e in case.events],
        "verification": verification_step(case, s),
        "verification_plan": verification_plan(case, users, pattern),
        "resolution_note": case.resolution_note,
    })
    return out


def _vendor_info(v: Vendor) -> dict:
    return {"id": v.id, "name": v.name, "ntn": v.ntn, "category": v.category, "phone": v.phone, "address": v.address,
            "status": v.status, "created_at": v.created_at.isoformat() + "Z", "related_party_note": v.related_party_note}


def verification_step(case: Case, s: RiskScore | None) -> str:
    t = suspected_case_type(case, s)
    if t == "F2":
        return ("Use a vendor contact independently verified outside the bank-change request, then confirm the new "
                "account in writing. The current phone record alone does not establish the pre-change contact.")
    if t == "F1":
        return "Compare both invoices with the delivery challans; ask the vendor to confirm whether this bill was already settled."
    if t == "F3":
        return "Verify the vendor's NTN on the FBR portal, visit the registered address, and ask the linked employee to declare the relationship."
    if t == "F4":
        return "Check the unit price against the purchase order and the vendor's last quotation before paying."
    if t == "F5":
        return "Ask the requester why one purchase was split; route the combined amount through owner approval."
    if t == "F7":
        return "Have a second approver review the supporting documents; confirm the goods/services were received."
    return "Review the supporting documents with a second person before releasing."


CHECKLISTS = {
    "F1": [("invoice_history", "Compare the invoice with prior payments and invoice records"),
           ("delivery_documents", "Check delivery challans or evidence of goods/services received")],
    "F2": [("registered_phone", "Independently verify the vendor contact and confirm the bank request"),
           ("bank_details", "Compare previous and proposed bank details with the signed request"),
           ("supporting_documents", "Review the supporting invoice and bank-change documents")],
    "F3": [("vendor_register", "Verify NTN, registered address and vendor identity"),
           ("relationship_check", "Check employee/vendor links and any related-party declaration")],
    "F4": [("purchase_order", "Match goods or services to the purchase order"),
           ("price_check", "Compare prices with the approved quotation or prior purchases")],
    "F5": [("requester_review", "Review the purchase explanation and records with the requester"),
           ("combined_amount", "Check the combined vendor amount and owner-approval requirement")],
}
DEFAULT_CHECKLIST = [("supporting_documents", "Check the invoice and evidence of goods/services received"),
                     ("independent_review", "Review the unusual activity with an independent person")]


def verification_plan(case: Case, users: dict[int, str], pattern: str | None = None) -> dict:
    """A guide and recorded human result, distinct from model evidence or an AI summary."""
    p = case.payment
    bank = p.bank_account
    records = []
    for account in p.vendor.bank_accounts:
        records.append({"id": account.id, "bank_name": account.bank_name, "last4": account.iban_last4,
                        "status": account.status, "valid_from": account.valid_from.isoformat() + "Z",
                        "valid_to": account.valid_to.isoformat() + "Z" if account.valid_to else None,
                        "change_source": account.change_source, "requested_by": users.get(account.changed_by),
                        "approved_by": users.get(account.approved_by)})
    recorded = next((event for event in reversed(case.events)
                     if (event.detail_json or {}).get("verification")), None)
    result = None if recorded is None else {**recorded.detail_json["verification"],
                                           "by": users.get(recorded.user_id),
                                           "at": recorded.at.isoformat() + "Z"}
    return {
        "checklist": [{"id": key, "label": label} for key, label in CHECKLISTS.get(pattern, DEFAULT_CHECKLIST)],
        "registered_phone": p.vendor.phone,
        "phone_history_available": False,
        "contact_note": "Current phone on the vendor record. Nigraan has no historical phone record; independently verify this contact before relying on it.",
        "bank_accounts": records,
        "requester": users.get(p.created_by),
        "call_script": {
            "en": f"I am verifying invoice {p.invoice.invoice_no} for {p.vendor.name}. Please confirm that the goods or services were received, the amount is correct, and {bank.bank_name} account ending {bank.iban_last4} is authorised. What document can independently confirm this?",
            "ur": f"Main {p.vendor.name} ki invoice {p.invoice.invoice_no} verify kar raha/rahi hoon. Kya maal ya service mili, raqam durust hai, aur {bank.bank_name} ka account jis ke aakhri digits {bank.iban_last4} hain manzoor shuda hai? Is ki tasdeeq kis dastavez se ho sakti hai?",
        },
        "recorded_result": result,
    }


def resolve(db: Session, case: Case, user: User, outcome: str, note: str | None, block_vendor: bool,
            verification: VerificationIn | None = None) -> dict:
    if case.status != "open":
        raise ApiError(409, "already_resolved", "This case is already resolved")
    if outcome not in ("confirmed_fraud", "false_alarm"):
        raise ApiError(422, "validation_error", "outcome must be confirmed_fraud or false_alarm", "outcome")
    if user.role not in ("approver", "owner"):
        raise ApiError(403, "forbidden", "Only an approver or the owner can resolve cases")
    note = (note or "").strip()
    if len(" ".join(note.split())) < 10:
        raise ApiError(422, "verification_required", "Record what you verified in a resolution note (at least 10 characters)", "note")
    if verification is None:
        raise ApiError(422, "verification_required", "Record the verification method, result and evidence before resolving this case", "verification")
    if verification.method == "registered_phone" and not (case.payment.vendor.phone or "").strip():
        raise ApiError(422, "verification_required", "There is no registered phone on this vendor record; choose another verification method", "verification.method")
    score = db.execute(select(RiskScore).where(RiskScore.payment_id == case.payment_id)
                       .order_by(RiskScore.id.desc())).scalars().first()
    pattern = suspected_case_type(case, score)
    required = {key for key, _ in CHECKLISTS.get(pattern, DEFAULT_CHECKLIST)}
    if set(verification.checks) != required:
        raise ApiError(422, "verification_required", "Complete every verification check for this case", "verification.checks")
    reference = " ".join(verification.reference.split())
    if len(reference) < 10:
        raise ApiError(422, "verification_required", "Record the contact, document or record used to verify the case (at least 10 characters)", "verification.reference")
    expected = "verified_legitimate" if outcome == "false_alarm" else "confirmed_issue"
    if verification.result != expected:
        raise ApiError(422, "verification_mismatch", "The recorded verification result does not support this case outcome", "verification.result")
    recorded = verification.model_dump()
    recorded["reference"] = reference
    recorded["checks"] = sorted(required)
    now = utcnow()
    case.status, case.resolved_at, case.resolved_by, case.resolution_note = outcome, now, user.id, note
    p = case.payment
    if outcome == "confirmed_fraud":
        p.status = "rejected"
        p.invoice.status = "rejected"
        if block_vendor:
            v = p.vendor
            v.status, v.blocked_at = "blocked", now
            audit(db, user, "block_vendor", "vendor", v.id, case_id=case.id)
    else:
        # The model's red decision stays on record. Only unsettled, live instructions can
        # return to approval; resolving a historical case must not rewrite a settled ledger.
        if p.status not in ("released", "exported") and p.run is not None and p.run.is_live:
            p.status = "pending"
            p.override_decision = "review"
            p.override_by = user.id
            if p.run.status == "exported":
                # Existing exported lines remain immutable. A subsequent file contains only
                # the newly approved recovery, so the earlier instructions are never duplicated.
                p.run.status = "open"
                audit(db, user, "reopen_run", "payment_run", p.run.id, case_id=case.id,
                      reason="false_alarm_recovered")
            audit(db, user, "override_decision", "payment", p.id, from_decision="blocked", to_decision="review", note=note)
    db.add(CaseEvent(case_id=case.id, at=now, user_id=user.id, kind=outcome,
                     detail_json={"note": note, "block_vendor": block_vendor, "verification": recorded}))
    audit(db, user, "resolve_case", "case", case.id, outcome=outcome, note=note, verification=recorded)
    db.commit()
    runtime.bump()
    return {"id": case.id, "status": case.status}
