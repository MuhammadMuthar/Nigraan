"""Per-payment behaviour features (section 6.3).

Every feature is computed only from rows dated strictly before the payment's created_at
(the prediction moment). tests/test_leakage.py proves it by truncating the ledger.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.services.calendar_pk import PKT_OFFSET, is_off_day
from app.services.ledger import Ledger

DAY_NS = 86_400 * 10**9

FEATURES = [
    "amount_log", "amount_vs_vendor_median", "amount_vendor_z", "unit_price_vs_median_max",
    "unit_price_vs_vendor_last",
    "days_since_bank_change", "account_changed", "first_payment_to_account", "changer_prior_edits",
    "changer_edit_share", "change_unverified", "vendor_age_days", "vendor_prior_invoices", "is_round_amount",
    "vendor_round_share", "no_sales_tax", "same_payee_48h", "same_payee_48h_vs_limit", "limit_gap",
    "creator_can_approve", "entry_hour", "is_night", "off_day", "vague_line_share", "line_count",
    "days_receipt_to_payment", "days_to_due",
]

# Isolation Forest sees a compact, imputed subset.
ISO_FEATURES = [
    "amount_vs_vendor_median", "unit_price_vs_median_max", "days_since_bank_change", "first_payment_to_account",
    "vendor_age_days", "same_payee_48h", "limit_gap", "is_night", "off_day", "vague_line_share",
    "is_round_amount", "days_receipt_to_payment", "changer_edit_share", "creator_can_approve",
]
ISO_IMPUTE = {"amount_vs_vendor_median": 1.0, "unit_price_vs_median_max": 1.0, "changer_edit_share": 0.5}

VAGUE_RE = re.compile(
    r"\b(consult\w*|misc\w*|professional services|advisory|coordination|service charges|supply of goods|survey)\b",
    re.I)

_EMPTY = (np.array([], dtype=np.int64), np.array([], dtype=float), np.array([], dtype=np.int64))


def _ns(ts) -> int:
    return pd.Timestamp(ts).value


@dataclass
class _Acct:
    vendor_id: int
    valid_from: int
    changed_by: int | None
    change_source: str
    blocked_at: int | None


class FeatureContext:
    """Indexes over a Ledger so per-payment features are O(log n)."""

    def __init__(self, L: Ledger):
        self.L = L
        self.limit = int(L.company["approval_limit"])
        self.user_role = dict(zip(L.users["id"], L.users["role"]))

        pays = L.payments.sort_values(["created_at", "id"])
        ok = pays[~pays["status"].isin(["blocked", "rejected"])]
        self.vendor_pay: dict[int, tuple] = {}
        for vid, g in ok.groupby("vendor_id"):
            self.vendor_pay[int(vid)] = (g["created_at"].values.astype("int64"), g["amount"].values.astype(float),
                                         g["id"].values.astype(np.int64))
        self.acct_pay: dict[int, np.ndarray] = {}
        for aid, g in ok.groupby("bank_account_id"):
            self.acct_pay[int(aid)] = g["created_at"].values.astype("int64")
        self.pay_by_id = pays.set_index("id")

        self.acct: dict[int, _Acct] = {}
        for a in L.accounts.itertuples(index=False):
            self.acct[int(a.id)] = _Acct(int(a.vendor_id), _ns(a.valid_from),
                                         None if pd.isna(a.changed_by) else int(a.changed_by), a.change_source,
                                         None if pd.isna(a.blocked_at) else _ns(a.blocked_at))
        edits = []
        for v in L.vendors.itertuples(index=False):
            if not pd.isna(v.created_by):
                edits.append((_ns(v.created_at), int(v.created_by)))
        for a in L.accounts.itertuples(index=False):
            if a.change_source != "onboarding" and not pd.isna(a.changed_by):
                edits.append((_ns(a.valid_from), int(a.changed_by)))
        edits.sort()
        self.edit_all = np.array([e[0] for e in edits], dtype=np.int64)
        by_user = defaultdict(list)
        for t, u in edits:
            by_user[u].append(t)
        self.edit_by_user = {u: np.array(ts, dtype=np.int64) for u, ts in by_user.items()}

        self.vendors = L.vendors.set_index("id")
        self.vendor_created = {int(i): _ns(t) for i, t in zip(L.vendors["id"], L.vendors["created_at"])}
        inv = L.invoices.copy()
        inv["is_round"] = (inv["total"] % 100_000 == 0).astype(int)
        self.inv = inv.set_index("id")
        self.vendor_inv: dict[int, tuple] = {}
        for vid, g in inv.sort_values("received_at").groupby("vendor_id"):
            self.vendor_inv[int(vid)] = (g["received_at"].values.astype("int64"), g["is_round"].values.astype(float),
                                         g["id"].values.astype(np.int64))
        lines = L.lines.merge(inv[["id", "received_at"]].rename(columns={"id": "invoice_id"}), on="invoice_id")
        self.lines_by_invoice: dict[int, list[tuple]] = defaultdict(list)
        for l in lines.itertuples(index=False):
            self.lines_by_invoice[int(l.invoice_id)].append(
                (None if pd.isna(l.item_id) else int(l.item_id), float(l.unit_price), str(l.description)))
        self.item_hist: dict[int, tuple] = {}
        li = lines[lines["item_id"].notna()].sort_values("received_at")
        for iid, g in li.groupby("item_id"):
            self.item_hist[int(iid)] = (g["received_at"].values.astype("int64"), g["unit_price"].values.astype(float),
                                        g["invoice_id"].values.astype(np.int64))
        li = li.merge(inv[["id", "vendor_id"]].rename(columns={"id": "invoice_id"}), on="invoice_id")
        self.vendor_item_hist: dict[tuple, tuple] = {}
        for (vid, iid), g in li.groupby(["vendor_id", "item_id"]):
            self.vendor_item_hist[(int(vid), int(iid))] = (g["received_at"].values.astype("int64"),
                                                           g["unit_price"].values.astype(float),
                                                           g["invoice_id"].values.astype(np.int64))

    # ------------------------------------------------------------------
    def features_for(self, pid: int) -> dict:
        p = self.pay_by_id.loc[pid]
        t = _ns(p["created_at"])
        vid, amount = int(p["vendor_id"]), float(p["amount"])
        inv_id = int(p["invoice_id"])
        inv = self.inv.loc[inv_id]
        f: dict[str, float] = {}

        f["amount_log"] = math.log10(max(amount / 100, 1.0))
        times, amts, ids = self.vendor_pay.get(vid, _EMPTY)
        k = int(np.searchsorted(times, t, side="left"))
        prior = amts[:k]
        if len(prior) >= 3:
            med = float(np.median(prior))
            f["amount_vs_vendor_median"] = amount / med if med > 0 else np.nan
            sd = float(np.std(prior))
            f["amount_vendor_z"] = (amount - float(np.mean(prior))) / sd if sd > 0 else 0.0
        else:
            f["amount_vs_vendor_median"] = np.nan
            f["amount_vendor_z"] = np.nan
        k48 = int(np.searchsorted(times, t - 2 * DAY_NS, side="left"))
        f["same_payee_48h"] = float(k - k48)
        f["same_payee_48h_vs_limit"] = (float(amts[k48:k].sum()) + amount) / self.limit

        # unit price vs 90-day item median (other invoices only)
        ratios = []
        for item_id, price, _ in self.lines_by_invoice.get(inv_id, []):
            if item_id is None or item_id not in self.item_hist:
                continue
            ht, hp, hinv = self.item_hist[item_id]
            lo = int(np.searchsorted(ht, t - 90 * DAY_NS, side="left"))
            hi = int(np.searchsorted(ht, t, side="left"))
            sel = hp[lo:hi][hinv[lo:hi] != inv_id]
            if len(sel) >= 3:
                ratios.append(price / float(np.median(sel)))
        f["unit_price_vs_median_max"] = max(ratios) if ratios else np.nan
        # same vendor, same item: price vs the vendor's own last price before this payment
        vr = []
        for item_id, price, _ in self.lines_by_invoice.get(inv_id, []):
            h = self.vendor_item_hist.get((vid, item_id)) if item_id is not None else None
            if h is None:
                continue
            ht, hp, hinv = h
            hi = int(np.searchsorted(ht, t, side="left"))
            sel = hp[:hi][hinv[:hi] != inv_id]
            if len(sel):
                vr.append(price / float(sel[-1]))
        f["unit_price_vs_vendor_last"] = max(vr) if vr else np.nan

        acc = self.acct[int(p["bank_account_id"])]
        f["days_since_bank_change"] = max(0.0, (t - acc.valid_from) / DAY_NS)
        f["account_changed"] = float(acc.change_source != "onboarding")
        ap = self.acct_pay.get(int(p["bank_account_id"]), np.array([], dtype=np.int64))
        f["first_payment_to_account"] = float(int(np.searchsorted(ap, t, side="left")) == 0)
        changer = acc.changed_by
        n_all = int(np.searchsorted(self.edit_all, acc.valid_from, side="left"))
        if changer is not None:
            mine = self.edit_by_user.get(changer, np.array([], dtype=np.int64))
            n_mine = int(np.searchsorted(mine, acc.valid_from, side="left"))
            f["changer_prior_edits"] = float(n_mine)
            f["changer_edit_share"] = n_mine / n_all if n_all > 0 else np.nan
        else:
            f["changer_prior_edits"] = np.nan
            f["changer_edit_share"] = np.nan
        f["change_unverified"] = float(acc.change_source in ("email", "phone"))

        f["vendor_age_days"] = max(0.0, (t - self.vendor_created[vid]) / DAY_NS)
        vt, vround, vids = self.vendor_inv.get(vid, _EMPTY)
        kv = int(np.searchsorted(vt, t, side="left"))
        prior_mask = vids[:kv] != inv_id
        n_prior_inv = int(prior_mask.sum())
        f["vendor_prior_invoices"] = float(n_prior_inv)
        is_round = float(int(inv["total"]) % 100_000 == 0)
        f["is_round_amount"] = is_round
        f["vendor_round_share"] = (float(vround[:kv][prior_mask].sum()) + is_round) / (n_prior_inv + 1)
        f["no_sales_tax"] = float(int(inv["tax"]) == 0)
        f["limit_gap"] = (self.limit - amount) / self.limit

        creator = p["created_by"]
        role = self.user_role.get(int(creator)) if not pd.isna(creator) else None
        f["creator_can_approve"] = float(role in ("approver", "owner"))
        local = pd.Timestamp(p["created_at"]) + PKT_OFFSET
        hour = local.hour + local.minute / 60
        f["entry_hour"] = hour
        f["is_night"] = float(hour >= 22 or hour < 6)
        f["off_day"] = float(is_off_day(local.date()))

        lines = self.lines_by_invoice.get(inv_id, [])
        f["line_count"] = float(len(lines))
        f["vague_line_share"] = (sum(1 for _, _, d in lines if VAGUE_RE.search(d)) / len(lines)) if lines else 0.0
        f["days_receipt_to_payment"] = (t - _ns(inv["received_at"])) / DAY_NS
        f["days_to_due"] = float((pd.Timestamp(inv["due_date"]).date() - local.date()).days)
        return f

    def frame(self, payment_ids) -> pd.DataFrame:
        rows = [self.features_for(int(pid)) for pid in payment_ids]
        return pd.DataFrame(rows, columns=FEATURES, index=list(payment_ids)).astype(float)


def iso_matrix(X: pd.DataFrame) -> np.ndarray:
    Z = X[ISO_FEATURES].copy()
    for c in ISO_FEATURES:
        Z[c] = Z[c].fillna(ISO_IMPUTE.get(c, 0.0))
    Z["days_since_bank_change"] = np.log1p(Z["days_since_bank_change"])
    Z["vendor_age_days"] = np.log1p(Z["vendor_age_days"])
    Z["amount_vs_vendor_median"] = np.log(np.clip(Z["amount_vs_vendor_median"], 0.05, 50))
    Z["unit_price_vs_median_max"] = np.log(np.clip(Z["unit_price_vs_median_max"], 0.05, 50))
    Z["days_receipt_to_payment"] = np.log1p(np.clip(Z["days_receipt_to_payment"], 0, None))
    return Z.values
