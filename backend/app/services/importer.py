"""CSV import of vendor invoices (ERP export: one row per invoice line) and vendor matching."""
from __future__ import annotations

import csv
import io
import math
import re
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Invoice, InvoiceLine, Item, User, Vendor
from app.money import rupees_to_paisa
from app.services.identity import hash_id, last4, norm_invoice_no

REQUIRED = ["vendor_name", "invoice_no", "invoice_date", "due_date", "total", "description", "qty", "unit_price", "amount"]
MAX_LEDGER_PAISA = 2**63 - 1


def match_vendor(db: Session, ntn: str | None, name: str | None) -> tuple[Vendor | None, str, float]:
    """NTN first, then fuzzy name. Returns (vendor, method, confidence)."""
    if ntn:
        v = db.execute(select(Vendor).where(Vendor.ntn == ntn.strip())).scalars().first()
        if v:
            return v, "ntn", 1.0
    if name:
        vendors = db.execute(select(Vendor.id, Vendor.name)).all()
        choices = {vid: n for vid, n in vendors}
        best = process.extractOne(name, choices, scorer=fuzz.token_sort_ratio)
        if best and best[1] >= 88:
            return db.get(Vendor, best[2]), "name", best[1] / 100
    return None, "none", 0.0


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "")).replace(tzinfo=None)


def _invalid(row: int, field: str, message: str) -> ApiError:
    return ApiError(422, "bad_csv", f"CSV row {row}: {field} {message}", field)


def _value(row: dict, field: str, number: int) -> str:
    value = row.get(field)
    if value is None or not value.strip():
        raise _invalid(number, field, "is required")
    return value.strip()


def _date(value: str, field: str, number: int) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise _invalid(number, field, "must be a valid date in YYYY-MM-DD format") from exc


def _timestamp(value: str, field: str, number: int) -> datetime:
    try:
        return _dt(value)
    except ValueError as exc:
        raise _invalid(number, field, "must be a valid ISO date and time") from exc


def _money(value: str, field: str, number: int) -> int:
    # Validate before converting so NaN, infinity and malformed numbers never become money.
    cleaned = value.replace(",", "").replace("Rs", "").strip()
    if len(cleaned) > 64 or not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", cleaned):
        raise _invalid(number, field, "must be a valid amount in rupees")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise _invalid(number, field, "must be a valid amount in rupees") from exc
    if not amount.is_finite() or amount < 0:
        raise _invalid(number, field, "must be a finite, non-negative amount in rupees")
    if amount > Decimal(MAX_LEDGER_PAISA) / 100:
        raise _invalid(number, field, "is too large to store safely")
    if amount != amount.quantize(Decimal("0.01")):
        raise _invalid(number, field, "must have at most two decimal places")
    try:
        return rupees_to_paisa(format(amount, "f"))
    except (ValueError, OverflowError) as exc:
        raise _invalid(number, field, "must be a valid amount in rupees") from exc


def _quantity(value: str, number: int) -> float:
    try:
        qty = float(value)
    except (ValueError, OverflowError) as exc:
        raise _invalid(number, "qty", "must be a valid number") from exc
    if not math.isfinite(qty) or qty <= 0:
        raise _invalid(number, "qty", "must be a finite number greater than zero")
    return qty


def import_csv(db: Session, text: str, user: User, source: str = "csv") -> list[dict]:
    reader = csv.DictReader(io.StringIO(text), strict=True)
    try:
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
    except csv.Error as exc:
        raise _invalid(reader.line_num, "file", "has an invalid CSV header") from exc
    if missing:
        raise ApiError(422, "bad_csv", f"Missing columns: {', '.join(missing)}", "file")
    groups: OrderedDict[tuple, list[dict]] = OrderedDict()
    # Parse and validate the entire file before adding anything to the session. A bad later
    # row must not leave earlier invoices pending in a caller's transaction.
    try:
        for row in reader:
            number = reader.line_num
            if None in row:
                raise _invalid(number, "file", "has more values than the header")
            parsed = dict(row)
            for field in REQUIRED:
                parsed[field] = _value(row, field, number)
            for field in ("invoice_date", "due_date"):
                parsed[field] = _date(parsed[field], field, number)
            for field in ("total", "unit_price", "amount"):
                parsed[field] = _money(parsed[field], field, number)
            for field in ("subtotal", "tax"):
                if row.get(field) and row[field].strip():
                    parsed[field] = _money(row[field], field, number)
                else:
                    parsed[field] = None
            parsed["qty"] = _quantity(parsed["qty"], number)
            for field in ("entered_at", "payment_created_at"):
                parsed[field] = _timestamp(row[field], field, number) if row.get(field) else None
            parsed["_row"] = number
            groups.setdefault((parsed["vendor_name"], parsed["invoice_no"]), []).append(parsed)
    except csv.Error as exc:
        raise _invalid(reader.line_num, "file", "is not valid CSV; check quotes and delimiters") from exc
    if not groups:
        raise ApiError(422, "bad_csv", "CSV contains no invoice rows", "file")
    users = {u.email: u for u in db.execute(select(User)).scalars()}
    items = {n.lower(): i for i, n in db.execute(select(Item.id, Item.name)).all()}
    prepared = []
    for (vname, no), rows in groups.items():
        r0 = rows[0]
        vendor, method, conf = match_vendor(db, r0.get("vendor_ntn") or None, vname)
        if vendor is None:
            raise ApiError(422, "unknown_vendor", f"CSV row {r0['_row']}: vendor '{vname}' is not in the vendor master", "vendor_name")
        entered_by = users.get(r0.get("entered_by", ""), user)
        received = r0["entered_at"] or datetime.utcnow()
        iban = (r0.get("iban") or "").replace(" ", "")
        lines = [InvoiceLine(item_id=items.get(r["description"].lower()), description=r["description"],
                             qty=r["qty"], unit_price=r["unit_price"], amount=r["amount"]) for r in rows]
        subtotal = r0["subtotal"] if r0["subtotal"] is not None else sum(l.amount for l in lines)
        if subtotal > MAX_LEDGER_PAISA:
            raise _invalid(r0["_row"], "subtotal", "is too large to store safely")
        total = r0["total"]
        tax = r0["tax"] if r0["tax"] is not None else total - subtotal
        if tax < 0:
            raise _invalid(r0["_row"], "total", "cannot be less than the subtotal when tax is omitted")
        inv = Invoice(direction="payable", vendor_id=vendor.id, invoice_no=no, invoice_no_norm=norm_invoice_no(no),
                      invoice_date=r0["invoice_date"], due_date=r0["due_date"],
                      received_at=received, subtotal=subtotal,
                      tax=tax, total=total,
                      ntn=r0.get("vendor_ntn") or None, iban_last4=last4(iban) if iban else None,
                      iban_hash=hash_id(iban) if iban else None, status="received", source=source,
                      created_by=entered_by.id, file_name=r0.get("file") or None)
        inv.lines = lines
        meta = {}
        if r0.get("payment_created_at"):
            meta = {"created_at": r0["payment_created_at"],
                    "created_by": users.get(r0.get("payment_created_by", ""), entered_by).id}
        prepared.append((inv, vendor, method, conf, meta))
    out = []
    for inv, vendor, method, conf, meta in prepared:
        db.add(inv)
        db.flush()
        out.append({"invoice_id": inv.id, "vendor": vendor.name, "match": method, "match_confidence": conf, "meta": meta})
    db.commit()
    return out
