"""Fusion hard rules, leakage safety, duplicate normalisation."""
import numpy as np
import pandas as pd
import pytest

from app.services.identity import is_valid_pk_iban, make_pk_iban, norm_invoice_no
from app.services.scoring.fuse import decision_for, fuse, rescale

FUSION = {"weights": {"risk_model": 0.5, "anomaly": 0.2, "duplicate": 0.25, "graph": 0.25}, "t_yellow": 0.1, "t_red": 0.3}


@pytest.mark.parametrize("signals", [
    {"risk_model": 0.0, "anomaly": 0.0, "duplicate": 0.0, "graph": 0.0},
    {"risk_model": 0.01, "anomaly": 0.0, "duplicate": 0.2, "graph": 0.0},
])
def test_hard_rule_always_red(signals):
    score, raw, _ = fuse(signals, 1.0, FUSION)
    assert score == 100 and decision_for(score) == "blocked"


def test_soft_rule_floor_is_yellow():
    score, _, _ = fuse({"risk_model": 0, "anomaly": 0, "duplicate": 0, "graph": 0}, 0.6, FUSION)
    assert decision_for(score) == "review"


def test_rescale_maps_thresholds_to_bands_and_is_monotone():
    assert rescale(0.1, 0.1, 0.3) == pytest.approx(40)
    assert rescale(0.3, 0.1, 0.3) == pytest.approx(75)
    xs = np.linspace(0, 1, 101)
    ys = [rescale(x, 0.1, 0.3) for x in xs]
    assert all(b >= a for a, b in zip(ys, ys[1:]))
    assert decision_for(39) == "allow" and decision_for(40) == "review" and decision_for(75) == "blocked"


def test_invoice_number_normalisation():
    assert norm_invoice_no("INV-0102") == norm_invoice_no("INV102") == norm_invoice_no("102") == "102"
    assert norm_invoice_no("102A") != norm_invoice_no("102")
    assert norm_invoice_no("BD/25/0102") == norm_invoice_no("BD-25-102")


def test_iban_check_digits():
    iban = make_pk_iban("HABB", "0012345678901234")
    assert len(iban) == 24 and is_valid_pk_iban(iban)
    assert not is_valid_pk_iban(iban[:-1] + ("0" if iban[-1] != "0" else "1"))


@pytest.fixture(scope="module")
def world():
    from data_gen.generate_company import generate

    return generate(42, with_demo=False)


def test_no_feature_uses_data_after_prediction_moment(world):
    """Features computed on the full ledger equal features computed on a ledger truncated at the payment time."""
    from app.services.ledger import Ledger
    from app.services.scoring.features import FeatureContext

    L = Ledger.from_world(world)
    full = FeatureContext(L)
    rng = np.random.default_rng(0)
    labels = {l["payment_id"] for l in world.labels}
    sample = list(rng.choice(L.payments["id"].values, size=25, replace=False)) + sorted(labels)[:15]
    for pid in sample:
        p = L.payments.set_index("id").loc[pid]
        t = p["created_at"]

        def cut(df, col):
            return df[(df[col] < t) | df[col].isna()] if col in df else df

        Lc = Ledger(
            company=L.company, users=L.users, employees=L.employees[L.employees["hire_date"] <= t],
            vendors=L.vendors[L.vendors["created_at"] <= t],
            accounts=L.accounts[L.accounts["valid_from"] <= t].assign(
                valid_to=lambda d: d["valid_to"].where(d["valid_to"] <= t, pd.NaT)),
            items=L.items,
            invoices=L.invoices[(L.invoices["received_at"] < t) | (L.invoices["id"] == p["invoice_id"])],
            lines=L.lines, payments=L.payments[(L.payments["created_at"] < t) | (L.payments["id"] == pid)],
            cases=L.cases.iloc[0:0],
        )
        Lc.lines = L.lines[L.lines["invoice_id"].isin(Lc.invoices["id"])]
        a = full.features_for(int(pid))
        b = FeatureContext(Lc).features_for(int(pid))
        for k in a:
            if isinstance(a[k], float) and np.isnan(a[k]):
                assert np.isnan(b[k]), (pid, k)
            else:
                assert a[k] == pytest.approx(b[k]), (pid, k, a[k], b[k])
