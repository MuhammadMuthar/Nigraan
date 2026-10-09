"""Shared helpers for training/evaluation: time windows, labels, engine signals."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from app.services.ledger import Ledger
from app.services.scoring import rules as R
from app.services.scoring.duplicates import DupIndex
from app.services.scoring.features import FeatureContext
from app.services.scoring.graph import RelationGraph

START = date(2025, 10, 1)


def month_of(ts) -> int:
    t = pd.Timestamp(ts)
    return (t.year - START.year) * 12 + t.month - START.month + 1


def months_mask(payments: pd.DataFrame, lo: int, hi: int) -> pd.Series:
    m = payments["created_at"].map(month_of)
    return (m >= lo) & (m <= hi)


def labels_from_cases(L: Ledger) -> pd.Series:
    """Training labels come only from resolved cases (historical audit + analyst decisions)."""
    c = L.cases
    conf = c[c["status"] == "confirmed_fraud"]
    lab = pd.Series(0, index=L.payments["id"].values)
    lab.loc[lab.index.isin(conf["payment_id"])] = 1
    return lab


def types_from_cases(L: Ledger) -> pd.Series:
    c = L.cases[L.cases["status"] == "confirmed_fraud"]
    return pd.Series(c["fraud_type"].values, index=c["payment_id"].values)


def dup_pairs(dups: DupIndex, invoice_ids, f1_invoices: set[int]) -> tuple[np.ndarray, np.ndarray]:
    """Pair features and labels. For a confirmed F1 invoice, its closest candidate (text cosine) is the positive."""
    from app.services.scoring.duplicates import PAIR_FEATURES

    X, y = [], []
    for inv_id in invoice_ids:
        cands = dups.candidates(int(inv_id))
        if not cands:
            continue
        feats = [dups.pair_features(int(inv_id), c) for c in cands]
        best = int(np.argmax([f["text_cos"] + f["num_sim"] for f in feats])) if inv_id in f1_invoices else -1
        for j, f in enumerate(feats):
            X.append([f[k] for k in PAIR_FEATURES])
            y.append(1 if j == best else 0)
    return np.array(X, dtype=float), np.array(y, dtype=int)


def engine_signals(L: Ledger, fc: FeatureContext, dups: DupIndex, dup_model, graph: RelationGraph,
                   payment_ids) -> pd.DataFrame:
    """Duplicate prob, graph signal, rule hit and rules-only baseline flag for each payment."""
    rows = []
    for pid in payment_ids:
        p = fc.pay_by_id.loc[int(pid)]
        d = dups.score(int(p["invoice_id"]), dup_model)
        rr = R.evaluate(fc, int(pid), d)
        g = graph.links_for(int(p["vendor_id"]), pd.Timestamp(p["created_at"]).value)
        rows.append({"duplicate": d.prob, "graph": g.signal, "rule_hit": rr.hit,
                     "baseline": float(R.rules_only_baseline_flag(fc, int(pid)))})
    return pd.DataFrame(rows, index=list(payment_ids))
