"""Cash engine invariants (sections 7.3, 7.4)."""
from datetime import date, timedelta

import pytest

from app.services.cash.engine import Flow, move_flow, project

AS_OF = date(2026, 10, 12)  # Monday
RS = 100  # paisa per rupee


def f(day_offset, rupees, ref=None, basis="fact", kind="receipt"):
    return Flow(AS_OF + timedelta(days=day_offset), rupees * RS, kind, basis, ref or f"x{day_offset}", ref)


def test_daily_closing_formula():
    flows = [f(0, 100), f(1, -30), f(1, 10), f(3, -50)]
    p = project(AS_OF, 1000 * RS, 0, flows)
    assert [d.closing for d in p.days[:4]] == [1100 * RS, 1080 * RS, 1080 * RS, 1030 * RS]
    assert p.weeks[0].closing == 1030 * RS
    assert len(p.weeks) == 13 and len(p.days) == 91


def test_mid_week_breach_detected_even_if_week_ends_positive():
    # dips below reserve on Wednesday, recovers by Sunday
    flows = [f(2, -600), f(5, 800)]
    p = project(AS_OF, 1000 * RS, 500 * RS, flows)
    assert p.weeks[0].closing == 1200 * RS  # week ends above the reserve...
    assert p.first_breach == AS_OF + timedelta(days=2)  # ...but the breach on day 3 is caught
    assert p.low_point == 400 * RS and p.breach_gap == 100 * RS


def test_beyond_horizon_not_forced_into_week_13():
    flows = [f(95, 5000, ref="receivable:1"), f(10, 100)]
    p = project(AS_OF, 0, 0, flows)
    assert p.total_in == 100 * RS
    assert [x.ref for x in p.beyond_horizon] == ["receivable:1"]
    assert p.weeks[-1].inflow == 0


def test_flow_before_as_of_rejected():
    with pytest.raises(ValueError):
        project(AS_OF, 0, 0, [f(-1, 10)])


def test_amounts_must_be_integer_paisa():
    with pytest.raises(TypeError):
        project(AS_OF, 0, 0, [Flow(AS_OF, 10.5, "receipt", "fact", "x")])


def test_move_collection_changes_timing_not_total_and_gap_remains():
    """Moving Rs 150,000 from week 2 to week 1 changes timing but not the total; the week-2 gap remains."""
    reserve = 500_000 * RS
    flows = [
        f(9, 150_000, ref="receivable:7"),  # week 2 receipt to be moved
        f(10, -900_000, ref="outflow:1", kind="outflow"),  # big week-2 outflow causes the gap
        f(1, 20_000), f(12, 10_000),
    ]
    base = project(AS_OF, 1_000_000 * RS, reserve, flows)
    moved = move_flow(flows, "receivable:7", AS_OF + timedelta(days=2))
    scen = project(AS_OF, 1_000_000 * RS, reserve, moved)
    assert scen.total_in == base.total_in  # never adds a second receipt
    assert sum(1 for x in moved if x.ref == "receivable:7") == 1
    assert scen.weeks[0].inflow - base.weeks[0].inflow == 150_000 * RS
    assert base.first_breach is not None and scen.first_breach is not None  # week-2 gap still there
    assert scen.days[-1].closing == base.days[-1].closing


def test_move_unknown_ref_raises():
    with pytest.raises(KeyError):
        move_flow([f(1, 10, ref="receivable:1")], "receivable:2", AS_OF)


def test_paisa_arithmetic_exact():
    from app.money import fmt_rs, group_lakh, rupees_to_paisa

    assert rupees_to_paisa("1430000.50") == 143000050
    assert rupees_to_paisa("0.1") + rupees_to_paisa("0.2") == rupees_to_paisa("0.3")
    assert rupees_to_paisa("1,43,000.05") == 14300005
    flows = [Flow(AS_OF, rupees_to_paisa("0.1"), "receipt", "fact", "a") for _ in range(10)]
    assert project(AS_OF, 0, 0, flows).total_in == 100  # exactly Rs 1.00, no float drift
    assert group_lakh(1430000) == "14,30,000" and group_lakh(123456789) == "12,34,56,789"
    assert fmt_rs(143000000) == "Rs 14,30,000"
