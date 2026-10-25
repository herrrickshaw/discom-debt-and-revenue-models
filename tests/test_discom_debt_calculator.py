"""Tests for discom_debt_calculator.

Unit identity used throughout: 1 MU x Rs 1/kWh = 1e6 Rs = Rs 0.1 crore.
AT&C loss (PFC/CEA definition) = 1 - billing_efficiency x collection_efficiency,
so it already contains the collection shortfall.
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from discom_debt_calculator import (  # noqa: E402
    DiscomInputs,
    Scenario,
    consumer_bill_impact,
    default_scenarios,
    project,
)


def flat_inputs(**kw):
    """One year, no growth, no interest, no subsidy, no opening debt: closing debt = -op_gap."""
    base = dict(opening_debt_cr=0.0, energy_input_mu=1000.0, acs_per_kwh=0.0, arr_per_kwh=10.0,
                atc_loss_pct=15.0, collection_eff_pct=98.0, subsidy_cr=0.0, subsidy_realised_pct=100.0,
                interest_rate_pct=0.0, acs_growth_pct=0.0, demand_growth_pct=0.0, horizon_years=1)
    base.update(kw)
    return DiscomInputs(**base)


def test_unit_conversion_mu_times_rupees_per_kwh_is_tenth_crore():
    # No losses at all: 1000 MU x Rs 10/kWh = Rs 1e10 = Rs 1000 crore collected.
    r = project(flat_inputs(atc_loss_pct=0.0, collection_eff_pct=100.0), Scenario("x"))
    assert r["final_debt_cr"] == -1000


def test_collected_revenue_equals_input_times_one_minus_atc_loss():
    """AT&C 15% means 85% of input energy is billed AND collected (by definition).

    1000 MU x 0.85 x Rs 10 / 10 = Rs 850 crore. Applying collection efficiency on top
    (the current code) gives 850 x 0.98 = 833, double-counting the uncollected 2%.
    """
    r = project(flat_inputs(), Scenario("x"))
    assert r["final_debt_cr"] == -850


def test_collection_gain_lowers_atc_loss_with_billing_efficiency_held():
    """Billing eff = 0.72/0.90 = 0.80. Collection 90 -> 92 makes AT&C = 1 - 0.80*0.92 = 26.4%."""
    inp = flat_inputs(atc_loss_pct=28.0, collection_eff_pct=90.0)
    r = project(inp, Scenario("coll", collection_gain_pp=2.0))
    row = r["rows"][0]
    assert row["collection%"] == 92.0
    assert row["AT&C_loss%"] == pytest.approx(26.4, abs=0.05)
    assert r["final_debt_cr"] == pytest.approx(-1000 * 0.736, abs=1)


def test_status_quo_closing_debt_hand_computed():
    # debt 100, cost 1000 MU x Rs 1 = 100 cr, collected 1000 x 0.9 x 0.5 = 45 cr,
    # subsidy 20 x 50% = 10 -> op_gap = -45; interest 10% of 100 = 10 -> closing 155.
    inp = flat_inputs(opening_debt_cr=100.0, acs_per_kwh=1.0, arr_per_kwh=0.5, atc_loss_pct=10.0,
                      collection_eff_pct=100.0, subsidy_cr=20.0, subsidy_realised_pct=50.0,
                      interest_rate_pct=10.0)
    r = project(inp, Scenario("sq"))
    assert r["rows"][0]["op_gap_cr"] == -45
    assert r["rows"][0]["interest_cr"] == 10
    assert r["final_debt_cr"] == 155
    assert r["debt_change_cr"] == 55


def test_interest_compounds_on_closing_balance():
    inp = flat_inputs(opening_debt_cr=1000.0, arr_per_kwh=0.0, energy_input_mu=0.0,
                      interest_rate_pct=10.0, horizon_years=3)
    r = project(inp, Scenario("sq"))
    assert [row["closing_debt_cr"] for row in r["rows"]] == [1100, 1210, 1331]


def test_levers_apply_from_year_one_and_are_capped():
    inp = flat_inputs(atc_loss_pct=1.0, collection_eff_pct=99.5, subsidy_realised_pct=99.0, horizon_years=3)
    r = project(inp, Scenario("big", atc_loss_reduction_pp=5.0, collection_gain_pp=5.0,
                              subsidy_realised_pp=5.0, tariff_hike_pct=10.0))
    rows = r["rows"]
    assert len(rows) == 3
    assert rows[0]["ARR"] == 11.0 and rows[2]["ARR"] == pytest.approx(13.31, abs=0.01)
    assert all(row["collection%"] == 100.0 for row in rows)
    assert all(row["AT&C_loss%"] == 0.0 for row in rows)


def test_growth_of_cost_and_demand():
    # ACS 1 growing 10%/yr and energy 100 growing 10%/yr, nothing collected:
    # year1 cost = 110 x 1.1 / 10 = 12.1 cr.
    inp = flat_inputs(energy_input_mu=100.0, acs_per_kwh=1.0, arr_per_kwh=0.0,
                      acs_growth_pct=10.0, demand_growth_pct=10.0)
    r = project(inp, Scenario("sq"))
    assert r["rows"][0]["ACS"] == 1.1
    assert r["final_debt_cr"] == pytest.approx(12, abs=0.5)


def test_consumer_bill_impact_compounds_tariff_over_horizon():
    inp = DiscomInputs(arr_per_kwh=6.20, consumer_monthly_kwh=250.0, horizon_years=7)
    out = consumer_bill_impact(inp, [Scenario("flat"), Scenario("5pc", tariff_hike_pct=5.0)])
    assert out[0]["monthly_bill_yr0"] == 1550 and out[0]["bill_increase_pct"] == 0.0
    expected = 250 * 6.20 * 1.05 ** 7
    assert out[1]["monthly_bill_yr7"] == round(expected)
    assert out[1]["bill_increase_pct"] == pytest.approx((1.05 ** 7 - 1) * 100, abs=0.05)


def test_default_scenarios_rank_sensibly():
    inp = DiscomInputs()
    res = {sc.name: project(inp, sc)["final_debt_cr"] for sc in default_scenarios()}
    assert res["Aggressive turnaround"] < res["Combined (UDAY-style)"] < res["Status Quo (no action)"]
    assert math.isfinite(res["Status Quo (no action)"])
