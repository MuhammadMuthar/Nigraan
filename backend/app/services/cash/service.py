"""Cash projection for the app: assembles flows from the database and runs the deterministic engine."""
from __future__ import annotations

from datetime import date
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Invoice, Payment, PaymentRun, RiskScore, ScheduledOutflow, Vendor
from app.config import get_settings
from app.money import fmt_rs
from app.services.cash.engine import Flow, Projection, drop_flows, move_flow, project
from app.services.cash.inputs import estimate_receipts, outflow_flows, payable_flows, receipt_flows, run_flows
from app.services.runtime import runtime


def company(db: Session) -> Company:
    return db.execute(select(Company)).scalars().first()


def open_run(db: Session) -> PaymentRun | None:
    return db.execute(select(PaymentRun).where(PaymentRun.status == "open").order_by(PaymentRun.id.desc())).scalars().first()


def latest_decisions(db: Session, payment_ids: list[int]) -> dict[int, RiskScore]:
    if not payment_ids:
        return {}
    rows = db.execute(select(RiskScore).where(RiskScore.payment_id.in_(payment_ids)).order_by(RiskScore.id)).scalars().all()
    out: dict[int, RiskScore] = {}
    for r in rows:
        out[r.payment_id] = r
    return out


def effective_decision(p: Payment, score: RiskScore | None) -> str:
    if p.override_decision:
        return p.override_decision
    return score.decision if score else "unscored"


class CashInputs:
    def __init__(self, db: Session, run: PaymentRun | None):
        c = company(db)
        self.as_of: date = c.as_of_date
        self.opening, self.reserve = int(c.opening_cash), int(c.cash_reserve)
        r, cust = runtime.receivable_frames(db)
        self.receivables = r
        self.customers = cust.set_index("id")
        self.estimates = estimate_receipts(r, self.as_of)
        names = self.customers["name"].to_dict()
        self.receipts = receipt_flows(self.estimates, names)
        so = pd.DataFrame(db.execute(select(ScheduledOutflow.id, ScheduledOutflow.name, ScheduledOutflow.due_date,
                                            ScheduledOutflow.amount, ScheduledOutflow.basis)).all(),
                          columns=["id", "name", "due_date", "amount", "basis"])
        self.outflows = outflow_flows(so, self.as_of)
        inv = pd.DataFrame(db.execute(select(Invoice.id, Invoice.vendor_id, Invoice.invoice_no, Invoice.due_date,
                                             Invoice.total, Invoice.status)).all(),
                           columns=["id", "vendor_id", "invoice_no", "due_date", "total", "status"])
        payments = list(db.execute(select(Payment)).scalars())
        pays = pd.DataFrame([(p.id, p.invoice_id, p.amount, p.status, p.run_id) for p in payments],
                            columns=["id", "invoice_id", "amount", "status", "run_id"])
        outstanding = [p for p in payments if p.status not in ("released", "rejected")]
        # Each scheduled obligation belongs to its payment line even after a run is exported.
        # Held/blocked lines must not silently reappear as generic weekly invoice payments.
        assigned_invoices = {p.invoice_id for p in outstanding}
        vnames = dict(db.execute(select(Vendor.id, Vendor.name)).all())
        self.payables = payable_flows(inv, pays[pays["status"] == "released"], self.as_of, assigned_invoices, vnames)
        # Historical ledger rows with a future value date still reduce future cash. Payments
        # before as_of are already reflected in the supplied opening balance and stay excluded.
        self.future_settlements = run_flows([
            {"id": p.id, "amount": int(p.amount), "pay_date": p.pay_date,
             "label": f"{p.vendor.name} (recorded payment)"}
            for p in payments if p.status == "released" and p.pay_date >= self.as_of
        ])
        self.run = run
        self.lines: list[dict] = []
        self.other_lines: list[dict] = []
        outstanding_ids = {p.id for p in outstanding}
        displayed = [p for p in payments if p.id in outstanding_ids or (run is not None and p.run_id == run.id)]
        scores = latest_decisions(db, [p.id for p in displayed])
        for p in displayed:
            selected = run is not None and p.run_id == run.id
            line = {"id": p.id, "amount": int(p.amount), "pay_date": max(p.pay_date, self.as_of),
                    "label": f"{p.vendor.name} ({'this run' if selected else 'scheduled payment'})",
                    "decision": effective_decision(p, scores.get(p.id)), "status": p.status}
            (self.lines if selected else self.other_lines).append(line)

    def base_flows(self) -> list[Flow]:
        return self.receipts + self.outflows + self.payables + self.future_settlements + self._line_flows(self.other_lines, "nigraan")

    def line_flows(self, mode: str) -> list[Flow]:
        """mode: 'nigraan' (red blocked, held/rejected out), 'all' (release everything), 'green_only'."""
        return self._line_flows(self.lines, mode)

    @staticmethod
    def _line_flows(lines: list[dict], mode: str) -> list[Flow]:
        sel = []
        for l in lines:
            if l["status"] in ("rejected", "released"):
                continue
            # Exported instructions are committed outflows until settlement is reconciled.
            # A What-if toggle must not pretend it can withdraw an already exported file.
            if l["status"] == "exported" or mode == "all":
                sel.append(l)
            elif mode == "nigraan":
                if l["decision"] != "blocked" and l["status"] not in ("held", "blocked"):
                    sel.append(l)
            elif mode == "green_only":
                if l["decision"] == "allow" and l["status"] not in ("held", "blocked"):
                    sel.append(l)
        return run_flows(sel)

    def project(self, flows: list[Flow]) -> Projection:
        return project(self.as_of, self.opening, self.reserve, flows)


