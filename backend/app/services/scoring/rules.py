"""Deterministic rule layer. Hard rules force red; soft rules set a floor."""
from __future__ import annotations

from dataclasses import dataclass, field

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
