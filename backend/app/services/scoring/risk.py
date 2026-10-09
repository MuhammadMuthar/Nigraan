"""Trained artifacts: XGBoost risk model, Isolation Forest, duplicate LR, fusion parameters.

Loaded once at startup from models/. If an artifact is missing the scorer degrades to rules +
graph only and says so (model_version 'rules-only').
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb

from app.services.scoring.features import FEATURES, iso_matrix

DEFAULT_FUSION = {
    "weights": {"risk_model": 0.4, "anomaly": 0.2, "duplicate": 0.2, "graph": 0.2},
    "t_yellow": 0.2,
    "t_red": 0.5,
    "source": "prompt defaults (untuned)",
}


@dataclass
class ModelBundle:
    version: str = "rules-only"
    xgb: xgb.Booster | None = None
    iso: object | None = None
    iso_q: tuple[float, float] = (0.0, 1.0)  # anomaly-score quantiles used to normalise to 0-1
    dup_lr: object | None = None
    tfidf: object | None = None
    fusion: dict = field(default_factory=lambda: dict(DEFAULT_FUSION))
    late: dict | None = None
    metrics: dict = field(default_factory=dict)

    @property
    def has_ml(self) -> bool:
        return self.xgb is not None

    @classmethod
    def load(cls, models_dir: Path) -> "ModelBundle":
        b = cls()
        meta_p = models_dir / "fraud_meta.json"
        if not meta_p.exists():
            return b
        meta = json.loads(meta_p.read_text())
        b.version = meta["version"]
        b.fusion = meta.get("fusion", dict(DEFAULT_FUSION))
        b.iso_q = tuple(meta.get("iso_q", (0.0, 1.0)))
        booster = xgb.Booster()
        booster.load_model(str(models_dir / "fraud_xgb.json"))
        b.xgb = booster
        b.iso = joblib.load(models_dir / "iso_forest.joblib")
        dup = joblib.load(models_dir / "dup_lr.joblib")
        b.dup_lr, b.tfidf = dup["model"], dup["tfidf"]
        late_p = models_dir / "late_model.joblib"
        if late_p.exists():
            b.late = joblib.load(late_p)
        m = models_dir / "metrics.json"
        if m.exists():
            b.metrics = json.loads(m.read_text())
        return b


def xgb_predict(booster: xgb.Booster, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Probability and per-feature contributions (SHAP values in log-odds; last column = bias)."""
    d = xgb.DMatrix(X[FEATURES].values, feature_names=FEATURES, missing=np.nan)
    p = booster.predict(d)
    contrib = booster.predict(d, pred_contribs=True)
    return p, contrib


def iso_signal(iso, iso_q: tuple[float, float], X: pd.DataFrame) -> np.ndarray:
    """0 for typical payments, rising to 1 for the most anomalous (above the training 90th percentile)."""
    raw = -iso.score_samples(iso_matrix(X))  # higher = more anomalous
    lo, hi = iso_q
    return np.clip((raw - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
