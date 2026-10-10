"""All tables. Money columns are BIGINT paisa. Timestamps are naive UTC."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(80))
    sector: Mapped[str] = mapped_column(String(120))
    approval_limit: Mapped[int] = mapped_column(BigInteger)
    opening_cash: Mapped[int] = mapped_column(BigInteger)  # bank balance at as_of_date
    cash_reserve: Mapped[int] = mapped_column(BigInteger)
    as_of_date: Mapped[date] = mapped_column(Date)
    audited_through: Mapped[date] = mapped_column(Date)  # payments up to here have been audited (labels)
    data_seed: Mapped[int] = mapped_column(Integer, default=42)


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(60))
    designation: Mapped[str] = mapped_column(String(80))
    cnic_hash: Mapped[str] = mapped_column(String(64), index=True)
    cnic_last4: Mapped[str] = mapped_column(String(4))
    phone: Mapped[str] = mapped_column(String(20), index=True)
    address: Mapped[str] = mapped_column(String(250))
    address_norm: Mapped[str] = mapped_column(String(250), index=True)
    bank_hash: Mapped[str] = mapped_column(String(64), index=True)
    bank_last4: Mapped[str] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(20), default="active")
    hire_date: Mapped[date] = mapped_column(Date)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), unique=True)
    role: Mapped[str] = mapped_column(String(20))  # accountant | approver | owner
    password_hash: Mapped[str] = mapped_column(String(100))
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)


class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    ntn: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    strn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    category: Mapped[str] = mapped_column(String(60))
    phone: Mapped[str] = mapped_column(String(20), index=True)
    address: Mapped[str] = mapped_column(String(250))
    address_norm: Mapped[str] = mapped_column(String(250), index=True)
    owner_cnic_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    home_bank: Mapped[str] = mapped_column(String(40))
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    invoice_prefix: Mapped[str] = mapped_column(String(20), default="INV-")
    # Related-party register (Companies Act 2017 disclosure): known links are expected, not suspicious
    related_party_note: Mapped[str | None] = mapped_column(String(250), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | blocked
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    bank_accounts: Mapped[list[VendorBankAccount]] = relationship(back_populates="vendor", order_by="VendorBankAccount.valid_from")


class VendorBankAccount(Base):
    """Full history: a change closes the old row (valid_to) and opens a new one."""
    __tablename__ = "vendor_bank_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    bank_name: Mapped[str] = mapped_column(String(40))
    iban_hash: Mapped[str] = mapped_column(String(64), index=True)
    iban_last4: Mapped[str] = mapped_column(String(4))
    valid_from: Mapped[datetime] = mapped_column(DateTime)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    change_source: Mapped[str] = mapped_column(String(30))  # onboarding | vendor_letter | email | phone | portal
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # active | pending (awaiting a second user) | rejected. History before Nigraan is all 'active'.
    status: Mapped[str] = mapped_column(String(20), default="active")
    requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    vendor: Mapped[Vendor] = relationship(back_populates="bank_accounts")


class Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    unit: Mapped[str] = mapped_column(String(20))
    category: Mapped[str] = mapped_column(String(60))
    base_price: Mapped[int] = mapped_column(BigInteger)


class Invoice(Base):
    """Vendor (payable) invoices."""
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    direction: Mapped[str] = mapped_column(String(10), default="payable")
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), index=True, nullable=True)
    invoice_no: Mapped[str] = mapped_column(String(60))
    invoice_no_norm: Mapped[str] = mapped_column(String(60), index=True)
    invoice_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    received_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    subtotal: Mapped[int] = mapped_column(BigInteger)
    tax: Mapped[int] = mapped_column(BigInteger)
    total: Mapped[int] = mapped_column(BigInteger)
    ntn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    iban_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    iban_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="received")  # received | scheduled | paid | rejected
    source: Mapped[str] = mapped_column(String(20), default="erp")  # erp | csv | upload
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    extraction_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    lines: Mapped[list[InvoiceLine]] = relationship(back_populates="invoice", order_by="InvoiceLine.id")
    vendor: Mapped[Vendor | None] = relationship()


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), nullable=True, index=True)
    description: Mapped[str] = mapped_column(String(200))
    qty: Mapped[float] = mapped_column(Float)
    unit_price: Mapped[int] = mapped_column(BigInteger)
    amount: Mapped[int] = mapped_column(BigInteger)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class PaymentRun(Base):
    __tablename__ = "payment_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(120))
    run_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | closed | exported
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)  # created in the app (vs. history)

    payments: Mapped[list[Payment]] = relationship(back_populates="run", order_by="Payment.id")


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("payment_runs.id"), index=True, nullable=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    bank_account_id: Mapped[int] = mapped_column(ForeignKey("vendor_bank_accounts.id"))
    amount: Mapped[int] = mapped_column(BigInteger)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pay_date: Mapped[date] = mapped_column(Date, index=True)  # value date at the bank
    # pending | approved | held | blocked | exported (unsettled) | released (settled) | rejected
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # Set when a red line's case is closed as a false alarm: the line then needs a second approver.
    override_decision: Mapped[str | None] = mapped_column(String(10), nullable=True)
    override_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    run: Mapped[PaymentRun | None] = relationship(back_populates="payments")
    invoice: Mapped[Invoice] = relationship()
    vendor: Mapped[Vendor] = relationship()
    bank_account: Mapped[VendorBankAccount] = relationship()


class RiskScore(Base):
    """Append-only: a re-score adds a row, it never overwrites."""
    __tablename__ = "risk_scores"
    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(10))  # allow | review | blocked
    reasons_json: Mapped[list] = mapped_column(JSON)
    engine_scores_json: Mapped[dict] = mapped_column(JSON)
    evidence_json: Mapped[dict] = mapped_column(JSON)
    trace_json: Mapped[list] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), index=True)
    risk_score_id: Mapped[int | None] = mapped_column(ForeignKey("risk_scores.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | confirmed_fraud | false_alarm
    fraud_type: Mapped[str | None] = mapped_column(String(30), nullable=True)  # suspected / confirmed type
    source: Mapped[str] = mapped_column(String(20), default="auto")  # auto | historical | manual
    opened_at: Mapped[datetime] = mapped_column(DateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[int] = mapped_column(BigInteger)

    payment: Mapped[Payment] = relationship()
    events: Mapped[list[CaseEvent]] = relationship(back_populates="case", order_by="CaseEvent.at")


class CaseEvent(Base):
    __tablename__ = "case_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))
    detail_json: Mapped[dict] = mapped_column(JSON, default=dict)

    case: Mapped[Case] = relationship(back_populates="events")


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    city: Mapped[str] = mapped_column(String(60))
    segment: Mapped[str] = mapped_column(String(40))  # kiryana | superstore | wholesaler | pharmacy
    terms_days: Mapped[int] = mapped_column(Integer)
    phone: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[date] = mapped_column(Date)


class Receivable(Base):
    __tablename__ = "receivables"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    invoice_no: Mapped[str] = mapped_column(String(40))
    issue_date: Mapped[date] = mapped_column(Date, index=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    terms_days: Mapped[int] = mapped_column(Integer)
    amount: Mapped[int] = mapped_column(BigInteger)
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    paid_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    disputed_amount: Mapped[int] = mapped_column(BigInteger, default=0)

    customer: Mapped[Customer] = relationship()


class ScheduledOutflow(Base):
    __tablename__ = "scheduled_outflows"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(30))  # rent | salaries | tax | utilities | other
    due_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    basis: Mapped[str] = mapped_column(String(20), default="fact")  # fact | assumption


class Scenario(Base):
    __tablename__ = "scenarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    params_json: Mapped[dict] = mapped_column(JSON)
    result_json: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail_json: Mapped[dict] = mapped_column(JSON, default=dict)


class AiCache(Base):
    __tablename__ = "ai_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(60))
    response_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(40), unique=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime)
    n_labels: Mapped[int] = mapped_column(Integer)
    metrics_json: Mapped[dict] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


Index("ix_payments_vendor_created", Payment.vendor_id, Payment.created_at)
Index("ix_invoices_vendor_received", Invoice.vendor_id, Invoice.received_at)
