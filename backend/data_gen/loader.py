"""Write a generated World into the database, and the hidden ground truth to data_out/."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import bcrypt
from sqlalchemy import insert, text

from app.db import Base, engine
from app.models import tables as T
from data_gen.world import World

DEMO_PASSWORD = "nigraan-demo"

ORDER = [
    ("companies", T.Company), ("employees", T.Employee), ("users", T.User), ("vendors", T.Vendor),
    ("vendor_bank_accounts", T.VendorBankAccount), ("items", T.Item), ("invoices", T.Invoice),
    ("invoice_lines", T.InvoiceLine), ("payment_runs", T.PaymentRun), ("payments", T.Payment),
    ("cases", T.Case), ("customers", T.Customer), ("receivables", T.Receivable),
    ("scheduled_outflows", T.ScheduledOutflow),
]


def _clean(row: dict, cols: set[str]) -> dict:
    return {k: v for k, v in row.items() if not k.startswith("_") and k in cols}


def load_world(world: World, *, drop: bool = True) -> None:
    import app.models  # noqa: F401  (register tables)

    if drop:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    pw = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt(rounds=10)).decode()
    for u in world.users:
        u["password_hash"] = pw
    with engine.begin() as conn:
        for name, model in ORDER:
            rows = getattr(world, name)
            if not rows:
                continue
            cols = {c.name for c in model.__table__.columns}
            payload = [_clean(r, cols) for r in rows]
            for i in range(0, len(payload), 2000):
                conn.execute(insert(model), payload[i:i + 2000])
        if engine.dialect.name == "postgresql":
            for name, model in ORDER:
                conn.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{model.__tablename__}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {model.__tablename__}), 1))"))


def write_hidden_files(world: World, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "labels.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=["payment_id", "fraud_type", "group_id", "created_at", "amount"])
        wr.writeheader()
        for r in world.labels:
            wr.writerow(r)
    with open(out / "receivables_truth.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=["receivable_id", "true_paid_date", "profile", "late"])
        wr.writeheader()
        for r in world.receivable_truth:
            wr.writerow(r)
    (out / "README.txt").write_text(
        "Hidden ground truth written by data_gen.generate_company. The application never reads this folder.\n"
        "It is used only by ml/evaluate.py and tests.\n")
    if world.demo_week:
        (out / "demo_calibration.json").write_text(json.dumps(world.demo_week.get("calibration", {}), indent=2, default=str))
