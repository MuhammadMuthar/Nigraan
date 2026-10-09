"""Field accuracy of the document reader on the 40 demo-week PDFs vs the generator's ground truth.

    python -m ml.eval_extraction

Uses whatever engine is available (Gemini if GEMINI_API_KEY is set, else PDF text + regex) and also
writes demo_week/extraction_cache/<sha256>.json: genuine outputs of this pipeline, replayed (and
labelled "cached") only when no other engine can read a file.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

from app.config import get_settings
from app.services.docreader.pipeline import extract_document
from app.services.docreader.schema import FIELDS


def _eq(field: str, got, want) -> bool:
    if want is None:
        return got in (None, "")
    if got is None:
        return False
    if field in ("subtotal", "tax", "total"):
        return abs(float(got) - float(want)) <= 0.5
    if field == "vendor_name":
        return str(got).strip().lower() == str(want).strip().lower()
    return str(got).replace(" ", "").upper() == str(want).replace(" ", "").upper()


def main() -> None:
    s = get_settings()
    truth = json.loads((s.demo_week_dir / "ground_truth.json").read_text())
    cache = s.demo_week_dir / "extraction_cache"
    cache.mkdir(exist_ok=True)
    per_field = Counter()
    total = Counter()
    lines_ok = 0
    engines = Counter()
    misses = []
    for name, want in truth.items():
        data = (s.demo_week_dir / "pdfs" / name).read_bytes()
        ext = extract_document(None, name, "application/pdf", data)
        engines[ext["engine"]] += 1
        got = ext["fields"]
        for f in FIELDS:
            total[f] += 1
            if _eq(f, got.get(f), want.get(f)):
                per_field[f] += 1
            else:
                misses.append({"file": name, "field": f, "got": got.get(f), "want": want.get(f)})
        gl, wl = got.get("line_items") or [], want["line_items"]
        if len(gl) == len(wl) and all(abs((g.get("amount") or 0) - w["amount"]) <= 0.5 and g["name"] == w["name"]
                                      for g, w in zip(gl, wl)):
            lines_ok += 1
        (cache / f"{ext['sha256']}.json").write_text(json.dumps({"engine": ext["engine"], "extraction": got}, default=str))
    n_fields = sum(total.values())
    acc = sum(per_field.values()) / n_fields
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": {"field_accuracy": acc, "engine": ", ".join(f"{k} ({v})" for k, v in engines.items()),
                    "files": len(truth), "line_items_exact": lines_ok / len(truth)},
        "per_field": {f: per_field[f] / total[f] for f in FIELDS},
        "misses": misses[:30],
        "note": "Ground truth = the generator's invoice data. Gemini results appear here only when GEMINI_API_KEY is set.",
    }
    (s.models_dir / "extraction_eval.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"field accuracy {acc:.3f} over {len(truth)} files ({out['summary']['engine']}); "
          f"line items exact {lines_ok}/{len(truth)}")
    for f in FIELDS:
        print(f"  {f:13} {per_field[f]}/{total[f]}")
    for m in misses[:8]:
        print("  miss", m)


if __name__ == "__main__":
    main()
