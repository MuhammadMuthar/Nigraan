"""Train every model from the seeded synthetic company and write artifacts to models/.

    python -m ml.train_all --seed 42

Fraud: duplicate LR + XGBoost + Isolation Forest trained on months 1-8, XGBoost hyper-parameters and
fusion weights/thresholds tuned on months 9-10, then refit on months 1-10. Months 11-12 are never
touched here (ml/evaluate.py). Labels come only from confirmed historical cases (months 1-10).
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from app.config import get_settings
from app.services.ledger import Ledger
from app.services.receivables.late_model import late_labels, receivable_features
from app.services.scoring.features import FEATURES, FeatureContext
from ml.common import labels_from_cases, month_of, types_from_cases
from ml.fraud_training import signals_for, train_engines, tune_fusion
from ml.late_training import train_late


def train_fraud(L: Ledger, seed: int, log=print) -> tuple[dict, dict]:
    t0 = time.time()
    fc = FeatureContext(L)
    ids = L.payments["id"].values
    X = fc.frame(ids)
    y = labels_from_cases(L).loc[X.index]
    types = types_from_cases(L)
    months = L.payments.set_index("id").loc[X.index, "created_at"].map(month_of)
    audited = pd.Timestamp(L.company["audited_through"])
    labelled = L.payments.set_index("id").loc[X.index, "created_at"] <= audited + pd.Timedelta(days=1)
    f1 = set(types[types == "F1"].index)
    log(f"features: {len(X)} payments x {len(FEATURES)} ({time.time() - t0:.1f}s); "
        f"labelled frauds {int(y[labelled].sum())}/{int(labelled.sum())}")
    # Two time-ordered folds for tuning: train 1-6 -> tune on 7-8, train 1-8 -> tune on 9-10.
    S_parts, y_parts, xgb_params = [], [], None
    for tr_hi, va_lo, va_hi in ((8, 9, 10), (6, 7, 8)):
        tr = (months <= tr_hi) & labelled
        va = (months >= va_lo) & (months <= va_hi) & labelled
        stage = train_engines(L, fc, X, y, tr, f1, seed, xgb_params=xgb_params,
                              tune_on=(X[va], y[va].values) if xgb_params is None else None)
        xgb_params = stage.xgb_params
        S_parts.append(signals_for(L, fc, X, stage, X.index[va]))
        y_parts.append(y[va].values)
    S_val = pd.concat(S_parts)
    y_val = np.concatenate(y_parts)
    fusion = tune_fusion(S_val, y_val)
    log(f"xgb params {xgb_params}; fusion {fusion['weights']} t_yellow={fusion['t_yellow']} "
        f"t_red={fusion['t_red']} val(months 7-10)={ {k: round(v, 3) for k, v in fusion['val'].items()} }")
    final = train_engines(L, fc, X, y, labelled, f1, seed, xgb_params=xgb_params)
    meta = {
        "fusion": fusion, "iso_q": list(final.iso_q), "xgb_params": final.xgb_params, "features": FEATURES,
        "n_pos": int(y[labelled].sum()), "n_neg": int((y[labelled] == 0).sum()), "seed": seed,
        "trained_on": "payments in months 1-10 with audited labels; fusion tuned on out-of-time folds (months 7-8, 9-10)",
    }
    return meta, {"engines": final, "val_signals": S_val}


def save_fraud(models_dir: Path, version: str, meta: dict, engines) -> None:
    models_dir.mkdir(parents=True, exist_ok=True)
    engines.xgb.save_model(str(models_dir / "fraud_xgb.json"))
    joblib.dump(engines.iso, models_dir / "iso_forest.joblib", compress=3)
    joblib.dump({"model": engines.dup_lr, "tfidf": engines.tfidf}, models_dir / "dup_lr.joblib", compress=3)
    meta = dict(meta, version=version, trained_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    (models_dir / "fraud_meta.json").write_text(json.dumps(meta, indent=2, default=float))


def train_late_model(world, seed: int, log=print) -> tuple[dict, dict]:
    r = pd.DataFrame(world.receivables)
    c = pd.DataFrame(world.customers)
    X = receivable_features(r, c)
    data_end = world.companies[0]["as_of_date"]
    y = late_labels(r, data_end).loc[X.index]
    months = r.set_index("id").loc[X.index, "issue_date"].map(month_of)
    bundle, report = train_late(X, y, months, seed)
    log(f"late model: {report['note']} (calibrated={report['calibrated']})")
    return bundle, report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    from data_gen.generate_company import generate

    out = args.out or get_settings().models_dir
    t0 = time.time()
    world = generate(args.seed)
    L = Ledger.from_world(world)
    meta, res = train_fraud(L, args.seed)
    version = f"v1.0-s{args.seed}"
    save_fraud(out, version, meta, res["engines"])
    late_bundle, late_report = train_late_model(world, args.seed)
    late_bundle["version"] = version
    joblib.dump(late_bundle, out / "late_model.joblib", compress=3)
    (out / "late_meta.json").write_text(json.dumps(late_report, indent=2, default=float))
    print(f"saved models to {out} in {time.time() - t0:.1f}s (version {version})")


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
