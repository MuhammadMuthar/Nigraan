"""Case detail and resolution. Outcomes become training labels for the next retrain."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Case, CaseEvent, Payment, RiskScore, User, Vendor
from app.money import fmt_rs
from app.services.payment_runs import audit, utcnow
from app.services.runtime import runtime
from app.services.scoring.scorer import FRAUD_TYPES


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
    out.update({
        "payment": {"id": p.id, "amount": int(p.amount), "status": p.status, "created_by": users.get(p.created_by),
                    "created_at": p.created_at.isoformat() + "Z", "pay_date": p.pay_date.isoformat(),
                    "bank_name": p.bank_account.bank_name, "bank_last4": p.bank_account.iban_last4,
                    "override": p.override_decision},
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
    })
    return out


def _vendor_info(v: Vendor) -> dict:
    return {"id": v.id, "name": v.name, "ntn": v.ntn, "category": v.category, "phone": v.phone, "address": v.address,
            "status": v.status, "created_at": v.created_at.isoformat() + "Z", "related_party_note": v.related_party_note}


def verification_step(case: Case, s: RiskScore | None) -> str:
    t = case.fraud_type
    if t == "F2":
        return ("Call the vendor on the phone number registered before the bank change (not the one in the email) "
                "and confirm the new account in writing before releasing.")
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


def resolve(db: Session, case: Case, user: User, outcome: str, note: str | None, block_vendor: bool) -> dict:
    if case.status != "open":
        raise ApiError(409, "already_resolved", "This case is already resolved")
    if outcome not in ("confirmed_fraud", "false_alarm"):
        raise ApiError(422, "validation_error", "outcome must be confirmed_fraud or false_alarm", "outcome")
    if user.role not in ("approver", "owner"):
        raise ApiError(403, "forbidden", "Only an approver or the owner can resolve cases")
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
        # The model's red decision is kept on record; an explicit override lets a second approver release it.
        p.status = "pending"
        p.override_decision = "review"
        p.override_by = user.id
        audit(db, user, "override_decision", "payment", p.id, from_decision="blocked", to_decision="review", note=note)
    db.add(CaseEvent(case_id=case.id, at=now, user_id=user.id, kind=outcome,
                     detail_json={"note": note, "block_vendor": block_vendor}))
    audit(db, user, "resolve_case", "case", case.id, outcome=outcome, note=note)
    db.commit()
    runtime.bump()
    return {"id": case.id, "status": case.status}