def proj_payload(p: Projection, *, with_days: bool = True) -> dict:
    out = {
        "as_of": p.as_of.isoformat(), "opening": p.opening, "reserve": p.reserve, "low_point": p.low_point,
        "low_point_day": p.low_point_day.isoformat(), "first_breach": p.first_breach.isoformat() if p.first_breach else None,
        "breach_gap": p.breach_gap, "total_in": p.total_in, "total_out": p.total_out,
        "weeks": [{
            "week": w.week, "start": w.start.isoformat(), "end": w.end.isoformat(), "inflow": w.inflow, "outflow": w.outflow,
            "inflow_by_basis": w.inflow_by_basis, "outflow_by_basis": w.outflow_by_basis, "closing": w.closing,
            "low": w.low, "low_day": w.low_day.isoformat()} for w in p.weeks],
        "beyond_horizon": [{"day": f.day.isoformat(), "amount": f.amount, "label": f.label, "ref": f.ref}
                           for f in p.beyond_horizon],
    }
    if with_days:
        out["days"] = [{"day": d.day.isoformat(), "inflow": d.inflow, "outflow": d.outflow, "closing": d.closing}
                       for d in p.days]
    return out


def responsible_receivables(ci: CashInputs, p: Projection, k: int = 3) -> list[dict]:
    """Receivables that were due on/before the low point but are expected to arrive after it."""
    risk = runtime.late_risk_cached
    low_day = p.low_point_day
    out = []
    for e in ci.estimates:
        if e.due_date <= low_day and (e.expected_date is None or low_day < e.expected_date) and e.amount > 0:
            r = risk.get(e.receivable_id, {})
            out.append(_rec_row(ci, e, r))
    out.sort(key=lambda x: -x["amount"] * (0.5 + (x["risk"] if x.get("risk") is not None else 0.5)))
    return out[:k]


def _rec_row(ci: CashInputs, e, r: dict) -> dict:
    cust = ci.customers.loc[e.customer_id]
    rec = ci.receivables.set_index("id").loc[e.receivable_id]
    return {
        "receivable_id": e.receivable_id, "customer_id": e.customer_id, "customer": cust["name"], "segment": cust["segment"],
        "invoice_no": rec["invoice_no"], "amount": e.amount, "amount_fmt": fmt_rs(e.amount), "due_date": e.due_date.isoformat(),
        "expected_date": e.expected_date.isoformat() if e.expected_date is not None else None,
        "included_in_base": e.included_in_base, "overdue_days": e.overdue_days, "basis": e.basis, "note": e.note,
        "median_delay": e.median_delay, "limited_history": r.get("limited_history", e.limited_history),
        "risk": r.get("risk"), "reasons": r.get("reasons", []), "disputed": e.disputed,
    }


