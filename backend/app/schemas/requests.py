"""Request contracts (Pydantic v2). Money in requests is rupees (string or number); stored as paisa."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
from typing import Literal

from pydantic import AfterValidator, BaseModel, Field


def exact_money(value: Decimal) -> Decimal:
    """Do not silently round a request or overflow an integer-paisa ledger column."""
    if not value.is_finite() or value < 0:
        raise ValueError("Money must be finite, nonnegative and have at most two decimal places")
    if not value:
        return Decimal(0)  # discard huge exponents on zero before formatting/conversion
    if value > Decimal("92233720368547758.07"):
        raise ValueError("Money exceeds the supported ledger amount")
    # Inspect the exact representation instead of multiplying first: extreme exponents
    # could overflow or underflow the decimal context before validation runs.
    _, digits, exponent = value.as_tuple()
    # Only insignificant trailing zeroes may extend beyond the two paisa digits.
    trailing_zeroes = 0
    for digit in reversed(digits):
        if digit:
            break
        trailing_zeroes += 1
    if exponent + trailing_zeroes < -2:
        raise ValueError("Money must have at most two decimal places")
    return value


Money = Annotated[Decimal, AfterValidator(exact_money)]


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
    qty: float = Field(gt=0, allow_inf_nan=False)
    unit_price: Money = Field(description="rupees")
    amount: Money = Field(description="rupees")


class InvoicePatch(BaseModel):
    vendor_id: int | None = None
    invoice_no: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    subtotal: Money | None = None
    tax: Money | None = None
    total: Money | None = None
    lines: list[LineIn] | None = None
    confirm: bool = Field(default=False, description="Accountant confirms the extracted fields")


class RunIn(BaseModel):
    run_date: date | None = None
    invoice_ids: list[int] | None = Field(default=None, description="Defaults to all open invoices due within the run week")
    name: str | None = None


class LinesIn(BaseModel):
    payment_ids: list[int]
    note: str | None = None


class VerificationIn(BaseModel):
    result: Literal["verified_legitimate", "confirmed_issue"]
    method: Literal["registered_phone", "documents", "in_person", "requester_review"]
    checks: list[str] = Field(max_length=12)
    reference: str = Field(max_length=1000, description="Contact, document or record used to verify the case")


class ResolveIn(BaseModel):
    outcome: str = Field(description="confirmed_fraud | false_alarm")
    note: str | None = None
    block_vendor: bool = False
    verification: VerificationIn | None = None


class MoveIn(BaseModel):
    receivable_id: int
    new_date: date


class ScenarioIn(BaseModel):
    name: str = "Scenario"
    moves: list[MoveIn] = []
    hold_yellow: bool = False
    run_id: int | None = None
