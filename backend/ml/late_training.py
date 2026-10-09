"""Late-payment model training: baseline vs logistic regression vs XGBoost, chosen on held-out PR-AUC."""
from __future__ import annotations

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.services.receivables.late_model import LATE_FEATURES, MIN_HISTORY, predict
from ml.common import month_of


def fit_kind(kind: str, X: pd.DataFrame, y: np.ndarray, seed: int = 42) -> dict:
    base_rate = float(y.mean())
    if kind == "baseline":
        return {"kind": "baseline", "base_rate": base_rate}
    if kind == "lr":
        m = make_pipeline(SimpleImputer(strategy="median", add_indicator=False), StandardScaler(),
                          LogisticRegression(C=0.5, max_iter=2000))
        m.fit(X[LATE_FEATURES], y)
        return {"kind": "lr", "model": m, "base_rate": base_rate}
    d = xgb.DMatrix(X[LATE_FEATURES].values, label=y, feature_names=LATE_FEATURES, missing=np.nan)
    params = {"objective": "binary:logistic", "eval_metric": "aucpr", "max_depth": 3, "eta": 0.05, "subsample": 0.85,
              "colsample_bytree": 0.85, "min_child_weight": 5, "seed": seed, "nthread": 2}
    booster = xgb.train(params, d, num_boost_round=300)
    return {"kind": "xgb", "model": booster, "base_rate": base_rate}


def reliability(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.linspace(0, 1, bins + 1)
    out = []
    for i in range(bins):
        m = (p >= edges[i]) & (p < edges[i + 1] if i < bins - 1 else p <= 1)
        if m.sum() >= 5:
            out.append({"bin": f"{edges[i]:.1f}-{edges[i + 1]:.1f}", "n": int(m.sum()), "mean_pred": float(p[m].mean()),
                        "observed": float(y[m].mean())})
    return out


def metrics(y: np.ndarray, p: np.ndarray) -> dict:
    k = max(1, int(round(0.2 * len(p))))
    top = np.argsort(-p)[:k]
    return {
        "pr_auc": float(average_precision_score(y, p)) if len(set(y)) > 1 else float("nan"),
        "roc_auc": float(roc_auc_score(y, p)) if len(set(y)) > 1 and np.std(p) > 0 else 0.5,
        "brier": float(brier_score_loss(y, p)),
        "precision_top20": float(y[top].mean()),
        "recall_top20": float(y[top].sum() / max(1, y.sum())),
        "n": int(len(y)), "late_rate": float(y.mean()),
    }


def split_masks(receivables: pd.DataFrame, X: pd.DataFrame, y: pd.Series):
    m = receivables.set_index("id").loc[X.index, "issue_date"].map(month_of)
    known = y.loc[X.index].notna()
    return m, known


def train_late(X: pd.DataFrame, y: pd.Series, months: pd.Series, seed: int = 42) -> tuple[dict, dict]:
    """Select on months 9-10 (trained on 1-8), refit the winner on 1-10."""
    known = y.notna()
    tr = known & (months >= 1) & (months <= 8)
    va = known & (months >= 9) & (months <= 10)
    full = known & (months >= 1) & (months <= 10)
    yv = y[va].values
    report = {}
    for kind in ("baseline", "lr", "xgb"):
        b = fit_kind(kind, X[tr], y[tr].values, seed)
        p, _ = predict(b, X[va])
        report[kind] = metrics(yv, p)
    best = max(("lr", "xgb"), key=lambda k: report[k]["pr_auc"])
    if report[best]["pr_auc"] <= report["baseline"]["pr_auc"]:
        best = "baseline"
    note = (f"Shipped {best}: validation PR-AUC {report[best]['pr_auc']:.3f} vs "
            + ", ".join(f"{k} {v['pr_auc']:.3f}" for k, v in report.items() if k != best))
    final = fit_kind(best, X[full], y[full].values, seed)
    pv, _ = predict(fit_kind(best, X[tr], y[tr].values, seed), X[va])
    rel = reliability(yv, pv)
    gap = max((abs(r["mean_pred"] - r["observed"]) for r in rel), default=1.0)
    calibrated = report[best]["brier"] < report["baseline"]["brier"] and gap <= 0.12
    seg_cols = [c for c in X.columns if c.startswith("seg_")]
    seg_rates = {}
    for c in seg_cols:
        m = full & (X[c] == 1)
        if m.any():
            seg_rates[c[4:]] = float(y[m].mean())
    final.update({
        "features": LATE_FEATURES, "segment_rates": seg_rates, "calibrated": bool(calibrated),
        "max_reliability_gap": float(gap), "val": report, "note": note, "min_history": MIN_HISTORY,
        "output_label": "late-payment probability" if calibrated else "late-payment risk score",
    })
    return final, {"validation": report, "chosen": best, "note": note, "reliability_val": rel,
                   "calibrated": bool(calibrated)}
