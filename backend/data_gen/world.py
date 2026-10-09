"""In-memory representation of the generated company (rows are plain dicts keyed like DB columns)."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

TABLES = [
    "companies", "employees", "users", "vendors", "vendor_bank_accounts", "items", "invoices",
    "invoice_lines", "payment_runs", "payments", "cases", "customers", "receivables",
    "scheduled_outflows",
]


@dataclass
class World:
    seed: int
    companies: list[dict] = field(default_factory=list)
    employees: list[dict] = field(default_factory=list)
    users: list[dict] = field(default_factory=list)
    vendors: list[dict] = field(default_factory=list)
    vendor_bank_accounts: list[dict] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)
    invoices: list[dict] = field(default_factory=list)
    invoice_lines: list[dict] = field(default_factory=list)
    payment_runs: list[dict] = field(default_factory=list)
    payments: list[dict] = field(default_factory=list)
    cases: list[dict] = field(default_factory=list)
    customers: list[dict] = field(default_factory=list)
    receivables: list[dict] = field(default_factory=list)
    scheduled_outflows: list[dict] = field(default_factory=list)
    # Hidden ground truth: never loaded into the app database.
    labels: list[dict] = field(default_factory=list)  # payment_id, fraud_type, group_id
    receivable_truth: list[dict] = field(default_factory=list)  # receivable_id, true_paid_date
    customer_profiles: dict[int, str] = field(default_factory=dict)
    demo_week: dict = field(default_factory=dict)

    def frames(self) -> dict[str, pd.DataFrame]:
        out = {}
        for t in TABLES:
            rows = getattr(self, t)
            out[t] = pd.DataFrame(rows)
        return out

    def labels_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.labels, columns=["payment_id", "fraud_type", "group_id"])
