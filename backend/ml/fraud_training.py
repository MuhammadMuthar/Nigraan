"""Fraud model training: duplicate LR, XGBoost, Isolation Forest, fusion tuning. Used by train_all and retrain."""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.services.ledger import Ledger
from app.services.scoring.duplicates import DupIndex
from app.services.scoring.features import FEATURES, FeatureContext, iso_matrix
from app.services.scoring.fuse import ENGINES
from app.services.scoring.graph import RelationGraph
from ml.common import dup_pairs, engine_signals

PROMPT_WEIGHTS = {"risk_model": 0.4, "anomaly": 0.2, "duplicate": 0.2, "graph": 0.2}
FAR_TARGET = 0.04  # tune for <= 4% on validation to leave headroom under the 5% requirement
RED_FAR_TARGET = 0.005
WEIGHT_GRID = [0.1, 0.25, 0.5, 0.75, 1.0]


@dataclass
class EngineModels:
    tfidf: TfidfVectorizer
    dup_lr: object
    xgb: xgb.Booster
    iso: IsolationForest
    iso_q: tuple[float, float]
    xgb_params: dict


def fit_tfidf(dups: DupIndex, invoice_ids) -> TfidfVectorizer:
    texts = [dups.text(int(i)) for i in invoice_ids]
    return TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, max_features=20000).fit(texts)


def fit_dup_lr(X: np.ndarray, y: np.ndarray):
    # No class re-weighting: keeps probabilities honest so legit standing orders stay low
    model = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))
    return model.fit(X, y)


def fit_xgb(X: pd.DataFrame, y: np.ndarray, params: dict, seed: int = 42) -> xgb.Booster:
    pos = max(1, int(y.sum()))
    neg = len(y) - pos
    spw = neg / pos if params.get("spw") == "full" else float(np.sqrt(neg / pos))
    d = xgb.DMatrix(X[FEATURES].values, label=y, feature_names=FEATURES, missing=np.nan)
    p = {"objective": "binary:logistic", "eval_metric": "aucpr", "max_depth": params["max_depth"], "eta": 0.05,
         "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 3, "lambda": 2.0,
         "scale_pos_weight": spw, "seed": seed, "nthread": 2}
    return xgb.train(p, d, num_boost_round=params["rounds"])


def xgb_proba(b: xgb.Booster, X: pd.DataFrame) -> np.ndarray:
    return b.predict(xgb.DMatrix(X[FEATURES].values, feature_names=FEATURES, missing=np.nan))


def fit_iso(X: pd.DataFrame, seed: int = 42) -> tuple[IsolationForest, tuple[float, float]]:
    Z = iso_matrix(X)
    iso = IsolationForest(n_estimators=200, contamination=0.03, random_state=seed).fit(Z)
    raw = -iso.score_samples(Z)
    return iso, (float(np.quantile(raw, 0.90)), float(np.quantile(raw, 0.995)))


def iso_norm(iso, q, X) -> np.ndarray:
    raw = -iso.score_samples(iso_matrix(X))
    return np.clip((raw - q[0]) / max(q[1] - q[0], 1e-9), 0, 1)


def train_engines(L: Ledger, fc: FeatureContext, X: pd.DataFrame, y: pd.Series, train_mask: pd.Series,
                  f1_payments: set[int], seed: int = 42, xgb_params: dict | None = None,
                  tune_on: tuple[pd.DataFrame, np.ndarray] | None = None) -> EngineModels:
    pays = L.payments.set_index("id")
    train_ids = X.index[train_mask.values]
    train_invoices = sorted(set(pays.loc[train_ids, "invoice_id"].astype(int)))
    dups0 = DupIndex(L, None)
    tfidf = fit_tfidf(dups0, train_invoices)
    dups = DupIndex(L, tfidf)
    f1_inv = {int(pays.loc[p, "invoice_id"]) for p in f1_payments if p in pays.index}
    Xp, yp = dup_pairs(dups, train_invoices, f1_inv)
    dup_lr = fit_dup_lr(Xp, yp)
    Xt, yt = X.loc[train_ids], y.loc[train_ids].values
    if xgb_params is None:
        if tune_on is not None:
            Xv, yv = tune_on
            best, best_ap = None, -1
            for md, rounds, spw in itertools.product([3, 4], [250, 500], ["sqrt"]):
                params = {"max_depth": md, "rounds": rounds, "spw": spw}
                ap = average_precision_score(yv, xgb_proba(fit_xgb(Xt, yt, params, seed), Xv))
                if ap > best_ap:
                    best, best_ap = params, ap
            xgb_params = best
        else:
            xgb_params = {"max_depth": 3, "rounds": 400, "spw": "sqrt"}
    booster = fit_xgb(Xt, yt, xgb_params, seed)
    iso, q = fit_iso(Xt[~(yt == 1)] if (yt == 1).any() else Xt, seed)
    return EngineModels(tfidf, dup_lr, booster, iso, q, xgb_params)


