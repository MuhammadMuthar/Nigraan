"""Held-out evaluation (months 11-12, never seen in training). Every number on our slides comes from here.

    python -m ml.evaluate --months 11-12            # shipped models, seed 42
    python -m ml.evaluate --months 11-12 --seeds 42,43,44,45,46   # + robustness across 5 synthetic companies

Writes models/metrics.json and PNGs to docs/.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_curve

from app.config import get_settings
from app.services.cash.inputs import estimate_receipts, weekly_actual_receipts
from app.services.ledger import Ledger
from app.services.receivables.late_model import late_labels, predict as late_predict, receivable_features
from app.services.scoring import rules as R
from app.services.scoring.risk import ModelBundle
from app.services.scoring.scorer import FRAUD_TYPES, Scorer
from ml.common import month_of
from ml.late_training import fit_kind, metrics as late_metrics, reliability

TYPES = ["F1", "F2", "F3", "F4", "F5", "F7"]


def bundle_from_training(meta: dict, engines, version: str) -> ModelBundle:
    return ModelBundle(version=version, xgb=engines.xgb, iso=engines.iso, iso_q=tuple(engines.iso_q),
                       dup_lr=engines.dup_lr, tfidf=engines.tfidf, fusion=meta["fusion"])


def fraud_eval(world, bundle: ModelBundle, lo: int, hi: int) -> dict:
    L = Ledger.from_world(world)
    scorer = Scorer(bundle)
    ctx = scorer.prepare(L)
    pays = L.payments.set_index("id")
    months = pays["created_at"].map(month_of)
    ids = [int(i) for i in pays.index[(months >= lo) & (months <= hi)]]
    t0 = time.perf_counter()
    results = scorer.score(ctx, ids)
    ms_per = (time.perf_counter() - t0) * 1000 / max(1, len(ids))
    labels = world.labels_frame().set_index("payment_id")
    df = pd.DataFrame({
        "id": ids, "score": [r.score for r in results], "decision": [r.decision for r in results],
        "amount": [int(pays.loc[i, "amount"]) for i in ids],
        "type": [labels["fraud_type"].get(i) for i in ids],
        "signals": [r.signals for r in results], "rule": [max([0.0] + [1.0 if e["hard"] else 0.6 for e in r.evidence["rules"] if e["code"] != "INFO"]) for r in results],
    }).set_index("id")
    df["y"] = df["type"].notna().astype(int)
    df["baseline"] = [int(R.rules_only_baseline_flag(ctx.features, i)) for i in ids]
    df["alert"] = (df["score"] >= 40).astype(int)
    df["red"] = (df["score"] >= 75).astype(int)
    out = {"n_payments": len(df), "n_fraud": int(df["y"].sum()), "ms_per_payment": round(ms_per, 1)}
    out["nigraan"] = _summ(df, "alert", "red", "score")
    out["baseline_rules_only"] = _summ(df, "baseline", "baseline", "baseline")
    # ablation: zero one engine's weight, keep thresholds
    from app.services.scoring.fuse import ENGINES, fuse
    abl = {}
    for e in ENGINES:
        fz = dict(bundle.fusion, weights=dict(bundle.fusion["weights"], **{e: 0.0}))
        sc = np.array([fuse(s, rh, fz)[0] for s, rh in zip(df["signals"], df["rule"])])
        a = sc >= 40
        abl[f"without_{e}"] = {"recall": float(a[df["y"] == 1].mean()), "false_alarm_rate": float(a[df["y"] == 0].mean())}
    out["ablation"] = abl
    out["_frame"] = df
    return out


def _summ(df: pd.DataFrame, alert_col: str, red_col: str, score_col: str) -> dict:
    pos, neg = df["y"] == 1, df["y"] == 0
    a, r = df[alert_col] == 1, df[red_col] == 1
    per_type = {}
    for t in TYPES:
        m = df["type"] == t
        if m.any():
            per_type[t] = {"name": FRAUD_TYPES[t], "n": int(m.sum()), "caught": int((a & m).sum()),
                           "recall": float((a & m).sum() / m.sum()), "red": int((r & m).sum())}
    fraud_amt = int(df.loc[pos, "amount"].sum())
    return {
        "recall": float(a[pos].mean()) if pos.any() else None,
        "recall_red": float(r[pos].mean()) if pos.any() else None,
        "precision_alert": float(pos[a].mean()) if a.any() else None,
        "precision_red": float(pos[r].mean()) if r.any() else None,
        "false_alarm_rate": float(a[neg].mean()),
        "false_alarm_rate_red": float(r[neg].mean()),
        "pr_auc": float(average_precision_score(df["y"], df[score_col])) if pos.any() else None,
        "alerts": int(a.sum()), "reds": int(r.sum()),
        "rupees_fraud": fraud_amt, "rupees_protected_red": int(df.loc[pos & r, "amount"].sum()),
        "rupees_flagged": int(df.loc[pos & a, "amount"].sum()),
        "per_type": per_type,
    }


def late_eval(world, shipped: dict | None, lo: int, hi: int) -> dict:
    r = pd.DataFrame(world.receivables)
    c = pd.DataFrame(world.customers)
    X = receivable_features(r, c)
    y = late_labels(r, world.companies[0]["as_of_date"]).loc[X.index]
    months = r.set_index("id").loc[X.index, "issue_date"].map(month_of)
    tr = y.notna() & (months <= 10)
    te = y.notna() & (months >= lo) & (months <= hi)
    out = {"n_test": int(te.sum()), "late_rate_test": float(y[te].mean()), "models": {}}
    for kind in ("baseline", "lr", "xgb"):
        b = fit_kind(kind, X[tr], y[tr].values)
        p, _ = late_predict(b, X[te])
        out["models"][kind] = late_metrics(y[te].values, p)
    if shipped:
        p, _ = late_predict(shipped, X[te])
        out["shipped"] = {"kind": shipped["kind"], **late_metrics(y[te].values, p),
                          "reliability": reliability(y[te].values, p), "output_label": shipped.get("output_label")}
        limited = X.loc[te[te].index, "prior_settled"] < 5
        out["limited_history_share"] = float(limited.mean())
    out["excluded_unknown"] = int(((months >= lo) & (months <= hi) & y.isna()).sum())
    return out


def cash_eval(world, lo: int, hi: int, horizon_weeks: int = 4) -> dict:
    """Rolling-origin backtest of projected receipts (open receivables only) vs actual collections."""
    r = pd.DataFrame(world.receivables)
    truth = pd.DataFrame(world.receivable_truth).set_index("receivable_id")
    full = r.copy()
    full["paid_date"] = full["id"].map(truth["true_paid_date"])  # the backtest may use real outcomes
    full["paid_amount"] = full["amount"] - full["disputed_amount"].fillna(0)
    as_of = world.companies[0]["as_of_date"]
    start = date(2025, 10, 1)
    first = date(start.year + (start.month + lo - 2) // 12, (start.month + lo - 2) % 12 + 1, 1)
    last = date(start.year + (start.month + hi - 1) // 12, (start.month + hi - 1) % 12 + 1, 1) - timedelta(days=1)
    origins = []
    d = first + timedelta(days=(7 - first.weekday()) % 7)
    while d + timedelta(weeks=horizon_weeks) <= min(last + timedelta(days=1), as_of):
        origins.append(d)
        d += timedelta(days=7)
    errs = {"median_delay": [], "due_date": []}
    actual_tot = 0
    for o in origins:
        known = full.copy()
        known.loc[pd.to_datetime(known["paid_date"]) >= pd.Timestamp(o), ["paid_date"]] = None  # as seen at origin
        for method in errs:
            est = estimate_receipts(known, o, method=method)
            ids = {e.receivable_id for e in est}
            pred = np.zeros(horizon_weeks, dtype=np.int64)
            for e in est:
                k = (e.expected_date - o).days // 7
                if 0 <= k < horizon_weeks:
                    pred[k] += e.amount
            act = weekly_actual_receipts(full, ids, o, horizon_weeks)
            errs[method].append(np.abs(pred - act))
            if method == "median_delay":
                actual_tot += int(act.sum())
    res = {"origins": [o.isoformat() for o in origins], "horizon_weeks": horizon_weeks}
    for m, e in errs.items():
        arr = np.array(e)
        res[m] = {"mae_rupees_per_week": float(arr.mean() / 100), "wape": float(arr.sum() / max(1, actual_tot)),
                  "mae_by_horizon_week": [float(x / 100) for x in arr.mean(axis=0)]}
    res["improvement_vs_due_date"] = 1 - res["median_delay"]["mae_rupees_per_week"] / res["due_date"]["mae_rupees_per_week"]
    return res


def write_plots(df: pd.DataFrame, docs: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    docs.mkdir(parents=True, exist_ok=True)
    files = []
    # confusion matrix (alert = yellow or red)
    tp = int(((df["alert"] == 1) & (df["y"] == 1)).sum())
    fp = int(((df["alert"] == 1) & (df["y"] == 0)).sum())
    fn = int(((df["alert"] == 0) & (df["y"] == 1)).sum())
    tn = int(((df["alert"] == 0) & (df["y"] == 0)).sum())
    fig, ax = plt.subplots(figsize=(4.2, 3.6), dpi=160)
    mat = np.array([[tn, fp], [fn, tp]])
    ax.imshow(mat, cmap="Greys", alpha=0.25)
    for (i, j), v in np.ndenumerate(mat):
        ax.text(j, i, str(v), ha="center", va="center", fontsize=16, fontweight="bold")
    ax.set_xticks([0, 1], ["Allowed", "Flagged"])
    ax.set_yticks([0, 1], ["Legit", "Fraud"])
    ax.set_title("Held-out months 11-12", fontsize=10)
    fig.tight_layout()
    fig.savefig(docs / "confusion_matrix.png")
    plt.close(fig)
    files.append("confusion_matrix.png")
    # PR curve vs rules baseline point
    prec, rec, _ = precision_recall_curve(df["y"], df["score"])
    fig, ax = plt.subplots(figsize=(4.8, 3.6), dpi=160)
    ax.plot(rec, prec, color="#0f766e", lw=2, label="Nigraan (fused score)")
    b_rec = ((df["baseline"] == 1) & (df["y"] == 1)).sum() / max(1, df["y"].sum())
    b_prec = ((df["baseline"] == 1) & (df["y"] == 1)).sum() / max(1, (df["baseline"] == 1).sum())
    ax.scatter([b_rec], [b_prec], color="#b45309", zorder=3, label="Rules-only baseline")
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_xlim(0, 1.02)
    ax.set_ylim(0, 1.02)
    ax.grid(alpha=0.25)
    ax.legend(loc="lower left", fontsize=8, frameon=False)
    ax.set_title("Precision-recall, months 11-12", fontsize=10)
    fig.tight_layout()
    fig.savefig(docs / "pr_curve.png")
    plt.close(fig)
    files.append("pr_curve.png")
    return files


def robustness(seeds: list[int], lo: int, hi: int) -> dict:
    from data_gen.generate_company import generate
    from ml.train_all import train_fraud

    per_seed, pooled = [], []
    for s in seeds:
        w = generate(s, with_demo=False)
        meta, res = train_fraud(Ledger.from_world(w), s, log=lambda *_: None)
        ev = fraud_eval(w, bundle_from_training(meta, res["engines"], f"seed{s}"), lo, hi)
        n = ev["nigraan"]
        per_seed.append({"seed": s, "n_fraud": ev["n_fraud"], "recall": n["recall"], "false_alarm_rate": n["false_alarm_rate"],
                         "precision_red": n["precision_red"], "pr_auc": n["pr_auc"],
                         "baseline_recall": ev["baseline_rules_only"]["recall"],
                         "baseline_false_alarm_rate": ev["baseline_rules_only"]["false_alarm_rate"]})
        pooled.append(ev["_frame"])
        print(f"  seed {s}: recall {n['recall']:.2f} FAR {n['false_alarm_rate']:.3f} PR-AUC {n['pr_auc']:.2f}")
    df = pd.concat(pooled)
    summ = _summ(df, "alert", "red", "score")
    base = _summ(df, "baseline", "baseline", "baseline")
    agg = {k: {"mean": float(np.mean([p[k] for p in per_seed if p[k] is not None])),
               "min": float(np.min([p[k] for p in per_seed if p[k] is not None])),
               "max": float(np.max([p[k] for p in per_seed if p[k] is not None]))}
           for k in ("recall", "false_alarm_rate", "precision_red", "pr_auc", "baseline_recall", "baseline_false_alarm_rate")}
    return {"seeds": seeds, "per_seed": per_seed, "aggregate": agg, "pooled": summ, "pooled_baseline": base,
            "note": "Each seed is a different synthetic company: generated, trained on months 1-10, tested on 11-12."}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", default="11-12")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--seeds", default="")
    args = ap.parse_args()
    lo, hi = (int(x) for x in args.months.split("-"))
    s = get_settings()
    from data_gen.generate_company import generate

    world = generate(args.seed)
    bundle = ModelBundle.load(s.models_dir)
    if not bundle.has_ml:
        raise SystemExit("No trained models in models/. Run: python -m ml.train_all")
    t0 = time.time()
    fr = fraud_eval(world, bundle, lo, hi)
    df = fr.pop("_frame")
    plots = write_plots(df, s.models_dir.parent / "docs")
    shipped_late = bundle.late
    lt = late_eval(world, shipped_late, lo, hi)
    ce = cash_eval(world, lo, hi)
    metrics = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_version": bundle.version, "seed": args.seed, "test_months": f"{lo}-{hi}",
        "test_period": "Aug-Sep 2026 (months 11-12); training used Oct 2025-Jul 2026 only",
        "fraud": fr, "fusion": {k: bundle.fusion[k] for k in ("weights", "t_yellow", "t_red", "source")},
        "fusion_validation": bundle.fusion.get("val"), "fusion_prompt_defaults_validation": bundle.fusion.get("prompt_defaults_val"),
        "late_payment": lt, "cash": ce, "plots": plots,
    }
    ext = s.models_dir / "extraction_eval.json"
    if ext.exists():
        metrics["extraction"] = json.loads(ext.read_text())
    if args.seeds:
        seeds = [int(x) for x in args.seeds.split(",")]
        print(f"robustness over seeds {seeds} ...")
        metrics["robustness"] = robustness(seeds, lo, hi)
    else:
        old = s.models_dir / "metrics.json"
        if old.exists():
            prev = json.loads(old.read_text())
            if "robustness" in prev:
                metrics["robustness"] = prev["robustness"]
    (s.models_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, default=float))
    _print(metrics)
    print(f"done in {time.time() - t0:.0f}s -> models/metrics.json, docs/{', docs/'.join(plots)}")


def _print(m: dict) -> None:
    f = m["fraud"]
    n, b = f["nigraan"], f["baseline_rules_only"]
    print(f"\nFRAUD  months {m['test_months']}: {f['n_payments']} payments, {f['n_fraud']} frauds, {f['ms_per_payment']} ms/payment")
    print(f"{'':24}{'Nigraan':>10}{'Rules-only':>12}")
    for k in ("recall", "recall_red", "precision_red", "false_alarm_rate", "pr_auc"):
        nv, bv = n[k], b[k]
        print(f"{k:24}{(nv if nv is not None else float('nan')):>10.3f}{(bv if bv is not None else float('nan')):>12.3f}")
    print(f"{'rupees protected (red)':24}{n['rupees_protected_red'] / 100:>10,.0f}{b['rupees_protected_red'] / 100:>12,.0f}  of {n['rupees_fraud'] / 100:,.0f}")
    print("per type (caught/n): " + ", ".join(f"{t} {v['caught']}/{v['n']}" for t, v in n["per_type"].items()))
    print("baseline per type:   " + ", ".join(f"{t} {v['caught']}/{v['n']}" for t, v in b["per_type"].items()))
    print("ablation: " + ", ".join(f"{k} recall {v['recall']:.2f} FAR {v['false_alarm_rate']:.3f}" for k, v in f["ablation"].items()))
    lt = m["late_payment"]
    print(f"\nLATE PAYMENTS (n={lt['n_test']}, late rate {lt['late_rate_test']:.2f})")
    for k, v in lt["models"].items():
        print(f"  {k:9} PR-AUC {v['pr_auc']:.3f}  P@top20 {v['precision_top20']:.3f}  R@top20 {v['recall_top20']:.3f}  Brier {v['brier']:.3f}")
    c = m["cash"]
    print(f"\nCASH receipts backtest ({len(c['origins'])} origins x {c['horizon_weeks']} weeks)")
    for k in ("median_delay", "due_date"):
        print(f"  {k:13} MAE Rs {c[k]['mae_rupees_per_week']:,.0f}/week  WAPE {c[k]['wape']:.3f}")
    if "robustness" in m:
        a = m["robustness"]["aggregate"]
        print(f"\nROBUSTNESS seeds {m['robustness']['seeds']}: recall {a['recall']['mean']:.2f} "
              f"[{a['recall']['min']:.2f}-{a['recall']['max']:.2f}], FAR {a['false_alarm_rate']['mean']:.3f}")
        pt = m["robustness"]["pooled"]["per_type"]
        print("  pooled per type: " + ", ".join(f"{t} {v['caught']}/{v['n']}" for t, v in pt.items()))


if __name__ == "__main__":
    main()
