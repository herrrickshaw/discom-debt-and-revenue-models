# discom_debt_calculator.py
# ==========================
# DISCOM (electricity Distribution Company) debt-reduction scenario calculator.
#
# WHY
#   Indian DISCOMs carry large accumulated debt mainly because the average cost
#   of supplying power (ACS) exceeds the average revenue realised (ARR) — the
#   "ACS-ARR gap" — compounded by AT&C losses (theft + unbilled + uncollected)
#   and delayed state subsidies. This tool models how consumer-billing levers
#   (tariff hikes, loss reduction, collection-efficiency gains, subsidy timeliness)
#   close that gap and pay down debt over a multi-year horizon.
#
# CORE ECONOMICS (per year)
#   billed_units      = energy_input × (1 − AT&C_loss%)
#   revenue_billed    = billed_units × tariff(ARR)
#   revenue_collected = revenue_billed × collection_efficiency%
#   cost_of_supply    = energy_input × ACS
#   operating_gap     = revenue_collected + subsidy_received − cost_of_supply
#   interest          = opening_debt × interest_rate
#   closing_debt      = opening_debt − operating_gap + interest
#   (a positive operating_gap pays down debt; interest accrues on the balance)
#
# CONSUMER-BILL VIEW
#   For a representative consumer using `monthly_units` kWh, the calculator shows
#   the rupee impact of each tariff scenario on the monthly bill — so policy
#   trade-offs (debt relief vs consumer affordability) are explicit.
#
# Usage
#   python discom_debt_calculator.py                       # default illustrative DISCOM
#   python discom_debt_calculator.py --debt 50000 --acs 7.2 --arr 6.1 --loss 18
#   python discom_debt_calculator.py --json                # machine-readable output
#
# DISCLAIMER: illustrative model with simplifying assumptions (flat ACS growth,
# single blended tariff, no demand elasticity). For scenario education only —
# NOT a substitute for a regulatory tariff filing or audited DISCOM accounts.

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, asdict
from typing import List


# ── Inputs ────────────────────────────────────────────────────────────────────

@dataclass
class DiscomInputs:
    """Baseline financial & operational profile of a DISCOM (illustrative defaults)."""
    opening_debt_cr:     float = 40000.0   # accumulated debt, ₹ crore
    energy_input_mu:     float = 60000.0   # energy procured, million units (MU = GWh)
    acs_per_kwh:         float = 6.80      # Average Cost of Supply, ₹/kWh
    arr_per_kwh:         float = 6.20      # Average Revenue Realised (blended tariff), ₹/kWh
    atc_loss_pct:        float = 15.0      # Aggregate Technical & Commercial loss, %
    collection_eff_pct:  float = 98.0      # % of billed amount actually collected
    subsidy_cr:          float = 9000.0    # annual state subsidy booked, ₹ crore
    subsidy_realised_pct:float = 85.0      # % of booked subsidy actually received
    interest_rate_pct:   float = 9.5       # weighted avg interest on debt, %
    acs_growth_pct:      float = 4.0       # annual ACS inflation, %
    demand_growth_pct:   float = 3.0       # annual energy-input growth, %
    horizon_years:       int   = 7

    # Representative consumer (for bill-impact view)
    consumer_monthly_kwh: float = 250.0    # typical urban household


# ── Scenario definition (the billing levers) ──────────────────────────────────

@dataclass
class Scenario:
    name:                  str
    tariff_hike_pct:       float = 0.0     # annual blended-tariff increase, %
    atc_loss_reduction_pp: float = 0.0     # annual AT&C loss reduction, percentage points
    collection_gain_pp:    float = 0.0     # annual collection-efficiency gain, pp
    subsidy_realised_pp:   float = 0.0     # annual improvement in subsidy realisation, pp


def default_scenarios() -> List[Scenario]:
    return [
        Scenario("Status Quo (no action)"),
        Scenario("Tariff hike only (5%/yr)", tariff_hike_pct=5.0),
        Scenario("Loss + collection reform", atc_loss_reduction_pp=1.5, collection_gain_pp=1.0,
                 subsidy_realised_pp=3.0),
        Scenario("Combined (UDAY-style)", tariff_hike_pct=4.0, atc_loss_reduction_pp=1.5,
                 collection_gain_pp=1.0, subsidy_realised_pp=4.0),
        Scenario("Aggressive turnaround", tariff_hike_pct=6.0, atc_loss_reduction_pp=2.0,
                 collection_gain_pp=1.5, subsidy_realised_pp=5.0),
    ]


# ── Engine ────────────────────────────────────────────────────────────────────

