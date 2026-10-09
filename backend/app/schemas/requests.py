"""Request contracts (Pydantic v2). Money in requests is rupees (string or number); stored as paisa."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str
    password: str


class VendorIn(BaseModel):
    name: str = Field(min_length=2)
    ntn: str | None = None
    strn: str | None = None
    category: str = "staples"
    phone: str
    address: str
    iban: str
    bank_name: str = "HBL"
    payment_terms_days: int = 30


class VendorPatch(BaseModel):
    phone: str | None = None
    address: str | None = None
    payment_terms_days: int | None = None
    iban: str | None = Field(default=None, description="New IBAN: creates a pending bank change that a second user must approve")
    bank_name: str | None = None
    change_source: str = Field(default="vendor_letter", description="vendor_letter | email | phone | portal")


class LineIn(BaseModel):
    description: str
    qty: float
    unit_price: float = Field(description="rupees")
    amount: float = Field(description="rupees")


class InvoicePatch(BaseModel):
    vendor_id: int | None = None
    invoice_no: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    lines: list[LineIn] | None = None
    confirm: bool = Field(default=False, description="Accountant confirms the extracted fields")


class RunIn(BaseModel):
    run_date: date | None = None
    invoice_ids: list[int] | None = Field(default=None, description="Defaults to all open invoices due within the run week")
    name: str | None = None


class LinesIn(BaseModel):
    payment_ids: list[int]
    note: str | None = None


class ResolveIn(BaseModel):
    outcome: str = Field(description="confirmed_fraud | false_alarm")
    note: str | None = None
    block_vendor: bool = False


class MoveIn(BaseModel):
    receivable_id: int
    new_date: date


class ScenarioIn(BaseModel):
    name: str = "Scenario"
    moves: list[MoveIn] = []
    hold_yellow: bool = False
    run_id: int | None = None
