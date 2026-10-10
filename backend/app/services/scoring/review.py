"""Optional review-study results, tied to the exact shipped model artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

MODEL_FILES = ("fraud_meta.json", "fraud_xgb.json", "iso_forest.joblib", "dup_lr.joblib")


def model_fingerprints(models_dir: Path) -> dict[str, str]:
    return {name: hashlib.sha256((models_dir / name).read_bytes()).hexdigest() for name in MODEL_FILES}


def load_review_evaluation(models_dir: Path, model_version: str) -> dict | None:
    path = models_dir / "review_eval.json"
    if not path.exists():
        return None
    try:
        report = json.loads(path.read_text())
        if not isinstance(report, dict):
            return None
        if report.get("model_version") != model_version or report.get("source_artifacts") != model_fingerprints(models_dir):
            return None  # Retraining invalidates this comparison instead of displaying stale claims.
        return report
    except (OSError, ValueError, TypeError):
        return None
