"""Fallback reader: embedded PDF text (pypdf) or Tesseract OCR for images, then regex parsing of
common Pakistani invoice labels. Used when Gemini is unavailable; also the cross-check source that
gives the deterministic per-field confidence."""
from __future__ import annotations

import io
import re
import shutil
from datetime import date, datetime

LABELS = {
    "invoice_no": r"(?:Invoice\s*No\.?:?|Invoice\s*#|Bill\s*No\.?:?|Inv\.?\s*No\.?:?)\s*([A-Za-z0-9][A-Za-z0-9/\-\.]*)",
    "invoice_date": r"(?:Invoice\s*Date:?|Dated:?|(?<!Due )Date:)\s*([0-9]{1,2}[\-/ ][A-Za-z0-9]{2,3}[\-/ ][0-9]{4})",
    "due_date": r"(?:Due\s*Date:?|Payment\s*Due:?|Due\s*on:?)\s*([0-9]{1,2}[\-/ ][A-Za-z0-9]{2,3}[\-/ ][0-9]{4})",
    "ntn": r"(?:NTN|N\.T\.N)\s*(?:No\.?|#)?\s*:?\s*(\d{7}-\d|\d{13})",
    "strn": r"(?:STRN|S\.T\.R\.N|GST\s*No)\s*:?\s*(\d{13})",
    "subtotal": r"(?:Sub\s*Total|Subtotal|Value\s*excl\.?\s*tax)\s*(?:Rs\.?)?\s*([\d,]+(?:\.\d{1,2})?)",
    "tax": r"(?:Sales\s*Tax\s*(?:@\s*18%|\(18%\))?|GST\s*18%|GST)\s*(?:Rs\.?)?\s*([\d,]+(?:\.\d{1,2})?)",
    "total": r"(?:Total\s*Amount|Grand\s*Total|Total\s*Payable|Net\s*Payable)\s*(?:Rs\.?)?\s*([\d,]+(?:\.\d{1,2})?)",
    "iban": r"IBAN\s*:?\s*(PK[0-9A-Z ]{22,32})",
}
DATE_FORMATS = ["%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d-%b-%Y", "%d %B %Y"]
HEADER_LAST = {"amount (rs)", "value", "total", "amount"}
STOP = re.compile(r"^(sub\s*total|subtotal|value excl)", re.I)


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return shutil.which("tesseract") is not None


def image_text(data: bytes) -> str:
    import pytesseract
    from PIL import Image

    return pytesseract.image_to_string(Image.open(io.BytesIO(data)))


def _num(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(s.replace(",", "").strip())
    except ValueError:
        return None


def _date(s: str | None) -> date | None:
    if not s:
        return None
    s = s.strip()
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


HEADER_ONLY = {"ntn", "strn"}  # must come from the vendor's letterhead, not the "Bill To" block


def parse(text: str) -> dict:
    flat = re.sub(r"[ \t]+", " ", text)
    cut = re.search(r"Bill\s*To|Buyer|Customer", flat, re.I)
    header = flat[: cut.start()] if cut else flat
    out: dict = {}
    for field, pat in LABELS.items():
        m = re.search(pat, header if field in HEADER_ONLY else flat, re.I)
        out[field] = m.group(1).strip() if m else None
    out["iban"] = re.sub(r"\s", "", out["iban"]).upper()[:24] if out.get("iban") else None
    for f in ("subtotal", "tax", "total"):
        out[f] = _num(out[f])
    for f in ("invoice_date", "due_date"):
        out[f] = _date(out[f])
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out["vendor_name"] = lines[0] if lines else None
    if out["vendor_name"] and out["vendor_name"].isupper():
        out["vendor_name"] = out["vendor_name"].title().replace("&", "&")
    out["line_items"] = _line_items(lines)
    if out.get("tax") is None and out.get("subtotal") is not None and out.get("total") is not None \
            and abs(out["subtotal"] - out["total"]) < 0.5:
        out["tax"] = 0.0
    return out


def _line_items(lines: list[str]) -> list[dict]:
    start = None
    for i, l in enumerate(lines):
        if l.lower() in HEADER_LAST and i >= 4:
            start = i + 1
            break
    if start is None:
        return []
    items, i = [], start
    while i + 4 < len(lines) and not STOP.match(lines[i]):
        sno, desc, qty, price, amt = lines[i:i + 5]
        if not sno.isdigit():
            break
        items.append({"name": desc, "qty": _num(qty), "unit_price": _num(price), "amount": _num(amt)})
        i += 5
    return items
