"""LLM guardrails and the document-reader fallback (no API key needed)."""
import json

from app.config import get_settings
from app.services.docreader.pipeline import extract_document
from app.services.docreader.schema import Extraction, checks
from app.services.summary import check_numbers


def test_summary_number_guardrail():
    ev = {"amount": "Rs 4,50,000", "invoice_no": "PS-1001", "bank_change": {"changed_on": "2026-10-10"}}
    assert check_numbers("Nigraan blocked Rs 4,50,000 (invoice PS-1001), account changed 10 Oct.", ev)
    assert not check_numbers("Nigraan blocked Rs 4.5 lakh.", ev)  # reformatted number -> hidden
    assert not check_numbers("The vendor was paid Rs 9,99,999 last year.", ev)  # invented number -> hidden


def test_validators_flag_but_do_not_reject():
    e = Extraction(vendor_name="X", subtotal=100.0, tax=16.0, total=116.0, ntn="12345", iban="PK00ABCD0000000000000000",
                   line_items=[{"name": "a", "qty": 1, "unit_price": 100, "amount": 100}])
    by = {c["check"]: c["ok"] for c in checks(e)}
    assert by["lines_sum"] and by["total"]
    assert not by["tax_rate"] and not by["ntn_format"] and not by["iban_format"]


def test_pdf_fallback_extracts_demo_invoice_exactly():
    s = get_settings()
    truth = json.loads((s.demo_week_dir / "ground_truth.json").read_text())
    name, want = next(iter(truth.items()))
    ext = extract_document(None, name, "application/pdf", (s.demo_week_dir / "pdfs" / name).read_bytes())
    assert ext["engine"] == "pdf_text_regex"  # no Gemini key in tests: labelled fallback
    f = ext["fields"]
    assert f["invoice_no"] == want["invoice_no"] and abs(f["total"] - want["total"]) < 0.5
    assert f["iban"] == want["iban"] and ext["confidence"]["total"] >= 0.8
