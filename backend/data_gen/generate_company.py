"""Synthetic company generator: Bismillah Distributors (fictional), Lahore, FMCG distribution.

    python -m data_gen.generate_company --seed 42 --months 12 --fraud-rate 0.025

Builds 12 months of seeded history (vendors, invoices, weekly payment runs, employees, customers,
receivables), plants frauds F1-F7 and writes the hidden ground truth to data_out/labels.csv.
The app never reads labels.csv; it only sees the confirmed historical cases (months 1-10).
"""
from __future__ import annotations

import argparse
import math
from collections import defaultdict
from datetime import date, datetime, time, timedelta

import numpy as np

from app.services.calendar_pk import PUBLIC_HOLIDAYS, is_off_day, near_eid, next_business_day, to_utc
from app.services.identity import hash_id, last4, make_pk_iban, norm_address, norm_invoice_no, norm_phone
from data_gen import names as N
from data_gen.world import World

START = date(2025, 10, 1)
AS_OF = date(2026, 10, 12)
TAX_RATE = 0.18
QTY_FACTOR = 0.4


def rs(rupees: float) -> int:
    """Rupees -> paisa (whole rupees, as on real invoices)."""
    return int(round(rupees)) * 100


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def month_index(d: date) -> int:
    """1-based month of the data window (Oct 2025 = 1)."""
    return (d.year - START.year) * 12 + d.month - START.month + 1