def project(inp: DiscomInputs, sc: Scenario) -> dict:
    """Project the debt trajectory for one scenario over the horizon."""
    debt   = inp.opening_debt_cr
    energy = inp.energy_input_mu
    acs    = inp.acs_per_kwh
    arr    = inp.arr_per_kwh
    loss   = inp.atc_loss_pct
    coll   = inp.collection_eff_pct
    subq   = inp.subsidy_realised_pct

    rows = []
    for yr in range(1, inp.horizon_years + 1):
        # Apply annual levers
        arr  *= (1 + sc.tariff_hike_pct / 100.0)
        loss  = max(0.0, loss - sc.atc_loss_reduction_pp)
        coll  = min(100.0, coll + sc.collection_gain_pp)
        subq  = min(100.0, subq + sc.subsidy_realised_pp)
        acs  *= (1 + inp.acs_growth_pct / 100.0)
        energy *= (1 + inp.demand_growth_pct / 100.0)

        # Annual P&L (₹ crore):  MU × ₹/kWh = ₹ crore  (1 MU × ₹1/kWh = ₹0.1 cr... )
        # Unit math: 1 MU = 1e6 kWh; ₹/kWh × 1e6 = ₹ in millions = ₹/10 crore.
        # So crore = MU × ₹perkWh / 10.
        billed_units   = energy * (1 - loss / 100.0)
        rev_billed     = billed_units * arr / 10.0
        rev_collected  = rev_billed * coll / 100.0
        cost_supply    = energy * acs / 10.0
        subsidy_recv   = inp.subsidy_cr * subq / 100.0
        op_gap         = rev_collected + subsidy_recv - cost_supply   # +ve pays debt
        interest       = debt * inp.interest_rate_pct / 100.0
        debt           = debt - op_gap + interest

        rows.append({
            "year": yr,
            "ARR": round(arr, 2), "ACS": round(acs, 2),
            "ACS_ARR_gap": round(acs - arr, 2),
            "AT&C_loss%": round(loss, 1), "collection%": round(coll, 1),
            "op_gap_cr": round(op_gap, 0),
            "interest_cr": round(interest, 0),
            "closing_debt_cr": round(debt, 0),
        })

    return {"scenario": sc.name, "final_debt_cr": round(debt, 0),
            "debt_change_cr": round(debt - inp.opening_debt_cr, 0),
            "rows": rows}


def consumer_bill_impact(inp: DiscomInputs, scenarios: List[Scenario]) -> List[dict]:
    """Monthly bill for a representative consumer under each scenario at year `horizon`."""
    out = []
    base_bill = inp.consumer_monthly_kwh * inp.arr_per_kwh
    for sc in scenarios:
        arr = inp.arr_per_kwh * ((1 + sc.tariff_hike_pct / 100.0) ** inp.horizon_years)
        bill = inp.consumer_monthly_kwh * arr
        out.append({
            "scenario": sc.name,
            "tariff_yr0": round(inp.arr_per_kwh, 2),
            f"tariff_yr{inp.horizon_years}": round(arr, 2),
            "monthly_bill_yr0": round(base_bill, 0),
            f"monthly_bill_yr{inp.horizon_years}": round(bill, 0),
            "bill_increase_pct": round((bill - base_bill) / base_bill * 100, 1),
        })
    return out


# ── Reporting ─────────────────────────────────────────────────────────────────

