"""Fallback reader: embedded PDF text (pypdf) or Tesseract OCR for images, then regex parsing of
common Pakistani invoice labels. Used when Gemini is unavailable; also the cross-check source that
gives the deterministic per-field confidence."""
from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
import time
from datetime import date, datetime
from pathlib import Path

MAX_PDF_PAGES = 10
MAX_IMAGE_PIXELS = 20_000_000
PDF_OCR_TIMEOUT_S = 30

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
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ValueError(f"PDF exceeds the {MAX_PDF_PAGES}-page extraction limit")
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return shutil.which("tesseract") is not None


def pdf_ocr_available() -> bool:
    return ocr_available() and shutil.which("pdftoppm") is not None


def image_text(data: bytes, timeout_s: float = 10) -> str:
    import pytesseract
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValueError("Image is too large for OCR")
        return pytesseract.image_to_string(image, timeout=timeout_s)


def pdf_image_text(data: bytes) -> str:
    """Rasterize a scanned PDF for OCR, with bounded pages, resolution and runtime.

    Poppler and Tesseract remain optional system dependencies. No shell command or original
    filename is used, and temporary document images are removed after extraction.
    """
    from pypdf import PdfReader

    if not pdf_ocr_available():
        raise RuntimeError("Scanned PDF OCR requires pdftoppm and Tesseract")
    pages = len(PdfReader(io.BytesIO(data)).pages)
    if not 0 < pages <= MAX_PDF_PAGES:
        raise ValueError(f"PDF must contain 1-{MAX_PDF_PAGES} pages")
    deadline = time.monotonic() + PDF_OCR_TIMEOUT_S
    with tempfile.TemporaryDirectory(prefix="nigraan-pdf-ocr-") as temp:
        directory = Path(temp)
        document, output = directory / "document.pdf", directory / "page"
        document.write_bytes(data)
        subprocess.run(
            [shutil.which("pdftoppm"), "-f", "1", "-l", str(pages), "-scale-to", "2200",
             "-gray", "-png", str(document), str(output)],
            check=True, timeout=min(15, PDF_OCR_TIMEOUT_S), stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        images = sorted(directory.glob("page-*.png"))
        if len(images) != pages:
            raise RuntimeError("PDF rasterization did not produce every page")
        text = []
        for image in images:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Scanned PDF OCR timed out")
            text.append(image_text(image.read_bytes(), timeout_s=min(10, remaining)))
        return "\n".join(text)


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
