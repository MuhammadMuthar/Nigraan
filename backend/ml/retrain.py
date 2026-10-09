"""Learning loop (section 6.7): case outcomes become labels; retrain, bump model_version, report metrics.

Labelled payments = everything up to the audited date (historical audit) + any payment whose case an
analyst resolved in the app (confirmed fraud = 1, false alarm = 0). Fusion weights/thresholds are kept
from the last tuning so the UI bands stay stable; the engines are refit.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Case, ModelVersion
from app.services.ledger import Ledger
from app.services.runtime import runtime
from app.services.scoring.features import FeatureContext
from ml.common import types_from_cases
from ml.fraud_training import evaluate_fusion, signals_for, train_engines
from ml.train_all import save_fraud


def retrain_from_db(db: Session) -> dict:
    s = get_settings()
    t0 = datetime.now(timezone.utc)
    L = Ledger.from_db(db)
    fc = FeatureContext(L)
    pays = L.payments.set_index("id")
    X = fc.frame(pays.index.values)
    cases = L.cases[L.cases["status"].isin(["confirmed_fraud", "false_alarm"])]
    y = pd.Series(0, index=X.index)
    y.loc[y.index.isin(cases.loc[cases["status"] == "confirmed_fraud", "payment_id"])] = 1
    audited = pd.Timestamp(L.company["audited_through"]) + pd.Timedelta(days=1)
    resolved_ids = set(cases["payment_id"].astype(int))
    labelled = pd.Series((pays.loc[X.index, "created_at"] < audited).values | X.index.isin(list(resolved_ids)), index=X.index)
    types = types_from_cases(L)
    f1 = set(types[types == "F1"].index)
    old = json.loads((runtime.models_path / "fraud_meta.json").read_text())
    fusion = old["fusion"]

    # holdout: the last two audited months, trained on everything labelled before them
    cut = audited - pd.DateOffset(months=2)
    created = pays.loc[X.index, "created_at"]
    tr = labelled & (created < cut)
    ho = labelled & (created >= cut) & (created < audited)
    stage = train_engines(L, fc, X, y, tr, f1, old.get("seed", 42), xgb_params=old["xgb_params"])
    S = signals_for(L, fc, X, stage, X.index[ho])
    m = evaluate_fusion(S, y[ho].values, fusion["weights"], fusion["t_yellow"], fusion["t_red"])

    final = train_engines(L, fc, X, y, labelled, f1, old.get("seed", 42), xgb_params=old["xgb_params"])
    n_versions = db.execute(select(func.count(ModelVersion.id))).scalar() or 0
    version = f"v1.{n_versions + 1}-retrain"
    out_dir = s.data_out_dir / "models_runtime"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    for f in ("late_model.joblib", "late_meta.json", "metrics.json"):
        src = runtime.models_path / f
        if src.exists():
            shutil.copy(src, out_dir / f)
    meta = dict(old, iso_q=list(final.iso_q), n_pos=int(y[labelled].sum()), n_neg=int((y[labelled] == 0).sum()),
                trained_on="audited history + analyst-resolved cases")
    save_fraud(out_dir, version, meta, final)
    new_labels = int(db.execute(select(func.count(Case.id)).where(Case.source == "auto", Case.status != "open")).scalar() or 0)
    metrics = {k: (None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), 4)) for k, v in m.items()}
    db.add(ModelVersion(version=version, trained_at=t0.replace(tzinfo=None), n_labels=int(labelled.sum()),
                        metrics_json={"holdout_last_2_audited_months": metrics, "new_case_labels": new_labels},
                        notes=f"previous {runtime.bundle.version}"))
    db.commit()
    previous = runtime.bundle.version
    runtime.load_models(out_dir)
    return {"version": version, "previous_version": previous, "labelled_payments": int(labelled.sum()),
            "fraud_labels": int(y[labelled].sum()), "new_case_labels": new_labels,
            "holdout": {"period": f"{cut.date()} to {(audited - pd.Timedelta(days=1)).date()}", **metrics},
            "seconds": round((datetime.now(timezone.utc) - t0).total_seconds(), 1)}
