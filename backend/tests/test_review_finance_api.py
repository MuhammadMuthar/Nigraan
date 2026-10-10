"""Finance endpoints expose measured studies and uncertain collections consistently."""
from app.services.scoring import review
from tests.conftest import login, resolution_payload


def test_measured_review_and_cash_scope_reach_dashboard_and_evaluation(client):
    headers = login(client, "rashid")
    response = client.get("/api/v1/eval/results", headers=headers)
    assert response.status_code == 200, response.text
    evaluation = response.json()
    measured = evaluation["review"]
    assert measured["n_payments"] == evaluation["fraud"]["n_payments"]
    assert measured["n_fraud"] == evaluation["fraud"]["n_fraud"]
    assert measured["n_payments"] == measured["n_fraud"] + measured["n_legitimate"]
    assert "expert" in measured["rules_comparison"]
    assert measured["invoice_age_ablation"]["removed_feature"] == "days_since_invoice_date"

    response = client.get("/api/v1/dashboard/summary", headers=headers)
    assert response.status_code == 200, response.text
    dashboard = response.json()
    assert dashboard["metrics"]["review"] == measured
    assert dashboard["metrics"]["model_version"] == evaluation["model_version"]
    validation = dashboard["cash"]["validation"]
    assert validation == dashboard["cash_validation"] == evaluation["cash_validation"]
    assert validation["backtest_horizon_weeks"] < validation["forecast_horizon_weeks"]
    assert validation["receipt_policy"] == "exclude_unconfirmed"
    assert validation["current_policy_backtested"] is True
    assert validation["synthetic"] is True


def test_unavailable_review_study_is_omitted_without_breaking_evaluation(client, monkeypatch):
    monkeypatch.setattr(review, "load_review_evaluation", lambda *args: None)
    response = client.get("/api/v1/eval/results", headers=login(client, "sana"))
    assert response.status_code == 200, response.text
    assert "review" not in response.json()
    assert "fraud" in response.json()


def test_unconfirmed_receivable_dates_serialize_without_promising_collection(client):
    headers = login(client, "sana")
    response = client.get("/api/v1/receivables?page_size=500", headers=headers)
    assert response.status_code == 200, response.text
    uncertain = [row for row in response.json()["items"] if row["expected_date"] is None]
    assert uncertain, "the seeded company includes overdue balances without a defensible collection date"
    assert all(row["included_in_base"] is False and row["expected_basis"] == "assumption" for row in uncertain)
    outlook = client.get("/api/v1/cash/projection", headers=headers)
    assert outlook.status_code == 200, outlook.text
    excluded = [row for row in outlook.json()["receivables"] if not row["included_in_base"] and row["amount"] > 0]
    policy = outlook.json()["collection_policy"]
    assert policy["unconfirmed_amount"] == sum(row["amount"] for row in excluded)
    assert policy["unconfirmed_count"] == len(excluded)


def test_saved_evaluation_identifies_its_model_after_runtime_version_changes(client, monkeypatch):
    from app.services.runtime import runtime

    monkeypatch.setattr(runtime.bundle, "version", "test-new-model-version")
    response = client.get("/api/v1/dashboard/summary", headers=login(client, "rashid"))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["model_version"] == "test-new-model-version"
    assert data["metrics"]["model_version"] != data["model_version"]
    assert "review" not in data["metrics"]


def test_cleared_alert_is_not_counted_as_currently_blocked(client, demo_run):
    headers = login(client, "rashid")
    run = client.get(f"/api/v1/payment-runs/{demo_run}", headers=headers).json()
    blocked = next(line for line in run["lines"] if line["status"] == "blocked" and line["case"]["status"] == "open")
    before = client.get("/api/v1/dashboard/summary", headers=headers).json()
    # The monthly dashboard can include other live runs created by prior workflow
    # tests. One resolved case must remove exactly one current block from that scope.
    locked_before = sum(alert["red"] for alert in before["alerts_by_type"])
    assert locked_before > 0
    case_id = blocked["case"]["id"]
    response = client.post(f"/api/v1/cases/{case_id}/resolve", headers=headers,
                           json=resolution_payload(client, case_id))
    assert response.status_code == 200, response.text
    after = client.get("/api/v1/dashboard/summary", headers=headers).json()
    recovered = client.get(f"/api/v1/payment-runs/{demo_run}", headers=headers).json()
    line = next(line for line in recovered["lines"] if line["id"] == blocked["id"])
    assert line["status"] == "pending" and line["decision"] == "review" and line["model_decision"] == "blocked"
    assert sum(alert["red"] for alert in after["alerts_by_type"]) == locked_before - 1
