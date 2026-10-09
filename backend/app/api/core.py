"""Auth, vendors, payment runs, cases."""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import create_token, current_user, require_roles, verify_password
from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import Case, Company, Invoice, Payment, PaymentRun, RiskScore, User, Vendor, VendorBankAccount
from app.money import fmt_rs
from app.schemas.requests import LinesIn, LoginIn, ResolveIn, RunIn, VendorIn, VendorPatch
from app.services import cases as case_svc
from app.services import payment_runs as runs
from app.services.identity import hash_id, is_valid_pk_iban, last4, norm_address
from app.services.payment_runs import audit, utcnow
from app.services.runtime import runtime

router = APIRouter()


# ----------------------------------------------------------------------------- auth
@router.post("/auth/login", tags=["auth"])
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(func.lower(User.email) == body.email.strip().lower())).scalars().first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise ApiError(401, "bad_credentials", "Email or password is incorrect")
    audit(db, user, "login", "user", user.id)
    db.commit()
    return {"access_token": create_token(user), "token_type": "bearer", "user": _user(user)}


@router.get("/auth/me", tags=["auth"])
def me(user: User = Depends(current_user)):
    return _user(user)


@router.get("/auth/demo-users", tags=["auth"])
def demo_users(db: Session = Depends(get_db)):
    if not get_settings().demo_mode:
        return []
    users = db.execute(select(User).order_by(User.id)).scalars().all()
    return [_user(u) for u in users if u.email.split("@")[0] in ("sana", "bilal", "rashid")]


def _user(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role}