def collection_policy(ci: CashInputs) -> dict:
    unconfirmed = [e for e in ci.estimates if not e.included_in_base and e.amount > 0]
    return {"name": "exclude_unconfirmed", "unconfirmed_count": len(unconfirmed),
            "unconfirmed_amount": sum(e.amount for e in unconfirmed),
            "label": "Overdue beyond historical collection delays is excluded until a dated scenario is supplied."}


@lru_cache(maxsize=4)
def _review_metrics(models_dir: str) -> dict:
    """Read the additive offline artifact once; never run an evaluation in a request."""
    path = Path(models_dir) / "cash_review_metrics.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        inputs = Path(__file__).with_name("inputs.py")
        if data.get("inputs_sha256") != hashlib.sha256(inputs.read_bytes()).hexdigest():
            return {}
        return data
    except (OSError, ValueError, TypeError):
        return {}


def validation_metadata() -> dict:
    artifact = _review_metrics(str(get_settings().models_dir))
    current = artifact.get("policies", {}).get("exclude_unconfirmed")
    saved = runtime.bundle.metrics
    measured = current or saved.get("cash", {})
    origins = measured.get("origins", [])
    return {
        "forecast_horizon_weeks": 13,
        "backtest_horizon_weeks": measured.get("horizon_weeks"),
        "origins": origins,
        "synthetic": True,
        "seed": artifact.get("seed") if current else saved.get("seed"),
        "receipt_policy": "exclude_unconfirmed" if current else "legacy_next_week",
        "current_policy_backtested": bool(current),
        "mae_rupees_per_week": measured.get("median_delay", {}).get("mae_rupees_per_week"),
        "due_date_mae_rupees_per_week": measured.get("due_date", {}).get("mae_rupees_per_week"),
        "improvement_vs_due_date": measured.get("improvement_vs_due_date"),
        "wape": measured.get("median_delay", {}).get("wape"),
        "generated_at": artifact.get("generated_at") if current else saved.get("generated_at"),
        "scope": "Receipt timing tested over the backtest horizon only; weeks beyond it and full reserve outcomes are not validated.",
    }


def run_cash_panel(db: Session, run: PaymentRun) -> dict:
    runtime.late_risk_cached = runtime.late_risk(db)["by_id"]
    ci = CashInputs(db, run)
    base = ci.base_flows()
    p_nig = ci.project(base + ci.line_flows("nigraan"))
    p_all = ci.project(base + ci.line_flows("all"))
    p_green = ci.project(base + ci.line_flows("green_only"))
    totals = {"allow": 0, "review": 0, "blocked": 0, "unscored": 0}
    for l in ci.lines:
        if l["status"] in ("rejected",):
            continue
        totals[l["decision"] if l["decision"] in totals else "unscored"] += l["amount"]
    return {
        "as_of": ci.as_of.isoformat(), "cash_before_run": ci.opening, "reserve": ci.reserve,
        "collection_policy": collection_policy(ci), "validation": validation_metadata(),
        "run_total": sum(totals.values()), "totals_by_decision": totals, "blocked_amount": totals["blocked"],
        "with_nigraan": _panel_case(p_nig), "release_everything": _panel_case(p_all), "hold_yellow": _panel_case(p_green),
        "responsible_receivables": responsible_receivables(ci, p_nig if p_nig.first_breach else p_all),
        "chart": [{"day": d.day.isoformat(), "with_nigraan": d.closing, "release_everything": a.closing}
                  for d, a in zip(p_nig.days[:28], p_all.days[:28])],
    }


