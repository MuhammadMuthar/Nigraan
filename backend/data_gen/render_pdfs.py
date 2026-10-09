"""Render the demo week: 40 invoice PDFs (3 vendor layouts), the ERP CSV export, extraction ground truth,
and a few extra files for the live upload demo.

    python -m data_gen.render_pdfs --seed 42
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.config import get_settings
from app.money import group_lakh
from app.services.calendar_pk import PKT_OFFSET

BUYER = ("Bismillah Distributors (fictional)", "Plot 14, Sundar Industrial Estate, Lahore", "NTN 4410022-7")


def rs(paisa: int) -> str:
    return group_lakh(paisa // 100) + (f".{paisa % 100:02d}" if paisa % 100 else ".00")


def iban_spaced(iban: str) -> str:
    return " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))


def _layout(c: canvas.Canvas, inv: dict, style: int) -> None:
    W, H = A4
    accent = [colors.HexColor("#1f3a5f"), colors.HexColor("#5a2d0c"), colors.HexColor("#234d20")][style]
    x0, y = 18 * mm, H - 20 * mm
    # Header
    c.setFillColor(accent)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(x0, y, inv["vendor_name"].upper() if style == 1 else inv["vendor_name"])
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8.5)
    c.drawString(x0, y - 12, inv["vendor_address"])
    c.drawString(x0, y - 23, f"Ph: {inv['vendor_phone']}")
    ntn_label = ["NTN", "N.T.N No.", "NTN #"][style]
    if inv.get("vendor_ntn"):
        c.drawString(x0, y - 34, f"{ntn_label}: {inv['vendor_ntn']}" + (f"    STRN: {inv['vendor_strn']}" if inv.get("vendor_strn") else ""))
    title = ["SALES TAX INVOICE", "INVOICE", "Commercial Invoice"][style] if inv["tax"] else ["INVOICE", "BILL", "Invoice"][style]
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(W - 18 * mm, y, title)
    c.setFont("Helvetica", 9)
    no_label = ["Invoice No:", "Bill No.", "Invoice #"][style]
    date_label = ["Invoice Date:", "Date:", "Dated:"][style]
    due_label = ["Due Date:", "Payment Due:", "Due on:"][style]
    fmt = ["%d-%m-%Y", "%d/%m/%Y", "%d %b %Y"][style]
    c.drawRightString(W - 18 * mm, y - 16, f"{no_label} {inv['invoice_no']}")
    c.drawRightString(W - 18 * mm, y - 28, f"{date_label} {inv['invoice_date'].strftime(fmt)}")
    c.drawRightString(W - 18 * mm, y - 40, f"{due_label} {inv['due_date'].strftime(fmt)}")
    # Buyer
    y -= 62
    c.setStrokeColor(accent)
    c.line(x0, y + 8, W - 18 * mm, y + 8)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x0, y - 4, "Bill To:")
    c.setFont("Helvetica", 9)
    for i, line in enumerate(BUYER):
        c.drawString(x0 + 45, y - 4 - 11 * i, line)
    # Table
    y -= 50
    cols = [x0, x0 + 12 * mm, x0 + 105 * mm, x0 + 125 * mm, x0 + 152 * mm]
    heads = [["S.No", "Description", "Qty", "Rate (Rs)", "Amount (Rs)"],
             ["#", "Item / Service", "Qty", "Unit Price", "Value"],
             ["Sr", "Particulars", "Quantity", "Price", "Total"]][style]
    c.setFillColor(accent)
    c.rect(x0 - 2, y - 4, W - 36 * mm + 4, 15, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8.5)
    for cx, h in zip(cols, heads):
        c.drawString(cx + 2, y + 1, h)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8.5)
    y -= 16
    for i, l in enumerate(inv["lines"], start=1):
        c.drawString(cols[0] + 2, y, str(i))
        c.drawString(cols[1] + 2, y, l["description"])
        c.drawRightString(cols[3] - 4, y, f"{l['qty']:g}")
        c.drawRightString(cols[4] - 4, y, rs(l["unit_price"]))
        c.drawRightString(W - 18 * mm, y, rs(l["amount"]))
        y -= 14
    c.line(x0, y + 6, W - 18 * mm, y + 6)
    # Totals
    y -= 10
    c.setFont("Helvetica", 9)
    sub_label = ["Sub Total", "Value excl. tax", "Subtotal"][style]
    tax_label = ["Sales Tax @ 18%", "GST 18%", "Sales Tax (18%)"][style]
    tot_label = ["Total Amount", "Grand Total", "Total Payable"][style]
    c.drawRightString(W - 60 * mm, y, sub_label)
    c.drawRightString(W - 18 * mm, y, f"Rs {rs(inv['subtotal'])}")
    y -= 13
    if inv["tax"]:
        c.drawRightString(W - 60 * mm, y, tax_label)
        c.drawRightString(W - 18 * mm, y, f"Rs {rs(inv['tax'])}")
        y -= 13
    c.setFont("Helvetica-Bold", 10.5)
    c.drawRightString(W - 60 * mm, y, tot_label)
    c.drawRightString(W - 18 * mm, y, f"Rs {rs(inv['total'])}")
    # Bank details
    y -= 40
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x0, y, ["Bank Details", "Payment Instructions", "Please remit to"][style])
    c.setFont("Helvetica", 9)
    c.drawString(x0, y - 12, f"Account Title: {inv['vendor_name']}")
    c.drawString(x0, y - 24, f"IBAN: {iban_spaced(inv['iban']) if style == 1 else inv['iban']}")
    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColor(colors.grey)
    c.drawString(x0, 18 * mm, "This is a computer generated invoice. Synthetic data for the Nigraan demo - fictional company.")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    c.drawRightString(W - 18 * mm, 30 * mm, "Authorised Signatory")
    c.line(W - 70 * mm, 34 * mm, W - 18 * mm, 34 * mm)


def render_invoice(path: Path, inv: dict, style: int) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(f"{inv['vendor_name']} {inv['invoice_no']}")
    _layout(c, inv, style)
    c.showPage()
    c.save()


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


def write_demo_week(world, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = out_dir / "pdfs"
    pdf_dir.mkdir(exist_ok=True)
    for old in pdf_dir.glob("*.pdf"):
        old.unlink()
    dw = world.demo_week
    truth, labels = {}, {}
    rows = []
    for s in dw["invoices"]:
        style = s["vendor_id"] % 3
        render_invoice(pdf_dir / s["file"], s, style)
        truth[s["file"]] = {
            "vendor_name": s["vendor_name"], "ntn": s["vendor_ntn"], "strn": s["vendor_strn"], "invoice_no": s["invoice_no"],
            "invoice_date": s["invoice_date"].isoformat(), "due_date": s["due_date"].isoformat(),
            "line_items": [{"name": l["description"], "qty": l["qty"], "unit_price": l["unit_price"] / 100,
                            "amount": l["amount"] / 100} for l in s["lines"]],
            "subtotal": s["subtotal"] / 100, "tax": s["tax"] / 100, "total": s["total"] / 100, "iban": s["iban"],
        }
        labels[s["file"]] = {"fraud": s["fraud"], "note": s["note"]}
        for k, l in enumerate(s["lines"], start=1):
            rows.append({
                "file": s["file"], "vendor_name": s["vendor_name"], "vendor_ntn": s["vendor_ntn"] or "",
                "invoice_no": s["invoice_no"], "invoice_date": s["invoice_date"].isoformat(),
                "due_date": s["due_date"].isoformat(), "subtotal": f"{s['subtotal'] / 100:.2f}", "tax": f"{s['tax'] / 100:.2f}",
                "total": f"{s['total'] / 100:.2f}", "iban": s["iban"], "entered_by": s["entered_by"],
                "entered_at": _iso(s["entered_at"]), "payment_created_by": s["payment_created_by"],
                "payment_created_at": _iso(s["payment_created_at"]), "line_no": k, "description": l["description"],
                "qty": f"{l['qty']:g}", "unit_price": f"{l['unit_price'] / 100:.2f}", "amount": f"{l['amount'] / 100:.2f}",
            })
    with open(out_dir / "invoices.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (out_dir / "ground_truth.json").write_text(json.dumps(truth, indent=2))
    (out_dir / "labels_hidden.json").write_text(json.dumps(labels, indent=2))
    meta = {"run_date": dw["run_date"].isoformat(), "pay_date": dw["pay_date"].isoformat(), "count": len(dw["invoices"]),
            "calibration": dw["calibration"]}
    (out_dir / "week.json").write_text(json.dumps(meta, indent=2, default=str))
    _upload_samples(world, out_dir)
    return meta


def _upload_samples(world, out_dir: Path) -> None:
    """Extra files for the live upload demo (not part of the run)."""
    up = out_dir / "upload_samples"
    up.mkdir(exist_ok=True)
    for old in up.glob("*"):
        old.unlink()
    specs = world.demo_week["invoices"]
    legit = [s for s in specs if not s["fraud"]]
    # 1) a vendor re-sends an invoice that is already in this week's run (exact duplicate -> hard rule)
    dup = dict(legit[3])
    render_invoice(up / f"resent_{dup['file']}", dup, dup["vendor_id"] % 3)
    # 2) a clean next invoice from a regular vendor
    clean = dict(legit[7])
    clean["invoice_no"] = clean["invoice_no"] + "-1" if not clean["invoice_no"][-1].isdigit() else \
        clean["invoice_no"][:-1] + str((int(clean["invoice_no"][-1]) + 1) % 10)
    clean["invoice_date"] = clean["invoice_date"] + timedelta(days=4)
    clean["due_date"] = clean["due_date"] + timedelta(days=4)
    render_invoice(up / f"new_{clean['vendor_name'].split()[0].lower()}_invoice.pdf", clean, clean["vendor_id"] % 3)
    truth = {f"resent_{dup['file']}": "exact duplicate of a line already in this run",
             f"new_{clean['vendor_name'].split()[0].lower()}_invoice.pdf": "clean invoice"}
    (up / "README.txt").write_text("Drag these into Nigraan > Upload invoices during the demo.\n"
                                   + "\n".join(f"- {k}: {v}" for k, v in truth.items()) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    from data_gen.generate_company import generate

    world = generate(args.seed)
    meta = write_demo_week(world, get_settings().demo_week_dir)
    print(json.dumps(meta, indent=2, default=str))


if __name__ == "__main__":
    main()