def run(inp: DiscomInputs, scenarios: List[Scenario], as_json: bool = False):
    results = [project(inp, sc) for sc in scenarios]
    bills   = consumer_bill_impact(inp, scenarios)

    if as_json:
        print(json.dumps({"inputs": asdict(inp), "results": results,
                          "consumer_bills": bills}, indent=2))
        return {"results": results, "bills": bills}

    print("\n" + "=" * 78)
    print("  DISCOM DEBT-REDUCTION SCENARIO CALCULATOR")
    print("=" * 78)
    print(f"  Opening debt: ₹{inp.opening_debt_cr:,.0f} Cr | Energy input: {inp.energy_input_mu:,.0f} MU")
    print(f"  ACS ₹{inp.acs_per_kwh}/kWh vs ARR ₹{inp.arr_per_kwh}/kWh "
          f"(gap ₹{inp.acs_per_kwh-inp.arr_per_kwh:.2f}/kWh) | AT&C loss {inp.atc_loss_pct}% | "
          f"collection {inp.collection_eff_pct}%")
    print(f"  Interest {inp.interest_rate_pct}% | horizon {inp.horizon_years} yrs")

    print(f"\n  {'Scenario':<28} {'Final debt ₹Cr':>15} {'Δ vs today ₹Cr':>16} {'Outcome'}")
    print("  " + "─" * 74)
    for r in results:
        ch = r["debt_change_cr"]
        outcome = "▼ debt cut" if ch < 0 else ("≈ flat" if abs(ch) < inp.opening_debt_cr*0.05 else "▲ debt grows")
        print(f"  {r['scenario']:<28} {r['final_debt_cr']:>15,.0f} {ch:>+16,.0f}  {outcome}")

    # Debt trajectory of the best (combined) scenario
    best = min(results, key=lambda x: x["final_debt_cr"])
    print(f"\n  Debt trajectory — best scenario: «{best['scenario']}»")
    print(f"  {'Yr':>3} {'ARR':>6} {'ACS':>6} {'Gap':>6} {'Loss%':>6} {'OpGap ₹Cr':>11} {'Debt ₹Cr':>12}")
    print("  " + "─" * 58)
    for row in best["rows"]:
        print(f"  {row['year']:>3} {row['ARR']:>6.2f} {row['ACS']:>6.2f} "
              f"{row['ACS_ARR_gap']:>6.2f} {row['AT&C_loss%']:>6.1f} "
              f"{row['op_gap_cr']:>+11,.0f} {row['closing_debt_cr']:>12,.0f}")

    # Consumer affordability
    print(f"\n  CONSUMER BILL IMPACT (household @ {inp.consumer_monthly_kwh:.0f} kWh/month):")
    print(f"  {'Scenario':<28} {'Bill yr0':>10} {f'Bill yr{inp.horizon_years}':>10} {'Increase':>10}")
    print("  " + "─" * 60)
    for b in bills:
        print(f"  {b['scenario']:<28} ₹{b['monthly_bill_yr0']:>8,.0f} "
              f"₹{b[f'monthly_bill_yr{inp.horizon_years}']:>8,.0f} "
              f"{b['bill_increase_pct']:>9.1f}%")

    print(f"\n  ── INTERPRETATION ──")
    sq = next(r for r in results if "Status Quo" in r["scenario"])
    print(f"  • Doing nothing: debt moves to ₹{sq['final_debt_cr']:,.0f} Cr "
          f"({sq['debt_change_cr']:+,.0f} Cr) as interest compounds on the ACS-ARR gap.")
    print(f"  • Best scenario «{best['scenario']}»: ₹{best['final_debt_cr']:,.0f} Cr "
          f"({best['debt_change_cr']:+,.0f} Cr).")
    bb = next(b for b in bills if b["scenario"] == best["scenario"])
    print(f"    Cost to the consumer: +{bb['bill_increase_pct']:.0f}% on the monthly bill over "
          f"{inp.horizon_years} years.")
    ops = next(r for r in results if "Loss + collection" in r["scenario"])
    saved = sq["final_debt_cr"] - ops["final_debt_cr"]
    verdict = "cut" if ops["debt_change_cr"] < 0 else "still grow"
    print(f"  • Operational levers alone (loss + collection + subsidy, no tariff hike) save "
          f"₹{saved:,.0f} Cr vs doing nothing")
    print(f"    but debt would {verdict} ({ops['debt_change_cr']:+,.0f} Cr): reform cannot close the "
          f"gap without tariff action — the affordability trade-off.")
    print("=" * 78)
    print("  ⚠️  Illustrative model. NOT a tariff filing or audited DISCOM accounts.")
    print("=" * 78)
    return {"results": results, "bills": bills}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="DISCOM debt-reduction scenario calculator (power-bill levers).")
    p.add_argument("--debt", type=float, help="Opening debt (₹ Cr)")
    p.add_argument("--energy", type=float, help="Annual energy input (MU)")
    p.add_argument("--acs", type=float, help="Average Cost of Supply (₹/kWh)")
    p.add_argument("--arr", type=float, help="Average Revenue Realised (₹/kWh)")
    p.add_argument("--loss", type=float, help="AT&C loss (%%)")
    p.add_argument("--collection", type=float, help="Collection efficiency (%%)")
    p.add_argument("--interest", type=float, help="Interest rate on debt (%%)")
    p.add_argument("--horizon", type=int, help="Projection horizon (years)")
    p.add_argument("--monthly-kwh", type=float, help="Representative consumer monthly kWh")
    p.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    a = p.parse_args()

    inp = DiscomInputs()
    if a.debt is not None:        inp.opening_debt_cr = a.debt
    if a.energy is not None:      inp.energy_input_mu = a.energy
    if a.acs is not None:         inp.acs_per_kwh = a.acs
    if a.arr is not None:         inp.arr_per_kwh = a.arr
    if a.loss is not None:        inp.atc_loss_pct = a.loss
    if a.collection is not None:  inp.collection_eff_pct = a.collection
    if a.interest is not None:    inp.interest_rate_pct = a.interest
    if a.horizon is not None:     inp.horizon_years = a.horizon
    if a.monthly_kwh is not None: inp.consumer_monthly_kwh = a.monthly_kwh

    run(inp, default_scenarios(), as_json=a.json)


if __name__ == "__main__":
    main()
