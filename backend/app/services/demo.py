"""Demo controls (DEMO_MODE only): reset the seeded company, load the demo week."""
from __future__ import annotations

import json
import threading
import time
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import ApiError
from app.models import Company, PaymentRun, User
from app.services.importer import import_csv
from app.services.payment_runs import audit, create_run, run_detail
from app.services.runtime import runtime

_reset_lock = threading.Lock()


def reset(seed: int | None = None) -> dict:
    from data_gen.generate_company import generate
    from data_gen.loader import load_world

    s = get_settings()
    with _reset_lock:
        t0 = time.perf_counter()
        world = generate(seed or s.seed)
        load_world(world)
        runtime.load_models(s.models_dir)  # also reverts any in-session retrain
        return {"seed": seed or s.seed, "seconds": round(time.perf_counter() - t0, 1), "payments": len(world.payments),
                "invoices": len(world.invoices), "model_version": runtime.bundle.version}


def load_week(db: Session, user: User) -> dict:
    s = get_settings()
    if db.execute(select(PaymentRun).where(PaymentRun.status == "open")).scalars().first():
        raise ApiError(409, "run_open", "A payment run is already open. Reset the demo to load the week again.")
    csv_path = s.demo_week_dir / "invoices.csv"
    if not csv_path.exists():
        raise ApiError(500, "demo_missing", "demo_week/invoices.csv not found (run python -m data_gen.render_pdfs)")
    week = json.loads((s.demo_week_dir / "week.json").read_text())
    company = db.execute(select(Company)).scalars().first()
    t0 = time.perf_counter()
    imported = import_csv(db, csv_path.read_text(), user, source="csv")
    pay_date = date.fromisoformat(week["pay_date"])
    meta = {r["invoice_id"]: dict(r["meta"], pay_date=pay_date) for r in imported}
    run = create_run(db, user, company.as_of_date, [r["invoice_id"] for r in imported],
                     name=f"Weekly run {company.as_of_date:%d %b %Y}", line_meta=meta)
    audit(db, user, "load_demo_week", "payment_run", run.id, invoices=len(imported))
    db.commit()
    detail = run_detail(db, run, with_cash=False)
    return {"run_id": run.id, "invoices": len(imported), "seconds": round(time.perf_counter() - t0, 1),
            "totals": detail["totals"]}
