"""Invoices, receivables, cash, dashboard, evaluation, admin and demo endpoints."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import current_user, require_roles
from app.config import get_settings
from app.db import SessionLocal, get_db
from app.errors import ApiError
from app.models import (Case, Company, Customer, Invoice, InvoiceLine, ModelVersion, Payment, PaymentRun, Receivable,
                        RiskScore, Scenario, User)
from app.money import fmt_rs, rupees_to_paisa
from app.schemas.requests import InvoicePatch, ScenarioIn
from app.services import cash as _cash  # noqa: F401
from app.services.cash import service as cash_svc
from app.services.identity import norm_invoice_no
from app.services.importer import import_csv
from app.services.payment_runs import audit, latest_decisions, score_payments, utcnow
from app.services.runtime import runtime
from app.services.scoring.scorer import FRAUD_TYPES

router = APIRouter()


# ----------------------------------------------------------------------------- invoices
@router.post("/invoices/upload", tags=["invoices"])
async def upload_invoice(file: UploadFile = File(...), db: Session = Depends(get_db),
                         user: User = Depends(require_roles("accountant", "approver", "owner"))):
    from app.services.docreader.pipeline import read_and_store

    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise ApiError(413, "too_large", "File is larger than 8 MB", "file")
    return read_and_store(db, user, file.filename or "upload.pdf", file.content_type or "", data)


@router.post("/invoices/import", tags=["invoices"])
async def import_invoices(file: UploadFile = File(...), db: Session = Depends(get_db),
                          user: User = Depends(require_roles("accountant", "owner"))):
    text = (await file.read()).decode("utf-8-sig")
    rows = import_csv(db, text, user)
    audit(db, user, "import_invoices", "invoice", None, count=len(rows))
    db.commit()
    runtime.bump()
    return {"imported": len(rows), "invoices": [{k: v for k, v in r.items() if k != "meta"} for r in rows]}


@router.get("/invoices/{invoice_id}", tags=["invoices"])
def get_invoice(invoice_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    inv = db.get(Invoice, invoice_id) or _404("invoice")
    return _invoice_view(db, inv)


@router.patch("/invoices/{invoice_id}", tags=["invoices"])
def patch_invoice(invoice_id: int, body: InvoicePatch, db: Session = Depends(get_db),
                  user: User = Depends(require_roles("accountant", "approver", "owner"))):
    inv = db.get(Invoice, invoice_id) or _404("invoice")
    if inv.status not in ("draft", "received"):
        raise ApiError(409, "locked", "Invoice is already in a payment run")
    changed = {}
    for f in ("vendor_id", "invoice_no", "invoice_date", "due_date"):
        v = getattr(body, f)
        if v is not None:
            changed[f] = str(v)
            setattr(inv, f, v)
    if body.invoice_no:
        inv.invoice_no_norm = norm_invoice_no(body.invoice_no)
    for f in ("subtotal", "tax", "total"):
        v = getattr(body, f)
        if v is not None:
            changed[f] = v
            setattr(inv, f, rupees_to_paisa(str(v)))
    if body.lines is not None:
        for l in list(inv.lines):
            db.delete(l)
        inv.lines = [InvoiceLine(description=l.description, qty=l.qty, unit_price=rupees_to_paisa(str(l.unit_price)),
                                 amount=rupees_to_paisa(str(l.amount))) for l in body.lines]
    if body.confirm and inv.status == "draft":
        if inv.vendor_id is None:
            raise ApiError(422, "vendor_required", "Pick the vendor before confirming", "vendor_id")
        inv.status = "received"
    if inv.extraction_json is not None and changed:
        ext = dict(inv.extraction_json)
        ext["corrected_fields"] = sorted(set(ext.get("corrected_fields", [])) | set(changed))
        inv.extraction_json = ext
    audit(db, user, "edit_invoice", "invoice", inv.id, fields=changed, confirmed=body.confirm)
    db.commit()
    runtime.bump()
    return _invoice_view(db, inv)


@router.post("/invoices/{invoice_id}/score", tags=["invoices"])
def score_invoice(invoice_id: int, db: Session = Depends(get_db),
                  user: User = Depends(require_roles("accountant", "approver", "owner"))):
    """Adds the invoice to the open payment run (creating one if needed) and scores the line."""
    inv = db.get(Invoice, invoice_id) or _404("invoice")
    if inv.vendor_id is None:
        raise ApiError(422, "vendor_required", "Match the invoice to a vendor first", "vendor_id")
    if inv.status == "draft":
        inv.status = "received"
    p = db.execute(select(Payment).where(Payment.invoice_id == inv.id)).scalars().first()
    if p is None:
        from app.services.payment_runs import active_account

        company = db.execute(select(Company)).scalars().first()
        run = cash_svc.open_run(db)
        if run is None:
            run = PaymentRun(company_id=company.id, name=f"Weekly run {company.as_of_date:%d %b %Y}",
                             run_date=company.as_of_date, status="open", created_by=user.id, created_at=utcnow(), is_live=True)
            db.add(run)
            db.flush()
        now = utcnow()
        acct = active_account(db, inv.vendor_id, now)
        p = Payment(run_id=run.id, invoice_id=inv.id, vendor_id=inv.vendor_id, bank_account_id=acct.id,
                    amount=int(inv.total), created_by=user.id, created_at=now,
                    pay_date=max(company.as_of_date + timedelta(days=1), run.run_date), status="pending")
        db.add(p)
        inv.status = "scheduled"
        db.commit()
    score_payments(db, [p.id], user)
    s = db.execute(select(RiskScore).where(RiskScore.payment_id == p.id).order_by(RiskScore.id.desc())).scalars().first()
    case = db.execute(select(Case).where(Case.payment_id == p.id).order_by(Case.id.desc())).scalars().first()
    return {"invoice_id": inv.id, "payment_id": p.id, "run_id": p.run_id, "score": s.score, "decision": s.decision,
            "reasons": s.reasons_json, "trace": s.trace_json, "engines": s.engine_scores_json,
            "case_id": case.id if case else None, "model_version": s.model_version}


def _invoice_view(db: Session, inv: Invoice) -> dict:
    return {
        "id": inv.id, "vendor_id": inv.vendor_id, "vendor": inv.vendor.name if inv.vendor else None,
        "invoice_no": inv.invoice_no, "invoice_date": inv.invoice_date.isoformat(), "due_date": inv.due_date.isoformat(),
        "subtotal": int(inv.subtotal), "tax": int(inv.tax), "total": int(inv.total), "status": inv.status,
        "source": inv.source, "file_name": inv.file_name, "iban_last4": inv.iban_last4,
        "lines": [{"description": l.description, "qty": l.qty, "unit_price": int(l.unit_price), "amount": int(l.amount)}
                  for l in inv.lines],
        "extraction": inv.extraction_json,
    }


# ----------------------------------------------------------------------------- receivables
@router.get("/receivables", tags=["receivables"])
def receivables(status: str = Query("open", description="open | paid | all"), risk: str | None = Query(None, description="high | medium | low"),
                customer_id: int | None = None, q: str | None = None, sort: str = "expected_date",
                page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                db: Session = Depends(get_db), user: User = Depends(current_user)):
    company = db.execute(select(Company)).scalars().first()
    late = runtime.late_risk(db)
    risk_by = late["by_id"]
    from app.services.cash.inputs import estimate_receipts

    r, c = runtime.receivable_frames(db)
    est = {e.receivable_id: e for e in estimate_receipts(r, company.as_of_date)}
    cust = c.set_index("id")
    rows = []
    for x in r.itertuples(index=False):
        is_open = x.paid_date is None or str(x.paid_date) in ("NaT", "None")
        if status == "open" and not is_open or status == "paid" and is_open:
            continue
        if customer_id and int(x.customer_id) != customer_id:
            continue
        name = cust.loc[x.customer_id, "name"]
        if q and q.lower() not in name.lower() and q.lower() not in x.invoice_no.lower():
            continue
        rk = risk_by.get(int(x.id), {})
        e = est.get(int(x.id))
        row = {
            "id": int(x.id), "customer_id": int(x.customer_id), "customer": name, "segment": cust.loc[x.customer_id, "segment"],
            "invoice_no": x.invoice_no, "issue_date": str(x.issue_date), "due_date": str(x.due_date), "amount": int(x.amount),
            "amount_fmt": fmt_rs(int(x.amount)), "status": "open" if is_open else "paid",
            "paid_date": None if is_open else str(x.paid_date),
            "delay_days": None if is_open else (date.fromisoformat(str(x.paid_date)) - date.fromisoformat(str(x.due_date))).days,
            "risk": rk.get("risk"), "limited_history": rk.get("limited_history", False), "reasons": rk.get("reasons", []),
            "expected_date": e.expected_date.isoformat() if e else None, "expected_basis": e.basis if e else None,
            "overdue_days": e.overdue_days if e else None, "disputed_amount": int(x.disputed_amount or 0),
            "expected_note": e.note if e else None,
        }
        band = None if row["risk"] is None else ("high" if row["risk"] >= 0.6 else "medium" if row["risk"] >= 0.35 else "low")
        row["risk_band"] = band
        if risk and band != risk:
            continue
        rows.append(row)
    key = {"expected_date": lambda r: r["expected_date"] or "9999", "risk": lambda r: -(r["risk"] or 0),
           "amount": lambda r: -r["amount"], "due_date": lambda r: r["due_date"]}.get(sort, lambda r: r["expected_date"] or "")
    rows.sort(key=key)
    total = len(rows)
    open_rows = [x for x in rows if x["status"] == "open"]
    summary = {"count": total, "open_total": sum(x["amount"] for x in open_rows),
               "overdue_total": sum(x["amount"] for x in open_rows if (x["overdue_days"] or 0) > 0),
               "high_risk_total": sum(x["amount"] for x in open_rows if x["risk_band"] == "high"),
               "risk_label": late["label"], "risk_model": late["kind"]}
    return {"items": rows[(page - 1) * page_size: page * page_size], "page": page, "page_size": page_size,
            "total": total, "summary": summary}


# ----------------------------------------------------------------------------- cash
@router.get("/cash/projection", tags=["cash"])
def cash_projection(run_id: int | None = None, hold_yellow: bool = False, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    return cash_svc.outlook(db, run_id, hold_yellow)


@router.post("/cash/scenarios", tags=["cash"])
def cash_scenario(body: ScenarioIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        res = cash_svc.scenario(db, [m.model_dump() for m in body.moves], body.hold_yellow, body.run_id)
    except KeyError as e:
        raise ApiError(422, "unknown_receivable", f"Receivable not in the projection: {e}", "moves")
    except ValueError as e:
        raise ApiError(422, "invalid_date", str(e), "moves")
    sc = Scenario(name=body.name, params_json=body.model_dump(mode="json"), result_json=res["delta"], created_by=user.id,
                  created_at=utcnow())
    db.add(sc)
    db.commit()
    res["id"] = sc.id
    return res


# ----------------------------------------------------------------------------- dashboard & eval
@router.get("/dashboard/summary", tags=["dashboard"])
def dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    company = db.execute(select(Company)).scalars().first()
    m0 = company.as_of_date.replace(day=1)
    month_start = datetime.combine(m0, datetime.min.time()) - timedelta(hours=5)
    live = db.execute(select(Payment).where(Payment.created_at >= month_start - timedelta(days=7))).scalars().all()
    live = [p for p in live if p.run and p.run.is_live]
    scores = latest_decisions(db, [p.id for p in live])
    protected = sum(int(p.amount) for p in live if p.status in ("blocked", "rejected"))
    by_type: dict[str, dict] = {}
    for p in live:
        s = scores.get(p.id)
        if s and s.decision != "allow":
            t = (s.engine_scores_json or {}).get("fraud_type") or "ANOMALY"
            d = by_type.setdefault(t, {"type": t, "name": FRAUD_TYPES.get(t, t), "count": 0, "amount": 0, "red": 0})
            d["count"] += 1
            d["amount"] += int(p.amount)
            d["red"] += int(s.decision == "blocked")
    hist = db.execute(select(Case.fraud_type, func.count(Case.id), func.sum(Case.amount))
                      .where(Case.source == "historical").group_by(Case.fraud_type)).all()
    open_cases = db.execute(select(func.count(Case.id), func.coalesce(func.sum(Case.amount), 0)).where(Case.status == "open")).one()
    run = cash_svc.open_run(db) or db.execute(select(PaymentRun).where(PaymentRun.is_live.is_(True))
                                               .order_by(PaymentRun.id.desc())).scalars().first()
    cash = None
    if run is not None:
        panel = cash_svc.run_cash_panel(db, run)
        cash = {"run_id": run.id, **panel["with_nigraan"], "reserve": panel["reserve"],
                "release_everything": panel["release_everything"]}
    else:
        o = cash_svc.outlook(db, None)
        p = o["projection"]
        cash = {"run_id": None, "low_point": p["low_point"], "low_point_day": p["low_point_day"],
                "first_breach": p["first_breach"], "reserve": p["reserve"], "stays_above_reserve": p["first_breach"] is None}
    metrics = _metrics()
    lines = run_lines = None
    if run is not None:
        sc = latest_decisions(db, [p.id for p in run.payments])
        run_lines = {"total": len(run.payments),
                     "by_decision": {k: sum(1 for p in run.payments if cash_svc.effective_decision(p, sc.get(p.id)) == k)
                                     for k in ("allow", "review", "blocked")},
                     "pending": sum(1 for p in run.payments if p.status == "pending")}
    return {
        "company": {"name": company.name, "as_of": company.as_of_date.isoformat(), "reserve": int(company.cash_reserve),
                    "opening_cash": int(company.opening_cash), "approval_limit": int(company.approval_limit)},
        "rupees_protected_this_month": protected, "open_cases": {"count": int(open_cases[0]), "amount": int(open_cases[1])},
        "alerts_by_type": sorted(by_type.values(), key=lambda d: -d["amount"]),
        "historical_confirmed": [{"type": t, "name": FRAUD_TYPES.get(t or "", t), "count": int(n), "amount": int(a or 0)}
                                 for t, n, a in hist],
        "cash": cash, "run": run_lines, "model_version": runtime.bundle.version, "metrics": _metric_cards(metrics),
        "lines": lines,
    }


def _metrics() -> dict:
    p = get_settings().models_dir / "metrics.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _metric_cards(m: dict) -> dict | None:
    if not m:
        return None
    f = m["fraud"]
    lt = m["late_payment"]
    c = m["cash"]
    out = {
        "test_period": m.get("test_period"), "generated_at": m.get("generated_at"),
        "fraud": {"n_payments": f["n_payments"], "n_fraud": f["n_fraud"], "nigraan": {k: f["nigraan"][k] for k in (
            "recall", "precision_red", "false_alarm_rate", "pr_auc", "rupees_protected_red", "rupees_fraud")},
                  "baseline": {k: f["baseline_rules_only"][k] for k in ("recall", "precision_red", "false_alarm_rate", "pr_auc")},
                  "per_type": f["nigraan"]["per_type"]},
        "late": {"shipped": lt.get("shipped", {}).get("kind"), "pr_auc": lt.get("shipped", {}).get("pr_auc"),
                 "baseline_pr_auc": lt["models"]["baseline"]["pr_auc"], "lr_pr_auc": lt["models"]["lr"]["pr_auc"],
                 "xgb_pr_auc": lt["models"]["xgb"]["pr_auc"], "precision_top20": lt.get("shipped", {}).get("precision_top20"),
                 "brier": lt.get("shipped", {}).get("brier"), "baseline_brier": lt["models"]["baseline"]["brier"]},
        "cash": {"mae": c["median_delay"]["mae_rupees_per_week"], "baseline_mae": c["due_date"]["mae_rupees_per_week"],
                 "improvement": c["improvement_vs_due_date"]},
    }
    if "robustness" in m:
        out["robustness"] = m["robustness"]["aggregate"]
    if "extraction" in m:
        out["extraction"] = m["extraction"].get("summary")
    return out


@router.get("/eval/results", tags=["dashboard"])
def eval_results(user: User = Depends(current_user)):
    m = _metrics()
    if not m:
        raise ApiError(404, "not_found", "No evaluation results yet (run python -m ml.evaluate)")
    return m


# ----------------------------------------------------------------------------- admin
_jobs: dict[str, dict] = {}


@router.post("/admin/retrain", tags=["admin"], status_code=202)
def retrain(user: User = Depends(require_roles("owner", "approver"))):
    job = uuid.uuid4().hex[:10]
    _jobs[job] = {"id": job, "status": "running", "started_at": utcnow().isoformat() + "Z"}

    def work():
        from ml.retrain import retrain_from_db

        db = SessionLocal()
        try:
            res = retrain_from_db(db)
            _jobs[job].update(status="done", result=res)
            audit(db, user, "retrain", "model", None, version=res["version"])
            db.commit()
        except Exception as e:  # noqa: BLE001 - reported to the caller, logged server-side
            import logging
            logging.getLogger("nigraan").exception("retrain failed")
            _jobs[job].update(status="failed", message=str(e)[:200])
        finally:
            db.close()

    threading.Thread(target=work, daemon=True).start()
    return _jobs[job]


@router.get("/admin/retrain/{job_id}", tags=["admin"])
def retrain_status(job_id: str, user: User = Depends(current_user)):
    if job_id not in _jobs:
        _404("job")
    return _jobs[job_id]


@router.get("/admin/models", tags=["admin"])
def models_info(db: Session = Depends(get_db), user: User = Depends(current_user)):
    b = runtime.bundle
    hist = db.execute(select(ModelVersion).order_by(ModelVersion.id)).scalars().all()
    return {"version": b.version, "has_ml": b.has_ml, "fusion": {k: b.fusion.get(k) for k in ("weights", "t_yellow", "t_red", "source")},
            "late_model": b.late.get("kind") if b.late else None,
            "history": [{"version": h.version, "trained_at": h.trained_at.isoformat() + "Z", "n_labels": h.n_labels,
                         "metrics": h.metrics_json, "notes": h.notes} for h in hist]}


# ----------------------------------------------------------------------------- demo
def _demo_only():
    if not get_settings().demo_mode:
        raise ApiError(404, "not_found", "Not found")


@router.post("/demo/reset", tags=["demo"])
def demo_reset(user: User = Depends(current_user), db: Session = Depends(get_db)):
    _demo_only()
    db.close()
    from app.services.demo import reset

    return reset()


@router.post("/demo/load-week", tags=["demo"])
def demo_load_week(db: Session = Depends(get_db), user: User = Depends(current_user)):
    _demo_only()
    from app.services.demo import load_week

    sana = db.execute(select(User).where(User.email == "sana@bismillah.pk")).scalars().first() or user
    return load_week(db, sana)


@router.get("/demo/samples", tags=["demo"])
def demo_samples(user: User = Depends(current_user)):
    """Sample invoice files judges can upload without having them locally."""
    d = get_settings().demo_week_dir
    out = []
    up = d / "upload_samples"
    if up.exists():
        for f in sorted(up.glob("*.pdf")):
            out.append({"name": f.name, "group": "upload_samples",
                        "hint": "resent invoice (already in this run)" if f.name.startswith("resent_") else "new invoice"})
    pdfs = sorted((d / "pdfs").glob("*.pdf")) if (d / "pdfs").exists() else []
    for f in pdfs[:6]:
        out.append({"name": f.name, "group": "pdfs", "hint": "demo-week invoice"})
    return out


@router.get("/demo/samples/{group}/{name}", tags=["demo"])
def demo_sample_file(group: str, name: str, user: User = Depends(current_user)):
    from fastapi.responses import FileResponse

    if group not in ("upload_samples", "pdfs") or "/" in name or ".." in name or not name.endswith(".pdf"):
        _404("sample")
    path = get_settings().demo_week_dir / group / name
    if not path.exists():
        _404("sample")
    return FileResponse(path, media_type="application/pdf", filename=name)


@router.get("/demo/status", tags=["demo"])
def demo_status(db: Session = Depends(get_db)):
    s = get_settings()
    company = db.execute(select(Company)).scalars().first()
    run = cash_svc.open_run(db)
    return {"demo_mode": s.demo_mode, "seeded": company is not None, "open_run_id": run.id if run else None,
            "model_version": runtime.bundle.version, "gemini": bool(s.gemini_api_key),
            "as_of": company.as_of_date.isoformat() if company else None}


def _404(what: str):
    raise ApiError(404, "not_found", f"{what.capitalize()} not found")
