"""Strict extraction schema + deterministic validators (section 6.1)."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.services.identity import is_valid_ntn, is_valid_pk_iban

FIELDS = ["vendor_name", "ntn", "strn", "invoice_no", "invoice_date", "due_date", "subtotal", "tax", "total", "iban"]


class LineItem(BaseModel):
    name: str
    qty: float | None = None
    unit_price: float | None = None
    amount: float | None = None


class Extraction(BaseModel):
    vendor_name: str | None = None
    ntn: str | None = None
    strn: str | None = None
    invoice_no: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    iban: str | None = None


# JSON schema handed to Gemini (OpenAPI subset)
GEMINI_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "vendor_name": {"type": "STRING", "nullable": True},
        "ntn": {"type": "STRING", "nullable": True},
        "strn": {"type": "STRING", "nullable": True},
        "invoice_no": {"type": "STRING", "nullable": True},
        "invoice_date": {"type": "STRING", "nullable": True, "description": "YYYY-MM-DD"},
        "due_date": {"type": "STRING", "nullable": True, "description": "YYYY-MM-DD"},
        "line_items": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "name": {"type": "STRING"}, "qty": {"type": "NUMBER", "nullable": True},
            "unit_price": {"type": "NUMBER", "nullable": True}, "amount": {"type": "NUMBER", "nullable": True}},
            "required": ["name"]}},
        "subtotal": {"type": "NUMBER", "nullable": True},
        "tax": {"type": "NUMBER", "nullable": True},
        "total": {"type": "NUMBER", "nullable": True},
        "iban": {"type": "STRING", "nullable": True},
    },
    "required": ["vendor_name", "invoice_no", "total", "line_items"],
}


def checks(e: Extraction) -> list[dict]:
    """Deterministic checks. 'flag' never rejects; it highlights for the accountant."""
    out = []
    if e.line_items and e.subtotal is not None and all(l.amount is not None for l in e.line_items):
        s = round(sum(l.amount for l in e.line_items), 2)
        ok = abs(s - e.subtotal) <= 1.0
        out.append({"check": "lines_sum", "ok": ok, "text": f"Line items add up to the subtotal (Rs {s:,.2f})" if ok
                    else f"Line items add up to Rs {s:,.2f}, subtotal says Rs {e.subtotal:,.2f}"})
    for l in e.line_items:
        if l.qty is not None and l.unit_price is not None and l.amount is not None and abs(l.qty * l.unit_price - l.amount) > 1:
            out.append({"check": "line_math", "ok": False, "text": f"'{l.name}': qty x price != amount"})
    if e.subtotal is not None and e.tax is not None and e.total is not None:
        ok = abs(e.subtotal + e.tax - e.total) <= 1.0
        out.append({"check": "total", "ok": ok, "text": "Subtotal + tax = total" if ok else "Subtotal + tax does not equal total"})
    if e.subtotal and e.tax is not None:
        rate = e.tax / e.subtotal
        if e.tax == 0:
            out.append({"check": "tax_rate", "ok": False, "text": "No sales tax charged (unregistered vendor?)"})
        else:
            ok = abs(rate - 0.18) <= 0.005
            out.append({"check": "tax_rate", "ok": ok, "text": "Sales tax is 18%" if ok else f"Sales tax is {rate:.1%}, expected 18%"})
    if e.ntn is not None:
        ok = is_valid_ntn(e.ntn)
        out.append({"check": "ntn_format", "ok": ok, "text": "NTN format valid" if ok else f"NTN '{e.ntn}' is not a valid format"})
    if e.iban is not None:
        ok = is_valid_pk_iban(e.iban)
        out.append({"check": "iban_format", "ok": ok, "text": "IBAN valid (PK + 22, check digits)" if ok
                    else "IBAN is not a valid Pakistani IBAN"})
    if e.invoice_date and e.due_date and e.due_date < e.invoice_date:
        out.append({"check": "dates", "ok": False, "text": "Due date is before the invoice date"})
    return out
