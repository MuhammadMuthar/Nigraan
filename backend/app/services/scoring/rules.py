"""Deterministic rule layer. Hard rules force red; soft rules set a floor."""
from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np
import pandas as pd

from app.money import fmt_rs
from app.services.scoring.duplicates import DupResult
from app.services.scoring.features import DAY_NS, FeatureContext

SPLIT_BAND = 0.85  # "just under the limit" = 85-100% of the approval limit
SPLIT_FLOOR = 0.6  # soft rule -> at least yellow


@dataclass
class RuleHit:
    code: str
    text: str
    hard: bool


@dataclass
class RuleResult:
    hit: float = 0.0
    hard: bool = False
    hits: list[RuleHit] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


def evaluate(ctx: FeatureContext, pid: int, dup: DupResult) -> RuleResult:
    p = ctx.pay_by_id.loc[pid]
    t = pd.Timestamp(p["created_at"]).value
    res = RuleResult()
    if dup.hard and dup.match_invoice_id is not None:
        m = ctx.inv.loc[dup.match_invoice_id]
        res.hits.append(RuleHit("DUP_EXACT", f"Exact duplicate of invoice {m['invoice_no']} already in the books "
                                             f"(same vendor, number and total)", True))
    v = ctx.vendors.loc[int(p["vendor_id"])]
    if not pd.isna(v["blocked_at"]) and pd.Timestamp(v["blocked_at"]).value <= t:
        res.hits.append(RuleHit("VENDOR_BLOCKED", "Vendor is blocked", True))
    acc = ctx.acct[int(p["bank_account_id"])]
    if acc.blocked_at is not None and acc.blocked_at <= t:
        res.hits.append(RuleHit("ACCOUNT_BLOCKED", "Bank account is blocked", True))

    amount = float(p["amount"])
    limit = ctx.limit
    if SPLIT_BAND * limit <= amount < limit:
        times, amts, ids = ctx.vendor_pay.get(int(p["vendor_id"]), (np.array([]), np.array([]), np.array([])))
        lo = int(np.searchsorted(times, t - 2 * DAY_NS, side="left"))
        hi = int(np.searchsorted(times, t + 2 * DAY_NS, side="right"))
        near = [(int(i), float(a)) for i, a in zip(ids[lo:hi], amts[lo:hi])
                if int(i) != pid and SPLIT_BAND * limit <= a < limit]
        # Backwards in time only, plus lines of the same run: the decision is taken at run review,
        # when every line of the run is already known.
        same_run = lambda i: not pd.isna(p["run_id"]) and ctx.pay_by_id.loc[i]["run_id"] == p["run_id"]  # noqa: E731
        near = [(i, a) for i, a in near if pd.Timestamp(ctx.pay_by_id.loc[i]["created_at"]).value <= t or same_run(i)]
        if near:
            combined = amount + sum(a for _, a in near)
            res.hits.append(RuleHit(
                "SPLIT_PAYMENT",
                f"Possible split: {len(near) + 1} payments to this vendor just under the "
                f"{fmt_rs(limit)} approval limit within 48 h (combined {fmt_rs(int(combined))})", False))
    if amount > limit:
        res.info.append(f"Above the {fmt_rs(limit)} approval limit: owner approval required")

    if any(h.hard for h in res.hits):
        res.hard, res.hit = True, 1.0
    elif res.hits:
        res.hit = SPLIT_FLOOR
    return res


def rules_only_baseline_flag(ctx: FeatureContext, pid: int) -> bool:
    """Section 10 baseline: exact duplicate invoice number (same vendor) OR amount over the approval limit."""
    p = ctx.pay_by_id.loc[pid]
    if float(p["amount"]) > ctx.limit:
        return True
    inv = ctx.inv.loc[int(p["invoice_id"])]
    same = ctx.inv[(ctx.inv["vendor_id"] == inv["vendor_id"]) & (ctx.inv["invoice_no_norm"] == inv["invoice_no_norm"])]
    same = same[(same.index != int(p["invoice_id"])) & (same["received_at"] < inv["received_at"])]
    return not same.empty


