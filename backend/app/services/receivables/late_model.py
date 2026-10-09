"""Late-payment model for customer receivables (section 7.1).

Target: receivable fully paid after its due date (0 grace days). Prediction moment: issue date.
Features use only the customer's history settled before the issue date.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import xgboost as xgb

from app.services.calendar_pk import near_eid

SEGMENTS = ["kiryana", "superstore", "wholesaler", "pharmacy"]
LATE_FEATURES = [
    "amount_log", "terms_days", "issue_month", "eid_period", "june_yearend", "prior_settled", "prior_late_frac",
    "prior_delay_median", "prior_delay_std", "recent_delay_trend", "days_since_last_payment", "open_at_issue",
    "overdue_at_issue", "tenure_days", "amount_vs_customer_median",
] + [f"seg_{s}" for s in SEGMENTS]
MIN_HISTORY = 5


def receivable_features(receivables: pd.DataFrame, customers: pd.DataFrame) -> pd.DataFrame:
    r = receivables.copy()
    for c in ("issue_date", "due_date", "paid_date"):
        r[c] = pd.to_datetime(r[c])
    cust = customers.set_index("id")
    rows = {}
    for cid, g in r.sort_values(["issue_date", "id"]).groupby("customer_id"):
        seg = cust.loc[cid, "segment"] if cid in cust.index else "kiryana"
        created = pd.Timestamp(cust.loc[cid, "created_at"]) if cid in cust.index else g["issue_date"].min()
        issue = g["issue_date"].values
        due = g["due_date"].values
        paid = g["paid_date"].values
        amt = g["amount"].values.astype(float)
        for i, rid in enumerate(g["id"].values):
            t = issue[i]
            settled = ~pd.isna(paid) & (paid < t)
            delays = ((paid[settled] - due[settled]) / np.timedelta64(1, "D")).astype(float)
            order = np.argsort(paid[settled])
            delays_sorted = delays[order]
            n = len(delays)
            prior_issued = issue < t
            open_at = prior_issued & (pd.isna(paid) | (paid >= t))
            f = {
                "amount_log": math.log10(max(amt[i] / 100, 1)),
                "terms_days": float((due[i] - t) / np.timedelta64(1, "D")),
                "issue_month": float(pd.Timestamp(t).month),
                "eid_period": float(near_eid(pd.Timestamp(due[i]).date(), before=20, after=12)),
                "june_yearend": float(pd.Timestamp(due[i]).month == 6),
                "prior_settled": float(n),
                "prior_late_frac": float((delays > 0).mean()) if n else np.nan,
                "prior_delay_median": float(np.median(delays)) if n else np.nan,
                "prior_delay_std": float(np.std(delays)) if n >= 2 else np.nan,
                "recent_delay_trend": float(np.mean(delays_sorted[-3:]) - np.median(delays)) if n >= 4 else np.nan,
                "days_since_last_payment": float((t - paid[settled].max()) / np.timedelta64(1, "D")) if n else np.nan,
                "open_at_issue": float(open_at.sum()),
                "overdue_at_issue": float((open_at & (due < t)).sum()),
                "tenure_days": float((pd.Timestamp(t) - created).days),
                "amount_vs_customer_median": float(amt[i] / np.median(amt[prior_issued])) if prior_issued.any() else np.nan,
            }
            for s in SEGMENTS:
                f[f"seg_{s}"] = float(seg == s)
            rows[int(rid)] = f
    X = pd.DataFrame.from_dict(rows, orient="index")[LATE_FEATURES].astype(float)
    return X.loc[[int(i) for i in receivables["id"].values]]


def late_labels(receivables: pd.DataFrame, data_end) -> pd.Series:
    """1 = paid after due date (or still unpaid past due at data_end), 0 = on time, NaN = not yet known."""
    r = receivables
    paid = pd.to_datetime(r["paid_date"])
    due = pd.to_datetime(r["due_date"])
    end = pd.Timestamp(data_end)
    y = pd.Series(np.nan, index=r["id"].values)
    known_paid = paid.notna()
    y[known_paid.values] = (paid[known_paid] > due[known_paid]).astype(float).values
    unpaid_late = paid.isna() & (due < end)
    y[unpaid_late.values] = 1.0
    return y


def predict(bundle: dict, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray | None]:
    kind = bundle["kind"]
    if kind == "baseline":
        return np.full(len(X), bundle["base_rate"]), None
    if kind == "xgb":
        d = xgb.DMatrix(X[LATE_FEATURES].values, feature_names=LATE_FEATURES, missing=np.nan)
        return bundle["model"].predict(d), bundle["model"].predict(d, pred_contribs=True)
    model = bundle["model"]  # sklearn pipeline (imputer, scaler, LR)
    p = model.predict_proba(X[LATE_FEATURES])[:, 1]
    Z = model[:-1].transform(X[LATE_FEATURES])
    coef = model[-1].coef_[0]
    contrib = Z * coef
    contrib = np.hstack([contrib[:, : len(LATE_FEATURES)], np.zeros((len(X), 1))])
    return p, contrib


def late_reason(name: str, v: float, f: dict) -> str | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    n = int(f.get("prior_settled") or 0)
    if name == "prior_late_frac" and n:
        return f"Paid {round(v * n)} of {n} past invoices late"
    if name == "prior_delay_median":
        return f"Usually pays {v:.0f} days after the due date" if v > 0 else None
    if name == "recent_delay_trend":
        return f"Paying later recently (+{v:.0f} days vs usual)" if v > 3 else None
    if name == "eid_period":
        return "Due around Eid (slower collections)" if v else None
    if name == "june_yearend":
        return "Due in June year-end crunch" if v else None
    if name == "overdue_at_issue":
        return f"{v:.0f} invoice{'s' if v != 1 else ''} already overdue when this was issued" if v >= 1 else None
    if name == "open_at_issue":
        return f"{v:.0f} unpaid invoices open at issue" if v >= 3 else None
    if name == "days_since_last_payment":
        return f"No payment received for {v:.0f} days before issue" if v >= 30 else None
    if name == "amount_vs_customer_median":
        return f"Invoice is {v:.1f}× this customer's usual size" if v >= 1.5 else None
    if name == "terms_days":
        return f"Long credit terms ({v:.0f} days)" if v >= 45 else None
    if name == "prior_settled":
        return "Little payment history" if v < MIN_HISTORY else None
    if name == "tenure_days":
        return f"New customer ({v:.0f} days)" if v < 120 else None
    return None


def top_late_reasons(contrib_row: np.ndarray | None, feats: dict, k: int = 3) -> list[str]:
    if contrib_row is None:
        return []
    pairs = sorted(zip(LATE_FEATURES, contrib_row[: len(LATE_FEATURES)]), key=lambda kv: -kv[1])
    out = []
    for name, c in pairs:
        if c <= 0.02:
            break
        t = late_reason(name, feats.get(name), feats)
        if t and t not in out:
            out.append(t)
        if len(out) == k:
            break
    return out
