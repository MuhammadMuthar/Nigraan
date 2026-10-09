"""Fusion (section 6.5): score = 100 x max(rule_hit, w_x*p_xgb + w_a*a_iso + w_d*d_dup + w_g*g_graph).

The weighted sum is clipped to [0, 1] and mapped piecewise-linearly so the tuned thresholds land on
the fixed UI bands: t_yellow -> 40, t_red -> 75. The mapping is monotone, so ranking metrics are
unchanged. Weights and thresholds are tuned on months 9-10 (see ml/train_all.py).
"""
from __future__ import annotations

ENGINES = ("risk_model", "anomaly", "duplicate", "graph")
YELLOW, RED = 40, 75


def rescale(raw: float, t_yellow: float, t_red: float) -> float:
    raw = min(max(raw, 0.0), 1.0)
    if raw < t_yellow:
        return YELLOW * raw / t_yellow
    if raw < t_red:
        return YELLOW + (RED - YELLOW) * (raw - t_yellow) / (t_red - t_yellow)
    return RED + (100 - RED) * (raw - t_red) / max(1 - t_red, 1e-9)


def decision_for(score: int) -> str:
    if score >= RED:
        return "blocked"
    if score >= YELLOW:
        return "review"
    return "allow"


def fuse(signals: dict[str, float], rule_hit: float, fusion: dict) -> tuple[int, float, dict[str, float]]:
    w = fusion["weights"]
    contributions = {e: w.get(e, 0.0) * float(signals.get(e, 0.0)) for e in ENGINES}
    raw = min(1.0, sum(contributions.values()))
    scaled = rescale(raw, fusion["t_yellow"], fusion["t_red"])
    score = int(round(max(100 * rule_hit, scaled)))
    return min(score, 100), raw, contributions
