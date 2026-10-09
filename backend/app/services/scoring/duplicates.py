"""Duplicate / near-duplicate invoice detector (section 6.2).

Candidates: invoices received *before* this one, from the same or a fuzzy-matched vendor,
invoice date within +-90 days and total within +-2%. Pair features feed a logistic regression
trained on confirmed F1 cases. Hard rule: same vendor + same normalised number + same total = 1.0.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from rapidfuzz import fuzz

from app.services.ledger import Ledger

PAIR_FEATURES = ["num_sim", "num_exact", "num_seq_gap", "date_gap", "amount_diff_pct", "line_jaccard", "text_cos"]
DATE_WINDOW_DAYS = 90
AMOUNT_TOL = 0.02
VENDOR_FUZZ = 90


def invoice_text(vendor_name: str, invoice_no: str, lines: list[tuple]) -> str:
    parts = [vendor_name, invoice_no]
    for desc, qty, price in lines:
        parts.append(f"{desc} x{qty:g} @{int(price) // 100}")
    return " | ".join(parts)


@dataclass
class DupResult:
    prob: float = 0.0
    match_invoice_id: int | None = None
    hard: bool = False
    features: dict = field(default_factory=dict)
    n_candidates: int = 0


class DupIndex:
    def __init__(self, L: Ledger, vectorizer=None):
        self.vectorizer = vectorizer
        inv = L.invoices.copy()
        inv["rt"] = inv["received_at"].values.astype("int64")
        self.inv = inv.set_index("id")
        names = dict(zip(L.vendors["id"], L.vendors["name"]))
        self.vendor_name = names
        ids = list(names)
        self.vendor_group: dict[int, list[int]] = {}
        for a in ids:
            grp = [b for b in ids if b == a or fuzz.token_set_ratio(names[a], names[b]) >= VENDOR_FUZZ]
            self.vendor_group[int(a)] = [int(x) for x in grp]
        self.by_vendor: dict[int, pd.DataFrame] = {int(v): g.sort_values("rt") for v, g in self.inv.groupby("vendor_id")}
        self.lines: dict[int, list[tuple]] = {}
        for l in L.lines.itertuples(index=False):
            self.lines.setdefault(int(l.invoice_id), []).append((str(l.description), float(l.qty), float(l.unit_price)))
        self._vec_cache: dict[int, object] = {}

    def text(self, inv_id: int) -> str:
        row = self.inv.loc[inv_id]
        return invoice_text(self.vendor_name.get(int(row["vendor_id"]), ""), str(row["invoice_no"]),
                            self.lines.get(inv_id, []))

    def _vec(self, inv_id: int):
        if inv_id not in self._vec_cache:
            self._vec_cache[inv_id] = self.vectorizer.transform([self.text(inv_id)])
        return self._vec_cache[inv_id]

    def candidates(self, inv_id: int, cutoff_ns: int | None = None) -> list[int]:
        row = self.inv.loc[inv_id]
        cutoff = int(row["rt"]) if cutoff_ns is None else cutoff_ns
        total = float(row["total"])
        d0 = pd.Timestamp(row["invoice_date"])
        out = []
        for vid in self.vendor_group.get(int(row["vendor_id"]), [int(row["vendor_id"])]):
            g = self.by_vendor.get(vid)
            if g is None:
                continue
            k = int(np.searchsorted(g["rt"].values, cutoff, side="left"))
            prior = g.iloc[:k]
            if prior.empty:
                continue
            m = ((prior["total"] - total).abs() <= AMOUNT_TOL * max(total, 1.0)) & \
                ((prior["invoice_date"] - d0).abs() <= pd.Timedelta(days=DATE_WINDOW_DAYS))
            out.extend(int(i) for i in prior.index[m] if int(i) != inv_id)
        return out

    def pair_features(self, a: int, b: int) -> dict:
        A, B = self.inv.loc[a], self.inv.loc[b]
        na, nb = str(A["invoice_no_norm"]), str(B["invoice_no_norm"])
        la = {d for d, _, _ in self.lines.get(a, [])}
        lb = {d for d, _, _ in self.lines.get(b, [])}
        jac = len(la & lb) / len(la | lb) if (la | lb) else 0.0
        if self.vectorizer is not None:
            va, vb = self._vec(a), self._vec(b)
            cos = float((va @ vb.T).toarray()[0, 0])
        else:
            cos = jac
        ta, tb = float(A["total"]), float(B["total"])
        da, db = re.sub(r"\D", "", na), re.sub(r"\D", "", nb)
        # sequential numbers (1021 vs 1022) are distinct invoices; equal numeric parts are suspicious
        gap = math.log1p(abs(int(da[-9:]) - int(db[-9:]))) if da and db else 3.0
        return {
            "num_sim": fuzz.ratio(na, nb) / 100.0,
            "num_exact": float(na == nb and int(A["vendor_id"]) == int(B["vendor_id"])),
            "num_seq_gap": gap,
            "date_gap": float(abs((pd.Timestamp(A["invoice_date"]) - pd.Timestamp(B["invoice_date"])).days)),
            "amount_diff_pct": abs(ta - tb) / max(ta, tb, 1.0) * 100,
            "line_jaccard": jac,
            "text_cos": cos,
        }

    def score(self, inv_id: int, model=None, cutoff_ns: int | None = None) -> DupResult:
        cands = self.candidates(inv_id, cutoff_ns)
        if not cands:
            return DupResult()
        best = DupResult(n_candidates=len(cands))
        feats = [self.pair_features(inv_id, c) for c in cands]
        if model is not None:
            X = np.array([[f[k] for k in PAIR_FEATURES] for f in feats])
            probs = model.predict_proba(X)[:, 1]
        else:  # rules-only fallback: exact normalised number match
            probs = np.array([1.0 if f["num_exact"] and f["amount_diff_pct"] < 1 else 0.0 for f in feats])
        j = int(np.argmax(probs))
        best.prob = float(probs[j])
        best.match_invoice_id = cands[j]
        best.features = feats[j]
        for c, f in zip(cands, feats):
            if f["num_exact"] and f["amount_diff_pct"] == 0:
                best.hard, best.prob, best.match_invoice_id, best.features = True, 1.0, c, f
                break
        return best
