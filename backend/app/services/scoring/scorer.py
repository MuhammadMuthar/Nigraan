"""Scores payment lines: rules -> duplicate check -> risk model -> anomaly -> graph -> fusion -> decision.

Every step is timed and recorded in the trace so the UI can show the AI working.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.money import fmt_rs
from app.services.ledger import Ledger
from app.services.scoring import rules as R
from app.services.scoring.duplicates import DupIndex
from app.services.scoring.features import FEATURES, FeatureContext
from app.services.scoring.fuse import decision_for, fuse
from app.services.scoring.graph import RelationGraph
from app.services.scoring.reasons import top_feature_reasons
from app.services.scoring.risk import ModelBundle, iso_signal, xgb_predict

FRAUD_TYPES = {
    "F1": "Duplicate invoice", "F2": "Bank-detail change", "F3": "Shell vendor", "F4": "Inflated price",
    "F5": "Split payment", "F7": "Out-of-hours payment", "ANOMALY": "Unusual payment",
}
FEATURE_TYPE = {
    "days_since_bank_change": "F2", "account_changed": "F2", "first_payment_to_account": "F2",
    "changer_prior_edits": "F2", "changer_edit_share": "F2", "change_unverified": "F2",
    "unit_price_vs_median_max": "F4", "unit_price_vs_vendor_last": "F4", "same_payee_48h": "F5", "same_payee_48h_vs_limit": "F5", "limit_gap": "F5",
    "is_night": "F7", "off_day": "F7", "entry_hour": "F7",
    "vague_line_share": "F3", "is_round_amount": "F3", "vendor_round_share": "F3", "no_sales_tax": "F3",
    "vendor_age_days": "F3", "vendor_prior_invoices": "F3",
}


def suspected_type(reasons: list[dict], decision: str, features: dict | None = None) -> str | None:
    """Name the evidence shown to the reviewer, rather than unseen SHAP drivers.

    A short invoice-to-payment interval or an approver's role alone does not establish
    an out-of-hours pattern. Bank-account age alone may describe onboarding, not a change.
    The UI calls this a *suspected* pattern; it is never a confirmed fraud label.
    """
    if decision == "allow":
        return None
    features = features or {}
    shown = [r for r in reasons if r.get("engine") != "info" and not r.get("weak")][:4]
    for reason in shown:
        if reason.get("code") == "DUP_EXACT" or reason.get("engine") == "duplicate":
            return "F1"
        if reason.get("code") == "SPLIT_PAYMENT":
            return "F5"
        if reason.get("engine") == "graph":
            return "F3"
        feature = reason.get("feature")
        kind = FEATURE_TYPE.get(feature)
        if kind == "F2" and feature in ("days_since_bank_change", "first_payment_to_account",
                                       "changer_prior_edits", "changer_edit_share"):
            if not features.get("account_changed"):
                continue
        if kind:
            return kind
    return "ANOMALY"


@dataclass
class ScoreResult:
    payment_id: int
    score: int
    decision: str
    raw: float
    signals: dict
    contributions: dict
    reasons: list[dict]
    evidence: dict
    trace: list[dict]
    model_version: str
    fraud_type: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class ScoringContext:
    ledger: Ledger
    features: FeatureContext
    dups: DupIndex
    graph: RelationGraph
    build_ms: float


class Scorer:
    def __init__(self, bundle: ModelBundle):
        self.b = bundle

    def prepare(self, L: Ledger) -> ScoringContext:
        t0 = time.perf_counter()
        fc = FeatureContext(L)
        dups = DupIndex(L, self.b.tfidf)
        g = RelationGraph(L)
        return ScoringContext(L, fc, dups, g, (time.perf_counter() - t0) * 1000)

    # ------------------------------------------------------------------
    def score(self, ctx: ScoringContext, payment_ids: list[int]) -> list[ScoreResult]:
        n = max(1, len(payment_ids))
        t0 = time.perf_counter()
        X = ctx.features.frame(payment_ids)
        feat_ms = (time.perf_counter() - t0) * 1000 / n
        if self.b.has_ml:
            t0 = time.perf_counter()
            p_xgb, contrib = xgb_predict(self.b.xgb, X)
            xgb_ms = (time.perf_counter() - t0) * 1000 / n
            t0 = time.perf_counter()
            a_iso = iso_signal(self.b.iso, self.b.iso_q, X)
            iso_ms = (time.perf_counter() - t0) * 1000 / n
        else:
            p_xgb = np.zeros(n)
            contrib = np.zeros((n, len(FEATURES) + 1))
            a_iso = np.zeros(n)
            xgb_ms = iso_ms = 0.0
        out = []
        for i, pid in enumerate(payment_ids):
            out.append(self._one(ctx, int(pid), X.iloc[i].to_dict(), float(p_xgb[i]), contrib[i], float(a_iso[i]),
                                 feat_ms, xgb_ms, iso_ms))
        return out

    def _one(self, ctx: ScoringContext, pid: int, feats: dict, p_xgb: float, contrib: np.ndarray, a_iso: float,
             feat_ms: float, xgb_ms: float, iso_ms: float) -> ScoreResult:
        fc = ctx.features
        p = fc.pay_by_id.loc[pid]
        inv_id = int(p["invoice_id"])
        t_pay = pd.Timestamp(p["created_at"])
        trace = [{"step": "context", "label": "Load ledger history (only data before this payment)",
                  "ms": round(ctx.build_ms, 1), "detail": f"{len(fc.pay_by_id)} payments, {len(fc.inv)} invoices indexed"}]

        t0 = time.perf_counter()
        dup = ctx.dups.score(inv_id, self.b.dup_lr)
        dup_ms = (time.perf_counter() - t0) * 1000
        trace.append({"step": "duplicate_check", "label": "Duplicate detector (logistic regression on pair features)",
                      "ms": round(dup_ms, 1),
                      "detail": f"{dup.n_candidates} candidate invoice(s); best match p={dup.prob:.2f}"
                                + (f" (invoice #{dup.match_invoice_id})" if dup.match_invoice_id else "")})

        t0 = time.perf_counter()
        rr = R.evaluate(fc, pid, dup)
        trace.append({"step": "rules", "label": "Rule layer (hard rules force red)",
                      "ms": round((time.perf_counter() - t0) * 1000, 1),
                      "detail": "; ".join(h.code for h in rr.hits) or "no rule fired"})

        trace.append({"step": "features", "label": f"Behaviour features ({len(FEATURES)}, leakage-safe)", "ms": round(feat_ms, 1),
                      "detail": "amount vs vendor median, bank change age, approval-limit gap, entry time, ..."})
        names = FEATURES
        contribs = {names[j]: float(contrib[j]) for j in range(len(names))}
        top = top_feature_reasons(contribs, feats) if self.b.has_ml else []
        trace.append({"step": "risk_model", "label": "XGBoost risk model + SHAP reasons", "ms": round(xgb_ms, 2),
                      "detail": f"p(fraud)={p_xgb:.3f}" if self.b.has_ml else "model not loaded (rules-only mode)"})
        trace.append({"step": "anomaly", "label": "Isolation Forest (unseen patterns)", "ms": round(iso_ms, 2),
                      "detail": f"anomaly signal={a_iso:.2f}" if self.b.has_ml else "model not loaded"})

        t0 = time.perf_counter()
        gr = ctx.graph.links_for(int(p["vendor_id"]), t_pay.value)
        trace.append({"step": "graph", "label": "Deterministic relationship checks (vendors, employees, banks, phones, addresses)",
                      "ms": round((time.perf_counter() - t0) * 1000, 1),
                      "detail": gr.links[0]["text"] if gr.links else "no shared identifiers"})

        signals = {"risk_model": p_xgb, "anomaly": a_iso, "duplicate": dup.prob, "graph": gr.signal}
        t0 = time.perf_counter()
        score, raw, contributions = fuse(signals, rr.hit, self.b.fusion)
        decision = decision_for(score)
        w = self.b.fusion["weights"]
        trace.append({"step": "fusion", "label": "Fusion: max(100 x rule, calibrated weighted signals: " + " + ".join(
            f"{w[e]:.2f}·{e}" for e in ("risk_model", "anomaly", "duplicate", "graph")) + ")",
                      "ms": round((time.perf_counter() - t0) * 1000, 2),
                      "detail": f"raw={raw:.3f}, calibrated at raw {self.b.fusion['t_yellow']:.3f} -> 40 and {self.b.fusion['t_red']:.3f} -> 75; rule={rr.hit:.1f} -> score {score}"})
        trace.append({"step": "decision", "label": "Decision", "ms": 0.0,
                      "detail": {"allow": "Allow (green)", "review": "Review: second approver required (yellow)",
                                 "blocked": "Blocked: cannot be released; case opened (red)"}[decision]})

        # ---- reasons, most explanatory first: hard rules, duplicate, graph, soft rules, model, anomaly
        reasons: list[dict] = []
        for h in rr.hits:
            reasons.append({"engine": "rules", "text": h.text, "weight": 1.0 if h.hard else R.SPLIT_FLOOR,
                            "code": h.code, "priority": 0 if h.hard else 3})
        ev_dup = None
        if dup.match_invoice_id is not None:
            m = fc.inv.loc[dup.match_invoice_id]
            this = fc.inv.loc[inv_id]
            ev_dup = {
                "prob": round(dup.prob, 3), "hard": dup.hard, "features": {k: round(v, 3) for k, v in dup.features.items()},
                "this": _inv_summary(ctx, inv_id, this), "match": _inv_summary(ctx, dup.match_invoice_id, m),
            }
            if dup.prob >= 0.25 and not dup.hard:
                f = dup.features
                lead = "Looks like a duplicate of" if dup.prob >= 0.5 else "Similar to earlier invoice"
                reasons.append({"engine": "duplicate", "weight": contributions["duplicate"], "priority": 1, "text": (
                    f"{lead} {m['invoice_no']} ({pd.Timestamp(m['invoice_date']):%d %b}): "
                    + ("same number once zeros/dashes are removed" if f["num_exact"] else f"number {f['num_sim']:.0%} similar")
                    + f", {f['date_gap']:.0f} days apart, amount differs {f['amount_diff_pct']:.1f}%")})
        if gr.signal >= 0.3:
            reasons.append({"engine": "graph", "weight": contributions["graph"], "text": gr.links[0]["text"], "priority": 2})
        elif gr.links and gr.links[0].get("disclosed"):
            rr.info.append(gr.links[0]["text"])
        for r in top:
            reasons.append({"engine": "risk_model", "weight": contributions["risk_model"], "text": r["text"],
                            "feature": r["feature"], "contribution": r["contribution"], "priority": 4})
        if a_iso >= 0.5:
            reasons.append({"engine": "anomaly", "weight": contributions["anomaly"], "priority": 5,
                            "text": "Unusual combination compared with all past payments (anomaly detector)"})
        reasons.sort(key=lambda r: (r["priority"], -r["weight"]))
        if decision == "allow" and score < 20:
            reasons = [dict(r, weak=True) for r in reasons]
        for r in rr.info:
            reasons.append({"engine": "info", "weight": 0.0, "text": r, "priority": 9})

        ftype = suspected_type(reasons, decision, feats)

        acc = ctx.ledger.accounts
        vid = int(p["vendor_id"])
        hist = acc[acc["vendor_id"] == vid].sort_values("valid_from")
        users = dict(zip(ctx.ledger.users["id"], ctx.ledger.users["name"]))
        bank = {
            "account_id": int(p["bank_account_id"]),
            "history": [{
                "id": int(a.id), "bank": a.bank_name, "last4": a.iban_last4,
                "valid_from": pd.Timestamp(a.valid_from).isoformat(),
                "valid_to": None if pd.isna(a.valid_to) else pd.Timestamp(a.valid_to).isoformat(),
                "changed_by": users.get(None if pd.isna(a.changed_by) else int(a.changed_by)),
                "approved_by": users.get(None if pd.isna(a.approved_by) else int(a.approved_by)),
                "source": a.change_source, "blocked": bool(a.is_blocked),
                "current_for_payment": int(a.id) == int(p["bank_account_id"]),
            } for a in hist.itertuples(index=False) if pd.Timestamp(a.valid_from) <= t_pay],
        }
        evidence = {
            "duplicate": ev_dup,
            "graph": {"signal": gr.signal, "links": gr.links, "path": gr.path},
            "bank": bank,
            "rules": [{"code": h.code, "text": h.text, "hard": h.hard} for h in rr.hits] + [
                {"code": "INFO", "text": t, "hard": False} for t in rr.info],
            "risk_model": {"p": round(p_xgb, 4), "top": top,
                           "contributions": {k: round(v, 3) for k, v in sorted(contribs.items(), key=lambda kv: -abs(kv[1]))[:10]}},
            "anomaly": {"signal": round(a_iso, 3)},
            "features": {k: (None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), 3))
                         for k, v in feats.items()},
            "rules_comparison": R.comparison_for(ctx.features, pid, feats, rr.hits, gr.signal),
        }
        return ScoreResult(pid, score, decision, raw, {k: round(float(v), 4) for k, v in signals.items()},
                           {k: round(float(v), 4) for k, v in contributions.items()}, reasons, evidence, trace,
                           self.b.version, ftype)


def _inv_summary(ctx: ScoringContext, inv_id: int, row) -> dict:
    vendors = dict(zip(ctx.ledger.vendors["id"], ctx.ledger.vendors["name"]))
    paid = ctx.features.pay_by_id
    pays = paid[paid["invoice_id"] == inv_id]
    status = "paid" if (pays["status"] == "released").any() else ("in a payment run" if len(pays) else "not yet paid")
    return {
        "id": int(inv_id), "invoice_no": str(row["invoice_no"]), "vendor": vendors.get(int(row["vendor_id"])),
        "invoice_date": pd.Timestamp(row["invoice_date"]).date().isoformat(),
        "received_at": pd.Timestamp(row["received_at"]).isoformat(), "total": int(row["total"]),
        "total_fmt": fmt_rs(int(row["total"])), "status": status,
        "lines": [{"description": d, "qty": q, "unit_price": int(pr)} for d, q, pr in ctx.dups.lines.get(int(inv_id), [])],
    }
