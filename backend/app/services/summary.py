"""LLM case summary (section 6.6).

The LLM receives ONLY structured evidence (never invoice text - prompt-injection safety) and writes
3-4 sentences + one verification step. Every number in its output must appear in the evidence;
otherwise we show the evidence list only. Without a key we show a deterministic template (labelled).
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AiCache, Case, RiskScore
from app.money import fmt_rs
from app.services.cases import suspected_case_type, verification_step
from app.services.docreader import gemini
from app.services.scoring.scorer import FRAUD_TYPES

PROMPT = (
    "You write a short case note for a finance approver at a Pakistani SME. Use ONLY the JSON evidence below. "
    "Write 3-4 plain sentences explaining why this payment was stopped, then one line starting 'Verify:' with the "
    "single most useful verification step. Do not invent facts, numbers, names or dates. Do not give a score. "
    "Copy amounts, dates and invoice numbers exactly as they appear in the evidence (e.g. 'Rs 4,50,000'). "
    "{lang}\n\nEVIDENCE:\n{evidence}"
)
LANG = {"en": "Write in English.", "ur": "Write in Roman Urdu (Urdu in Latin script), simple business language."}


def _evidence(case: Case, s: RiskScore) -> dict:
    p = case.payment
    ev = s.evidence_json or {}
    out = {
        "vendor": p.vendor.name, "amount": fmt_rs(int(p.amount)), "invoice_no": p.invoice.invoice_no,
        "decision": {"allow": "allowed", "review": "needs review", "blocked": "blocked"}[s.decision],
        "suspected_pattern": FRAUD_TYPES.get(suspected_case_type(case, s) or "", "Unusual payment"),
        "reasons": [r["text"] for r in (s.reasons_json or []) if r.get("engine") != "info"][:5],
        "suggested_verification": verification_step(case, s),
    }
    if ev.get("duplicate") and ev["duplicate"].get("prob", 0) >= 0.5:
        m = ev["duplicate"]["match"]
        out["matched_invoice"] = {"invoice_no": m["invoice_no"], "date": m["invoice_date"], "amount": m["total_fmt"],
                                  "status": m["status"]}
    hist = (ev.get("bank") or {}).get("history") or []
    if len(hist) > 1:
        cur = hist[-1]
        out["bank_change"] = {"changed_on": cur["valid_from"][:10], "changed_by": cur["changed_by"], "source": cur["source"],
                              "new_account_last4": cur["last4"], "previous_account_last4": hist[-2]["last4"]}
    return out


def _numbers(text: str) -> set[str]:
    return {re.sub(r"[,\s]", "", n) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def check_numbers(output: str, evidence: dict) -> bool:
    allowed = _numbers(json.dumps(evidence, ensure_ascii=False))
    return all(n in allowed or len(n) <= 1 for n in _numbers(output))


def case_summary(db: Session, case: Case, lang: str = "en") -> dict:
    s = db.execute(select(RiskScore).where(RiskScore.payment_id == case.payment_id).order_by(RiskScore.id.desc())).scalars().first()
    if s is None:
        return {"mode": "none", "text": None, "evidence": None}
    ev = _evidence(case, s)
    settings = get_settings()
    lang = lang if lang in LANG else "en"
    payload = json.dumps(ev, ensure_ascii=False, sort_keys=True)
    key = gemini.cache_key("summary-" + lang, settings.gemini_model, payload.encode())
    hit = db.get(AiCache, key)
    text, mode = None, None
    if hit is not None:
        text, mode = hit.response_json.get("text"), "llm_cached"
    elif settings.gemini_api_key:
        try:
            out = gemini.call_gemini([{"text": PROMPT.format(lang=LANG[lang], evidence=payload)}], None, settings.ai_timeout_s)
            text, mode = out["text"].strip(), "llm"
            db.merge(AiCache(key=key, kind="summary", model=settings.gemini_model, response_json={"text": text},
                             created_at=datetime.now(timezone.utc).replace(tzinfo=None)))
            db.commit()
        except gemini.GeminiUnavailable:
            text = None
    if text is not None:
        if check_numbers(text, ev):
            return {"mode": mode, "text": text, "evidence": ev, "guardrail": "passed: every number appears in the evidence"}
        return {"mode": "evidence_only", "text": None, "evidence": ev,
                "guardrail": "failed: the summary contained a number not in the evidence, so it is hidden"}
    # deterministic template (no LLM available)
    reasons = ev["reasons"][:3]
    if lang == "ur":
        verb = {"blocked": "rok di hai", "needs review": "review ke liye bheji hai", "allowed": "allow ki hai"}[ev["decision"]]
        t = (f"Nigraan ne {ev['vendor']} ko {ev['amount']} ki payment (invoice {ev['invoice_no']}) {verb}; "
             f"shak hai ke yeh {ev['suspected_pattern'].lower()} ho sakta hai. Wajah: " + "; ".join(reasons) + "."
             + f"\nTasdeeq: {ev['suggested_verification']}")
    else:
        t = (f"Nigraan {ev['decision']} the {ev['amount']} payment to {ev['vendor']} (invoice {ev['invoice_no']}) "
             f"as a possible {ev['suspected_pattern'].lower()}. " + " ".join(f"{r}." for r in reasons)
             + f"\nVerify: {ev['suggested_verification']}")
    return {"mode": "template", "text": t, "evidence": ev, "guardrail": "template (no LLM key configured)"}
