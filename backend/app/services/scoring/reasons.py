"""Map model contributions to plain-English reasons."""
from __future__ import annotations

import math


def _hhmm(h: float) -> str:
    hh = int(h) % 24
    mm = int(round((h - int(h)) * 60)) % 60
    suffix = "AM" if hh < 12 else "PM"
    return f"{(hh % 12) or 12}:{mm:02d} {suffix}"


def feature_reason(name: str, v: float, f: dict) -> str | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if name == "amount_vs_vendor_median":
        return f"Amount is {v:.1f}× this vendor's usual payment" if v >= 1.3 else None
    if name == "amount_vendor_z":
        return f"Amount far above this vendor's normal range ({v:.1f} std. dev.)" if v >= 2 else None
    if name == "unit_price_vs_median_max":
        return f"Unit price {v:.2f}× the 90-day median for this item" if v >= 1.15 else None
    if name == "unit_price_vs_vendor_last":
        return f"Unit price {v:.2f}× this vendor's last price for the item" if v >= 1.15 else None
    if name == "days_since_bank_change":
        if f.get("account_changed"):
            if v < 1:
                return f"Bank account changed {max(1, round(v * 24))} hour{'s' if round(v * 24) > 1 else ''} before this payment"
            return f"Bank account changed {v:.0f} day{'s' if round(v) != 1 else ''} ago" if v <= 60 else None
        return f"Vendor and bank account only {v:.0f} days old" if v <= 60 else None
    if name == "account_changed":
        return "Paying to a changed bank account" if v else None
    if name == "first_payment_to_account":
        return "First payment ever to this bank account" if v else None
    if name in ("changer_prior_edits", "changer_edit_share"):
        n = f.get("changer_prior_edits")
        share = f.get("changer_edit_share")
        if share is not None and not math.isnan(share) and share < 0.15:
            what = "Bank details changed" if f.get("account_changed") else "Vendor set up"
            return f"{what} by a user who rarely edits vendors ({0 if n is None or math.isnan(n) else int(n)} edits before)"
        return None
    if name == "change_unverified":
        return "Bank change requested by email/phone, not verified in writing" if v else None
    if name == "vendor_age_days":
        return f"Vendor added only {v:.0f} days ago" if v <= 120 else None
    if name == "vendor_prior_invoices":
        return f"Only {v:.0f} previous invoice{'s' if v != 1 else ''} from this vendor" if v <= 5 else None
    if name == "is_round_amount":
        return "Suspiciously round amount" if v else None
    if name == "vendor_round_share":
        return f"{v:.0%} of this vendor's invoices are round amounts" if v >= 0.5 else None
    if name == "no_sales_tax":
        return "No sales tax charged (unregistered vendor)" if v else None
    if name == "same_payee_48h":
        return f"{v:.0f} other payment{'s' if v != 1 else ''} to this vendor in the last 48 h" if v >= 1 else None
    if name == "same_payee_48h_vs_limit":
        return f"Payments to this vendor in 48 h add up to {v:.1f}× the approval limit" if v >= 1 else None
    if name == "limit_gap":
        return f"Just under the approval limit ({v:.0%} below)" if 0 <= v <= 0.15 else None
    if name == "creator_can_approve":
        return "Entered by a user who can also approve payments" if v else None
    if name == "entry_hour":
        return f"Entered at {_hhmm(v)}" if v >= 21 or v < 7 else None
    if name == "is_night":
        return f"Entered at night ({_hhmm(f.get('entry_hour', 0))})" if v else None
    if name == "off_day":
        return "Entered on a Sunday or public holiday" if v else None
    if name == "vague_line_share":
        return "Vague line items (e.g. 'consultancy services')" if v >= 0.5 else None
    if name == "days_receipt_to_payment":
        if v < 0.05:
            return "Paid within an hour of the invoice being entered (no time to verify)"
        return f"Payment prepared {v * 24:.0f} hours after the invoice arrived" if v < 1 else None
    if name == "days_to_due":
        return f"Paid {v:.0f} days before it is due" if v >= 7 else None
    if name == "amount_log":
        return f"Large amount (Rs {10 ** v:,.0f})" if v >= 5.5 else None
    return None


LABEL = {
    "amount_log": "Payment size", "amount_vs_vendor_median": "Amount vs this vendor's usual",
    "amount_vendor_z": "Amount vs this vendor's range", "unit_price_vs_median_max": "Unit price vs 90-day item median",
    "unit_price_vs_vendor_last": "Unit price vs vendor's last price", "days_since_bank_change": "Age of bank account (days)",
    "account_changed": "Bank account changed", "first_payment_to_account": "First payment to account",
    "changer_prior_edits": "Edits by the user who set the account", "changer_edit_share": "Share of vendor edits by that user",
    "change_unverified": "Unverified bank change", "vendor_age_days": "Vendor age (days)",
    "vendor_prior_invoices": "Previous invoices from vendor", "is_round_amount": "Round amount",
    "vendor_round_share": "Vendor's share of round invoices", "no_sales_tax": "No sales tax",
    "same_payee_48h": "Other payments to vendor in 48 h", "same_payee_48h_vs_limit": "48-h total vs approval limit",
    "limit_gap": "Distance below approval limit", "creator_can_approve": "Creator can approve",
    "entry_hour": "Entry hour", "is_night": "Entered at night", "off_day": "Entered on Sunday/holiday",
    "vague_line_share": "Vague line items", "line_count": "Number of lines",
    "days_receipt_to_payment": "Days from invoice to payment", "days_to_due": "Days before due date",
}


def generic_reason(name: str, v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return f"{LABEL.get(name, name)}: missing"
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return f"{LABEL.get(name, name)}: {v:.2f}" if isinstance(v, float) else f"{LABEL.get(name, name)}: {v}"


def top_feature_reasons(contribs: dict[str, float], feats: dict[str, float], k: int = 3) -> list[dict]:
    out, seen = [], set()
    for i, (name, c) in enumerate(sorted(contribs.items(), key=lambda kv: -kv[1])):
        if c <= 0.05:
            break
        text = feature_reason(name, feats.get(name), feats)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append({"feature": name, "text": text, "contribution": round(float(c), 3), "value": feats.get(name)})
        if len(out) == k:
            break
    if not out:  # never hide the main driver: fall back to the raw value of the top feature
        name, c = max(contribs.items(), key=lambda kv: kv[1])
        if c >= 1.0:
            out.append({"feature": name, "text": generic_reason(name, feats.get(name)), "contribution": round(float(c), 3),
                        "value": feats.get(name)})
    return out
