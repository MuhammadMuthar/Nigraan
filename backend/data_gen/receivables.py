"""Customer receivables with hidden behaviour profiles (punctual, chronic, seasonal, deteriorating, new)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

import numpy as np

from app.services.calendar_pk import near_eid, next_business_day
from data_gen import names as N

SEGMENTS = {
    "kiryana": dict(n=38, terms=[15, 15, 30], size=(40_000, 160_000), rate=(2.5, 5.0)),
    "superstore": dict(n=16, terms=[30, 30, 45], size=(150_000, 550_000), rate=(2.0, 4.0)),
    "wholesaler": dict(n=16, terms=[30, 45, 45], size=(300_000, 1_200_000), rate=(1.5, 3.5)),
    "pharmacy": dict(n=10, terms=[15, 30], size=(50_000, 200_000), rate=(1.5, 3.0)),
}
PROFILES = ["punctual", "chronic", "seasonal", "deteriorating"]
PROFILE_P = [0.44, 0.22, 0.17, 0.17]
CITIES = ["Lahore"] * 8 + ["Sheikhupura", "Kasur", "Gujranwala"]


def _delay(g, profile: str, due: date, progress: float) -> int:
    if profile == "punctual":
        d = g.rng.normal(-3, 3)
        if g.chance(0.1):
            d = g.ri(1, 12)
    elif profile == "chronic":
        d = g.rng.lognormal(np.log(18), 0.5) if g.chance(0.88) else g.rng.normal(-2, 2)
    elif profile == "seasonal":
        d = g.rng.normal(-3, 3)
        if near_eid(due, before=20, after=12) or due.month == 6:
            d += g.ri(14, 35)
        elif g.chance(0.08):
            d = g.ri(1, 10)
    else:  # deteriorating
        d = g.rng.normal(-4 + 38 * progress, 5)
    return int(round(d))


def generate(g) -> None:
    w = g.w
    first_day = g.start - timedelta(days=90)  # opening history so month-1 features have context
    used = set()
    customers = []
    for seg, spec in SEGMENTS.items():
        for _ in range(spec["n"]):
            while True:
                name = f"{g.pick(N.CUSTOMER_FIRST)} {g.pick(N.CUSTOMER_SEGMENTS[seg])}"
                if name not in used:
                    used.add(name)
                    break
            customers.append((name, seg))
    order = list(g.rng.permutation(len(customers)))
    n_new = 8
    for rank, idx in enumerate(order):
        name, seg = customers[idx]
        spec = SEGMENTS[seg]
        cid = g.nid("customers")
        is_new = rank < n_new
        profile = PROFILES[int(g.rng.choice(len(PROFILES), p=PROFILE_P))]
        created = g.start + timedelta(days=g.ri(220, 330)) if is_new else first_day - timedelta(days=g.ri(30, 900))
        w.customers.append(dict(id=cid, name=name, city=g.pick(CITIES), segment=seg,
                                terms_days=int(g.pick(spec["terms"])), phone=g._new_phone(),
                                created_at=created))
        w.customer_profiles[cid] = ("new/" if is_new else "") + profile
        g.__dict__.setdefault("_cust_meta", {})[cid] = dict(
            profile=profile, rate=g.u(*spec["rate"]), size=g.u(*spec["size"]))

    # Monthly purchases, to size sales at ~12% gross margin over cost.
    purchases = defaultdict(int)
    for inv in w.invoices:
        purchases[(inv["invoice_date"].year, inv["invoice_date"].month)] += inv["subtotal"]
    raw = []
    for c in w.customers:
        meta = g._cust_meta[c["id"]]
        d = max(first_day, c["created_at"])
        while True:
            rate = meta["rate"] / 30.4 * g.seasonal_factor(d)
            d = d + timedelta(days=max(1, int(round(g.rng.exponential(1 / rate)))))
            d = next_business_day(d)
            if d >= g.as_of:
                break
            amt = meta["size"] * g.rng.lognormal(0, 0.35)
            raw.append([c, d, amt])
    # scale so monthly sales ~ 1.12 x purchases (window months only)
    sales = defaultdict(float)
    for c, d, amt in raw:
        sales[(d.year, d.month)] += amt
    win = [k for k in purchases if g.start <= date(k[0], k[1], 1) <= g.window_end]
    ratio = sum(purchases[k] / 100 for k in win) * 1.12 / max(1.0, sum(sales[k] for k in win))
    raw.sort(key=lambda r: r[1])
    seq = 10001
    span = (g.as_of - g.start).days
    for c, d, amt in raw:
        meta = g._cust_meta[c["id"]]
        amount = int(round(amt * ratio / 10)) * 10 * 100
        terms = c["terms_days"]
        due = d + timedelta(days=terms)
        progress = max(0.0, (d - g.start).days / span)
        delay = _delay(g, meta["profile"], due, progress)
        paid = next_business_day(max(d + timedelta(days=1), due + timedelta(days=delay)))
        disputed = 0
        if g.chance(0.025):
            disputed = int(round(amount * g.u(0.1, 0.3) / 10000)) * 10000
        rid = g.nid("receivables")
        is_open = paid >= g.as_of
        w.receivables.append(dict(
            id=rid, customer_id=c["id"], invoice_no=f"BD-S-{seq}", issue_date=d, due_date=due, terms_days=terms,
            amount=amount, paid_date=None if is_open else paid,
            paid_amount=None if is_open else amount - disputed, disputed_amount=disputed if is_open else 0,
        ))
        w.receivable_truth.append(dict(receivable_id=rid, true_paid_date=paid, profile=w.customer_profiles[c["id"]],
                                       late=int(paid > due)))
        seq += 1
