"""Regressions for actionable CSV failures and real scanned-PDF extraction."""
from __future__ import annotations

import csv
import io
import subprocess

import pytest
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import func, select

from app.config import get_settings
from app.db import SessionLocal
from app.errors import ApiError
from app.models import Invoice, User
from app.services.docreader import ocr_fallback
from app.services.docreader.pipeline import extract_document
from app.services.importer import import_csv
from tests.conftest import login


def _row() -> dict:
    with (get_settings().demo_week_dir / "invoices.csv").open(newline="") as file:
        row = next(csv.DictReader(file))
    return row | {"invoice_no": "CSV-REGRESSION-001"}


def _csv(rows: list[dict]) -> str:
    file = io.StringIO()
    writer = csv.DictWriter(file, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return file.getvalue()


@pytest.mark.parametrize("field,value", [
    ("invoice_date", "bad-date"), ("due_date", "2026-02-30"),
    ("total", "not-money"), ("total", "-100"), ("total", "NaN"),
    ("total", "Infinity"), ("total", "9999999999999999999999999999999"),
    ("total", "100.001"), ("unit_price", "-0.50"), ("amount", "NaN"),
    ("qty", "many"), ("qty", "inf"), ("qty", "0"),
    ("entered_at", "tomorrow"), ("payment_created_at", "not-a-time"),
])
def test_invalid_csv_has_row_field_error_and_no_partial_import(client, field, value):
    with SessionLocal() as db:
        before = db.scalar(select(func.count(Invoice.id)))
    first = _row()
    second = first | {"invoice_no": "CSV-REGRESSION-002", field: value}
    response = client.post("/api/v1/invoices/import", headers=login(client, "sana"),
                           files={"file": ("invoices.csv", _csv([first, second]).encode(), "text/csv")})
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "bad_csv"
    assert response.json()["field"] == field
    assert "CSV row 3" in response.json()["message"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Invoice.id))) == before


def test_csv_validation_does_not_leave_pending_invoices(client):
    first = _row()
    invalid = first | {"invoice_no": "CSV-REGRESSION-002", "vendor_name": "Unknown audit vendor 923",
                       "vendor_ntn": ""}
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "sana@bismillah.pk"))
        with pytest.raises(ApiError) as raised:
            import_csv(db, _csv([first, invalid]), user)
        assert raised.value.code == "unknown_vendor"
        assert "CSV row 3" in raised.value.message
        assert not db.new


def test_non_utf8_csv_is_actionable(client):
    response = client.post("/api/v1/invoices/import", headers=login(client, "sana"),
                           files={"file": ("invoices.csv", b"vendor_name\n\xff\xfe", "text/csv")})
    assert response.status_code == 422, response.text
    assert response.json()["field"] == "file"
    assert "UTF-8" in response.json()["message"]


@pytest.mark.parametrize("content", [
    '"vendor_name,invoice_no',
    ",".join(_row()) + "\n",
    _csv([_row()]) + '"unclosed quote',
])
def test_empty_or_malformed_csv_returns_actionable_error(client, content):
    response = client.post("/api/v1/invoices/import", headers=login(client, "sana"),
                           files={"file": ("invoices.csv", content.encode(), "text/csv")})
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "bad_csv"
    assert response.json()["field"] == "file"


def test_csv_uses_exact_paisa_and_preserves_amount_mismatch_evidence(client):
    # A mismatch remains available to risk scoring; input validation must not repair it.
    row = _row() | {"invoice_no": "CSV-EXACT-PAISA", "subtotal": "1,000.25", "tax": "180.25",
                   "total": "1,250.50", "unit_price": "1,000.25", "amount": "1,000.25", "qty": "1"}
    response = client.post("/api/v1/invoices/import", headers=login(client, "sana"),
                           files={"file": ("invoices.csv", _csv([row]).encode(), "text/csv")})
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        invoice = db.get(Invoice, response.json()["invoices"][0]["invoice_id"])
        assert (invoice.subtotal, invoice.tax, invoice.total) == (100025, 18025, 125050)
        assert invoice.lines[0].amount == 100025


def _scanned_invoice() -> bytes:
    image = Image.new("RGB", (1800, 1500), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=48)
    lines = ["Al-Fazal Cold Drinks & Co.", "Invoice No: SCAN-2026-001", "Invoice Date: 12-10-2026",
             "Due Date: 12-11-2026", "Subtotal Rs 1000.00", "Sales Tax (18%) Rs 180.00",
             "Total Amount Rs 1180.00"]
    for index, line in enumerate(lines):
        draw.text((70, 70 + index * 150), line, fill="black", font=font)
    output = io.BytesIO()
    image.save(output, format="PDF", resolution=100)
    return output.getvalue()


@pytest.mark.skipif(not ocr_fallback.pdf_ocr_available(), reason="requires pdftoppm and Tesseract")
def test_image_only_pdf_uses_real_ocr_without_gemini():
    data = _scanned_invoice()
    assert not ocr_fallback.pdf_text(data).strip()
    extraction = extract_document(None, "scanned-invoice.pdf", "application/pdf", data)
    assert extraction["engine"] == "ocr_regex"
    assert extraction["fields"]["invoice_no"] == "SCAN-2026-001"
    assert extraction["fields"]["invoice_date"] == "2026-10-12"
    assert extraction["fields"]["total"] == 1180.0
    assert "tesseract_pdf" in extraction["trace"][0]["detail"]


def test_pdf_rasterizer_timeout_is_bounded_and_temporary_files_removed(monkeypatch):
    observed = {}
    monkeypatch.setattr(ocr_fallback, "pdf_ocr_available", lambda: True)

    def timeout(command, **kwargs):
        from pathlib import Path

        observed["document"] = Path(command[-2])
        observed["timeout"] = kwargs["timeout"]
        assert observed["document"].exists()
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(ocr_fallback.subprocess, "run", timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        ocr_fallback.pdf_image_text(_scanned_invoice())
    assert observed["timeout"] <= ocr_fallback.PDF_OCR_TIMEOUT_S
    assert not observed["document"].parent.exists()


def test_pdf_page_limit_is_checked_before_rasterization(monkeypatch):
    from reportlab.pdfgen import canvas

    output = io.BytesIO()
    document = canvas.Canvas(output)
    for _ in range(ocr_fallback.MAX_PDF_PAGES + 1):
        document.showPage()
    document.save()
    monkeypatch.setattr(ocr_fallback, "pdf_ocr_available", lambda: True)
    monkeypatch.setattr(ocr_fallback.subprocess, "run", lambda *args, **kwargs: pytest.fail("must not render"))
    with pytest.raises(ValueError, match="pages"):
        ocr_fallback.pdf_image_text(output.getvalue())
