"""The live demo week: 40 invoices due in the week of the as-of date (7 fraudulent lines, one scheme
of each type F1-F5, F7) and the master-data events that precede them.

The company's opening cash is calibrated so that releasing every line would push cash below the
reserve mid-week, while blocking the planted frauds keeps it above. This is a scripted scenario on
synthetic data and is documented as such in docs/decisions.md; all model metrics come from the
separate months 11-12 backtest.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np

from app.services.calendar_pk import is_off_day, next_business_day, to_utc
from app.services.cash.engine import project
from app.services.cash.inputs import estimate_receipts, outflow_flows, payable_flows, receipt_flows, run_flows
from app.services.identity import norm_invoice_no
from data_gen.fraud_scenarios import _scale_lines_to, number_variant


def _local(y, m, d, hh, mm) -> datetime:
    return to_utc(datetime(y, m, d, hh, mm))


def plan(g) -> None:
    w = g.w
    U = {k: v for k, v in g.users.items()}
    sana, kashif, bilal = U["sana"], U["kashif"], U["bilal"]
    as_of = g.as_of
    pay_date = next_business_day(as_of + timedelta(days=1))
    vb = g.vendor_by_name

    # --- master data events before the run ---------------------------------------------------
    imran = g.emp_by_name["Imran Butt"]
    shell = g._make_vendor("Prime Solutions", "services", _local(2026, 9, 22, 11, 40), sana["id"], "C",
                           phone=imran["phone"], registered=False, terms=7, prefix="PS-")
    g.accounts_by_vendor[shell["id"]] = [a for a in w.vendor_bank_accounts if a["vendor_id"] == shell["id"]]
    g.vendor_meta[shell["id"]].update(items=[], price_factor=1.0, rate=0, scale=1, max_lines=2, next_no=1001)
    alnoor = vb["Al-Noor Traders"]
    old_acc = g.active_account(alnoor["id"], _local(2026, 10, 10, 14, 0))
    fraud_acc = g.change_account(alnoor["id"], _local(2026, 10, 10, 14, 22), kashif["id"], "email", bank="Allied",
                                 approved_by=None, fraud=True)
    fraud_acc["_demo"] = True

    specs: list[dict] = []

    def add(vendor: dict, inv_date: date, lines: list[dict], *, entered_by: dict, entered_at: datetime,
            pay_by: dict, pay_at: datetime, fraud: str | None = None, invoice_no: str | None = None,
            tax_rate: float | None = None, iban: str | None = None, terms: int | None = None, note: str = "") -> dict:
        meta = g.vendor_meta[vendor["id"]]
        if tax_rate is None:
            tax_rate = 0.18 if meta.get("registered", True) else 0.0
        sub = sum(l["amount"] for l in lines)
        tax = int(round(sub * tax_rate / 100)) * 100
        no = invoice_no or g.next_invoice_no(vendor["id"])
        acc = g.active_account(vendor["id"], pay_at)
        s = dict(
            vendor_id=vendor["id"], vendor_name=vendor["name"], vendor_ntn=vendor["ntn"], vendor_strn=vendor["strn"],
            vendor_address=vendor["address"], vendor_phone=vendor["phone"], invoice_no=no,
            invoice_no_norm=norm_invoice_no(no), invoice_date=inv_date,
            due_date=inv_date + timedelta(days=terms if terms is not None else vendor["payment_terms_days"]),
            lines=[dict(description=l["description"], qty=l["qty"], unit_price=l["unit_price"], amount=l["amount"],
                        item_id=l.get("item_id")) for l in lines],
            subtotal=sub, tax=tax, total=sub + tax, iban=iban or acc["_iban"], entered_by=entered_by["email"],
            entered_at=entered_at, payment_created_by=pay_by["email"], payment_created_at=pay_at, fraud=fraud,
            note=note,
        )
        specs.append(s)
        return s

    def office(d: date, h0=10.0, h1=17.5) -> datetime:
        return g.at(d, h0, h1)

    # --- legit invoices -------------------------------------------------------------------------
    special = {"Al-Noor Traders", "Shan Packages", "Ravi Goods Transport", "Hilal Cosmetics", "Prime Solutions"}
    shells = {v["id"] for v in w.vendors if g.vendor_meta[v["id"]].get("items") == []}
    pool = [v for v in w.vendors if v["name"] not in special and v["id"] not in shells and v["status"] == "active"]
    tier = lambda v: g.vendor_meta[v["id"]]["tier"]  # noqa: E731
    chosen = [v for v in pool if tier(v) == "A"]
    rest_b = [v for v in pool if tier(v) == "B" and v["name"] != "Gill Goods Transport"]
    rest_c = [v for v in pool if tier(v) == "C" and v["name"] != "Gill Goods Transport"]
    g.rng.shuffle(rest_b)
    g.rng.shuffle(rest_c)
    chosen += [vb["Gill Goods Transport"]]
    need = 33 - len(chosen)
    chosen += rest_b[: min(len(rest_b), need - 6)]
    chosen += rest_c[: 33 - len(chosen) - 1]

    # Two legit lines that deserve a second look (expected yellow): a recent, properly approved bank
    # change, and a vendor onboarded three weeks ago.
    changed = next(v for v in chosen if tier(v) == "B" and v["name"] not in ("Gill Goods Transport", "Madina Dairies"))
    g.change_account(changed["id"], _local(2026, 10, 2, 11, 10), sana["id"], "vendor_letter", approved_by=bilal["id"])
    newv = g._make_vendor("Faisal Packaging Industries", "packaging", _local(2026, 9, 24, 10, 30), sana["id"], "B",
                          terms=15)
    g.accounts_by_vendor[newv["id"]] = [a for a in w.vendor_bank_accounts if a["vendor_id"] == newv["id"]]
    pool_items = g.items_by_cat["packaging"]
    g.vendor_meta[newv["id"]].update(items=[int(x) for x in g.rng.choice(pool_items, size=4, replace=False)],
                                     price_factor=1.0, rate=4, scale=1.0, max_lines=3)
    chosen.append(newv)
    big_done = False
    for v in chosen:
        due = as_of + timedelta(days=g.ri(-3, 6))
        inv_date = due - timedelta(days=v["payment_terms_days"])
        if is_off_day(inv_date):
            inv_date = next_business_day(inv_date)
        lines = g.make_lines(v["id"], inv_date)
        if not big_done and tier(v) == "A" and v["name"] != "Madina Dairies":
            lines = g.make_lines(v["id"], inv_date, n_lines=g.vendor_meta[v["id"]]["max_lines"], scale=3.0)
            while sum(l["amount"] for l in lines) * 1.18 < g.approval_limit * 1.15:
                for l in lines:
                    l["qty"] += max(1.0, round(l["qty"] * 0.2))
                    l["amount"] = int(l["unit_price"] * l["qty"])
            big_done = True
        rd = next_business_day(inv_date + timedelta(days=g.ri(0, 2)))
        by = kashif if g.chance(0.15) else sana
        pay_at = office(date(2026, 10, 10), 10, 17.5) if by is sana else office(date(2026, 10, 9), 10, 18)
        add(v, inv_date, lines, entered_by=by, entered_at=office(rd), pay_by=by, pay_at=pay_at)

    # --- F1: near-duplicate of an invoice Madina Dairies was already paid for -------------------
    madina = vb["Madina Dairies"]
    paid = [i for i in w.invoices if i["vendor_id"] == madina["id"] and i["status"] == "paid"
            and i["received_at"].date() >= as_of - timedelta(days=90) and not i.get("_fraud")]
    orig = sorted(paid, key=lambda i: i["received_at"])[-1]
    lines = [dict(l) for l in orig["_lines"]]
    cheapest = min(lines, key=lambda l: l["unit_price"])
    if cheapest["unit_price"] < 0.009 * orig["subtotal"]:
        cheapest["qty"] += 1
        cheapest["amount"] = int(cheapest["unit_price"] * cheapest["qty"])
    add(madina, orig["invoice_date"] + timedelta(days=3), lines, invoice_no=number_variant(orig["invoice_no"], "pad"),
        entered_by=sana, entered_at=_local(2026, 10, 8, 12, 40), pay_by=sana, pay_at=_local(2026, 10, 10, 11, 5),
        fraud="F1", note=f"near-duplicate of {orig['invoice_no']} (invoice id {orig['id']})")

    # --- F2: bank details changed 2 days ago by email, then a large payment ---------------------
    hist = [i["total"] for i in w.invoices if i["vendor_id"] == alnoor["id"]]
    med = float(np.median(hist))
    d2 = as_of + timedelta(days=3) - timedelta(days=alnoor["payment_terms_days"])
    d2 = next_business_day(d2)
    lines = g.make_lines(alnoor["id"], d2, n_lines=g.vendor_meta[alnoor["id"]]["max_lines"])
    lines = _scale_lines_to(g, lines, int(3.1 * med / 1.18))
    add(alnoor, d2, lines, entered_by=kashif, entered_at=_local(2026, 10, 7, 12, 20), pay_by=kashif,
        pay_at=_local(2026, 10, 10, 16, 5), fraud="F2", iban=fraud_acc["_iban"],
        note="vendor bank account changed 10 Oct by email; amount ~3x usual")

    # --- F3: shell vendor sharing the purchase officer's phone ----------------------------------
    add(shell, date(2026, 10, 2), [
        dict(item_id=None, description="Consultancy services - market survey (Sep 2026)", qty=1.0,
             unit_price=300_000 * 100, amount=300_000 * 100),
        dict(item_id=None, description="Coordination services", qty=1.0, unit_price=150_000 * 100,
             amount=150_000 * 100),
    ], tax_rate=0.0, terms=7, entered_by=sana, entered_at=_local(2026, 10, 7, 11, 15), pay_by=sana,
        pay_at=_local(2026, 10, 10, 12, 30), fraud="F3", note="vendor phone = employee Imran Butt (Purchase)")

    # --- F4: inflated unit price -----------------------------------------------------------------
    shan = vb["Shan Packages"]
    d4 = next_business_day(as_of + timedelta(days=2) - timedelta(days=shan["payment_terms_days"]))
    lines = g.make_lines(shan["id"], d4, n_lines=min(3, len(g.vendor_meta[shan["id"]]["items"])))
    target = max(lines, key=lambda l: l["amount"])
    target["unit_price"] = int(round(target["unit_price"] * 2.4 / 100)) * 100
    target["amount"] = int(target["unit_price"] * target["qty"])
    add(shan, d4, lines, entered_by=sana, entered_at=_local(2026, 10, 6, 14, 10), pay_by=sana,
        pay_at=_local(2026, 10, 10, 13, 45), fraud="F4", note=f"unit price of {target['description']} x2.4")

    # --- F5: split payment just under the approval limit -----------------------------------------
    ravi = vb["Ravi Goods Transport"]
    for j, (frac, ent, pay) in enumerate([(0.972, _local(2026, 10, 8, 16, 10), _local(2026, 10, 9, 12, 0)),
                                          (0.986, _local(2026, 10, 9, 11, 30), _local(2026, 10, 9, 12, 4))]):
        rate = 0.18 if g.vendor_meta[ravi["id"]].get("registered", True) else 0.0
        d5 = date(2026, 10, 7) + timedelta(days=j)
        lines = _scale_lines_to(g, g.make_lines(ravi["id"], d5, n_lines=g.vendor_meta[ravi["id"]]["max_lines"]),
                                int(frac * g.approval_limit / (1 + rate)))
        add(ravi, d5, lines, terms=3, entered_by=kashif, entered_at=ent, pay_by=kashif, pay_at=pay, fraud="F5",
            note="two invoices just under the Rs 5,00,000 approval limit within 24 h")

    # --- F7: approver enters and wants to self-approve at night on a weekend ---------------------
    hilal = vb["Hilal Cosmetics"]
    hh = [i["total"] for i in w.invoices if i["vendor_id"] == hilal["id"]]
    target_total = min(2.2 * float(np.median(hh)), 0.9 * g.approval_limit)
    rate = 0.18 if g.vendor_meta[hilal["id"]].get("registered", True) else 0.0
    lines = _scale_lines_to(g, g.make_lines(hilal["id"], date(2026, 10, 9), n_lines=g.vendor_meta[hilal["id"]]["max_lines"]),
                            int(target_total / (1 + rate)))
    add(hilal, date(2026, 10, 9), lines, entered_by=bilal, entered_at=_local(2026, 10, 10, 23, 52), pay_by=bilal,
        pay_at=_local(2026, 10, 10, 23, 58), fraud="F7", note="entered by the approver at 23:52 on a Saturday")

    order = list(g.rng.permutation(len(specs)))
    specs = [specs[i] for i in order]
    for k, s in enumerate(specs, start=1):
        slug = "".join(c if c.isalnum() else "_" for c in s["vendor_name"].lower()).strip("_")
        s["seq"] = k
        s["file"] = f"{k:02d}_{slug}_{''.join(c if c.isalnum() else '-' for c in s['invoice_no'])}.pdf"

    # --- calibrate opening cash ------------------------------------------------------------------
    f = w.frames()
    names = {c["id"]: c["name"] for c in w.customers}
    base = (receipt_flows(estimate_receipts(f["receivables"], as_of), names)
            + outflow_flows(f["scheduled_outflows"], as_of)
            + payable_flows(f["invoices"], f["payments"], as_of))
    all_lines = [dict(id=i, amount=s["total"], pay_date=pay_date, label=s["vendor_name"]) for i, s in enumerate(specs)]
    legit_lines = [l for l, s in zip(all_lines, specs) if not s["fraud"]]
    pa = project(as_of, 0, 0, base + run_flows(all_lines))
    pb = project(as_of, 0, 0, base + run_flows(legit_lines))
    m_a1 = min(r.closing for r in pa.days[:7])
    m_b_all = min(r.closing for r in pb.days)
    # O_max: largest opening at which releasing everything still dips below the reserve in week 1
    # O_min: smallest opening at which blocking the frauds keeps all 13 weeks above the reserve
    o_max = g.reserve - m_a1 - 50_000_00
    o_min = g.reserve - m_b_all + 50_000_00
    opening = (o_max + o_min) / 2 if o_min <= o_max else o_min
    opening = int(round(opening / 100_000)) * 100_000  # whole Rs 1,000
    w.companies[0]["opening_cash"] = opening
    check_b = project(as_of, opening, g.reserve, base + run_flows(legit_lines))
    check_a = project(as_of, opening, g.reserve, base + run_flows(all_lines))
    w.demo_week = dict(
        run_date=as_of, pay_date=pay_date, invoices=specs, fraud_account_id=fraud_acc["id"], shell_vendor_id=shell["id"],
        calibration=dict(opening=opening, low_all_lines=check_a.low_point, breach_all_lines=str(check_a.first_breach),
                         low_frauds_blocked=check_b.low_point, breach_frauds_blocked=str(check_b.first_breach)),
    )