def _panel_case(p: Projection) -> dict:
    return {"low_point": p.low_point, "low_point_day": p.low_point_day.isoformat(),
            "first_breach": p.first_breach.isoformat() if p.first_breach else None, "breach_gap": p.breach_gap,
            "stays_above_reserve": p.first_breach is None}


def outlook(db: Session, run_id: int | None, hold_yellow: bool = False) -> dict:
    run = db.get(PaymentRun, run_id) if run_id else open_run(db)
    late = runtime.late_risk(db)
    runtime.late_risk_cached = late["by_id"]
    ci = CashInputs(db, run)
    flows = ci.base_flows() + ci.line_flows("green_only" if hold_yellow else "nigraan")
    p = ci.project(flows)
    recs = [_rec_row(ci, e, late["by_id"].get(e.receivable_id, {})) for e in ci.estimates]
    recs.sort(key=lambda r: r["expected_date"] or "9999")
    return {"projection": proj_payload(p), "receivables": recs, "run_id": run.id if run else None,
            "collection_policy": collection_policy(ci), "validation": validation_metadata(),
            "risk_label": late["label"], "risk_model": late["kind"],
            "assumptions": [
                "Only invoices already issued or received are projected; new sales and purchases are not forecast.",
                "Expected receipt date = due date + the customer's median past delay (global median if fewer than 5 settled invoices).",
                "Overdue beyond median and slow-payer (80th percentile) delay has no confirmed date and is excluded from base cash. Add a dated What-if to assess collection; this does not record a payment promise.",
                "Disputed amounts are excluded.",
                "Vendor invoices are paid in the weekly run that covers their due date.",
                "Bank-file export is not settlement; exported instructions remain cash outflows at their value date until reconciled.",
                "Utility bills after this month are estimates (assumption)."],
            "basis_legend": {"fact": "Contracted or already approved", "estimate": "Historical-delay estimate (expected date)",
                             "assumption": "Assumption"}}


def scenario(db: Session, moves: list[dict], hold_yellow: bool, run_id: int | None) -> dict:
    run = db.get(PaymentRun, run_id) if run_id else open_run(db)
    ci = CashInputs(db, run)
    base_flows = ci.base_flows() + ci.line_flows("nigraan")
    scen = list(ci.base_flows())
    estimates = {e.receivable_id: e for e in ci.estimates}
    assumed_amount, assumed_count = 0, 0
    moved_ids: set[int] = set()
    for m in moves:
        rid = int(m["receivable_id"])
        if rid in moved_ids:
            raise ValueError("Each receivable can have only one scenario collection date")
        moved_ids.add(rid)
        estimate = estimates.get(rid)
        if estimate is None or estimate.amount <= 0:
            raise KeyError(rid)
        new_day = date.fromisoformat(m["new_date"]) if isinstance(m["new_date"], str) else m["new_date"]
        if not estimate.included_in_base:
            scen.append(Flow(new_day, estimate.amount, "receipt", "assumption",
                             f"{ci.customers.loc[estimate.customer_id, 'name']} (unconfirmed collection scenario)",
                             f"receivable:{rid}"))
            assumed_amount += estimate.amount
            assumed_count += 1
        else:
            scen = move_flow(scen, f"receivable:{rid}", new_day)
    scen = scen + ci.line_flows("green_only" if hold_yellow else "nigraan")
    pb, ps = ci.project(base_flows), ci.project(scen)
    return {
        "base": proj_payload(pb, with_days=True), "scenario": proj_payload(ps, with_days=True),
        "delta": {"low_point_change": ps.low_point - pb.low_point,
                  "breach_before": pb.first_breach.isoformat() if pb.first_breach else None,
                  "breach_after": ps.first_breach.isoformat() if ps.first_breach else None,
                  "total_in_change": ps.total_in - pb.total_in,
                  "unconfirmed_receipts_assumed_amount": assumed_amount,
                  "unconfirmed_receipts_assumed_count": assumed_count},
    }


runtime.late_risk_cached = {}
_ = drop_flows  # re-exported for scenario extensions