def signals_for(L: Ledger, fc: FeatureContext, X: pd.DataFrame, models: EngineModels, ids) -> pd.DataFrame:
    dups = DupIndex(L, models.tfidf)
    graph = RelationGraph(L)
    S = engine_signals(L, fc, dups, models.dup_lr, graph, ids)
    S["risk_model"] = xgb_proba(models.xgb, X.loc[ids])
    S["anomaly"] = iso_norm(models.iso, models.iso_q, X.loc[ids])
    return S


def _threshold_for_far(legit_raw: np.ndarray, legit_forced: np.ndarray, target: float) -> float:
    """Smallest threshold t such that share of legit with (forced or raw >= t) <= target."""
    n = len(legit_raw)
    allowed = int(np.floor(target * n)) - int(legit_forced.sum())
    free = np.sort(legit_raw[~legit_forced])[::-1]
    if allowed <= 0:
        return float(free[0] + 1e-6) if len(free) else 0.5
    if allowed >= len(free):
        return 0.0
    return float(free[allowed] + 1e-6)  # strictly above the (allowed+1)-th highest


def evaluate_fusion(S: pd.DataFrame, y: np.ndarray, weights: dict, t_yellow: float, t_red: float) -> dict:
    raw = np.clip(sum(weights[e] * S[e].values for e in ENGINES), 0, 1)
    rule = S["rule_hit"].values
    alert = (rule >= 0.4) | (raw >= t_yellow)
    red = (rule >= 1.0) | (raw >= t_red)
    pos, neg = y == 1, y == 0
    return {
        "recall": float(alert[pos].mean()) if pos.any() else float("nan"),
        "recall_red": float(red[pos].mean()) if pos.any() else float("nan"),
        "far": float(alert[neg].mean()), "far_red": float(red[neg].mean()),
        "precision_red": float(pos[red].mean()) if red.any() else float("nan"),
        "precision_alert": float(pos[alert].mean()) if alert.any() else float("nan"),
        "pr_auc": float(average_precision_score(y, np.maximum(raw, rule))) if pos.any() else float("nan"),
    }


def tune_fusion(S: pd.DataFrame, y: np.ndarray) -> dict:
    best = None
    legit = y == 0
    for wx, wa, wd, wg in itertools.product(WEIGHT_GRID, [0.0, 0.1, 0.2, 0.4], WEIGHT_GRID, WEIGHT_GRID):
        w = {"risk_model": wx, "anomaly": wa, "duplicate": wd, "graph": wg}
        raw = np.clip(sum(w[e] * S[e].values for e in ENGINES), 0, 1)
        forced_y = S["rule_hit"].values[legit] >= 0.4
        forced_r = S["rule_hit"].values[legit] >= 1.0
        ty = max(0.05, _threshold_for_far(raw[legit], forced_y, FAR_TARGET))
        tr = max(ty + 0.05, _threshold_for_far(raw[legit], forced_r, RED_FAR_TARGET))
        if tr >= 0.99:
            continue
        m = evaluate_fusion(S, y, w, ty, tr)
        dist = sum(abs(w[e] - PROMPT_WEIGHTS[e]) for e in ENGINES)
        key = (round(m["recall"], 4), round(m["recall_red"], 4), -dist)
        if best is None or key > best[0]:
            best = (key, {"weights": w, "t_yellow": round(ty, 4), "t_red": round(tr, 4), "val": m})
    out = best[1]
    out["source"] = ("tuned on out-of-time folds, months 7-8 and 9-10 (grid search: max recall s.t. "
                     "false alarms <= 4%, red false alarms <= 0.5%)")
    # Prompt defaults evaluated with thresholds fitted the same way, for the ablation table
    w = PROMPT_WEIGHTS
    raw = np.clip(sum(w[e] * S[e].values for e in ENGINES), 0, 1)
    ty = max(0.05, _threshold_for_far(raw[legit], S["rule_hit"].values[legit] >= 0.4, FAR_TARGET))
    tr = max(ty + 0.05, _threshold_for_far(raw[legit], S["rule_hit"].values[legit] >= 1.0, RED_FAR_TARGET))
    out["prompt_defaults_val"] = {"t_yellow": ty, "t_red": tr, **evaluate_fusion(S, y, w, ty, tr)}
    return out
