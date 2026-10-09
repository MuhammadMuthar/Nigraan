"""Ledger: the tables the engines read, as pandas frames.

The same object is built from the generator (training/evaluation) or from the database (live
scoring), so the feature code is identical in both paths.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import tables as T

DT_COLS = {
    "vendors": ["created_at", "blocked_at"],
    "vendor_bank_accounts": ["valid_from", "valid_to", "blocked_at"],
    "employees": ["hire_date"],
    "invoices": ["invoice_date", "due_date", "received_at"],
    "payments": ["created_at", "approved_at", "pay_date"],
    "receivables": ["issue_date", "due_date", "paid_date"],
    "customers": ["created_at"],
    "scheduled_outflows": ["due_date"],
    "cases": ["opened_at", "resolved_at"],
}

COLUMNS = {
    "users": ["id", "name", "email", "role", "employee_id"],
    "employees": ["id", "name", "department", "designation", "cnic_hash", "phone", "address", "address_norm",
                  "bank_hash", "bank_last4", "hire_date"],
    "vendors": ["id", "name", "ntn", "category", "phone", "address", "address_norm", "owner_cnic_hash", "status",
                "blocked_at", "created_at", "created_by", "related_party_note"],
    "vendor_bank_accounts": ["id", "vendor_id", "bank_name", "iban_hash", "iban_last4", "valid_from", "valid_to",
                             "changed_by", "approved_by", "change_source", "is_blocked", "blocked_at", "status"],
    "items": ["id", "name", "unit", "category"],
    "invoices": ["id", "vendor_id", "invoice_no", "invoice_no_norm", "invoice_date", "due_date", "received_at",
                 "subtotal", "tax", "total", "status", "created_by", "iban_hash", "source"],
    "invoice_lines": ["id", "invoice_id", "item_id", "description", "qty", "unit_price", "amount"],
    "payments": ["id", "run_id", "invoice_id", "vendor_id", "bank_account_id", "amount", "created_by", "created_at",
                 "approved_by", "approved_at", "pay_date", "status"],
    "cases": ["id", "payment_id", "status", "fraud_type", "source", "opened_at", "resolved_at"],
}

MODEL_BY_TABLE = {
    "users": T.User, "employees": T.Employee, "vendors": T.Vendor, "vendor_bank_accounts": T.VendorBankAccount,
    "items": T.Item, "invoices": T.Invoice, "invoice_lines": T.InvoiceLine, "payments": T.Payment, "cases": T.Case,
}


@dataclass
class Ledger:
    company: dict
    users: pd.DataFrame
    employees: pd.DataFrame
    vendors: pd.DataFrame
    accounts: pd.DataFrame
    items: pd.DataFrame
    invoices: pd.DataFrame
    lines: pd.DataFrame
    payments: pd.DataFrame
    cases: pd.DataFrame

    @staticmethod
    def _frame(rows_or_df, table: str) -> pd.DataFrame:
        cols = COLUMNS[table]
        df = rows_or_df if isinstance(rows_or_df, pd.DataFrame) else pd.DataFrame(rows_or_df)
        for c in cols:
            if c not in df.columns:
                df[c] = None
        df = df[cols].copy()
        for c in DT_COLS.get(table, []):
            if c in df.columns:
                # pandas 3 may infer microsecond resolution; the engines compare int64 nanoseconds
                df[c] = pd.to_datetime(df[c]).astype("datetime64[ns]")
        return df.reset_index(drop=True)

    @classmethod
    def from_world(cls, world) -> "Ledger":
        return cls(
            company=dict(world.companies[0]),
            users=cls._frame(world.users, "users"),
            employees=cls._frame(world.employees, "employees"),
            vendors=cls._frame(world.vendors, "vendors"),
            accounts=cls._frame(world.vendor_bank_accounts, "vendor_bank_accounts"),
            items=cls._frame(world.items, "items"),
            invoices=cls._frame(world.invoices, "invoices"),
            lines=cls._frame(world.invoice_lines, "invoice_lines"),
            payments=cls._frame(world.payments, "payments"),
            cases=cls._frame(world.cases, "cases"),
        )

    @classmethod
    def from_db(cls, db: Session) -> "Ledger":
        frames = {}
        for table, model in MODEL_BY_TABLE.items():
            cols = [getattr(model, c) for c in COLUMNS[table]]
            rows = db.execute(select(*cols)).all()
            frames[table] = cls._frame(pd.DataFrame(rows, columns=COLUMNS[table]), table)
        acc = frames["vendor_bank_accounts"]
        frames["vendor_bank_accounts"] = acc[acc["status"].fillna("active") == "active"].reset_index(drop=True)
        comp = db.execute(select(T.Company)).scalars().first()
        company = {c.name: getattr(comp, c.name) for c in T.Company.__table__.columns}
        return cls(company=company, users=frames["users"], employees=frames["employees"], vendors=frames["vendors"],
                   accounts=frames["vendor_bank_accounts"], items=frames["items"], invoices=frames["invoices"],
                   lines=frames["invoice_lines"], payments=frames["payments"], cases=frames["cases"])
