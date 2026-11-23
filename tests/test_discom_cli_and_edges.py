"""CLI text report, argument overrides, input validation and sign conventions of discom_debt_calculator."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discom_debt_calculator as dc  # noqa: E402


def test_run_text_report_and_return_value(capsys):
    inp = dc.DiscomInputs()
    out = dc.run(inp, dc.default_scenarios())
    text = capsys.readouterr().out
    assert [r["scenario"] for r in out["results"]] == [s.name for s in dc.default_scenarios()]
    assert len(out["bills"]) == 5
    assert "debt grows" in text or "debt cut" in text or "flat" in text
    assert "Status Quo" in text and "Combined (UDAY-style)" in text
    sq = out["results"][0]
    assert f"({sq['debt_change_cr']:+,.0f} Cr)" in text
    assert "still grow" in text or "cut" in text


def test_run_json_mode_is_valid_and_matches_text_mode_numbers(capsys):
    import json
    inp = dc.DiscomInputs()
    dc.run(inp, dc.default_scenarios(), as_json=True)
    data = json.loads(capsys.readouterr().out)
    assert set(data) >= {"results", "consumer_bills"}
    assert data["results"][0]["scenario"] == "Status Quo (no action)"
    direct = dc.project(inp, dc.default_scenarios()[0])
    assert data["results"][0]["final_debt_cr"] == direct["final_debt_cr"]


def test_outcome_labels_match_the_debt_change(capsys):
    inp = dc.DiscomInputs()
    out = dc.run(inp, dc.default_scenarios())
    lines = capsys.readouterr().out.splitlines()
    seen = set()
    for r in out["results"]:
        ch = r["debt_change_cr"]
        label = "▼ debt cut" if ch < 0 else ("≈ flat" if abs(ch) < inp.opening_debt_cr * 0.05 else "▲ debt grows")
        assert any(r["scenario"] in ln and label in ln for ln in lines), (r["scenario"], label)
        seen.add(label)
    assert "▲ debt grows" in seen


def test_flat_label_when_debt_barely_moves(capsys):
    inp = dc.DiscomInputs(opening_debt_cr=1_000_000.0, interest_rate_pct=0.0, horizon_years=1)
    out = dc.run(inp, [dc.Scenario("Status Quo (no action)"), dc.Scenario("Loss + collection reform")])
    assert abs(out["results"][0]["debt_change_cr"]) < 50_000
    assert "≈ flat" in capsys.readouterr().out


@pytest.mark.parametrize("coll,loss", [(0.0, 10.0), (101.0, 10.0), (98.0, -1.0), (98.0, 101.0)])
def test_project_rejects_out_of_range_inputs(coll, loss):
    with pytest.raises(ValueError, match="collection efficiency must be in"):
        dc.project(dc.DiscomInputs(collection_eff_pct=coll, atc_loss_pct=loss), dc.Scenario("x"))


def test_project_accepts_boundary_values():
    r = dc.project(dc.DiscomInputs(collection_eff_pct=100.0, atc_loss_pct=0.0), dc.Scenario("x"))
    assert r["rows"][0]["AT&C_loss%"] == 0.0 and r["rows"][0]["collection%"] == 100.0
    r = dc.project(dc.DiscomInputs(collection_eff_pct=100.0, atc_loss_pct=100.0), dc.Scenario("x"))
    assert r["rows"][0]["AT&C_loss%"] == 100.0


def test_zero_horizon_has_no_rows_and_no_change():
    r = dc.project(dc.DiscomInputs(horizon_years=0), dc.Scenario("x"))
    assert r["rows"] == [] and r["final_debt_cr"] == 40000.0 and r["debt_change_cr"] == 0


def test_main_overrides_every_input(monkeypatch, capsys):
    import json
    argv = ["dc", "--debt", "1000", "--energy", "100", "--acs", "5", "--arr", "5.5", "--loss", "10",
            "--collection", "99", "--interest", "8", "--horizon", "2", "--monthly-kwh", "100", "--json"]
    monkeypatch.setattr(sys, "argv", argv)
    dc.main()
    data = json.loads(capsys.readouterr().out)
    sq = data["results"][0]
    assert len(sq["rows"]) == 2
    assert "tariff_yr2" in data["consumer_bills"][0] and data["consumer_bills"][0]["monthly_bill_yr0"] == 550
    expected = dc.project(dc.DiscomInputs(opening_debt_cr=1000.0, energy_input_mu=100.0, acs_per_kwh=5.0,
                                          arr_per_kwh=5.5, atc_loss_pct=10.0, collection_eff_pct=99.0,
                                          interest_rate_pct=8.0, horizon_years=2, consumer_monthly_kwh=100.0),
                          dc.default_scenarios()[0])
    assert sq["final_debt_cr"] == expected["final_debt_cr"]


def test_main_defaults_without_arguments(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["dc"])
    dc.main()
    assert "Status Quo" in capsys.readouterr().out


def test_main_zero_value_overrides_are_applied_not_ignored(monkeypatch, capsys):
    import json
    monkeypatch.setattr(sys, "argv", ["dc", "--debt", "0", "--interest", "0", "--horizon", "1", "--json"])
    dc.main()
    sq = json.loads(capsys.readouterr().out)["results"][0]
    assert sq["rows"][0]["interest_cr"] == 0                              # `is not None`, so 0 is a real override


# ------------------------------- mutation-driven additions -------------------------------

def _op(inp, sc):
    return dc.project(inp, sc)["rows"][0]["op_gap_cr"]


def test_atc_loss_cannot_fall_below_the_collection_shortfall():
    inp = dc.DiscomInputs(atc_loss_pct=5.0, collection_eff_pct=96.0)
    row = dc.project(inp, dc.Scenario("x", atc_loss_reduction_pp=3.0))["rows"][0]
    assert row["AT&C_loss%"] >= 100.0 - row["collection%"] - 1e-9            # floor = 4% shortfall
    assert row["AT&C_loss%"] == pytest.approx(4.0, abs=0.1)


def test_subsidy_realisation_lever_adds_cash():
    inp = dc.DiscomInputs(subsidy_cr=10000.0, subsidy_realised_pct=50.0)
    base = _op(inp, dc.Scenario("x"))
    better = _op(inp, dc.Scenario("x", subsidy_realised_pp=10.0))
    assert better - base == pytest.approx(1000.0, abs=1.0)                 # 10 pp of a Rs 10,000 cr subsidy
    inp = dc.DiscomInputs(subsidy_cr=10000.0, subsidy_realised_pct=95.0)
    capped = _op(inp, dc.Scenario("x", subsidy_realised_pp=10.0)) - _op(inp, dc.Scenario("x"))
    assert capped == pytest.approx(500.0, abs=1.0)                         # realisation is capped at 100%


def test_energy_grows_with_demand_growth_not_cost_growth():
    inp = dc.DiscomInputs(demand_growth_pct=10.0, acs_growth_pct=0.0, subsidy_cr=0.0, atc_loss_pct=0.0,
                          collection_eff_pct=100.0, acs_per_kwh=5.0, arr_per_kwh=6.0, horizon_years=1)
    # year-1 energy = 60000 * 1.10 = 66000 MU; margin Rs 1/kWh -> 66000 * 1 / 10 = 6600 cr
    assert _op(inp, dc.Scenario("x")) == pytest.approx(6600.0, abs=1.0)


def _flat_inputs(**kw):
    base = dict(opening_debt_cr=100.0, interest_rate_pct=0.0, energy_input_mu=0.0, subsidy_cr=0.0, horizon_years=1)
    base.update(kw)
    return dc.DiscomInputs(**base)


def test_zero_change_is_labelled_flat_not_cut(capsys):
    out = dc.run(_flat_inputs(), [dc.Scenario("Status Quo (no action)"), dc.Scenario("Loss + collection reform")])
    assert out["results"][0]["debt_change_cr"] == 0
    text = capsys.readouterr().out
    line = next(ln for ln in text.splitlines() if "Status Quo (no action)" in ln and "flat" in ln or
                "Status Quo (no action)" in ln and "debt" in ln)
    assert "≈ flat" in line and "debt cut" not in line


def test_flat_threshold_is_five_percent_of_opening_debt(capsys):
    # interest alone adds 10% of opening debt in a year: well above 5% -> "debt grows"
    out = dc.run(_flat_inputs(interest_rate_pct=10.0),
                 [dc.Scenario("Status Quo (no action)"), dc.Scenario("Loss + collection reform")])
    assert out["results"][0]["debt_change_cr"] == pytest.approx(10.0)
    status_line = next(ln for ln in capsys.readouterr().out.splitlines()
                       if "Status Quo (no action)" in ln and ("debt" in ln or "flat" in ln))
    assert "▲ debt grows" in status_line
    out = dc.run(_flat_inputs(interest_rate_pct=4.0),
                 [dc.Scenario("Status Quo (no action)"), dc.Scenario("Loss + collection reform")])
    assert out["results"][0]["debt_change_cr"] == pytest.approx(4.0)         # 4% < 5%: flat
    assert "≈ flat" in capsys.readouterr().out


def test_report_names_the_lowest_debt_scenario_and_the_verdict(capsys):
    inp = dc.DiscomInputs()
    out = dc.run(inp, dc.default_scenarios())
    text = capsys.readouterr().out
    best = min(out["results"], key=lambda r: r["final_debt_cr"])
    assert f"({best['debt_change_cr']:+,.0f} Cr)." in text
    ops = next(r for r in out["results"] if "Loss + collection" in r["scenario"])
    sq = out["results"][0]
    assert f"₹{sq['final_debt_cr'] - ops['final_debt_cr']:,.0f} Cr vs doing nothing" in text
    expected = "cut" if ops["debt_change_cr"] < 0 else "still grow"
    assert f"debt would {expected} ({ops['debt_change_cr']:+,.0f} Cr)" in text


def test_verdict_says_cut_when_reform_alone_reduces_debt(capsys):
    inp = dc.DiscomInputs(opening_debt_cr=10.0, acs_per_kwh=5.0, arr_per_kwh=7.0, interest_rate_pct=0.0)
    out = dc.run(inp, dc.default_scenarios())
    ops = next(r for r in out["results"] if "Loss + collection" in r["scenario"])
    assert ops["debt_change_cr"] < 0
    assert "debt would cut" in capsys.readouterr().out


def test_cli_zero_debt_override_is_applied(monkeypatch, capsys):
    import json
    monkeypatch.setattr(sys, "argv", ["dc", "--debt", "0", "--interest", "0", "--horizon", "1", "--json"])
    dc.main()
    row = json.loads(capsys.readouterr().out)["results"][0]["rows"][0]
    assert row["closing_debt_cr"] == -row["op_gap_cr"]                      # opening debt really was 0, not 40,000


def test_documented_defaults(monkeypatch, capsys):
    import json
    d = dc.DiscomInputs()
    assert (d.consumer_monthly_kwh, d.horizon_years) == (250.0, 7)
    monkeypatch.setattr(sys, "argv", ["dc", "--json"])
    dc.main()
    bill = json.loads(capsys.readouterr().out)["consumer_bills"][0]
    assert bill["monthly_bill_yr0"] == round(250 * 6.2, 0) and "tariff_yr7" in bill
