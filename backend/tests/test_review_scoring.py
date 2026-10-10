"""Review labels, live comparator exposure and stale-evaluation safeguards."""
from types import SimpleNamespace
import json

import pandas as pd
import pytest

from app.services.scoring.reasons import feature_reason
from app.services.scoring.review import MODEL_FILES, load_review_evaluation, model_fingerprints
from app.services.scoring.rules import comparison_for, comparison_summary
from app.services.scoring.scorer import suspected_type


@pytest.mark.parametrize("reasons,features,expected", [
    ([{"engine": "risk_model", "feature": "days_since_invoice_date"}], {}, "ANOMALY"),
    ([{"engine": "risk_model", "feature": "creator_can_approve"}], {}, "ANOMALY"),
    ([{"engine": "risk_model", "feature": "days_since_bank_change"}], {"account_changed": 0}, "ANOMALY"),
    ([{"engine": "risk_model", "feature": "days_since_bank_change"}], {"account_changed": 1}, "F2"),
    ([{"engine": "risk_model", "feature": "is_night"}], {}, "F7"),
    ([{"engine": "anomaly"}], {}, "ANOMALY"),
    ([{"engine": "rules", "code": "DUP_EXACT"}, {"engine": "risk_model", "feature": "is_night"}], {}, "F1"),
    ([{"engine": "rules", "code": "SPLIT_PAYMENT"}], {}, "F5"),
    ([{"engine": "graph"}], {}, "F3"),
    ([{"engine": "info", "feature": "is_night"}, {"engine": "risk_model", "feature": "vague_line_share", "weak": True}], {}, "ANOMALY"),
    ([{"engine": "anomaly"}] * 4 + [{"engine": "risk_model", "feature": "is_night"}], {}, "ANOMALY"),
])
def test_suspected_pattern_uses_only_actual_displayed_evidence(reasons, features, expected):
    assert suspected_type(reasons, "review", features) == expected
    assert suspected_type(reasons, "allow", features) is None


@pytest.mark.parametrize("feature", ["changer_prior_edits", "changer_edit_share"])
def test_vendor_onboarding_editor_reason_is_not_a_bank_change(feature):
    features = {"account_changed": 0, "changer_prior_edits": 1, "changer_edit_share": 0.05}
    text = feature_reason(feature, features[feature], features)
    assert text.startswith("Vendor set up by a user who rarely edits vendors")
    assert suspected_type([{"engine": "risk_model", "feature": feature, "text": text}], "review", features) == "ANOMALY"
    features["account_changed"] = 1
    changed_text = feature_reason(feature, features[feature], features)
    assert changed_text.startswith("Bank details changed by a user who rarely edits vendors")
    assert suspected_type([{"engine": "risk_model", "feature": feature, "text": changed_text}], "review", features) == "F2"


def context():
    invoices = pd.DataFrame([{"id": 1, "vendor_id": 1, "invoice_no_norm": "102", "received_at": pd.Timestamp("2026-10-10")}]).set_index("id")
    payments = pd.DataFrame([{"id": 1, "vendor_id": 1, "invoice_id": 1, "amount": 10000, "bank_account_id": 1,
                              "created_at": pd.Timestamp("2026-10-11")}]).set_index("id")
    vendors = pd.DataFrame([{"id": 1, "blocked_at": pd.NaT}]).set_index("id")
    return SimpleNamespace(inv=invoices, pay_by_id=payments, vendors=vendors, limit=50000000,
                           acct={1: SimpleNamespace(blocked_at=None)})


def test_expert_comparator_exposes_recent_bank_change_simple_does_not():
    result = comparison_for(context(), 1, {"account_changed": 1, "days_since_bank_change": 2})
    assert not result["simple"]["flagged"]
    assert result["expert"]["flagged"]
    assert [hit["code"] for hit in result["expert"]["checks"]] == ["RECENT_BANK_CHANGE"]


def test_comparators_do_not_invent_flags_from_missing_features_or_invoice_age():
    result = comparison_for(context(), 1, {"is_night": float("nan"), "vendor_age_days": None,
                                         "days_since_invoice_date": 1})
    assert not result["simple"]["flagged"] and not result["expert"]["flagged"]


def test_expert_comparator_includes_deterministic_relationship_and_split_checks():
    result = comparison_for(context(), 1, {}, [{"code": "SPLIT_PAYMENT", "text": "Two linked payments"}], 1.0)
    assert {hit["code"] for hit in result["expert"]["checks"]} == {"SPLIT_PAYMENT", "EMPLOYEE_RELATIONSHIP"}


def test_comparison_summary_counts_stored_paisa_and_excludes_rejected_exposure():
    permit = {"simple": {"flagged": False}, "expert": {"flagged": False}}
    expert_flag = {"simple": {"flagged": False}, "expert": {"flagged": True}}
    lines = [{"amount": 10001, "model_decision": "review", "status": "pending", "rules_comparison": permit},
             {"amount": 20002, "model_decision": "blocked", "status": "blocked", "rules_comparison": expert_flag},
             {"amount": 30003, "model_decision": "blocked", "status": "rejected", "rules_comparison": permit},
             {"amount": 40004, "model_decision": None, "status": "pending", "rules_comparison": None}]
    result = comparison_summary(lines)
    assert result["evaluated_count"] == 2
    assert result["simple"]["nigraan_additional_count"] == 2
    assert result["simple"]["nigraan_additional_amount"] == 30003
    assert result["expert"]["nigraan_additional_amount"] == 10001
    assert result["expert"]["flagged_count"] == 1 and result["expert"]["flagged_amount"] == 20002


def test_optional_study_hides_after_retraining_or_invalid_artifact(tmp_path):
    for filename in MODEL_FILES:
        (tmp_path / filename).write_text(filename)
    report = {"model_version": "v1", "source_artifacts": model_fingerprints(tmp_path)}
    path = tmp_path / "review_eval.json"
    path.write_text(json.dumps(report))
    assert load_review_evaluation(tmp_path, "v1") == report
    assert load_review_evaluation(tmp_path, "v2") is None
    (tmp_path / "fraud_xgb.json").write_text("retrained")
    assert load_review_evaluation(tmp_path, "v1") is None
    path.write_text("[]")
    assert load_review_evaluation(tmp_path, "v1") is None
    path.write_text("invalid json")
    assert load_review_evaluation(tmp_path, "v1") is None


def test_evidence_wording_does_not_imply_settlement_or_tax_registration():
    assert feature_reason("days_since_invoice_date", 1, {}) == "Payment entered 1 day after the invoice date"
    assert "unregistered" not in feature_reason("no_sales_tax", 1, {})
