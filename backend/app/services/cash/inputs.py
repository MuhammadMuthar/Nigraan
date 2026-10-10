"""Turn ledger tables (pandas) into cash-engine flows. Shared by the app, the generator and the backtest.

Expected collection date (deterministic baseline, section 7.2):
  due_date + the customer's median prior delay (global median if < 5 settled invoices).
  Overdue beyond the usual delay -> no defensible collection date; excluded from base cash.
  The legacy next-week policy is retained explicitly for reproducing the original backtest.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.services.calendar_pk import next_business_day
from app.services.cash.engine import Flow

MIN_HISTORY = 5
STALE_DAYS = 7


@dataclass
class ReceiptEstimate:
    receivable_id: int
    customer_id: int
    amount: int
    disputed: int
    due_date: date
    expected_date: date | None
    basis: str
    overdue_days: int
    median_delay: float
    limited_history: bool
    settled_count: int
    note: str

    @property
    def included_in_base(self) -> bool:
        return self.expected_date is not None


def _d(x) -> date:
    return x if isinstance(x, date) else pd.Timestamp(x).date()


def customer_delay_stats(receivables: pd.DataFrame, as_of: date) -> tuple[dict[int, tuple[float, int, float]], tuple[float, float]]:
    """(median delay, settled count, 80th-percentile delay) per customer, from invoices settled before as_of."""
    r = receivables
    paid = pd.to_datetime(r["paid_date"])
    settled = r[paid.notna() & (paid < pd.Timestamp(as_of))].copy()
    if settled.empty:
        return {}, (0.0, 0.0)
    settled["delay"] = (pd.to_datetime(settled["paid_date"]) - pd.to_datetime(settled["due_date"])).dt.days
    g = settled.groupby("customer_id")["delay"]
    med, cnt, p80 = g.median(), g.count(), g.quantile(0.8)
    stats = {int(c): (float(med[c]), int(cnt[c]), float(p80[c])) for c in med.index}
    return stats, (float(settled["delay"].median()), float(settled["delay"].quantile(0.8)))


def open_receivables(receivables: pd.DataFrame, as_of: date) -> pd.DataFrame:
    r = receivables
    issue = pd.to_datetime(r["issue_date"])
    paid = pd.to_datetime(r["paid_date"])
    mask = (issue < pd.Timestamp(as_of)) & (paid.isna() | (paid >= pd.Timestamp(as_of)))
    return r[mask]


def estimate_receipts(receivables: pd.DataFrame, as_of: date, *, include_disputed: bool = False,
                      method: str = "median_delay", stale_policy: str = "exclude_unconfirmed") -> list[ReceiptEstimate]:
    if stale_policy not in ("exclude_unconfirmed", "legacy_next_week"):
        raise ValueError(f"unknown stale-receipt policy: {stale_policy}")
    stats, (global_median, global_p80) = customer_delay_stats(receivables, as_of)
    out: list[ReceiptEstimate] = []
    for row in open_receivables(receivables, as_of).itertuples(index=False):
        due = _d(row.due_date)
        med, n, p80 = stats.get(int(row.customer_id), (global_median, 0, global_p80))
        limited = n < MIN_HISTORY
        if limited:
            med, p80 = global_median, global_p80
        if method == "due_date":
            med = p80 = 0.0
        disputed = int(getattr(row, "disputed_amount", 0) or 0)
        amount = int(row.amount) - (0 if include_disputed else disputed)
        overdue = max(0, (as_of - due).days)
        base = due + timedelta(days=int(round(med)))
        slow = due + timedelta(days=int(round(max(med, p80))))
        basis, note = "estimate", ""
        if base >= as_of:
            exp = base
        elif due >= as_of:
            exp = as_of  # expected early / today
        elif slow >= as_of:
            exp = slow
            note = "Already later than this customer's median delay; using their slow-payer (80th percentile) delay"
        else:
            basis = "assumption"
            if stale_policy == "legacy_next_week":
                exp = as_of + timedelta(days=STALE_DAYS)
                note = "Legacy policy: overdue beyond usual delay; assumed next week"
            else:
                exp = None
                note = "Overdue beyond the historical median and slow-payer delay; collection date unconfirmed, excluded from base cash"
        exp = next_business_day(exp) if exp is not None else None
        out.append(ReceiptEstimate(int(row.id), int(row.customer_id), amount, disputed, due, exp, basis, overdue,
                                   float(med), limited, n, note))
    return out


def receipt_flows(estimates: list[ReceiptEstimate], customer_names: dict[int, str] | None = None) -> list[Flow]:
    names = customer_names or {}
    return [Flow(e.expected_date, e.amount, "receipt", e.basis,
                 f"{names.get(e.customer_id, 'Customer')} (receivable)", f"receivable:{e.receivable_id}")
            for e in estimates if e.amount > 0 and e.expected_date is not None]


def outflow_flows(scheduled: pd.DataFrame, as_of: date) -> list[Flow]:
    s = scheduled[pd.to_datetime(scheduled["due_date"]) >= pd.Timestamp(as_of)]
    return [Flow(_d(r.due_date), -int(r.amount), "outflow", r.basis if r.basis in ("fact", "assumption") else "fact",
                 r.name, f"outflow:{r.id}") for r in s.itertuples(index=False)]


def next_run_day(d: date) -> date:
    """Monday on or after d."""
    return d + timedelta(days=(7 - d.weekday()) % 7)


def payable_flows(invoices: pd.DataFrame, payments: pd.DataFrame, as_of: date,
                  exclude_invoice_ids: set[int] | None = None, vendor_names: dict[int, str] | None = None) -> list[Flow]:
    """Open vendor invoices not in the current run, paid in the weekly run that covers their due date."""
    exclude = exclude_invoice_ids or set()
    names = vendor_names or {}
    inv = invoices[(invoices["status"].isin(["received", "scheduled"])) & (~invoices["id"].isin(list(exclude)))]
    if inv.empty:
        return []
    paid = payments[payments["status"].isin(["released", "approved", "pending", "held"])].groupby("invoice_id")["amount"].sum()
    first_future_run = next_run_day(as_of + timedelta(days=1))
    flows = []
    for r in inv.itertuples(index=False):
        remaining = int(r.total) - int(paid.get(r.id, 0))
        if remaining <= 0:
            continue
        due = _d(r.due_date)
        run = due - timedelta(days=due.weekday())  # Monday of the due week
        day = max(first_future_run, run)
        flows.append(Flow(day, -remaining, "payable", "fact", f"{names.get(r.vendor_id, 'Vendor')} invoice {r.invoice_no}",
                          f"invoice:{r.id}"))
    return flows


def run_flows(lines: list[dict]) -> list[Flow]:
    """lines: dicts with id, amount, pay_date, label."""
    return [Flow(l["pay_date"], -int(l["amount"]), "run_payment", "fact", l["label"], f"payment:{l['id']}")
            for l in lines]


def weekly_actual_receipts(receivables: pd.DataFrame, ids: set[int], start: date, weeks: int) -> np.ndarray:
    out = np.zeros(weeks, dtype=np.int64)
    r = receivables[receivables["id"].isin(list(ids))]
    for row in r.itertuples(index=False):
        if row.paid_date is None or pd.isna(row.paid_date):
            continue
        k = (_d(row.paid_date) - start).days // 7
        if 0 <= k < weeks:
            out[k] += int(row.paid_amount if row.paid_amount is not None and not pd.isna(row.paid_amount) else row.amount)
    return out
