"""Money is always integer paisa. These helpers are the only place we convert."""
from __future__ import annotations

PAISA_PER_RUPEE = 100


def rupees_to_paisa(rupees: int | float | str) -> int:
    """Exact conversion; strings avoid float rounding ("1430000.50")."""
    if isinstance(rupees, str):
        s = rupees.replace(",", "").replace("Rs", "").strip()
        if "." in s:
            whole, frac = s.split(".", 1)
            frac = (frac + "00")[:2]
            sign = -1 if whole.startswith("-") else 1
            return int(whole) * 100 + sign * int(frac)
        return int(s) * 100
    if isinstance(rupees, int):
        return rupees * 100
    return int(round(rupees * 100))


def group_lakh(n: int) -> str:
    """1430000 -> '14,30,000' (South Asian grouping)."""
    s = str(abs(n))
    if len(s) <= 3:
        out = s
    else:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        out = ",".join(parts + [tail])
    return ("-" if n < 0 else "") + out


def fmt_rs(paisa: int | None) -> str:
    if paisa is None:
        return "—"
    rupees = paisa // 100 if paisa >= 0 else -((-paisa) // 100)
    return f"Rs {group_lakh(rupees)}"
