"""Upload pipeline: extract -> validate -> per-field confidence -> match vendor -> create invoice.

Engines, in order: Gemini (if GEMINI_API_KEY), embedded PDF text / Tesseract + regex, and finally a
cached extraction for the demo files. The engine actually used is always returned and shown in the UI.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import ApiError
from app.models import Company, Invoice, InvoiceLine, Item, User, VendorBankAccount
from app.money import rupees_to_paisa
from app.services.docreader import gemini, ocr_fallback
from app.services.docreader.schema import FIELDS, Extraction, checks
from app.services.identity import hash_id, last4, norm_invoice_no
from app.services.importer import match_vendor

LOW = 0.8
PDF_MIME = "application/pdf"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cache_dir():
    return get_settings().demo_week_dir / "extraction_cache"


def _normalise(raw: dict) -> Extraction:
    d = dict(raw)
    for f in ("invoice_date", "due_date"):
        v = d.get(f)
        if isinstance(v, str):
            try:
                d[f] = date.fromisoformat(v[:10])
            except ValueError:
                d[f] = None
    if d.get("iban"):
        d["iban"] = str(d["iban"]).replace(" ", "").upper()
    d["line_items"] = [li for li in (d.get("line_items") or []) if li.get("name")]
    return Extraction.model_validate({k: d.get(k) for k in Extraction.model_fields})


def _eq(field: str, a, b) -> bool:
    if a is None or b is None:
        return False
    if isinstance(a, float) or isinstance(b, float):
        return abs(float(a) - float(b)) <= 1.0
    if field == "vendor_name":
        return fuzz.token_sort_ratio(str(a), str(b)) >= 90
    return str(a).replace(" ", "").upper() == str(b).replace(" ", "").upper()


def extract_document(db: Session | None, filename: str, content_type: str, data: bytes) -> dict:
    """Pure extraction (no invoice created). Used by the upload endpoint and the extraction eval."""
    trace = []
    is_pdf = data[:4] == b"%PDF" or content_type == PDF_MIME or filename.lower().endswith(".pdf")
    mime = PDF_MIME if is_pdf else (content_type or "image/png")
    t0 = time.perf_counter()
    text_raw, text_err = None, None
    try:
        if is_pdf:
            txt = ocr_fallback.pdf_text(data)
            src = "pdf_text"
            if not txt.strip():
                if ocr_fallback.pdf_ocr_available():
                    txt = ocr_fallback.pdf_image_text(data)
                    src = "tesseract_pdf"
                else:
                    text_err = "Scanned PDF OCR requires pdftoppm and Tesseract"
                    src = None
            text_raw = ocr_fallback.parse(txt) if txt.strip() else None
        elif ocr_fallback.ocr_available():
            txt = ocr_fallback.image_text(data)
            text_raw = ocr_fallback.parse(txt) if txt.strip() else None
            src = "tesseract"
        else:
            src = None
            text_err = "Tesseract not installed"
    except Exception as e:  # noqa: BLE001 - malformed files fall through to the next engine
        src, text_err = None, type(e).__name__
    trace.append({"step": "text_layer", "label": "Embedded PDF text / OCR + regex", "ms": round((time.perf_counter() - t0) * 1000, 1),
                  "detail": f"{src}: {'parsed' if text_raw else 'no text'}" if src else f"unavailable ({text_err})"})

    t0 = time.perf_counter()
    g_raw, g_cached, g_err = None, False, None
    try:
        g_raw, g_cached = gemini.extract(db, data, mime)
    except gemini.GeminiUnavailable as e:
        g_err = str(e)
    trace.append({"step": "gemini", "label": f"Gemini ({get_settings().gemini_model}) vision extraction, temperature 0",
                  "ms": round((time.perf_counter() - t0) * 1000, 1),
                  "detail": ("replayed from cache (same file hash)" if g_cached else "called") if g_raw else f"skipped: {g_err}"})

    engine, primary, secondary = None, None, None
    if g_raw:
        engine, primary, secondary = ("gemini_cached" if g_cached else "gemini"), _normalise(g_raw), (
            _normalise(text_raw) if text_raw else None)
    elif text_raw:
        engine, primary = ("pdf_text_regex" if src == "pdf_text" else "ocr_regex"), _normalise(text_raw)
    else:
        cached = _cache_dir() / f"{_sha(data)}.json"
        if cached.exists():
            engine, primary = "cached", _normalise(json.loads(cached.read_text())["extraction"])
            trace.append({"step": "cache", "label": "Cached extraction for a known demo file", "ms": 0.0,
                          "detail": "replayed from demo_week/extraction_cache (labelled 'cached')"})
    if primary is None:
        raise ApiError(422, "unreadable", "Could not extract readable invoice text. Upload a clear PDF or image, "
                       "or configure Gemini for vision extraction.",
                       "file")

    t0 = time.perf_counter()
    vchecks = checks(primary)
    failed = {c["check"] for c in vchecks if not c["ok"]}
    conf = {}
    for f in FIELDS:
        v = getattr(primary, f)
        if v is None:
            conf[f] = 0.0
            continue
        if secondary is not None:
            c = 0.97 if _eq(f, v, getattr(secondary, f)) else 0.6
        else:
            c = 0.9 if engine in ("pdf_text_regex", "cached") else 0.85
        if f in ("subtotal", "tax", "total") and ({"lines_sum", "total"} & failed):
            c = min(c, 0.55)
        if f == "ntn" and "ntn_format" in failed or f == "iban" and "iban_format" in failed:
            c = min(c, 0.5)
        if f == "due_date" and "dates" in failed:
            c = min(c, 0.5)
        conf[f] = round(c, 2)
    conf["line_items"] = 0.95 if primary.line_items and "lines_sum" not in failed else (0.5 if primary.line_items else 0.0)
    trace.append({"step": "validate", "label": "Schema + deterministic checks (sums, 18% tax, NTN, IBAN)",
                  "ms": round((time.perf_counter() - t0) * 1000, 1),
                  "detail": f"{sum(c['ok'] for c in vchecks)}/{len(vchecks)} checks passed"})
    return {"engine": engine, "fields": json.loads(primary.model_dump_json()), "confidence": conf, "checks": vchecks,
            "low_confidence": [f for f, c in conf.items() if c < LOW], "trace": trace, "sha256": _sha(data)}


def read_and_store(db: Session, user: User, filename: str, content_type: str, data: bytes) -> dict:
    ext = extract_document(db, filename, content_type, data)
    f = ext["fields"]
    t0 = time.perf_counter()
    vendor, method, vconf = match_vendor(db, f.get("ntn"), f.get("vendor_name"))
    flags = []
    if vendor is not None and f.get("iban"):
        accounts = db.execute(select(VendorBankAccount).where(VendorBankAccount.vendor_id == vendor.id,
                                                              VendorBankAccount.status == "active",
                                                              VendorBankAccount.valid_to.is_(None))).scalars().all()
        h = hash_id(f["iban"])
        if accounts and all(a.iban_hash != h for a in accounts):
            flags.append(f"Invoice asks for payment to ••{last4(f['iban'])}, but the vendor master account is "
                         f"••{accounts[-1].iban_last4}")
    ext["trace"].append({"step": "match_vendor", "label": "Match vendor by NTN, then fuzzy name", "ms": round((time.perf_counter() - t0) * 1000, 1),
                         "detail": f"{vendor.name} via {method} ({vconf:.0%})" if vendor else "no match - accountant must pick"})
    company = db.execute(select(Company)).scalars().first()
    items = {n.lower(): i for i, n in db.execute(select(Item.id, Item.name)).all()}
    names = list(items)
    lines = []
    for li in f.get("line_items") or []:
        iid = items.get(li["name"].lower())
        if iid is None and names:
            best = process.extractOne(li["name"].lower(), names, scorer=fuzz.ratio)
            iid = items[best[0]] if best and best[1] >= 92 else None
        qty = li.get("qty") or 1
        amount = li.get("amount") or (qty * (li.get("unit_price") or 0))
        price = li.get("unit_price") or (amount / qty if qty else amount)
        lines.append(InvoiceLine(item_id=iid, description=li["name"][:200], qty=float(qty),
                                 unit_price=rupees_to_paisa(f"{price:.2f}"), amount=rupees_to_paisa(f"{amount:.2f}")))
    total = f.get("total") or sum(l.amount for l in lines) / 100
    subtotal = f.get("subtotal") if f.get("subtotal") is not None else total - (f.get("tax") or 0)
    inv_date = date.fromisoformat(f["invoice_date"]) if f.get("invoice_date") else company.as_of_date
    due = date.fromisoformat(f["due_date"]) if f.get("due_date") else inv_date + timedelta(
        days=vendor.payment_terms_days if vendor else 30)
    key_fields = ["vendor_name", "invoice_no", "total", "invoice_date"]
    ready = vendor is not None and all(ext["confidence"].get(k, 0) >= LOW for k in key_fields)
    no = f.get("invoice_no") or f"UPLOAD-{ext['sha256'][:6]}"
    inv = Invoice(direction="payable", vendor_id=vendor.id if vendor else None, invoice_no=no,
                  invoice_no_norm=norm_invoice_no(no), invoice_date=inv_date, due_date=due,
                  received_at=datetime.now(timezone.utc).replace(tzinfo=None),
                  subtotal=rupees_to_paisa(f"{subtotal:.2f}"), tax=rupees_to_paisa(f"{(f.get('tax') or 0):.2f}"),
                  total=rupees_to_paisa(f"{total:.2f}"), ntn=f.get("ntn"),
                  iban_last4=last4(f["iban"]) if f.get("iban") else None, iban_hash=hash_id(f["iban"]) if f.get("iban") else None,
                  status="received" if ready else "draft", source="upload", created_by=user.id, file_name=filename[:200],
                  extraction_json={k: ext[k] for k in ("engine", "fields", "confidence", "checks", "low_confidence", "sha256")}
                  | {"vendor_match": {"method": method, "confidence": vconf}, "flags": flags})
    inv.lines = lines
    db.add(inv)
    db.commit()
    from app.services.runtime import runtime

    runtime.bump()
    return {"invoice_id": inv.id, "status": inv.status, "ready_to_score": ready, "engine": ext["engine"],
            "cached": ext["engine"] in ("cached", "gemini_cached"), "fields": f, "confidence": ext["confidence"],
            "low_confidence": ext["low_confidence"], "checks": ext["checks"], "flags": flags,
            "vendor": {"id": vendor.id, "name": vendor.name, "method": method, "confidence": vconf} if vendor else None,
            "trace": ext["trace"]}
