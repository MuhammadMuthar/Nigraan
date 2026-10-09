"""Planted frauds. Ground truth goes to labels.csv only (see generate_company._labels_and_cases).

F1 duplicate / near-duplicate invoice     F2 bank-detail change scam      F3 shell vendor
F4 inflated invoice (unit price 1.5-3x)    F5 split payment under limit    F7 self-approval at night/holiday
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import numpy as np

from app.services.calendar_pk import PUBLIC_HOLIDAYS, is_off_day, next_business_day, to_utc
from data_gen import names as N

SHARES = {"F1": 0.26, "F2": 0.14, "F3": 0.16, "F4": 0.16, "F5": 0.14, "F7": 0.14}
DEMO_NAMES = {"Al-Noor Traders", "Madina Dairies", "Shan Packages", "Ravi Goods Transport", "Hilal Cosmetics",
              "Gill Goods Transport"}
GOODS = {"dairy", "beverages", "snacks", "cooking_oil", "personal_care", "staples", "packaging"}


def strat_dates(g, k: int, lo: date, hi: date) -> list[date]:
    span = (hi - lo).days
    return [lo + timedelta(days=int(span * (i + g.u()) / k)) for i in range(k)]


def plant_all(g) -> None:
    est_payments = int(len(g.w.invoices) * 0.92)  # pre-window and still-open invoices are not paid in-window
    n_fraud = round(g.fraud_rate * est_payments / (1 - g.fraud_rate))
    counts = {k: max(4, round(n_fraud * s)) for k, s in SHARES.items()}
    g.fraud_plan = counts
    lo, hi = g.start + timedelta(days=35), g.window_end - timedelta(days=10)
    plant_f1(g, counts["F1"], lo, hi)
    plant_f2(g, max(4, round(counts["F2"] / 1.5)), lo, hi)  # ~1.5 payments hit each fraudulent account
    plant_f3(g, counts["F3"], g.start + timedelta(days=20), hi - timedelta(days=30))
    plant_f4(g, counts["F4"], lo, hi)
    plant_f5(g, counts["F5"], lo, hi)
    plant_f7(g, counts["F7"], lo, hi)


def _vendor_invoices_before(g, vid: int, t: datetime) -> list[dict]:
    return [i for i in g.w.invoices if i["vendor_id"] == vid and i["received_at"] < t and not i.get("_fraud")]


def _clone_lines(lines: list[dict]) -> list[dict]:
    return [dict(item_id=l["item_id"], description=l["description"], qty=l["qty"], unit_price=l["unit_price"],
                 amount=l["amount"]) for l in lines]


def number_variant(no: str, kind: str) -> str:
    m = re.match(r"^(.*?)(\d+)$", no)
    if not m:
        return no + "A"
    prefix, digits = m.group(1), m.group(2)
    if kind == "pad":
        return f"{prefix}0{digits}"
    if kind == "nodash":
        return re.sub(r"[-/ ]", "", prefix) + digits if re.search(r"[-/ ]", prefix) else f"{prefix}-{digits}"
    if kind == "prefix":
        return digits if prefix else f"No. {digits}"
    if kind == "suffix":
        return f"{no}A"
    return no  # exact


def plant_f1(g, k: int, lo: date, hi: date) -> None:
    for i, T in enumerate(strat_dates(g, k, lo, hi)):
        t0 = g.at(T, 0, 0.01)
        cands = [inv for inv in g.w.invoices
                 if not inv.get("_fraud") and g.vendor_meta[inv["vendor_id"]]["tier"] in ("A", "B")
                 and g.w.vendors[inv["vendor_id"] - 1]["name"] not in DEMO_NAMES
                 and timedelta(days=10) <= (t0 - inv["received_at"]) <= timedelta(days=60)
                 and inv["total"] < g.approval_limit * 1.4]
        if not cands:
            continue
        orig = g.pick(cands)
        kind = str(g.rng.choice(["exact", "pad", "nodash", "prefix", "suffix", "renumber"], p=[.18, .22, .18, .18, .14, .1]))
        lines = _clone_lines(orig["_lines"])
        if g.chance(0.5):
            small = [l for l in lines if l["unit_price"] < 0.008 * orig["subtotal"]]
            if small:
                l = small[0]
                dq = 1.0 if (g.chance(0.5) or l["qty"] <= 1) else -1.0
                l["qty"] += dq
                l["amount"] = int(l["unit_price"] * l["qty"])
        shift = g.ri(1, 5) * (1 if g.chance(0.6) else -1)
        inv_date = orig["invoice_date"] + timedelta(days=shift)
        received = g.at(next_business_day(T), 10, 18)
        rate = orig["tax"] / orig["subtotal"] if orig["subtotal"] else 0
        no = g.next_invoice_no(orig["vendor_id"]) if kind == "renumber" else number_variant(orig["invoice_no"], kind)
        g.add_invoice(orig["vendor_id"], inv_date, lines, received_at=received,
                      invoice_no=no, tax_rate=rate,
                      fraud=dict(type="F1", group=f"F1-{i:03d}", dup_of=orig["id"], variant=kind))


def _run_monday_for(due: date, received: datetime, g) -> date:
    """The weekly run (Monday) that would pay an invoice with this due date."""
    from app.services.calendar_pk import to_utc as _u
    m = due - timedelta(days=6)
    m = m + timedelta(days=(7 - m.weekday()) % 7)
    while True:
        prep = m - timedelta(days=3)
        while is_off_day(prep):
            prep -= timedelta(days=1)
        if received <= _u(datetime.combine(prep, datetime.min.time()) + timedelta(hours=19)):
            return m
        m += timedelta(days=7)


def plant_f2(g, k: int, lo: date, hi: date) -> None:
    users = g.users
    changers = [users["kashif"]["id"]] * 5 + [users["bilal"]["id"]] * 3 + [users["sana"]["id"]] * 2
    used_vendors: set[int] = set()
    for i, T in enumerate(strat_dates(g, k, lo, hi)):
        t0 = g.at(T, 0, 0.01)
        vendors = [v for v in g.w.vendors if v["id"] not in g.legit_change_vendors and v["id"] not in used_vendors
                   and v["name"] not in DEMO_NAMES and g.vendor_meta[v["id"]]["tier"] in ("B", "C")
                   and v["category"] != "services"]
        g.rng.shuffle(vendors)
        done = False
        for v in vendors:
            hist = _vendor_invoices_before(g, v["id"], t0)
            if len(hist) < 8:
                continue
            med = float(np.median([h["total"] for h in hist]))
            targets = [inv for inv in g.w.invoices if inv["vendor_id"] == v["id"] and not inv.get("_fraud")
                       and T <= inv["due_date"] <= T + timedelta(days=21) and inv["total"] >= 1.3 * med]
            if targets:
                target = targets[0]
            else:
                d = T - timedelta(days=v["payment_terms_days"]) + timedelta(days=g.ri(0, 6))
                d = next_business_day(d)
                target = g.add_invoice(v["id"], d, g.make_lines(v["id"], d, n_lines=g.vendor_meta[v["id"]]["max_lines"],
                                                                 scale=g.u(2.2, 3.2)))
            R = _run_monday_for(target["due_date"], target["received_at"], g)
            prep = R - timedelta(days=3)
            while is_off_day(prep):
                prep -= timedelta(days=1)
            change_day = prep - timedelta(days=g.ri(1, 6))
            while is_off_day(change_day):
                change_day -= timedelta(days=1)
            if change_day < g.start + timedelta(days=20):
                continue
            by = changers[g.ri(0, len(changers) - 1)]
            src = "email" if g.chance(0.7) else "phone"
            if g.chance(0.25):  # stealth: forged letter processed by the usual vendor-master clerk
                by, src = users["sana"]["id"], "vendor_letter"
            original = g.active_account(v["id"], g.at(change_day, 9, 9.1))
            acc = g.change_account(v["id"], g.at(change_day, 9.5, 19), by, src, approved_by=None, fraud=True)
            acc["_group"] = f"F2-{i:03d}"
            # vendor phones about the missing payment a few days later; account reverted before the next run
            revert_at = g.at(next_business_day(R + timedelta(days=g.ri(2, 3))), 10, 17)
            g.change_account(v["id"], revert_at, users["sana"]["id"], "vendor_letter", iban=original["_iban"],
                             bank=original["bank_name"], approved_by=users["bilal"]["id"])
            acc["is_blocked"] = True
            acc["blocked_at"] = revert_at
            used_vendors.add(v["id"])
            done = True
            break
        if not done:
            continue


SHELL_FIRST = ["Ali", "Prime", "Star", "Smart", "Global", "United", "Classic", "Elite", "Venus", "Apex", "Zenith",
               "Fast", "Metro", "Unique"]
SHELL_KIND = ["Enterprises", "Solutions", "Services", "Traders", "Associates", "Consultants"]


def plant_f3(g, n_payments: int, lo: date, hi: date) -> None:
    users = g.users
    n_shells = max(2, round(n_payments / 3))
    excluded = {"Imran Butt", "Waqas Gill"} | {u["name"] for u in g.w.users}
    emps = [e for e in g.w.employees if e["department"] in ("Purchase", "Warehouse", "Sales", "Delivery")
            and e["name"] not in excluded]
    per_shell = [n_payments // n_shells + (1 if j < n_payments % n_shells else 0) for j in range(n_shells)]
    existing = {v["name"] for v in g.w.vendors}
    for i, c in enumerate(strat_dates(g, n_shells, lo, hi)):
        creator = users["sana"]["id"] if g.chance(0.6) else users["kashif"]["id"]
        if i == 1:
            emp = g.emp_by_name["Kashif Mehmood"]
            link = "address"
            creator = users["kashif"]["id"]
        else:
            emp = g.pick(emps)
            link = str(g.rng.choice(["phone", "bank", "address"], p=[.4, .3, .3]))
        while True:
            name = f"{g.pick(SHELL_FIRST)} {g.pick(SHELL_KIND)}"
            if name not in existing:
                existing.add(name)
                break
        created = g.at(next_business_day(c), 10, 18)
        stealth = g.chance(0.25)  # registered, taxed, concrete line items: only the relationship gives it away
        v = g._make_vendor(
            name, "services", created, creator, "C",
            phone=emp["phone"] if link == "phone" else None,
            address=emp["address"] if link == "address" else None,
            iban=emp["_iban"] if link == "bank" else None,
            registered=stealth, terms=7,
        )
        if g.chance(0.5) and not stealth:
            v["ntn"] = f"{g.ri(1000000, 9999999)}-{g.ri(0, 9)}"
        g.accounts_by_vendor[v["id"]] = [a for a in g.w.vendor_bank_accounts if a["vendor_id"] == v["id"]]
        meta = g.vendor_meta[v["id"]]
        meta.update(items=[], price_factor=1.0, rate=0, scale=1, max_lines=2)
        d = c + timedelta(days=g.ri(5, 15))
        last = d
        for j in range(per_shell[i]):
            d = next_business_day(d)
            if stealth:
                svc = [it for it in g.w.items if it["category"] == "services"]
                lines = []
                for it in [svc[int(k)] for k in g.rng.choice(len(svc), size=g.ri(1, 2), replace=False)]:
                    price = int(round(g.price_at(it["id"], d) * g.u(1.0, 1.15))) * 100
                    qty = float(g.ri(1, 6))
                    lines.append(dict(item_id=it["id"], description=it["name"], qty=qty, unit_price=price,
                                      amount=int(price * qty)))
                g.add_invoice(v["id"], d, lines, tax_rate=0.18, terms=7,
                              fraud=dict(type="F3", group=f"F3-{i:03d}", link=link, employee_id=emp["id"]))
                last = d
                d = d + timedelta(days=g.ri(7, 21))
                continue
            amount = int(round(g.u(120_000, 480_000) / 5000)) * 5000
            descs = list(g.rng.choice(N.VAGUE_ITEMS, size=g.ri(1, 2), replace=False))
            if len(descs) == 2:
                a1 = int(round(amount * g.u(0.4, 0.7) / 5000)) * 5000
                parts = [a1, amount - a1]
            else:
                parts = [amount]
            lines = [dict(item_id=None, description=str(desc), qty=1.0, unit_price=p * 100, amount=p * 100)
                     for desc, p in zip(descs, parts)]
            g.add_invoice(v["id"], d, lines, tax_rate=0.0, terms=7,
                          fraud=dict(type="F3", group=f"F3-{i:03d}", link=link, employee_id=emp["id"]))
            last = d
            d = d + timedelta(days=g.ri(7, 21))
        discovered = last + timedelta(days=g.ri(40, 70))
        if discovered < g.as_of and last <= g.audited_through:
            v["status"] = "blocked"
            v["blocked_at"] = g.at(next_business_day(discovered), 11, 16)


def plant_f4(g, k: int, lo: date, hi: date) -> None:
    for i, T in enumerate(strat_dates(g, k, lo, hi)):
        t0 = g.at(T, 0, 0.01)
        cands = [inv for inv in g.w.invoices
                 if not inv.get("_fraud") and g.w.vendors[inv["vendor_id"] - 1]["category"] in GOODS
                 and g.w.vendors[inv["vendor_id"] - 1]["name"] not in DEMO_NAMES
                 and timedelta(0) <= inv["received_at"] - t0 <= timedelta(days=10)
                 and inv["subtotal"] < 700_000 * 100 and any(l["item_id"] for l in inv["_lines"])]
        cands = [c for c in cands if len(_vendor_invoices_before(g, c["vendor_id"], c["received_at"])) >= 8]
        if not cands:
            continue
        inv = g.pick(cands)
        lines = [l for l in inv["_lines"] if l["item_id"]]
        n = 1 if len(lines) == 1 or g.chance(0.6) else 2
        for l in lines[:n]:
            factor = g.u(1.3, 3.0)
            l["unit_price"] = int(round(l["unit_price"] * factor / 100)) * 100
            l["amount"] = int(l["unit_price"] * l["qty"])
        g.recompute_totals(inv)
        inv["_fraud"] = dict(type="F4", group=f"F4-{i:03d}")


def _scale_lines_to(g, lines: list[dict], target_subtotal: int) -> list[dict]:
    cur = sum(l["amount"] for l in lines)
    s = target_subtotal / cur
    for l in lines:
        l["qty"] = float(max(1, int(round(l["qty"] * s))))
        l["amount"] = int(l["unit_price"] * l["qty"])
    # walk down until under target
    lines.sort(key=lambda l: -l["unit_price"])
    while sum(l["amount"] for l in lines) > target_subtotal:
        for l in lines:
            if l["qty"] > 1 and sum(x["amount"] for x in lines) > target_subtotal:
                l["qty"] -= 1
                l["amount"] = int(l["unit_price"] * l["qty"])
        if all(l["qty"] <= 1 for l in lines):
            break
    return lines


def plant_f5(g, n_payments: int, lo: date, hi: date) -> None:
    users = g.users
    sizes = []
    while sum(sizes) < n_payments:
        sizes.append(int(g.rng.choice([2, 3, 4], p=[.45, .35, .2])))
    vendors = [v for v in g.w.vendors if g.vendor_meta[v["id"]]["tier"] in ("B", "C") and v["name"] not in DEMO_NAMES
               and v["category"] in GOODS | {"logistics"}]
    for i, (T, size) in enumerate(zip(strat_dates(g, len(sizes), lo, hi), sizes)):
        v = g.pick(vendors)
        creator = users["kashif"]["id"] if g.chance(0.5) else users["sana"]["id"]
        base = g.at(next_business_day(T), 10, 13)
        lo_f, hi_f = (0.78, 0.90) if g.chance(0.2) else (0.90, 0.985)  # some splits stay further under the limit
        for j in range(size):
            target_total = int(g.u(lo_f, hi_f) * g.approval_limit)
            rate = 0.18 if g.vendor_meta[v["id"]].get("registered", True) else 0.0
            sub = int(target_total / (1 + rate))
            d = T + timedelta(days=j // 2)
            lines = _scale_lines_to(g, g.make_lines(v["id"], d, n_lines=g.vendor_meta[v["id"]]["max_lines"]), sub)
            received = base + timedelta(hours=j * g.u(2, 20))
            g.add_invoice(v["id"], d, lines, received_at=received, created_by=creator, terms=3,
                          fraud=dict(type="F5", group=f"F5-{i:03d}"))


def plant_f7(g, k: int, lo: date, hi: date) -> None:
    bilal = g.users["bilal"]["id"]
    vendors = [v for v in g.w.vendors if g.vendor_meta[v["id"]]["tier"] in ("B", "C") and v["name"] not in DEMO_NAMES
               and v["category"] != "services"]
    for i, T in enumerate(strat_dates(g, k, lo, hi)):
        v = g.pick(vendors)
        t0 = g.at(T, 0, 0.01)
        hist = _vendor_invoices_before(g, v["id"], t0)
        med = float(np.median([h["total"] for h in hist])) if hist else 150_000 * 100
        target_total = int(min(g.u(1.2, 3.0) * med, 0.95 * g.approval_limit))
        r = g.rng.random()
        if r < 0.45:
            t = g.at(T, 23, 27.5)  # 23:00 - 03:30
        elif r < 0.7:
            t = g.at(next_business_day(T), 19.5, 21.5)  # stealth: weekday evening
        else:
            d = T
            while not is_off_day(d):
                d += timedelta(days=1)
            t = g.at(d, 11, 18)
        rate = 0.18 if g.vendor_meta[v["id"]].get("registered", True) else 0.0
        local_day = (t + timedelta(hours=5)).date()
        inv_date = local_day - timedelta(days=g.ri(0, 3))
        lines = _scale_lines_to(g, g.make_lines(v["id"], inv_date, n_lines=g.vendor_meta[v["id"]]["max_lines"]),
                                int(target_total / (1 + rate)))
        g.add_invoice(v["id"], inv_date, lines, received_at=t, created_by=bilal,
                      fraud=dict(type="F7", group=f"F7-{i:03d}", pay_created_at=t + timedelta(minutes=g.ri(5, 30)),
                                 pay_created_by=bilal, approver=bilal))
