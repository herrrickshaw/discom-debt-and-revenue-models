"""Characterisation tests: numeric outputs pinned to the pre-refactor values."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import discom_debt_calculator as ddc

REPO = Path(__file__).resolve().parents[1]

# Final debt (Rs crore) per scenario, default inputs -- from the original script.
GOLDEN_DEFAULT_FINAL_DEBT = {
    "Status Quo (no action)": 175288.0,
    "Tariff hike only (5%/yr)": 108496.0,
    "Loss + collection reform": 139081.0,
    "Combined (UDAY-style)": 79852.0,
    "Aggressive turnaround": 36496.0,
}
# Same for `--debt 50000 --acs 7.2 --arr 6.1 --loss 18` (the README example).
GOLDEN_ALT_FINAL_DEBT = {
    "Status Quo (no action)": 239657.0,
    "Tariff hike only (5%/yr)": 176262.0,
    "Loss + collection reform": 204109.0,
    "Combined (UDAY-style)": 147672.0,
    "Aggressive turnaround": 106051.0,
}
GOLDEN_DEFAULT_BILL_YR7 = {
    "Status Quo (no action)": (1550.0, 0.0),
    "Tariff hike only (5%/yr)": (2181.0, 40.7),
    "Loss + collection reform": (1550.0, 0.0),
    "Combined (UDAY-style)": (2040.0, 31.6),
    "Aggressive turnaround": (2331.0, 50.4),
}


def test_default_scenarios_match_golden():
    out = ddc.compute(ddc.DiscomInputs(), ddc.default_scenarios())
    got = {r["scenario"]: r["final_debt_cr"] for r in out["results"]}
    assert got == GOLDEN_DEFAULT_FINAL_DEBT
    for r in out["results"]:
        assert r["debt_change_cr"] == r["final_debt_cr"] - 40000.0
        assert len(r["rows"]) == 7


def test_readme_example_matches_golden():
    inp = ddc.DiscomInputs(opening_debt_cr=50000, acs_per_kwh=7.2, arr_per_kwh=6.1, atc_loss_pct=18)
    out = ddc.compute(inp, ddc.default_scenarios())
    got = {r["scenario"]: r["final_debt_cr"] for r in out["results"]}
    assert got == GOLDEN_ALT_FINAL_DEBT


def test_consumer_bills_match_golden():
    bills = ddc.consumer_bill_impact(ddc.DiscomInputs(), ddc.default_scenarios())
    got = {b["scenario"]: (b["monthly_bill_yr7"], b["bill_increase_pct"]) for b in bills}
    assert got == GOLDEN_DEFAULT_BILL_YR7
    assert all(b["monthly_bill_yr0"] == 1550.0 for b in bills)


def test_uday_first_year_row():
    uday = ddc.default_scenarios()[3]
    row = ddc.project(ddc.DiscomInputs(), uday)["rows"][0]
    assert row == {
        "year": 1,
        "ARR": 6.45,
        "ACS": 7.07,
        "ACS_ARR_gap": 0.62,
        "AT&C_loss%": 13.5,
        "collection%": 99.0,
        "op_gap_cr": -1571.0,
        "interest_cr": 3800.0,
        "closing_debt_cr": 45371.0,
    }


def test_annual_pnl_unit_math():
    """1 MU at Rs 1/kWh with no losses, full collection, no subsidy -> Rs 0.1 crore revenue."""
    inp = ddc.DiscomInputs(subsidy_cr=0.0, interest_rate_pct=10.0)
    state = ddc.YearState(
        debt_cr=100.0,
        energy_mu=1.0,
        acs=0.0,
        arr=1.0,
        loss_pct=0.0,
        collection_pct=100.0,
        subsidy_realised_pct=0.0,
    )
    pnl = ddc.annual_pnl(state, inp)
    assert pnl["op_gap_cr"] == pytest.approx(0.1)
    assert pnl["interest_cr"] == pytest.approx(10.0)


def test_levers_are_clamped():
    inp = ddc.DiscomInputs(acs_growth_pct=0.0, demand_growth_pct=0.0)
    sc = ddc.Scenario("x", atc_loss_reduction_pp=50.0, collection_gain_pp=50.0, subsidy_realised_pp=50.0)
    state = ddc.YearState.from_inputs(inp)
    ddc.apply_levers(state, inp, sc)
    assert state.loss_pct == 0.0
    assert state.collection_pct == 100.0
    assert state.subsidy_realised_pct == 100.0


def test_outcome_label():
    assert ddc._outcome_label(-1.0, 40000) == "▼ debt cut"
    assert ddc._outcome_label(100.0, 40000) == "≈ flat"
    assert ddc._outcome_label(5000.0, 40000) == "▲ debt grows"


def test_inputs_from_args_only_overrides_given_flags():
    a = ddc.build_parser().parse_args(["--debt", "1", "--monthly-kwh", "99"])
    inp = ddc.inputs_from_args(a)
    assert inp.opening_debt_cr == 1.0
    assert inp.consumer_monthly_kwh == 99.0
    assert inp.acs_per_kwh == ddc.DiscomInputs().acs_per_kwh


def test_format_report_contains_key_sections():
    out = ddc.compute(ddc.DiscomInputs(), ddc.default_scenarios())
    text = ddc.format_report(ddc.DiscomInputs(), out["results"], out["bills"])
    assert "DISCOM DEBT-REDUCTION SCENARIO CALCULATOR" in text
    assert "Aggressive turnaround                 36,496           -3,504  ▼ debt cut" in text
    assert "CONSUMER BILL IMPACT (household @ 250 kWh/month)" in text


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO / "discom_debt_calculator.py"), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
    )


def test_cli_json_smoke():
    r = _cli("--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert set(data) == {"inputs", "results", "consumer_bills"}
    assert data["results"][-1]["final_debt_cr"] == 36496.0


def test_cli_text_smoke():
    r = _cli("--debt", "50000", "--acs", "7.2", "--arr", "6.1", "--loss", "18")
    assert r.returncode == 0, r.stderr
    assert "Opening debt: ₹50,000 Cr" in r.stdout
