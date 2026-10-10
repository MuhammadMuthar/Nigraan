"""Reproduce a stronger rules comparison and invoice-age sensitivity study.

    python -m ml.review_evaluate

Only writes models/review_eval.json. Comparison engines are fitted in memory;
production models, data, scores, thresholds and metrics are never overwritten.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xgboost as xgb
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score

from app.config import get_settings
from app.services.ledger import Ledger
from app.services.scoring.features import FEATURES, ISO_FEATURES, FeatureContext, iso_matrix
from app.services.scoring.fuse import fuse
from app.services.scoring.review import MODEL_FILES, model_fingerprints
from app.services.scoring.risk import ModelBundle
from app.services.scoring.scorer import Scorer
from data_gen.generate_company import generate
from ml.common import labels_from_cases, month_of
from ml.evaluate import _summ, fraud_eval

AGE = "days_since_invoice_date"


def _fit_without_age(X, y, params: dict, seed: int):
    names = [name for name in FEATURES if name != AGE]
    pos = max(1, int(y.sum()))
    neg = len(y) - pos
    spw = neg / pos if params.get("spw") == "full" else float(np.sqrt(neg / pos))
    settings = {"objective": "binary:logistic", "eval_metric": "aucpr", "max_depth": params["max_depth"],
                "eta": 0.05, "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 3,
                "lambda": 2.0, "scale_pos_weight": spw, "seed": seed, "nthread": 2}
    booster = xgb.train(settings, xgb.DMatrix(X[names].values, label=y, feature_names=names, missing=np.nan),
                        num_boost_round=params["rounds"])
    keep = [i for i, name in enumerate(ISO_FEATURES) if name != AGE]
    legitimate = X.loc[y == 0]
    Z = iso_matrix(legitimate)[:, keep]
    iso = IsolationForest(n_estimators=200, contamination=0.03, random_state=seed).fit(Z)
    raw = -iso.score_samples(Z)
    quantiles = (float(np.quantile(raw, 0.90)), float(np.quantile(raw, 0.995)))
    return booster, names, iso, keep, quantiles


def evaluate(models_dir: Path) -> dict:
    before = model_fingerprints(models_dir)
    meta = json.loads((models_dir / "fraud_meta.json").read_text())
    seed = int(meta["seed"])
    if meta.get("features") != FEATURES:
        raise ValueError("Study expects the current feature schema")
    world = generate(seed)
    bundle = ModelBundle.load(models_dir)
    held_out = fraud_eval(world, bundle, 11, 12)
    df = held_out.pop("_frame")
    L = Ledger.from_world(world)
    fc = FeatureContext(L)
    X = fc.frame(L.payments["id"].values)
    y = labels_from_cases(L).loc[X.index]
    payments = L.payments.set_index("id")
    months = payments.loc[X.index, "created_at"].map(month_of)
    audited = payments.loc[X.index, "created_at"] <= np.datetime64(L.company["audited_through"]) + np.timedelta64(1, "D")
    train = (months <= 10) & audited
    test_ids = df.index
    # Reuse the exact checks persisted by the live scorer; no separate cherry-picked comparator.
    scorer = Scorer(bundle)
    ctx = scorer.prepare(L)
    results = scorer.score(ctx, list(test_ids))
    df["expert"] = [int(result.evidence["rules_comparison"]["expert"]["flagged"]) for result in results]
    expert = _summ(df, "expert", "expert", "expert")
    booster, names, iso, keep, q = _fit_without_age(X.loc[train], y.loc[train].values, meta["xgb_params"], seed)
    risk = booster.predict(xgb.DMatrix(X.loc[test_ids, names].values, feature_names=names, missing=np.nan))
    raw_anomaly = -iso.score_samples(iso_matrix(X.loc[test_ids])[:, keep])
    anomaly = np.clip((raw_anomaly - q[0]) / max(q[1] - q[0], 1e-9), 0, 1)
    signals = [dict(signal, risk_model=float(risk[i]), anomaly=float(anomaly[i])) for i, signal in enumerate(df["signals"])]
    reduced_scores = [fuse(signal, rule, bundle.fusion)[0] for signal, rule in zip(signals, df["rule"])]
    reduced = df.copy()
    reduced["score"] = reduced_scores
    reduced["alert"] = (reduced["score"] >= 40).astype(int)
    reduced["red"] = (reduced["score"] >= 75).astype(int)
    reduced_metrics = _summ(reduced, "alert", "red", "score")
    pos = df["y"].values == 1
    risk_only = {"with_invoice_age_pr_auc": float(average_precision_score(df["y"], [s["risk_model"] for s in df["signals"]])),
                 "without_invoice_age_pr_auc": float(average_precision_score(df["y"], risk)),
                 "without_invoice_age_recall_at_half": float((risk[pos] >= 0.5).mean())}
    after = model_fingerprints(models_dir)
    if before != after:
        raise RuntimeError("Shipped model artifacts changed during the study")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_version": bundle.version, "source_artifacts": before, "seed": seed,
        "test_period": "Aug–Sep 2026, synthetic held-out months 11–12",
        "training_period": "Oct 2025–Jul 2026, months 1–10 with audited labels",
        "n_payments": int(len(df)), "n_fraud": int(df["y"].sum()), "n_legitimate": int((df["y"] == 0).sum()),
        "rules_comparison": {"nigraan": held_out["nigraan"], "simple": held_out["baseline_rules_only"], "expert": expert,
                             "simple_description": "Above approval limit or prior same-vendor normalized invoice number",
                             "expert_description": "Simple checks plus recent bank change (30 days), new vendor (30 days/no history), night entry (22–06 PKT), item price ≥1.3× historical price, combined 48-hour exposure, blocked/duplicate/split rules and undisclosed employee relationship",
                             "note": "Binary rule flags mean review, not automatic red blocks. Expert rules have no learned parameters; graph and split checks are deterministic. The same heuristics are used in the live payment run."},
        "invoice_age_ablation": {"removed_feature": AGE, "trained_rows": int(train.sum()),
                                 "with_feature": held_out["nigraan"], "without_feature": reduced_metrics,
                                 "risk_model_only": risk_only,
                                 "method": "Refit XGBoost and Isolation Forest in memory without invoice age, using the original seed, audited months 1–10, hyperparameters and model settings. Keep shipped duplicate model, deterministic graph/rules, fusion weights and thresholds. No hold-out retuning.",
                                 "note": "A single synthetic-company sensitivity study, not external validation or a recalibrated replacement model. Other correlated features may preserve synthetic shortcuts. Production models are unchanged."},
        "limitations": ["Synthetic labels and one company's held-out months do not establish real-world accuracy.",
                        f"Only {int(df['y'].sum())} held-out fraud examples; individual fraud patterns have small samples.",
                        "Rule checks and deterministic relationship links can catch patterns without ML.",
                        "No customer pilot or measured real-world savings are claimed."],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    models_dir = get_settings().models_dir
    output = args.out or models_dir / "review_eval.json"
    if output.resolve() in {(models_dir / name).resolve() for name in (*MODEL_FILES, "metrics.json", "late_model.joblib", "late_meta.json", "extraction_eval.json")}:
        raise SystemExit("Refusing to overwrite a shipped model or evaluation artifact")
    report = evaluate(models_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False))
    for name, values in report["rules_comparison"].items():
        if isinstance(values, dict):
            print(f"{name}: recall {values['recall']:.3f}, false alarms {values['false_alarm_rate']:.3f}, review flags {values['alerts']}")
    values = report["invoice_age_ablation"]["without_feature"]
    print(f"Without invoice age: recall {values['recall']:.3f}, false alarms {values['false_alarm_rate']:.3f}; saved {output}")


if __name__ == "__main__":
    main()
