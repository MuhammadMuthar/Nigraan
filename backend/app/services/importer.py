"""CSV import of vendor invoices (ERP export: one row per invoice line) and vendor matching."""
from __future__ import annotations

import csv
import io
from collections import OrderedDict
from datetime import date, datetime

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Invoice, InvoiceLine, Item, User, Vendor
from app.money import rupees_to_paisa
from app.services.identity import hash_id, last4, norm_invoice_no

REQUIRED = ["vendor_name", "invoice_no", "invoice_date", "due_date", "total", "description", "qty", "unit_price", "amount"]


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


def import_csv(db: Session, text: str, user: User, source: str = "csv") -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
    if missing:
        raise ApiError(422, "bad_csv", f"Missing columns: {', '.join(missing)}", "file")
    groups: OrderedDict[tuple, list[dict]] = OrderedDict()
    for row in reader:
        groups.setdefault((row["vendor_name"], row["invoice_no"]), []).append(row)
    users = {u.email: u for u in db.execute(select(User)).scalars()}
    items = {n.lower(): i for i, n in db.execute(select(Item.id, Item.name)).all()}
    out = []
    for (vname, no), rows in groups.items():
        r0 = rows[0]
        vendor, method, conf = match_vendor(db, r0.get("vendor_ntn") or None, vname)
        if vendor is None:
            raise ApiError(422, "unknown_vendor", f"Vendor '{vname}' is not in the vendor master", "vendor_name")
        entered_by = users.get(r0.get("entered_by", ""), user)
        received = _dt(r0["entered_at"]) if r0.get("entered_at") else datetime.utcnow()
        iban = (r0.get("iban") or "").replace(" ", "")
        lines = [InvoiceLine(item_id=items.get(r["description"].lower()), description=r["description"],
                             qty=float(r["qty"]), unit_price=rupees_to_paisa(r["unit_price"]),
                             amount=rupees_to_paisa(r["amount"])) for r in rows]
        subtotal = rupees_to_paisa(r0["subtotal"]) if r0.get("subtotal") else sum(l.amount for l in lines)
        total = rupees_to_paisa(r0["total"])
        inv = Invoice(direction="payable", vendor_id=vendor.id, invoice_no=no, invoice_no_norm=norm_invoice_no(no),
                      invoice_date=date.fromisoformat(r0["invoice_date"]), due_date=date.fromisoformat(r0["due_date"]),
                      received_at=received, subtotal=subtotal,
                      tax=rupees_to_paisa(r0["tax"]) if r0.get("tax") else total - subtotal, total=total,
                      ntn=r0.get("vendor_ntn") or None, iban_last4=last4(iban) if iban else None,
                      iban_hash=hash_id(iban) if iban else None, status="received", source=source,
                      created_by=entered_by.id, file_name=r0.get("file") or None)
        inv.lines = lines
        db.add(inv)
        db.flush()
        meta = {}
        if r0.get("payment_created_at"):
            meta = {"created_at": _dt(r0["payment_created_at"]),
                    "created_by": users.get(r0.get("payment_created_by", ""), entered_by).id}
        out.append({"invoice_id": inv.id, "vendor": vendor.name, "match": method, "match_confidence": conf, "meta": meta})
    db.commit()
    return out