def comparison_for(ctx: FeatureContext, pid: int, feats: dict | None = None,
                   rule_hits: list | None = None, graph_signal: float | None = None) -> dict:
    """Two named, deterministic comparators; these never change payment decisions.

    Thresholds are explicit review heuristics, not fitted to the held-out labels. The
    expert comparator includes graph relationships and split exposure: neither is ML.
    Invoice age is deliberately excluded because it can be a synthetic-data shortcut.
    """
    p = ctx.pay_by_id.loc[pid]
    inv = ctx.inv.loc[int(p["invoice_id"])]
    f = feats if feats is not None else ctx.features_for(pid)
    simple: list[dict] = []
    if int(p["amount"]) > ctx.limit:
        simple.append({"code": "OVER_LIMIT", "text": f"Payment exceeds the {fmt_rs(ctx.limit)} approval limit"})
    prior = ctx.inv[(ctx.inv["vendor_id"] == inv["vendor_id"])
                    & (ctx.inv["invoice_no_norm"] == inv["invoice_no_norm"])
                    & (ctx.inv.index != int(p["invoice_id"]))
                    & (ctx.inv["received_at"] < inv["received_at"])]
    if not prior.empty:
        simple.append({"code": "REPEATED_NUMBER", "text": "Same vendor and normalized invoice number already in the ledger"})
    expert = list(simple)

    def present(name: str) -> bool:
        value = f.get(name)
        return value is not None and math.isfinite(float(value))

    def add(code: str, text: str) -> None:
        if not any(h["code"] == code for h in expert):
            expert.append({"code": code, "text": text})

    for hit in rule_hits or []:
        code = hit.get("code") if isinstance(hit, dict) else hit.code
        text = hit.get("text") if isinstance(hit, dict) else hit.text
        if code != "INFO":
            add(code, text)
    t = pd.Timestamp(p["created_at"]).value
    vendor = ctx.vendors.loc[int(p["vendor_id"])]
    if not pd.isna(vendor["blocked_at"]) and pd.Timestamp(vendor["blocked_at"]).value <= t:
        add("VENDOR_BLOCKED", "Vendor was blocked when the payment was entered")
    account = ctx.acct[int(p["bank_account_id"])]
    if account.blocked_at is not None and account.blocked_at <= t:
        add("ACCOUNT_BLOCKED", "Bank account was blocked when the payment was entered")
    if present("account_changed") and f["account_changed"] and present("days_since_bank_change") and f["days_since_bank_change"] <= 30:
        add("RECENT_BANK_CHANGE", "Bank details changed within 30 days of this payment")
    if (present("vendor_age_days") and f["vendor_age_days"] <= 30) or (present("vendor_prior_invoices") and f["vendor_prior_invoices"] == 0):
        add("NEW_VENDOR", "Vendor is at most 30 days old or has no previous invoices")
    if present("is_night") and f["is_night"]:
        add("NIGHT_ENTRY", "Payment entered between 10 PM and 6 AM Pakistan time")
    if any(present(name) and f[name] >= 1.3 for name in ("unit_price_vs_median_max", "unit_price_vs_vendor_last")):
        add("PRICE_INCREASE", "Item price is at least 1.3 times its historical median or the vendor's last price")
    if present("same_payee_48h") and f["same_payee_48h"] >= 1 and present("same_payee_48h_vs_limit") and f["same_payee_48h_vs_limit"] >= 1:
        add("COMBINED_EXPOSURE", "This vendor's payments in 48 hours reach the approval limit")
    if graph_signal is not None and graph_signal >= 0.7:
        add("EMPLOYEE_RELATIONSHIP", "Vendor has a strong, undisclosed shared identifier with an employee")
    return {"simple": {"name": "Simple rules", "flagged": bool(simple), "checks": simple},
            "expert": {"name": "Expert rules", "flagged": bool(expert), "checks": expert}}


def comparison_summary(lines: list[dict]) -> dict:
    """Amounts are exact stored paisa; flags describe review checks, not authorizations."""
    eligible = [line for line in lines if line.get("status") != "rejected" and line.get("rules_comparison")]
    out = {"evaluated_count": len(eligible),
           "note": "Deterministic comparison on these lines, not an accuracy measurement. A flag requires review; no flag does not authorize payment. Nigraan combines ML with rules and relationship checks."}
    for key, name in (("simple", "Simple rules"), ("expert", "Expert rules")):
        flagged = [line for line in eligible if line["rules_comparison"][key]["flagged"]]
        additional = [line for line in eligible if line.get("model_decision") in ("review", "blocked")
                      and not line["rules_comparison"][key]["flagged"]]
        out[key] = {"name": name, "flagged_count": len(flagged),
                    "flagged_amount": sum(int(line["amount"]) for line in flagged),
                    "nigraan_additional_count": len(additional),
                    "nigraan_additional_amount": sum(int(line["amount"]) for line in additional)}
    return out