# ----------------------------------------------------------------------------- vendors
@router.get("/vendors", tags=["vendors"])
def list_vendors(q: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(Vendor).order_by(Vendor.name)
    if q:
        stmt = stmt.where(Vendor.name.ilike(f"%{q}%"))
    vendors = db.execute(stmt).scalars().all()
    paid = dict(db.execute(select(Payment.vendor_id, func.sum(Payment.amount)).where(Payment.status == "released")
                           .group_by(Payment.vendor_id)).all())
    open_cases = dict(db.execute(select(Payment.vendor_id, func.count(Case.id)).join(Case, Case.payment_id == Payment.id)
                                 .where(Case.status == "open").group_by(Payment.vendor_id)).all())
    out = []
    for v in vendors:
        acc = [a for a in v.bank_accounts if a.status == "active"]
        cur = acc[-1] if acc else None
        out.append({"id": v.id, "name": v.name, "category": v.category, "ntn": v.ntn, "status": v.status,
                    "bank": f"{cur.bank_name} ••{cur.iban_last4}" if cur else None,
                    "last_bank_change": cur.valid_from.isoformat() + "Z" if cur and cur.change_source != "onboarding" else None,
                    "paid_total": int(paid.get(v.id, 0)), "paid_total_fmt": fmt_rs(int(paid.get(v.id, 0))),
                    "open_cases": int(open_cases.get(v.id, 0)), "related_party_note": v.related_party_note,
                    "pending_bank_change": any(a.status == "pending" for a in v.bank_accounts)})
    return out


@router.post("/vendors", tags=["vendors"], status_code=201)
def create_vendor(body: VendorIn, db: Session = Depends(get_db),
                  user: User = Depends(require_roles("accountant", "owner"))):
    iban = body.iban.replace(" ", "").upper()
    if not is_valid_pk_iban(iban):
        raise ApiError(422, "invalid_iban", "IBAN must be PK + 22 characters with a valid check digit", "iban")
    now = utcnow()
    v = Vendor(name=body.name, ntn=body.ntn, strn=body.strn, category=body.category, phone=body.phone,
               address=body.address, address_norm=norm_address(body.address), home_bank=body.bank_name,
               payment_terms_days=body.payment_terms_days, status="active", created_at=now, created_by=user.id)
    db.add(v)
    db.flush()
    db.add(VendorBankAccount(vendor_id=v.id, bank_name=body.bank_name, iban_hash=hash_id(iban), iban_last4=last4(iban),
                             valid_from=now, changed_by=user.id, change_source="onboarding", status="active"))
    audit(db, user, "create_vendor", "vendor", v.id, name=v.name)
    db.commit()
    runtime.bump()
    return {"id": v.id}


@router.patch("/vendors/{vendor_id}", tags=["vendors"])
def patch_vendor(vendor_id: int, body: VendorPatch, db: Session = Depends(get_db), user: User = Depends(current_user)):
    v = db.get(Vendor, vendor_id) or _404("vendor")
    if body.phone is not None:
        v.phone = body.phone
    if body.address is not None:
        v.address, v.address_norm = body.address, norm_address(body.address)
    if body.payment_terms_days is not None:
        v.payment_terms_days = body.payment_terms_days
    pending = None
    if body.iban:
        iban = body.iban.replace(" ", "").upper()
        if not is_valid_pk_iban(iban):
            raise ApiError(422, "invalid_iban", "IBAN must be PK + 22 characters with a valid check digit", "iban")
        pending = VendorBankAccount(vendor_id=v.id, bank_name=body.bank_name or v.home_bank, iban_hash=hash_id(iban),
                                    iban_last4=last4(iban), valid_from=utcnow(), changed_by=user.id,
                                    change_source=body.change_source, status="pending", requested_at=utcnow())
        db.add(pending)
        db.flush()
        audit(db, user, "request_bank_change", "vendor", v.id, account_id=pending.id, source=body.change_source,
              last4=pending.iban_last4)
    audit(db, user, "update_vendor", "vendor", v.id)
    db.commit()
    runtime.bump()
    return {"id": v.id, "pending_bank_change_id": pending.id if pending else None,
            "message": "Bank change recorded; a second user must approve it before it is used" if pending else "Saved"}


@router.post("/vendors/{vendor_id}/bank-changes/{account_id}/approve", tags=["vendors"])
def approve_bank_change(vendor_id: int, account_id: int, db: Session = Depends(get_db),
                        user: User = Depends(require_roles("approver", "owner"))):
    acc = db.get(VendorBankAccount, account_id)
    if acc is None or acc.vendor_id != vendor_id or acc.status != "pending":
        _404("pending bank change")
    if acc.changed_by == user.id:
        raise ApiError(403, "same_user", "A bank change must be approved by a different user")
    now = utcnow()
    for a in db.execute(select(VendorBankAccount).where(VendorBankAccount.vendor_id == vendor_id,
                                                        VendorBankAccount.status == "active",
                                                        VendorBankAccount.valid_to.is_(None))).scalars():
        a.valid_to = now
    acc.status, acc.valid_from, acc.approved_by = "active", now, user.id
    audit(db, user, "approve_bank_change", "vendor", vendor_id, account_id=account_id)
    db.commit()
    runtime.bump()
    return {"id": acc.id, "status": acc.status}


@router.get("/vendors/{vendor_id}/risk", tags=["vendors"])
def vendor_risk(vendor_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    v = db.get(Vendor, vendor_id) or _404("vendor")
    users = dict(db.execute(select(User.id, User.name)).all())
    ctx = runtime.scoring_context(db)
    now = pd.Timestamp(utcnow()).value
    links = ctx.graph.links_for(v.id, now)
    pays = db.execute(select(Payment).where(Payment.vendor_id == v.id).order_by(Payment.created_at.desc()).limit(25)).scalars().all()
    scores = {s.payment_id: s for s in db.execute(select(RiskScore).where(RiskScore.payment_id.in_([p.id for p in pays]))
                                                    .order_by(RiskScore.id)).scalars()}
    amounts = [p.amount for p in db.execute(select(Payment).where(Payment.vendor_id == v.id,
                                                                  Payment.status == "released")).scalars()]
    return {
        "vendor": case_svc._vendor_info(v),
        "graph": {"signal": links.signal, "links": links.links, "neighbourhood": ctx.graph.neighbourhood(v.id, now)},
        "bank_history": [{"id": a.id, "bank": a.bank_name, "last4": a.iban_last4, "status": a.status,
                          "valid_from": a.valid_from.isoformat() + "Z",
                          "valid_to": a.valid_to.isoformat() + "Z" if a.valid_to else None,
                          "changed_by": users.get(a.changed_by), "approved_by": users.get(a.approved_by),
                          "source": a.change_source, "blocked": a.is_blocked} for a in v.bank_accounts],
        "stats": {"payments": len(amounts), "median": int(pd.Series(amounts).median()) if amounts else None,
                  "total": int(sum(amounts))},
        "recent_payments": [{"id": p.id, "amount": int(p.amount), "status": p.status,
                             "created_at": p.created_at.isoformat() + "Z", "invoice_no": p.invoice.invoice_no,
                             "score": scores[p.id].score if p.id in scores else None,
                             "decision": scores[p.id].decision if p.id in scores else None} for p in pays],
    }


# ----------------------------------------------------------------------------- payment runs
@router.get("/payment-runs", tags=["payment runs"])
def list_runs(db: Session = Depends(get_db), user: User = Depends(current_user), limit: int = 20):
    rows = db.execute(select(PaymentRun).order_by(PaymentRun.run_date.desc(), PaymentRun.id.desc()).limit(limit)).scalars().all()
    totals = dict(db.execute(select(Payment.run_id, func.sum(Payment.amount)).group_by(Payment.run_id)).all())
    counts = dict(db.execute(select(Payment.run_id, func.count(Payment.id)).group_by(Payment.run_id)).all())
    return [{"id": r.id, "name": r.name, "run_date": r.run_date.isoformat(), "status": r.status, "is_live": r.is_live,
             "total": int(totals.get(r.id, 0)), "lines": int(counts.get(r.id, 0))} for r in rows]


@router.post("/payment-runs", tags=["payment runs"], status_code=201)
def create_payment_run(body: RunIn, db: Session = Depends(get_db),
                       user: User = Depends(require_roles("accountant", "owner"))):
    company = db.execute(select(Company)).scalars().first()
    run_date = body.run_date or company.as_of_date
    ids = body.invoice_ids
    if not ids:
        in_runs = {i for (i,) in db.execute(select(Payment.invoice_id)).all()}
        ids = [i for (i,) in db.execute(select(Invoice.id).where(Invoice.status == "received",
                                                                 Invoice.due_date <= run_date + timedelta(days=6))).all()
               if i not in in_runs]
    if not ids:
        raise ApiError(422, "nothing_due", "No open invoices are due in this run's week")
    run = runs.create_run(db, user, run_date, ids, body.name)
    return runs.run_detail(db, run)


@router.get("/payment-runs/current", tags=["payment runs"])
def current_run(db: Session = Depends(get_db), user: User = Depends(current_user)):
    run = db.execute(select(PaymentRun).where(PaymentRun.is_live.is_(True)).order_by(PaymentRun.id.desc())).scalars().first()
    if run is None:
        return {"run": None}
    return {"run": runs.run_detail(db, run)}


@router.get("/payment-runs/{run_id}", tags=["payment runs"])
def get_run(run_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    run = db.get(PaymentRun, run_id) or _404("payment run")
    return runs.run_detail(db, run)


@router.post("/payment-runs/{run_id}/approve", tags=["payment runs"])
def approve(run_id: int, body: LinesIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    run = db.get(PaymentRun, run_id) or _404("payment run")
    return runs.approve_lines(db, run, user, body.payment_ids, body.note)


@router.post("/payment-runs/{run_id}/approve-green", tags=["payment runs"])
def approve_green(run_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    run = db.get(PaymentRun, run_id) or _404("payment run")
    return runs.approve_all_green(db, run, user)


@router.post("/payment-runs/{run_id}/hold", tags=["payment runs"])
def hold(run_id: int, body: LinesIn, db: Session = Depends(get_db),
         user: User = Depends(require_roles("approver", "owner"))):
    run = db.get(PaymentRun, run_id) or _404("payment run")
    return runs.hold_lines(db, run, user, body.payment_ids, body.note)


@router.get("/payment-runs/{run_id}/export", tags=["payment runs"], response_class=PlainTextResponse)
def export(run_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("approver", "owner"))):
    run = db.get(PaymentRun, run_id) or _404("payment run")
    text = runs.export_csv(db, run, user)
    return PlainTextResponse(text, media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="nigraan_run_{run_id}.csv"'})


@router.get("/payments/{payment_id}/score", tags=["payment runs"])
def payment_score(payment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = db.get(Payment, payment_id) or _404("payment")
    s = db.execute(select(RiskScore).where(RiskScore.payment_id == p.id).order_by(RiskScore.id.desc())).scalars().first()
    if s is None:
        _404("score")
    case = db.execute(select(Case).where(Case.payment_id == p.id).order_by(Case.id.desc())).scalars().first()
    return {"payment_id": p.id, "vendor": p.vendor.name, "invoice_no": p.invoice.invoice_no, "amount": int(p.amount),
            "score": s.score, "decision": s.decision, "reasons": s.reasons_json, "engines": s.engine_scores_json,
            "evidence": s.evidence_json, "trace": s.trace_json, "model_version": s.model_version,
            "scored_at": s.created_at.isoformat() + "Z", "case_id": case.id if case else None,
            "invoice_source": p.invoice.source, "extraction": p.invoice.extraction_json}


# ----------------------------------------------------------------------------- cases
@router.get("/cases", tags=["cases"])
def list_cases(status: str | None = Query(default=None, description="open | confirmed_fraud | false_alarm"),
               source: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(Case).order_by(Case.opened_at.desc())
    if status:
        stmt = stmt.where(Case.status == status)
    if source:
        stmt = stmt.where(Case.source == source)
    users = dict(db.execute(select(User.id, User.name)).all())
    rows = db.execute(stmt.limit(200)).scalars().all()
    scores = {}
    if rows:
        for s in db.execute(select(RiskScore).where(RiskScore.payment_id.in_([c.payment_id for c in rows]))
                            .order_by(RiskScore.id)).scalars():
            scores[s.payment_id] = s
    out = []
    for c in rows:
        r = case_svc.case_row(c, users)
        s = scores.get(c.payment_id)
        r["score"] = s.score if s else None
        r["top_reason"] = next((x["text"] for x in (s.reasons_json if s else []) if x.get("engine") != "info"), None)
        out.append(r)
    return out


@router.get("/cases/{case_id}", tags=["cases"])
def get_case(case_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = db.get(Case, case_id) or _404("case")
    return case_svc.case_detail(db, c, user)


@router.post("/cases/{case_id}/resolve", tags=["cases"])
def resolve_case(case_id: int, body: ResolveIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = db.get(Case, case_id) or _404("case")
    return case_svc.resolve(db, c, user, body.outcome, body.note, body.block_vendor)


@router.get("/cases/{case_id}/summary", tags=["cases"])
def case_summary(case_id: int, lang: str = "en", db: Session = Depends(get_db), user: User = Depends(current_user)):
    from app.services.summary import case_summary as summarise

    c = db.get(Case, case_id) or _404("case")
    return summarise(db, c, lang)


def _404(what: str):
    raise ApiError(404, "not_found", f"{what.capitalize()} not found")