class Generator:
    def __init__(self, seed: int = 42, months: int = 12, fraud_rate: float = 0.025, as_of: date = AS_OF):
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.months = months
        self.fraud_rate = fraud_rate
        self.as_of = as_of
        self.start = START
        self.window_end = add_months(START, months) - timedelta(days=1)
        self.hist_end = as_of - timedelta(days=1)
        self.audited_through = add_months(START, 10) - timedelta(days=1)
        self.w = World(seed=seed)
        self._ids: dict[str, int] = defaultdict(int)
        self.approval_limit = rs(500_000)
        self.reserve = rs(5_000_000)
        self.users: dict[str, dict] = {}
        self.vendor_meta: dict[int, dict] = {}
        self.item_drift: dict[int, float] = {}
        self.used_numbers: dict[int, set] = defaultdict(set)

    # ------------------------------------------------------------------ helpers
    def nid(self, table: str) -> int:
        self._ids[table] += 1
        return self._ids[table]

    def u(self, a: float = 0.0, b: float = 1.0) -> float:
        return float(self.rng.uniform(a, b))

    def ri(self, a: int, b: int) -> int:
        """Inclusive integer."""
        return int(self.rng.integers(a, b + 1))

    def pick(self, seq):
        return seq[int(self.rng.integers(0, len(seq)))]

    def chance(self, p: float) -> bool:
        return bool(self.rng.random() < p)

    def at(self, d: date, h0: float, h1: float) -> datetime:
        """Random local (PKT) time on day d between hours h0 and h1, returned as naive UTC."""
        hours = self.u(h0, h1)
        local = datetime.combine(d, time(0, 0)) + timedelta(hours=hours)
        return to_utc(local.replace(microsecond=0, second=int(self.rng.integers(0, 60))))

    def biz_day_on_or_after(self, d: date) -> date:
        return next_business_day(d)

    def price_at(self, item_id: int, d: date) -> float:
        item = self.w.items[item_id - 1]
        months = (d - self.start).days / 30.4
        return item["base_price"] / 100 * (1 + self.item_drift[item_id]) ** months

    # ------------------------------------------------------------------ master data
    def _company(self) -> None:
        self.w.companies.append(dict(
            id=1, name="Bismillah Distributors (fictional)", city="Lahore",
            sector="FMCG distribution", approval_limit=self.approval_limit, opening_cash=0,
            cash_reserve=self.reserve, as_of_date=self.as_of, audited_through=self.audited_through,
            data_seed=self.seed,
        ))

    def _new_phone(self, mobile: bool = True) -> str:
        if mobile:
            return f"03{self.ri(0, 4)}{self.ri(0, 9)}-{self.ri(1000000, 9999999)}"
        return f"042-3{self.ri(5000000, 7999999)}"

    def _new_iban(self, bank: str) -> str:
        acct = "".join(str(self.ri(0, 9)) for _ in range(16))
        return make_pk_iban(N.BANKS[bank], acct)

    def _home_address(self) -> str:
        return f"{self.pick(N.HOUSE_KINDS)} {self.ri(1, 480)}, Street {self.ri(1, 40)}, {self.pick(N.LAHORE_AREAS)}, Lahore"

    def _people(self) -> None:
        specials = [
            ("Sana Iqbal", "Accounts", "Accountant", "accountant", "sana@bismillah.pk"),
            ("Kashif Mehmood", "Accounts", "Accounts Assistant", "accountant", "kashif@bismillah.pk"),
            ("Bilal Ahmed", "Accounts", "Finance Manager", "approver", "bilal@bismillah.pk"),
            ("Haji Abdul Rashid", "Admin", "Managing Director", "owner", "rashid@bismillah.pk"),
            ("Imran Butt", "Purchase", "Purchase Officer", None, None),
            ("Waqas Gill", "Warehouse", "Warehouse Supervisor", None, None),
        ]
        used_names = set()
        rows = []
        for name, dept, desig, role, email in specials:
            rows.append((name, dept, desig, role, email))
            used_names.add(name)
        while len(rows) < 45:
            female = self.chance(0.2)
            first = self.pick(N.FEMALE_FIRST if female else N.MALE_FIRST)
            name = f"{first} {self.pick(N.LAST)}"
            if name in used_names:
                continue
            used_names.add(name)
            dept, desigs = self.pick(N.DEPARTMENTS)
            rows.append((name, dept, self.pick(desigs), None, None))
        self.salary_total = 0
        for name, dept, desig, role, email in rows:
            eid = self.nid("employees")
            cnic = f"35202-{self.ri(1000000, 9999999)}-{self.ri(1, 9)}"
            iban = self._new_iban(self.pick(list(N.BANKS)))
            addr = self._home_address()
            hire = date(self.ri(2012, 2025), self.ri(1, 12), self.ri(1, 28))
            if hire > self.start - timedelta(days=30):
                hire = self.start - timedelta(days=self.ri(30, 400))
            self.w.employees.append(dict(
                id=eid, name=name, department=dept, designation=desig, cnic_hash=hash_id(cnic),
                cnic_last4=last4(cnic), phone=self._new_phone(), address=addr, address_norm=norm_address(addr),
                bank_hash=hash_id(iban), bank_last4=last4(iban), status="active", hire_date=hire,
            ))
            self.w.employees[-1]["_iban"] = iban
            salary = {"Managing Director": 0, "Finance Manager": 180000, "Purchase Manager": 150000,
                      "Area Sales Manager": 140000}.get(desig, self.ri(38000, 85000))
            self.salary_total += salary
            if role:
                uid = self.nid("users")
                self.w.users.append(dict(
                    id=uid, company_id=1, name=name, email=email, role=role, password_hash="",
                    employee_id=eid,
                ))
                self.users[email.split("@")[0]] = self.w.users[-1]
        self.emp_by_name = {e["name"]: e for e in self.w.employees}

    def _items(self) -> None:
        cat_drift = {"dairy": 0.012, "beverages": 0.009, "snacks": 0.008, "cooking_oil": 0.014,
                     "personal_care": 0.007, "packaging": 0.006, "staples": 0.011, "logistics": 0.01,
                     "services": 0.006}
        for name, unit, cat, price in N.ITEMS:
            iid = self.nid("items")
            self.w.items.append(dict(id=iid, name=name, unit=unit, category=cat, base_price=rs(price)))
            self.item_drift[iid] = max(0.0, cat_drift[cat] + self.u(-0.006, 0.006))
        self.items_by_cat: dict[str, list[int]] = defaultdict(list)
        for it in self.w.items:
            self.items_by_cat[it["category"]].append(it["id"])

    def _make_vendor(self, name: str, category: str, created_at: datetime, created_by: int | None,
                     tier: str, *, phone: str | None = None, address: str | None = None,
                     iban: str | None = None, bank: str | None = None, registered: bool = True,
                     terms: int | None = None, prefix: str | None = None) -> dict:
        vid = self.nid("vendors")
        bank = bank or self.pick(list(N.BANKS))
        iban = iban or self._new_iban(bank)
        address = address or f"{self.pick(N.STREET_KINDS)} {self.ri(1, 220)}, {self.pick(N.LAHORE_AREAS)}, Lahore"
        phone = phone or self._new_phone(mobile=self.chance(0.5))
        if prefix is None:
            initials = "".join(w[0] for w in name.replace("-", " ").split() if w[0].isalpha())[:3].upper()
            prefix = self.pick(["INV-", f"{initials}-", f"{initials}/", "", "BL-"])
        v = dict(
            id=vid, name=name, ntn=f"{self.ri(1000000, 9999999)}-{self.ri(0, 9)}" if registered else None,
            strn=f"{self.ri(10, 99)}{self.ri(10000000000, 99999999999)}" if registered else None,
            category=category, phone=phone, address=address, address_norm=norm_address(address),
            owner_cnic_hash=None, home_bank=bank, payment_terms_days=terms or int(self.pick([15, 30, 30, 45])),
            invoice_prefix=prefix, related_party_note=None, status="active", blocked_at=None, created_at=created_at,
            created_by=created_by,
        )
        self.w.vendors.append(v)
        acc = dict(
            id=self.nid("vendor_bank_accounts"), vendor_id=vid, bank_name=bank, iban_hash=hash_id(iban),
            iban_last4=last4(iban), valid_from=created_at, valid_to=None, changed_by=created_by,
            approved_by=self.users["bilal"]["id"], change_source="onboarding", is_blocked=False, blocked_at=None,
        )
        acc["_iban"] = iban
        self.w.vendor_bank_accounts.append(acc)
        self.vendor_meta[vid] = dict(tier=tier, next_no=self.ri(100, 4800), prefix=prefix, registered=registered)
        return v

    def _vendors(self) -> None:
        plan = [("staples", 8), ("dairy", 7), ("beverages", 8), ("snacks", 8), ("cooking_oil", 6),
                ("personal_care", 9), ("packaging", 6), ("logistics", 5), ("services", 3)]
        sana, bilal = self.users["sana"]["id"], self.users["bilal"]["id"]
        used = set()
        # Fixed names used by the demo story
        fixed = {("staples", 0): "Al-Noor Traders", ("dairy", 0): "Madina Dairies",
                 ("packaging", 0): "Shan Packages", ("logistics", 0): "Ravi Goods Transport",
                 ("personal_care", 0): "Hilal Cosmetics", ("logistics", 1): "Gill Goods Transport"}
        tiers = ["A"] * 12 + ["B"] * 24 + ["C"] * 24
        tiers = list(self.rng.permutation(tiers))
        k = 0
        for cat, count in plan:
            for j in range(count):
                if (cat, j) in fixed:
                    name = fixed[(cat, j)]
                else:
                    while True:
                        name = f"{self.pick(N.VENDOR_FIRST)} {self.pick(N.VENDOR_KIND[cat])}"
                        if self.chance(0.4):
                            name += f" {self.pick(N.SUFFIX)}"
                        if name not in used and not any(name.startswith(f) for f in fixed.values()):
                            break
                used.add(name)
                tier = tiers[k]
                if name in ("Al-Noor Traders", "Madina Dairies"):
                    tier = "A"
                if name in ("Hilal Cosmetics", "Ravi Goods Transport", "Shan Packages"):
                    tier = "B"
                k += 1
                new_vendor = k > 52  # last 8 vendors are onboarded during the window
                if new_vendor:
                    d = self.start + timedelta(days=self.ri(35, 300))
                    created = self.at(next_business_day(d), 10, 17)
                    creator = sana
                else:
                    d = date(self.ri(2019, 2025), self.ri(1, 12), self.ri(1, 28))
                    d = min(d, self.start - timedelta(days=60))
                    created = self.at(d, 10, 17)
                    creator = sana if self.chance(0.85) else bilal
                registered = not (cat in ("logistics", "services") and self.chance(0.4))
                if name == "Gill Goods Transport":
                    # Disclosed related party: owned by the warehouse supervisor's brother, same family home.
                    waqas = self.emp_by_name["Waqas Gill"]
                    v = self._make_vendor(name, cat, created, creator, tier, address=waqas["address"],
                                          registered=True)
                    v["related_party_note"] = ("Disclosed related party: owned by the brother of Waqas Gill "
                                               "(Warehouse Supervisor); declared in the 2024 related-party register")
                else:
                    v = self._make_vendor(name, cat, created, creator, tier, registered=registered)
                meta = self.vendor_meta[v["id"]]
                pool = self.items_by_cat[cat]
                n_items = min(len(pool), self.ri(3, 8) if cat not in ("services", "logistics") else self.ri(2, 4))
                meta["items"] = [int(x) for x in self.rng.choice(pool, size=n_items, replace=False)]
                meta["price_factor"] = self.u(0.97, 1.03)
                # legit price revisions (inflation pass-through, budget changes): 1-2 steps of 4-12% a year
                meta["revisions"] = sorted(
                    (self.start + timedelta(days=self.ri(20, 360)), self.u(1.04, 1.12)) for _ in range(self.ri(1, 2)))
                meta["rate"] = {"A": self.u(11, 15), "B": self.u(4.5, 8), "C": self.u(1, 3)}[tier]
                meta["scale"] = {"A": self.u(1.2, 2.2), "B": self.u(0.7, 1.4), "C": self.u(0.4, 1.0)}[tier]
                meta["max_lines"] = 5 if cat not in ("services", "logistics") else 2
        # Sister concerns legitimately sharing one office (vendor-vendor link, not employee link)
        a, b = self.w.vendors[20], self.w.vendors[21]
        b["address"], b["address_norm"] = a["address"], a["address_norm"]
        self.vendor_by_name = {v["name"]: v for v in self.w.vendors}

    # ------------------------------------------------------------------ invoices
    def next_invoice_no(self, vid: int) -> str:
        meta = self.vendor_meta[vid]
        n = meta["next_no"]
        meta["next_no"] += 1
        p = meta["prefix"]
        if p.endswith("/"):
            return f"{p}{n:05d}"
        return f"{p}{n}"

    def vendor_price_factor(self, vid: int, d: date) -> float:
        meta = self.vendor_meta[vid]
        f = meta["price_factor"]
        for when, step in meta.get("revisions", []):
            if d >= when:
                f *= step
        return f

    def make_lines(self, vid: int, d: date, *, n_lines: int | None = None, scale: float = 1.0) -> list[dict]:
        meta = self.vendor_meta[vid]
        items = meta["items"]
        n = n_lines or self.ri(1, min(meta["max_lines"], len(items)))
        chosen = [int(x) for x in self.rng.choice(items, size=min(n, len(items)), replace=False)]
        lines = []
        for iid in chosen:
            item = self.w.items[iid - 1]
            unit_price = rs(self.price_at(iid, d) * self.vendor_price_factor(vid, d) * self.rng.normal(1, 0.004))
            base_qty = {"carton": 14, "crate": 30, "tin": 25, "bag": 18, "bundle": 10, "roll": 12,
                        "piece": 6, "trip": 2, "day": 3, "guard": 4, "month": 1, "visit": 1, "unit": 6,
                        "job": 1, "litre": 300, "pack": 20, "set": 15, "voucher": 10, "cylinder": 4}.get(item["unit"], 5)
            qty = max(1, int(round(base_qty * QTY_FACTOR * meta["scale"] * scale * self.rng.lognormal(0, 0.45))))
            lines.append(dict(item_id=iid, description=item["name"], qty=float(qty), unit_price=unit_price,
                              amount=unit_price * qty))
        return lines

    def add_invoice(self, vid: int, inv_date: date, lines: list[dict], *, received_at: datetime | None = None,
                    created_by: int | None = None, invoice_no: str | None = None, tax_rate: float | None = None,
                    terms: int | None = None, fraud: dict | None = None, iban_hash: str | None = None,
                    iban_last4: str | None = None) -> dict:
        vendor = self.w.vendors[vid - 1]
        meta = self.vendor_meta[vid]
        if tax_rate is None:
            tax_rate = TAX_RATE if meta.get("registered", True) else 0.0
        subtotal = sum(l["amount"] for l in lines)
        tax = int(round(subtotal * tax_rate / 100)) * 100
        if received_at is None:
            rd = next_business_day(inv_date + timedelta(days=int(self.rng.choice([0, 1, 2, 3], p=[.4, .35, .15, .1]))))
            received_at = self.at(rd, 10, 18.5)
        if created_by is None:
            created_by = self.users["sana"]["id"] if self.chance(0.8) else self.users["kashif"]["id"]
        no = invoice_no or self.next_invoice_no(vid)
        inv = dict(
            id=self.nid("invoices"), direction="payable", vendor_id=vid, invoice_no=no,
            invoice_no_norm=norm_invoice_no(no), invoice_date=inv_date,
            due_date=inv_date + timedelta(days=terms if terms is not None else vendor["payment_terms_days"]),
            received_at=received_at, subtotal=subtotal, tax=tax, total=subtotal + tax, ntn=vendor["ntn"],
            iban_last4=iban_last4, iban_hash=iban_hash, status="received", source="erp", created_by=created_by,
            file_name=None, extraction_json=None,
        )
        inv["_fraud"] = fraud
        inv["_lines"] = []
        for l in lines:
            row = dict(id=self.nid("invoice_lines"), invoice_id=inv["id"], **l)
            self.w.invoice_lines.append(row)
            inv["_lines"].append(row)
        self.w.invoices.append(inv)
        return inv

    def recompute_totals(self, inv: dict) -> None:
        sub = sum(l["amount"] for l in inv["_lines"])
        rate = inv["tax"] / inv["subtotal"] if inv["subtotal"] else 0
        inv["subtotal"] = sub
        inv["tax"] = int(round(sub * rate / 100)) * 100
        inv["total"] = sub + inv["tax"]

    def seasonal_factor(self, d: date) -> float:
        f = 1.0
        if near_eid(d, before=3, after=4):
            f *= 0.45
        elif near_eid(d, before=18, after=-4):
            f *= 1.25  # pre-Eid stocking
        if d.month in (5, 6):
            f *= 1.3  # peak before June year-end
        if d.month == 7:
            f *= 0.85
        return f

    def _legit_invoices(self) -> None:
        end = self.hist_end
        for v in list(self.w.vendors):
            vid = v["id"]
            meta = self.vendor_meta[vid]
            d = max(self.start - timedelta(days=50), v["created_at"].date() + timedelta(days=self.ri(3, 12)))
            while d <= end:
                rate_per_day = meta["rate"] / 30.4 * self.seasonal_factor(d)
                gap = self.rng.exponential(1 / rate_per_day)
                d = d + timedelta(days=max(1, int(round(gap))))
                if d > end:
                    break
                inv_date = d
                if is_off_day(inv_date):
                    inv_date = next_business_day(inv_date)
                inv = self.add_invoice(vid, inv_date, self.make_lines(vid, inv_date))
                if inv["received_at"].date() > end:
                    self.w.invoices.pop()
                    for _ in inv["_lines"]:
                        self.w.invoice_lines.pop()

    # ------------------------------------------------------------------ bank changes
    def active_account(self, vid: int, at: datetime) -> dict:
        best = None
        for a in self.accounts_by_vendor[vid]:
            if a["valid_from"] <= at and (a["valid_to"] is None or at < a["valid_to"]):
                best = a
        if best is None:  # payment before onboarding timestamp (pre-window invoices): first account
            best = self.accounts_by_vendor[vid][0]
        return best

    def change_account(self, vid: int, at: datetime, by: int, source: str, *, iban: str | None = None,
                       bank: str | None = None, approved_by: int | None = None, fraud: bool = False) -> dict:
        cur = self.active_account(vid, at)
        cur["valid_to"] = at
        bank = bank or self.pick(list(N.BANKS))
        iban = iban or self._new_iban(bank)
        acc = dict(
            id=self.nid("vendor_bank_accounts"), vendor_id=vid, bank_name=bank, iban_hash=hash_id(iban),
            iban_last4=last4(iban), valid_from=at, valid_to=None, changed_by=by, approved_by=approved_by,
            change_source=source, is_blocked=False, blocked_at=None,
        )
        acc["_iban"] = iban
        acc["_fraud"] = fraud
        self.w.vendor_bank_accounts.append(acc)
        self.accounts_by_vendor[vid].append(acc)
        self.accounts_by_vendor[vid].sort(key=lambda a: a["valid_from"])
        return acc

    def _index_accounts(self) -> None:
        self.accounts_by_vendor: dict[int, list[dict]] = defaultdict(list)
        for a in self.w.vendor_bank_accounts:
            self.accounts_by_vendor[a["vendor_id"]].append(a)

    def _legit_bank_changes(self) -> None:
        sana, bilal = self.users["sana"]["id"], self.users["bilal"]["id"]
        rashid = self.users["rashid"]["id"]
        candidates = [v["id"] for v in self.w.vendors if self.vendor_meta[v["id"]]["tier"] in ("A", "B")
                      and v["name"] not in ("Al-Noor Traders", "Madina Dairies", "Gill Goods Transport")]
        chosen = [int(x) for x in self.rng.choice(candidates, size=9, replace=False)]
        self.legit_change_vendors = set(chosen)
        for vid in chosen:
            d = next_business_day(self.start + timedelta(days=self.ri(40, 330)))
            by = sana if self.chance(0.9) else bilal
            self.change_account(vid, self.at(d, 10, 17), by, self.pick(["vendor_letter", "vendor_letter", "portal"]),
                                approved_by=bilal if by == sana else rashid)

    # ------------------------------------------------------------------ payment runs
    def _simulate_payment_runs(self) -> None:
        users = self.users
        sana, kashif, bilal, rashid = (users[k]["id"] for k in ("sana", "kashif", "bilal", "rashid"))
        invoices = sorted(self.w.invoices, key=lambda i: i["received_at"])
        remaining = {i["id"]: i["total"] for i in invoices}
        first_monday = self.start + timedelta(days=(7 - self.start.weekday()) % 7 + 7)
        mondays = []
        m = first_monday
        while m < self.as_of:
            mondays.append(m)
            m += timedelta(days=7)
        instalment_next: dict[int, int] = {}
        for R in mondays:
            run_day = next_business_day(R)
            prep = R - timedelta(days=3)
            while is_off_day(prep):
                prep -= timedelta(days=1)
            cutoff = to_utc(datetime.combine(prep, time(19, 0)))
            run_cutoff = to_utc(datetime.combine(run_day, time(11, 0)))
            run = dict(id=self.nid("payment_runs"), company_id=1, name=f"Weekly run {R:%d %b %Y}", run_date=R,
                       status="closed", created_by=sana, created_at=to_utc(datetime.combine(prep, time(10, 0))),
                       is_live=False)
            self.w.payment_runs.append(run)
            due_limit = R + timedelta(days=6)
            batch = []
            for inv in invoices:
                if remaining[inv["id"]] <= 0:
                    continue
                f = inv.get("_fraud") or {}
                if f.get("pay_created_at") is not None:
                    if f["pay_created_at"] < run_cutoff:
                        batch.append(inv)
                    continue
                if inv["received_at"] <= cutoff and inv["due_date"] <= due_limit:
                    batch.append(inv)
                elif inv["id"] in instalment_next and inv["received_at"] <= cutoff:
                    batch.append(inv)
            for inv in batch:
                f = inv.get("_fraud") or {}
                amount = remaining[inv["id"]]
                if (not f and inv["id"] not in instalment_next and inv["total"] > rs(400_000)
                        and self.chance(0.35) and R < self.as_of - timedelta(days=21)):
                    amount = int(round(inv["total"] * 0.6 / 100)) * 100
                    instalment_next[inv["id"]] = inv["total"] - amount
                elif inv["id"] in instalment_next:
                    amount = instalment_next.pop(inv["id"])
                remaining[inv["id"]] -= amount
                if f.get("pay_created_at") is not None:
                    created_at, creator = f["pay_created_at"], f["pay_created_by"]
                else:
                    r = self.rng.random()
                    creator = sana if r < 0.85 else (kashif if r < 0.98 else bilal)
                    if self.chance(0.1):
                        created_at = self.at(run_day, 9, 10.5)
                    elif prep.day >= 27 and self.chance(0.25):
                        created_at = self.at(prep, 21, 23.4)  # month-end late nights (legit)
                    else:
                        created_at = self.at(prep, 10, 19)
                    created_at = max(created_at, inv["received_at"] + timedelta(minutes=20))
                    if self.chance(0.006):
                        creator = rashid  # owner enters an urgent payment himself
                        created_at = self.at(run_day, 9.5, 12)
                if f.get("approver"):
                    approver = f["approver"]
                elif amount > self.approval_limit or creator in (bilal, rashid):
                    approver = rashid
                else:
                    approver = bilal if self.chance(0.92) else rashid
                approved_at = max(self.at(run_day, 11, 17.5), created_at + timedelta(minutes=30))
                pay_date = run_day if self.chance(0.8) else next_business_day(run_day + timedelta(days=1))
                acc = f.get("account") or self.active_account(inv["vendor_id"], created_at)
                pid = self.nid("payments")
                self.w.payments.append(dict(
                    id=pid, run_id=run["id"], invoice_id=inv["id"], vendor_id=inv["vendor_id"],
                    bank_account_id=acc["id"], amount=amount, created_by=creator, created_at=created_at,
                    approved_by=approver, approved_at=approved_at, pay_date=pay_date, status="released",
                ))
                if remaining[inv["id"]] <= 0:
                    inv["status"] = "paid"
                else:
                    inv["status"] = "scheduled"
        # Invoices still unpaid at as-of stay "received" (open payables).

    # ------------------------------------------------------------------ labels & cases
    def _labels_and_cases(self) -> None:
        inv_by_id = {i["id"]: i for i in self.w.invoices}
        acc_by_id = {a["id"]: a for a in self.w.vendor_bank_accounts}
        rashid = self.users["rashid"]["id"]
        for p in self.w.payments:
            inv = inv_by_id[p["invoice_id"]]
            acc = acc_by_id[p["bank_account_id"]]
            ftype, group = None, None
            if acc.get("_fraud"):
                ftype, group = "F2", acc.get("_group")
            elif inv.get("_fraud"):
                ftype, group = inv["_fraud"]["type"], inv["_fraud"]["group"]
            if not ftype:
                continue
            self.w.labels.append(dict(payment_id=p["id"], fraud_type=ftype, group_id=group,
                                      created_at=p["created_at"], amount=p["amount"]))
            if p["created_at"].date() <= self.audited_through:
                opened = to_utc(datetime.combine(p["pay_date"] + timedelta(days=self.ri(7, 45)), time(12, 0)))
                if opened.date() >= self.as_of:
                    opened = to_utc(datetime.combine(self.as_of - timedelta(days=2), time(12, 0)))
                resolved = opened + timedelta(days=self.ri(1, 10))
                self.w.cases.append(dict(
                    id=self.nid("cases"), payment_id=p["id"], risk_score_id=None, status="confirmed_fraud",
                    fraud_type=ftype, source="historical", opened_at=opened, resolved_at=resolved,
                    resolved_by=rashid, resolution_note="Confirmed in internal audit (pre-Nigraan).",
                    amount=p["amount"],
                ))

    # ------------------------------------------------------------------ outflows
    def _scheduled_outflows(self) -> None:
        horizon = self.as_of + timedelta(days=130)
        purchases = defaultdict(int)
        for inv in self.w.invoices:
            purchases[(inv["invoice_date"].year, inv["invoice_date"].month)] += inv["subtotal"]
        sales = defaultdict(int)
        for r in self.w.receivables:
            sales[(r["issue_date"].year, r["issue_date"].month)] += r["amount"]
        m = date(self.start.year, self.start.month, 1)
        recent_tax = []
        while m <= horizon:
            future = m >= date(self.as_of.year, self.as_of.month, 1)
            basis = "assumption" if future else "fact"

            def add(name, cat, d, amount, b="fact"):
                if d < self.start or d > horizon:
                    return
                self.w.scheduled_outflows.append(dict(
                    id=self.nid("scheduled_outflows"), company_id=1, name=name, category=cat,
                    due_date=d, amount=amount, basis=b))

            add(f"Warehouse rent {m:%b %Y}", "rent", next_business_day(m), rs(650_000))
            last = add_months(m, 1) - timedelta(days=1)
            while is_off_day(last):
                last -= timedelta(days=1)
            add(f"Salaries {m:%b %Y}", "salaries", last, rs(self.salary_total))
            add(f"LESCO & SNGPL bills {m:%b %Y}", "utilities", next_business_day(m.replace(day=12)),
                rs(320_000 * (1.25 if m.month in (5, 6, 7, 8) else 1.0)) if future else rs(self.ri(260_000, 410_000)),
                "assumption" if future else "fact")
            add(f"Withholding tax deposit {m:%b %Y}", "tax", next_business_day(m.replace(day=15)), rs(160_000))
            prev = add_months(m, -1)
            st = int(max(0, sales.get((prev.year, prev.month), 0) - purchases.get((prev.year, prev.month), 0)) * TAX_RATE)
            if st > 0:
                recent_tax.append(st)
            elif recent_tax:
                st = int(np.mean(recent_tax[-3:]))
            st = int(round(st / 10000)) * 10000
            if st > 0:
                add(f"Sales tax return {prev:%b %Y}", "tax", next_business_day(m.replace(day=18)), st,
                    "assumption" if sales.get((prev.year, prev.month), 0) == 0 else "fact")
            if m.month in (9, 12, 3):
                add(f"Advance income tax Q{(m.month % 12) // 3 + 1}", "tax", next_business_day(m.replace(day=25)), rs(900_000))
            if m.month == 6:
                add("Advance income tax Q4", "tax", next_business_day(m.replace(day=15)), rs(900_000))
            m = add_months(m, 1)

    # ------------------------------------------------------------------ build
    def build(self, with_demo: bool = True) -> World:
        from data_gen import demo_week, fraud_scenarios, receivables

        self._company()
        self._people()
        self._items()
        self._vendors()
        self._index_accounts()
        self._legit_invoices()
        self._legit_bank_changes()
        fraud_scenarios.plant_all(self)
        self._simulate_payment_runs()
        self._drop_open_this_week()
        self._labels_and_cases()
        receivables.generate(self)
        self._scheduled_outflows()
        if with_demo:
            demo_week.plan(self)
        return self.w

    def _drop_open_this_week(self) -> None:
        """Unpaid invoices payable in the demo week are replaced by the 40 demo-week invoices."""
        limit = self.as_of + timedelta(days=6)
        paid_ids = {p["invoice_id"] for p in self.w.payments}
        drop = {inv["id"] for inv in self.w.invoices
                if not inv.get("_fraud") and inv["id"] not in paid_ids and inv["due_date"] <= limit}
        self.w.invoices = [i for i in self.w.invoices if i["id"] not in drop]
        self.w.invoice_lines = [l for l in self.w.invoice_lines if l["invoice_id"] not in drop]


def generate(seed: int = 42, months: int = 12, fraud_rate: float = 0.025, with_demo: bool = True) -> World:
    return Generator(seed=seed, months=months, fraud_rate=fraud_rate).build(with_demo=with_demo)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--fraud-rate", type=float, default=0.025)
    ap.add_argument("--no-db", action="store_true", help="only write data_out/ files")
    args = ap.parse_args()

    from app.config import get_settings
    from data_gen.loader import load_world, write_hidden_files

    world = generate(args.seed, args.months, args.fraud_rate)
    out = get_settings().data_out_dir
    write_hidden_files(world, out)
    n_pay = len(world.payments)
    n_fraud = len(world.labels)
    print(f"vendors={len(world.vendors)} items={len(world.items)} invoices={len(world.invoices)} "
          f"payments={n_pay} frauds={n_fraud} ({n_fraud / max(1, n_pay):.2%}) employees={len(world.employees)} "
          f"customers={len(world.customers)} receivables={len(world.receivables)}")
    if not args.no_db:
        load_world(world)
        print("database loaded")


if __name__ == "__main__":
    main()
