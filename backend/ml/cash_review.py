"""Compare receipt policies without retraining or replacing shipped model metrics.

    python -m ml.cash_review --seed 42 --months 11-12

Both policies use the same synthetic ledger and rolling origins. This evaluates receipts
over four weeks; it does not validate the full thirteen-week cash or reserve forecast.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone

from app.config import get_settings
from data_gen.generate_company import generate
from ml.evaluate import cash_eval


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--months", default="11-12")
    args = parser.parse_args()
    lo, hi = (int(x) for x in args.months.split("-"))
    world = generate(args.seed)
    settings = get_settings()
    inputs_path = settings.models_dir.parent / "backend/app/services/cash/inputs.py"
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": args.seed,
        "synthetic": True,
        "test_months": args.months,
        "inputs_sha256": hashlib.sha256(inputs_path.read_bytes()).hexdigest(),
        "scope": "Rolling-origin receipt backtest only; not a validation of thirteen-week balances or reserve outcomes.",
        "policies": {
            policy: cash_eval(world, lo, hi, stale_policy=policy)
            for policy in ("legacy_next_week", "exclude_unconfirmed")
        },
    }
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    output = settings.models_dir / "cash_review_metrics.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"path": str(output), "policies": result["policies"]}, indent=2))


if __name__ == "__main__":
    main()
