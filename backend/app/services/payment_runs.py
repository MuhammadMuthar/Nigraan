"""Payment runs: create, score, approve (with segregation of duties), hold, export."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone

from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import AuditLog, Case, CaseEvent, Company, Invoice, Payment, PaymentRun, RiskScore, User, Vendor
from app.money import fmt_rs
from app.services.cash.service import effective_decision, latest_decisions
from app.services.runtime import runtime
from app.services.scoring.rules import comparison_for, comparison_summary
from app.services.scoring.scorer import FRAUD_TYPES, ScoreResult, suspected_type

OPEN_STATUSES = ("pending",)  # a line still waiting for a decision


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def audit(db: Session, user: User | None, action: str, entity: str, entity_id: int | None, **detail) -> None:
    db.add(AuditLog(at=utcnow(), user_id=user.id if user else None, action=action, entity=entity, entity_id=entity_id,
                    detail_json=detail))


def store_scores(db: Session, results: list[ScoreResult], user: User | None = None) -> list[RiskScore]:
    """Append scores (never overwrite); red lines are locked and get a case automatically."""
    out = []
    now = utcnow()
    for r in results:
        rs = RiskScore(payment_id=r.payment_id, score=r.score, decision=r.decision, reasons_json=r.reasons,
                       engine_scores_json={"signals": r.signals, "contributions": r.contributions,
                                           "fraud_type": r.fraud_type},
                       evidence_json=r.evidence, trace_json=r.trace, model_version=r.model_version, created_at=now)
        db.add(rs)
        db.flush()
        p = db.get(Payment, r.payment_id)
        if r.decision == "blocked" and p.status in ("pending", "approved"):
            p.status = "blocked"
            existing = db.execute(select(Case).where(Case.payment_id == p.id, Case.status == "open")).scalars().first()
            if existing is None:
                case = Case(payment_id=p.id, risk_score_id=rs.id, status="open", fraud_type=r.fraud_type, source="auto",
                            opened_at=now, amount=p.amount)
                db.add(case)
                db.flush()
                db.add(CaseEvent(case_id=case.id, at=now, user_id=None, kind="opened",
                                 detail_json={"score": r.score, "reason": r.reasons[0]["text"] if r.reasons else None,
                                              "suspected": FRAUD_TYPES.get(r.fraud_type or "", None)}))
        out.append(rs)
    return out


def score_payments(db: Session, payment_ids: list[int], user: User | None = None) -> list[RiskScore]:
    runtime.bump()
    ctx = runtime.scoring_context(db)
    results = runtime.scorer.score(ctx, payment_ids)
    stored = store_scores(db, results, user)
    db.commit()
    runtime.bump()
    return stored


def claim_invoices(db: Session, invoice_ids: list[int]) -> None:
    """Atomically reserve invoices on SQLite as well as PostgreSQL before inserting instructions."""
    claimed = db.execute(update(Invoice).where(
        Invoice.id.in_(invoice_ids), Invoice.status == "received",
        ~exists(select(Payment.id).where(Payment.invoice_id == Invoice.id)),
    ).values(status="scheduled").execution_options(synchronize_session=False))
    if claimed.rowcount != len(invoice_ids):
        raise ApiError(409, "invoice_not_open", "An invoice was already scheduled by another request", "invoice_ids")
    # A SQLite claim may have waited for a concurrent field correction. Refresh amounts
    # under the write lock before creating instructions from previously loaded objects.
    db.execute(select(Invoice).where(Invoice.id.in_(invoice_ids))
               .execution_options(populate_existing=True)).scalars().all()


def lock_open_run(db: Session, run: PaymentRun, *, exporting: bool = False) -> None:
    """Serialize decisions and export on both databases; stale open-state reads are insufficient."""
    claimed = db.execute(update(PaymentRun).where(PaymentRun.id == run.id, PaymentRun.status == "open")
                         .values(status="exported" if exporting else "open")
                         .execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        raise ApiError(409, "run_closed", "This payment run is closed")
    db.refresh(run)
    db.expire(run, ["payments"])


def create_run(db: Session, user: User, run_date: date, invoice_ids: list[int], name: str | None = None,
               line_meta: dict[int, dict] | None = None) -> PaymentRun:
    company = db.execute(select(Company)).scalars().first()
    if len(invoice_ids) != len(set(invoice_ids)):
        raise ApiError(422, "duplicate_invoice", "Each invoice can appear only once in a payment run", "invoice_ids")
    # Lock before checking lifecycle so competing PostgreSQL requests cannot schedule the same invoice.
    invoices = {i.id: i for i in db.execute(select(Invoice).where(Invoice.id.in_(invoice_ids))
                                          .order_by(Invoice.id).with_for_update()).scalars()}
    existing = set(db.execute(select(Payment.invoice_id).where(Payment.invoice_id.in_(invoice_ids))).scalars())
    for iid in invoice_ids:
        inv = invoices.get(iid)
        if inv is None or inv.vendor_id is None:
            raise ApiError(422, "invalid_invoice", f"Invoice {iid} has no matched vendor", "invoice_ids")
        if inv.status != "received" or iid in existing:
            raise ApiError(409, "invoice_not_open", f"Invoice {iid} is not a confirmed, unscheduled invoice", "invoice_ids")
        if inv.total < 0:
            raise ApiError(422, "invalid_amount", f"Invoice {iid} has a negative total", "invoice_ids")
    claim_invoices(db, invoice_ids)
    now = utcnow()
    run = PaymentRun(company_id=company.id, name=name or f"Weekly run {run_date:%d %b %Y}", run_date=run_date,
                     status="open", created_by=user.id, created_at=now, is_live=True)
    db.add(run)
    db.flush()
    meta = line_meta or {}
    pay_ids = []
    for iid in invoice_ids:
        inv = invoices[iid]
        m = meta.get(iid, {})
        created_at = m.get("created_at") or now
        acct = active_account(db, inv.vendor_id, created_at)
        p = Payment(run_id=run.id, invoice_id=iid, vendor_id=inv.vendor_id, bank_account_id=acct.id,
                    amount=int(inv.total), created_by=m.get("created_by", user.id), created_at=created_at,
                    pay_date=m.get("pay_date", run_date), status="pending")
        db.add(p)
        db.flush()
        inv.status = "scheduled"
        pay_ids.append(p.id)
    audit(db, user, "create_run", "payment_run", run.id, lines=len(pay_ids))
    db.commit()
    score_payments(db, pay_ids, user)
    return run


def active_account(db: Session, vendor_id: int, at: datetime):
    from app.models import VendorBankAccount as A

    rows = db.execute(select(A).where(A.vendor_id == vendor_id, A.status == "active").order_by(A.valid_from)).scalars().all()
    best = rows[0] if rows else None
    for a in rows:
        if a.valid_from <= at and (a.valid_to is None or at < a.valid_to):
            best = a
    if best is None:
        raise ApiError(422, "no_bank_account", "Vendor has no active bank account")
    return best


def line_view(p: Payment, s: RiskScore | None, users: dict[int, str]) -> dict:
    d = effective_decision(p, s)
    reasons = (s.reasons_json if s else []) or []
    top = next((r for r in reasons if r.get("engine") != "info" and not r.get("weak")), None)
    return {
        "id": p.id, "invoice_id": p.invoice_id, "invoice_no": p.invoice.invoice_no, "vendor_id": p.vendor_id,
        "vendor": p.vendor.name, "amount": int(p.amount), "amount_fmt": fmt_rs(int(p.amount)), "status": p.status,
        "decision": d, "model_decision": s.decision if s else None, "score": s.score if s else None,
        "top_reason": top["text"] if top else ("No significant risk signals" if s else None),
        "reasons": [r for r in reasons if r.get("engine") != "info"][:4],
        "info": [r["text"] for r in reasons if r.get("engine") == "info"],
        "fraud_type": suspected_type(reasons, s.decision, (s.evidence_json or {}).get("features")) if s else None,
        "rules_comparison": (s.evidence_json or {}).get("rules_comparison") if s else None,
        "created_by": users.get(p.created_by), "created_by_id": p.created_by, "created_at": p.created_at.isoformat() + "Z",
        "approved_by": users.get(p.approved_by), "pay_date": p.pay_date.isoformat(), "override": p.override_decision,
        "override_by": users.get(p.override_by), "override_by_id": p.override_by,
        "bank_last4": p.bank_account.iban_last4, "bank_name": p.bank_account.bank_name,
        "model_version": s.model_version if s else None,
    }


def run_detail(db: Session, run: PaymentRun, with_cash: bool = True) -> dict:
    from app.services.cash.service import run_cash_panel

    users = dict(db.execute(select(User.id, User.name)).all())
    ps = list(run.payments)
    scores = latest_decisions(db, [p.id for p in ps])
    lines = [line_view(p, scores.get(p.id), users) for p in ps]
    missing_comparisons = [line for line in lines if line["model_decision"] is not None and not line["rules_comparison"]]
    if missing_comparisons:
        ctx = runtime.scoring_context(db)
        for line in missing_comparisons:
            evidence = scores[line["id"]].evidence_json or {}
            line["rules_comparison"] = comparison_for(ctx.features, line["id"], evidence.get("features"),
                                                      evidence.get("rules"), (evidence.get("graph") or {}).get("signal"))
    order = {"blocked": 0, "review": 1, "allow": 2, "unscored": 3}
    lines.sort(key=lambda l: (order.get(l["decision"], 4), -(l["score"] or 0)))
    totals = {}
    for k in ("allow", "review", "blocked"):
        sel = [l for l in lines if l["decision"] == k and l["status"] != "rejected"]
        totals[k] = {"count": len(sel), "amount": sum(l["amount"] for l in sel)}
    cases = db.execute(select(Case.id, Case.payment_id, Case.status).where(Case.payment_id.in_([p.id for p in ps]))).all()
    case_by_pay = {pid: {"id": cid, "status": st} for cid, pid, st in cases}
    for l in lines:
        l["case"] = case_by_pay.get(l["id"])
    company = db.execute(select(Company)).scalars().first()
    commitments = vendor_commitments(ps)
    for line in lines:
        line["vendor_commitment_amount"] = commitments.get(line["vendor_id"], 0)
        line["requires_owner_approval"] = line["vendor_commitment_amount"] > company.approval_limit
    out = {
        "id": run.id, "name": run.name, "run_date": run.run_date.isoformat(), "status": run.status,
        "created_at": run.created_at.isoformat() + "Z", "lines": lines, "totals": totals,
        "open_lines": sum(1 for l in lines if l["status"] in OPEN_STATUSES),
        "approval_limit": int(company.approval_limit), "model_version": runtime.bundle.version,
        "approval_policy": "The approval limit applies to each vendor's combined pending, approved and exported amount within this run. Held, blocked, rejected and settled lines are excluded. Case clearers and review-line creators cannot approve their own instruction.",
        "rules_comparison": comparison_summary(lines),
        "can_export": not any(l["status"] in OPEN_STATUSES for l in lines) and any(l["status"] == "approved" for l in lines),
    }
    if with_cash:
        out["cash"] = run_cash_panel(db, run)
    return out


def vendor_commitments(payments: list[Payment]) -> dict[int, int]:
    """Current run exposure, including approvals and unsettled exports already committed.

    Counting all pending siblings prevents a split purchase being approved one line at
    a time. A held/rejected/blocked instruction cannot be exported and is excluded;
    released instructions are settled and no longer a payable commitment.
    """
    totals: dict[int, int] = {}
    for payment in payments:
        if payment.status in ("pending", "approved", "exported"):
            totals[payment.vendor_id] = totals.get(payment.vendor_id, 0) + int(payment.amount)
    return totals


def approve_lines(db: Session, run: PaymentRun, user: User, payment_ids: list[int], note: str | None = None) -> dict:
    lock_open_run(db, run)
    company = db.execute(select(Company)).scalars().first()
    ps = {p.id: p for p in run.payments}
    scores = latest_decisions(db, list(ps))
    commitments = vendor_commitments(list(ps.values()))
    for pid in payment_ids:  # validate everything first: all-or-nothing
        p = ps.get(pid)
        if p is None:
            raise ApiError(404, "not_found", f"Line {pid} is not in this run", "payment_ids")
        d = effective_decision(p, scores.get(pid))
        if p.status == "blocked" or (d == "blocked" and not p.override_decision):
            raise ApiError(409, "blocked_line", f"{p.vendor.name}: blocked lines cannot be released (open the case)",
                           "payment_ids")
        if p.status not in ("pending",):
            raise ApiError(409, "not_pending", f"{p.vendor.name}: line is {p.status}", "payment_ids")
        if user.role not in ("approver", "owner"):
            raise ApiError(403, "forbidden", "Only an approver or the owner can release payments")
        if d in ("review",) and p.created_by == user.id:
            raise ApiError(403, "same_user", f"{p.vendor.name}: needs a second approver - you entered this line",
                           "payment_ids")
        if p.override_by == user.id:
            raise ApiError(403, "same_clearer", f"{p.vendor.name}: a different person must approve this line after you cleared its case",
                           "payment_ids")
        if commitments[p.vendor_id] > company.approval_limit and user.role != "owner":
            raise ApiError(403, "over_limit", f"{p.vendor.name}: combined run commitment {fmt_rs(commitments[p.vendor_id])} "
                                              f"is above the {fmt_rs(company.approval_limit)} limit, "
                                              "owner approval required", "payment_ids")
        if d == "unscored":
            raise ApiError(409, "unscored", f"{p.vendor.name}: line has not been scored yet", "payment_ids")
    now = utcnow()
    for pid in payment_ids:
        p = ps[pid]
        p.status = "approved"
        p.approved_by = user.id
        p.approved_at = now
        audit(db, user, "approve_payment", "payment", pid, decision=effective_decision(p, scores.get(pid)),
              amount=int(p.amount), note=note)
    db.commit()
    runtime.bump()
    return {"approved": payment_ids}


def approve_all_green(db: Session, run: PaymentRun, user: User) -> dict:
    """Bulk-approve every green line this user may approve; report the rest instead of failing."""
    if user.role not in ("approver", "owner"):
        raise ApiError(403, "forbidden", "Only an approver or the owner can release payments")
    lock_open_run(db, run)
    company = db.execute(select(Company)).scalars().first()
    scores = latest_decisions(db, [p.id for p in run.payments])
    commitments = vendor_commitments(list(run.payments))
    ok, skipped = [], []
    for p in run.payments:
        if p.status != "pending" or effective_decision(p, scores.get(p.id)) != "allow":
            continue
        if p.override_by == user.id:
            skipped.append({"id": p.id, "vendor": p.vendor.name,
                            "reason": "a different person must approve a line after its case is cleared"})
            continue
        if commitments[p.vendor_id] > company.approval_limit and user.role != "owner":
            skipped.append({"id": p.id, "vendor": p.vendor.name,
                            "reason": "combined vendor amount above approval limit: owner must approve"})
            continue
        ok.append(p.id)
    if ok:
        approve_lines(db, run, user, ok, note="approve all green")
    return {"approved": ok, "skipped": skipped}


def hold_lines(db: Session, run: PaymentRun, user: User, payment_ids: list[int], note: str | None = None) -> dict:
    lock_open_run(db, run)
    ps = {p.id: p for p in run.payments}
    for pid in payment_ids:
        p = ps.get(pid)
        if p is None:
            raise ApiError(404, "not_found", f"Line {pid} is not in this run", "payment_ids")
    for pid in payment_ids:
        p = ps[pid]
        if p.status in ("pending", "approved"):
            p.status = "held"
            audit(db, user, "hold_payment", "payment", pid, note=note)
    db.commit()
    runtime.bump()
    return {"held": payment_ids}


def export_csv(db: Session, run: PaymentRun, user: User) -> str:
    lock_open_run(db, run, exporting=True)
    ps = list(run.payments)
    open_lines = [p for p in ps if p.status in OPEN_STATUSES]
    if open_lines:
        raise ApiError(409, "open_lines", f"{len(open_lines)} line(s) still need a decision before the bank file can be exported")
    approved = [p for p in ps if p.status == "approved"]
    if not approved:
        raise ApiError(409, "nothing_to_export", "No approved lines to export")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["payment_id", "value_date", "beneficiary", "bank", "account_last4", "amount_pkr", "reference"])
    for p in approved:
        w.writerow([p.id, p.pay_date.isoformat(), p.vendor.name, p.bank_account.bank_name, p.bank_account.iban_last4,
                    f"{p.amount // 100}.{p.amount % 100:02d}", p.invoice.invoice_no])
        # Generating a file is not evidence of bank settlement. Keep the obligation in cash forecasts.
        p.status = "exported"
    run.status = "exported"
    audit(db, user, "export_bank_file", "payment_run", run.id, lines=len(approved),
          total=sum(int(p.amount) for p in approved), settlement_confirmed=False)
    db.commit()
    runtime.bump()
    return buf.getvalue()


def vendor_name(db: Session, vid: int) -> str:
    v = db.get(Vendor, vid)
    return v.name if v else "?"
