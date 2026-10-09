"""Identifier hygiene shared by the generator, the app and the ML features.

CNICs and full IBANs are never stored: only a salted SHA-256 and the last 4 digits.
"""
from __future__ import annotations

import hashlib
import os
import re

HASH_SALT = os.environ.get("HASH_SALT", "nigraan-demo-salt")


def hash_id(value: str) -> str:
    norm = re.sub(r"[^0-9A-Za-z]", "", value).upper()
    return hashlib.sha256((HASH_SALT + ":" + norm).encode()).hexdigest()


def last4(value: str) -> str:
    digits = re.sub(r"[^0-9A-Za-z]", "", value)
    return digits[-4:]


def norm_phone(phone: str) -> str:
    d = re.sub(r"\D", "", phone or "")
    if d.startswith("92") and len(d) == 12:
        d = "0" + d[2:]
    return d


_ADDR_SUBS = [
    (r"\bst\b\.?", "street"), (r"\brd\b\.?", "road"), (r"\bno\b\.?", ""), (r"#", ""),
    (r"\bblk\b\.?", "block"), (r"\bmkt\b\.?", "market"), (r"\bh\b\.?", "house"),
]


def norm_address(addr: str) -> str:
    a = (addr or "").lower()
    a = re.sub(r"[,.\-/]", " ", a)
    for pat, rep in _ADDR_SUBS:
        a = re.sub(pat, rep, a)
    a = re.sub(r"\blahore\b|\bpakistan\b|\bpunjab\b", "", a)
    return re.sub(r"\s+", " ", a).strip()


def norm_invoice_no(no: str) -> str:
    """'INV-0102' -> '102', 'INV102' -> '102', 'BD/25/0102' -> '25102'.

    Strip letters/prefixes, separators and leading zeros of every digit group, then join.
    A trailing letter suffix ('102A') is kept so it stays *similar*, not equal.
    """
    s = (no or "").upper().strip()
    suffix = ""
    m = re.search(r"\d([A-Z]{1,2})$", s)
    if m:
        suffix = m.group(1)
    groups = re.findall(r"\d+", s)
    if not groups:
        return re.sub(r"[^A-Z0-9]", "", s)
    return "".join(g.lstrip("0") or "0" for g in groups) + suffix


# --- Pakistani IBAN: 'PK' + 2 check digits + 4-letter bank code + 16 digits (24 chars) ---

def _iban_mod97(iban: str) -> int:
    s = iban[4:] + iban[:4]
    num = "".join(str(int(c, 36)) for c in s)
    return int(num) % 97


def make_pk_iban(bank_code: str, account16: str) -> str:
    base = f"PK00{bank_code}{account16}"
    check = 98 - _iban_mod97(base)
    return f"PK{check:02d}{bank_code}{account16}"


def is_valid_pk_iban(iban: str) -> bool:
    s = re.sub(r"\s", "", iban or "").upper()
    if not re.fullmatch(r"PK\d{2}[A-Z]{4}\d{16}", s):
        return False
    return _iban_mod97(s) == 1


NTN_RE = re.compile(r"^(\d{7}-\d|\d{13})$")


def is_valid_ntn(ntn: str) -> bool:
    return bool(NTN_RE.match((ntn or "").strip()))


def mask_iban(iban_last4: str | None) -> str:
    return f"PK•• •••• •••• {iban_last4}" if iban_last4 else "—"
