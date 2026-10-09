"""Deterministic 13-week cash engine. Pure functions, no I/O, no ML. Fully unit-tested.

closing(day) = opening + expected receipts - scheduled outflows - approved payments, day by day.
A mid-week breach is caught because the reserve check is daily, not weekly.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

HORIZON_DAYS = 91  # 13 weeks
BASIS = ("fact", "estimate", "assumption")


@dataclass(frozen=True)
class Flow:
    day: date
    amount: int  # paisa; + receipt, - outflow
    kind: str  # receipt | outflow | payable | run_payment
    basis: str  # fact | estimate | assumption
    label: str
    ref: str | None = None


@dataclass
class DayRow:
    day: date
    inflow: int
    outflow: int
    closing: int


@dataclass
class WeekRow:
    week: int
    start: date
    end: date
    inflow: int
    outflow: int
    inflow_by_basis: dict
    outflow_by_basis: dict
    closing: int
    low: int
    low_day: date


@dataclass
class Projection:
    as_of: date
    opening: int
    reserve: int
    days: list[DayRow]
    weeks: list[WeekRow]
    low_point: int
    low_point_day: date
    first_breach: date | None
    breach_gap: int  # reserve - low point if breached else 0
    beyond_horizon: list[Flow] = field(default_factory=list)
    total_in: int = 0
    total_out: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def project(as_of: date, opening: int, reserve: int, flows: list[Flow], horizon_days: int = HORIZON_DAYS) -> Projection:
    for f in flows:
        if f.day < as_of:
            raise ValueError(f"flow dated before as-of date: {f.label} on {f.day}")
        if f.basis not in BASIS:
            raise ValueError(f"unknown basis {f.basis}")
        if not isinstance(f.amount, int):
            raise TypeError("amounts must be integer paisa")
    end = as_of + timedelta(days=horizon_days - 1)
    inside = [f for f in flows if f.day <= end]
    beyond = sorted((f for f in flows if f.day > end), key=lambda f: f.day)

    by_day_in = [0] * horizon_days
    by_day_out = [0] * horizon_days
    in_basis = [{b: 0 for b in BASIS} for _ in range(horizon_days)]
    out_basis = [{b: 0 for b in BASIS} for _ in range(horizon_days)]
    for f in inside:
        i = (f.day - as_of).days
        if f.amount >= 0:
            by_day_in[i] += f.amount
            in_basis[i][f.basis] += f.amount
        else:
            by_day_out[i] += -f.amount
            out_basis[i][f.basis] += -f.amount

    days: list[DayRow] = []
    bal = opening
    breach = None
    for i in range(horizon_days):
        d = as_of + timedelta(days=i)
        bal = bal + by_day_in[i] - by_day_out[i]
        days.append(DayRow(d, by_day_in[i], by_day_out[i], bal))
        if breach is None and bal < reserve:
            breach = d
    low_row = min(days, key=lambda r: (r.closing, r.day))
    low, low_day = low_row.closing, low_row.day

    weeks: list[WeekRow] = []
    for w in range(horizon_days // 7):
        chunk = days[w * 7:(w + 1) * 7]
        lo_row = min(chunk, key=lambda r: (r.closing, r.day))
        ib = {b: sum(in_basis[w * 7 + j][b] for j in range(7)) for b in BASIS}
        ob = {b: sum(out_basis[w * 7 + j][b] for j in range(7)) for b in BASIS}
        weeks.append(WeekRow(
            week=w + 1, start=chunk[0].day, end=chunk[-1].day, inflow=sum(r.inflow for r in chunk),
            outflow=sum(r.outflow for r in chunk), inflow_by_basis=ib, outflow_by_basis=ob,
            closing=chunk[-1].closing, low=lo_row.closing, low_day=lo_row.day,
        ))
    return Projection(
        as_of=as_of, opening=opening, reserve=reserve, days=days, weeks=weeks, low_point=low,
        low_point_day=low_day, first_breach=breach, breach_gap=max(0, reserve - low) if breach else 0,
        beyond_horizon=beyond, total_in=sum(by_day_in), total_out=sum(by_day_out),
    )


def move_flow(flows: list[Flow], ref: str, new_day: date) -> list[Flow]:
    """Scenario primitive: change the date of an expected receipt. Never adds a second receipt."""
    out, moved = [], 0
    for f in flows:
        if f.ref == ref:
            out.append(Flow(new_day, f.amount, f.kind, "assumption", f.label + " (scenario date)", f.ref))
            moved += 1
        else:
            out.append(f)
    if moved != 1:
        raise KeyError(f"expected exactly one flow with ref {ref}, found {moved}")
    return out


def drop_flows(flows: list[Flow], refs: set[str]) -> list[Flow]:
    return [f for f in flows if f.ref not in refs]
