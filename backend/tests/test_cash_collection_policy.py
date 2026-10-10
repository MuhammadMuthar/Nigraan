"""Unconfirmed overdue receipts cannot flatter the base reserve calculation."""
from datetime import date, timedelta

import pandas as pd
import pytest

from app.services.cash import service
from app.services.cash.inputs import estimate_receipts, receipt_flows

AS_OF = date(2026, 10, 12)


def ledger():
    rows = []
    for rid, delay in enumerate([2, 4, 5, 6, 10], 1):
        due = date(2026, 9, rid)
        rows.append({"id": rid, "customer_id": 1, "invoice_no": f"H{rid}",
                     "issue_date": due - timedelta(days=10), "due_date": due,
                     "amount": 1_000_000, "paid_date": due + timedelta(days=delay),
                     "paid_amount": 1_000_000, "disputed_amount": 0})
    for rid, due, amount, disputed in [
        (10, date(2026, 10, 1), 10_000_005, 5),
        (11, date(2026, 10, 5), 3_000_000, 0),
        (12, date(2026, 10, 8), 20_000_301, 301),
    ]:
        rows.append({"id": rid, "customer_id": 1, "invoice_no": f"OPEN{rid}",
                     "issue_date": due - timedelta(days=10), "due_date": due,
                     "amount": amount, "paid_date": None, "paid_amount": None,
                     "disputed_amount": disputed})
    return pd.DataFrame(rows)


def cash_inputs():
    ci = service.CashInputs.__new__(service.CashInputs)
    ci.as_of, ci.opening, ci.reserve = AS_OF, 5_000_000, 4_000_000
    ci.receivables = ledger()
    ci.customers = pd.DataFrame([{"id": 1, "name": "Test customer", "segment": "retail"}]).set_index("id")
    ci.estimates = estimate_receipts(ci.receivables, AS_OF)
    ci.receipts = receipt_flows(ci.estimates, {1: "Test customer"})
    ci.outflows, ci.payables, ci.future_settlements = [], [], []
    ci.run, ci.lines, ci.other_lines = None, [], []
    return ci


def test_stale_receipt_has_no_fabricated_collection_date_and_is_excluded():
    estimates = {e.receivable_id: e for e in estimate_receipts(ledger(), AS_OF)}
    stale = estimates[10]
    assert stale.expected_date is None
    assert stale.included_in_base is False
    assert stale.basis == "assumption"
    assert stale.amount == 10_000_000  # disputed paisa remain excluded
    assert "unconfirmed" in stale.note
    assert {f.ref for f in receipt_flows(list(estimates.values()))} == {"receivable:11", "receivable:12"}


def test_overdue_but_within_observed_slow_delay_stays_an_estimate():
    estimate = next(e for e in estimate_receipts(ledger(), AS_OF) if e.receivable_id == 11)
    assert estimate.expected_date == AS_OF
    assert estimate.basis == "estimate"
    assert estimate.included_in_base
    assert "80th percentile" in estimate.note


def test_legacy_policy_can_reproduce_original_backtest_explicitly():
    estimates = estimate_receipts(ledger(), AS_OF, stale_policy="legacy_next_week")
    stale = next(e for e in estimates if e.receivable_id == 10)
    assert stale.expected_date == AS_OF + timedelta(days=7)
    assert sum(f.amount for f in receipt_flows(estimates)) == 33_000_000
    with pytest.raises(ValueError, match="policy"):
        estimate_receipts(ledger(), AS_OF, stale_policy="assume_everything_paid")


@pytest.fixture
def scenario_inputs(monkeypatch):
    ci = cash_inputs()
    monkeypatch.setattr(service, "CashInputs", lambda db, run: ci)
    monkeypatch.setattr(service, "open_run", lambda db: None)
    return ci


def test_scenario_adds_excluded_receipt_once_as_assumption_without_mutating_base(scenario_inputs):
    ci = scenario_inputs
    before = ci.project(ci.base_flows())
    result = service.scenario(None, [{"receivable_id": 10, "new_date": AS_OF}], False, None)
    assert result["base"]["total_in"] == before.total_in == 23_000_000
    assert result["scenario"]["total_in"] == 33_000_000
    assert result["scenario"]["weeks"][0]["inflow_by_basis"]["assumption"] == 10_000_000
    assert result["delta"]["unconfirmed_receipts_assumed_amount"] == 10_000_000
    assert result["delta"]["unconfirmed_receipts_assumed_count"] == 1
    assert ci.project(ci.base_flows()).to_dict() == before.to_dict()
    assert service.collection_policy(ci)["unconfirmed_amount"] == 10_000_000


def test_scenario_move_preserves_estimated_receipt_total(scenario_inputs):
    result = service.scenario(None, [{"receivable_id": 12, "new_date": AS_OF}], False, None)
    assert result["delta"]["total_in_change"] == 0
    assert result["delta"]["unconfirmed_receipts_assumed_amount"] == 0
    assert result["base"]["total_in"] == result["scenario"]["total_in"]


def test_scenario_rejects_duplicate_or_past_dates_and_unknown_receivable(scenario_inputs):
    move = {"receivable_id": 10, "new_date": AS_OF}
    with pytest.raises(ValueError, match="only one"):
        service.scenario(None, [move, move], False, None)
    with pytest.raises(ValueError, match="before as-of"):
        service.scenario(None, [{**move, "new_date": AS_OF - timedelta(days=1)}], False, None)
    with pytest.raises(KeyError):
        service.scenario(None, [{"receivable_id": 999999, "new_date": AS_OF}], False, None)


def test_low_point_receivables_include_undated_overdue_amount(scenario_inputs):
    ci = scenario_inputs
    projection = ci.project(ci.base_flows())
    # Use a later low point to exercise both missing collection dates and ordinary estimates.
    projection.low_point_day = AS_OF + timedelta(days=4)
    rows = service.responsible_receivables(ci, projection)
    assert any(r["receivable_id"] == 10 and r["expected_date"] is None for r in rows)


def test_cash_api_exposes_actual_exclusion_totals_and_narrow_backtest_scope(client, demo_run):
    from tests.conftest import login
    response = client.get("/api/v1/cash/projection", headers=login(client, "rashid"))
    assert response.status_code == 200, response.text
    result = response.json()
    excluded = [r for r in result["receivables"] if not r["included_in_base"] and r["amount"] > 0]
    assert excluded
    assert all(r["expected_date"] is None for r in excluded)
    assert result["collection_policy"]["unconfirmed_amount"] == sum(r["amount"] for r in excluded)
    assert result["collection_policy"]["unconfirmed_count"] == len(excluded)
    validation = result["validation"]
    assert validation["forecast_horizon_weeks"] == 13
    assert validation["backtest_horizon_weeks"] == 4
    assert validation["current_policy_backtested"]
    assert validation["receipt_policy"] == "exclude_unconfirmed"
    assert len(validation["origins"]) == 5
