"""DISCOM (electricity Distribution Company) debt-reduction scenario calculator.

WHY
    Indian DISCOMs carry large accumulated debt mainly because the average cost
    of supplying power (ACS) exceeds the average revenue realised (ARR) -- the
    "ACS-ARR gap" -- compounded by AT&C losses (theft + unbilled + uncollected)
    and delayed state subsidies. This tool models how consumer-billing levers
    (tariff hikes, loss reduction, collection-efficiency gains, subsidy
    timeliness) close that gap and pay down debt over a multi-year horizon.

CORE ECONOMICS (per year)
    billed_units      = energy_input x (1 - AT&C_loss%)
    revenue_billed    = billed_units x tariff(ARR)
    revenue_collected = revenue_billed x collection_efficiency%
    cost_of_supply    = energy_input x ACS
    operating_gap     = revenue_collected + subsidy_received - cost_of_supply
    interest          = opening_debt x interest_rate
    closing_debt      = opening_debt - operating_gap + interest
    (a positive operating_gap pays down debt; interest accrues on the balance)

CONSUMER-BILL VIEW
    For a representative consumer using `consumer_monthly_kwh`, the calculator
    shows the rupee impact of each tariff scenario on the monthly bill -- so
    policy trade-offs (debt relief vs consumer affordability) are explicit.

Usage
    python discom_debt_calculator.py                       # default illustrative DISCOM
    python discom_debt_calculator.py --debt 50000 --acs 7.2 --arr 6.1 --loss 18
    python discom_debt_calculator.py --json                # machine-readable output

DISCLAIMER: illustrative model with simplifying assumptions (flat ACS growth,
single blended tariff, no demand elasticity). For scenario education only --
NOT a substitute for a regulatory tariff filing or audited DISCOM accounts.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

# Unit math: 1 MU = 1e6 kWh, so MU x Rs/kWh = Rs millions = Rs crore / 10.
MU_TIMES_RUPEE_PER_KWH_TO_CRORE = 10.0
# A debt change within +/- this fraction of opening debt is reported as "flat".
FLAT_BAND_FRACTION = 0.05
PCT = 100.0

# ── Inputs ────────────────────────────────────────────────────────────────────


@dataclass
class DiscomInputs:
    """Baseline financial & operational profile of a DISCOM (illustrative defaults)."""

    opening_debt_cr: float = 40000.0  # accumulated debt, Rs crore
    energy_input_mu: float = 60000.0  # energy procured, million units (MU = GWh)
    acs_per_kwh: float = 6.80  # Average Cost of Supply, Rs/kWh
    arr_per_kwh: float = 6.20  # Average Revenue Realised (blended tariff), Rs/kWh
    atc_loss_pct: float = 15.0  # Aggregate Technical & Commercial loss, %
    collection_eff_pct: float = 98.0  # % of billed amount actually collected
    subsidy_cr: float = 9000.0  # annual state subsidy booked, Rs crore
    subsidy_realised_pct: float = 85.0  # % of booked subsidy actually received
    interest_rate_pct: float = 9.5  # weighted avg interest on debt, %
    acs_growth_pct: float = 4.0  # annual ACS inflation, %
    demand_growth_pct: float = 3.0  # annual energy-input growth, %
    horizon_years: int = 7

    # Representative consumer (for bill-impact view)
    consumer_monthly_kwh: float = 250.0  # typical urban household


# ── Scenario definition (the billing levers) ──────────────────────────────────


@dataclass
class Scenario:
    """Annual policy levers applied cumulatively each year of the horizon."""

    name: str
    tariff_hike_pct: float = 0.0  # annual blended-tariff increase, %
    atc_loss_reduction_pp: float = 0.0  # annual AT&C loss reduction, percentage points
    collection_gain_pp: float = 0.0  # annual collection-efficiency gain, pp
    subsidy_realised_pp: float = 0.0  # annual improvement in subsidy realisation, pp


def default_scenarios() -> list[Scenario]:
    """The five illustrative scenarios compared by the CLI."""
    return [
        Scenario("Status Quo (no action)"),
        Scenario("Tariff hike only (5%/yr)", tariff_hike_pct=5.0),
        Scenario(
            "Loss + collection reform",
            atc_loss_reduction_pp=1.5,
            collection_gain_pp=1.0,
            subsidy_realised_pp=3.0,
        ),
        Scenario(
            "Combined (UDAY-style)",
            tariff_hike_pct=4.0,
            atc_loss_reduction_pp=1.5,
            collection_gain_pp=1.0,
            subsidy_realised_pp=4.0,
        ),
        Scenario(
            "Aggressive turnaround",
            tariff_hike_pct=6.0,
            atc_loss_reduction_pp=2.0,
            collection_gain_pp=1.5,
            subsidy_realised_pp=5.0,
        ),
    ]


# ── Engine ────────────────────────────────────────────────────────────────────


@dataclass
class YearState:
    """Mutable operating state carried from one projection year to the next."""

    debt_cr: float
    energy_mu: float
    acs: float
    arr: float
    loss_pct: float
    collection_pct: float
    subsidy_realised_pct: float

    @classmethod
    def from_inputs(cls, inp: DiscomInputs) -> YearState:
        return cls(
            debt_cr=inp.opening_debt_cr,
            energy_mu=inp.energy_input_mu,
            acs=inp.acs_per_kwh,
            arr=inp.arr_per_kwh,
            loss_pct=inp.atc_loss_pct,
            collection_pct=inp.collection_eff_pct,
            subsidy_realised_pct=inp.subsidy_realised_pct,
        )


def apply_levers(state: YearState, inp: DiscomInputs, sc: Scenario) -> None:
    """Advance tariff, losses, collection, subsidy, ACS and demand by one year (in place)."""
    state.arr *= 1 + sc.tariff_hike_pct / PCT
    state.loss_pct = max(0.0, state.loss_pct - sc.atc_loss_reduction_pp)
    state.collection_pct = min(PCT, state.collection_pct + sc.collection_gain_pp)
    state.subsidy_realised_pct = min(PCT, state.subsidy_realised_pct + sc.subsidy_realised_pp)
    state.acs *= 1 + inp.acs_growth_pct / PCT
    state.energy_mu *= 1 + inp.demand_growth_pct / PCT


def annual_pnl(state: YearState, inp: DiscomInputs) -> dict[str, float]:
    """One year's P&L in Rs crore: operating gap (+ve pays debt) and interest on opening debt."""
    billed_units = state.energy_mu * (1 - state.loss_pct / PCT)
    rev_billed = billed_units * state.arr / MU_TIMES_RUPEE_PER_KWH_TO_CRORE
    rev_collected = rev_billed * state.collection_pct / PCT
    cost_supply = state.energy_mu * state.acs / MU_TIMES_RUPEE_PER_KWH_TO_CRORE
    subsidy_recv = inp.subsidy_cr * state.subsidy_realised_pct / PCT
    op_gap = rev_collected + subsidy_recv - cost_supply
    interest = state.debt_cr * inp.interest_rate_pct / PCT
    return {"op_gap_cr": op_gap, "interest_cr": interest}


def project(inp: DiscomInputs, sc: Scenario) -> dict[str, Any]:
    """Project the debt trajectory for one scenario over the horizon.

    Returns ``{"scenario", "final_debt_cr", "debt_change_cr", "rows"}`` where each
    row carries the year-end ARR/ACS (Rs/kWh), gap, loss %, collection %,
    operating gap, interest and closing debt (Rs crore, rounded).
    """
    state = YearState.from_inputs(inp)
    rows = []
    for yr in range(1, inp.horizon_years + 1):
        apply_levers(state, inp, sc)
        pnl = annual_pnl(state, inp)
        state.debt_cr = state.debt_cr - pnl["op_gap_cr"] + pnl["interest_cr"]
        rows.append(
            {
                "year": yr,
                "ARR": round(state.arr, 2),
                "ACS": round(state.acs, 2),
                "ACS_ARR_gap": round(state.acs - state.arr, 2),
                "AT&C_loss%": round(state.loss_pct, 1),
                "collection%": round(state.collection_pct, 1),
                "op_gap_cr": round(pnl["op_gap_cr"], 0),
                "interest_cr": round(pnl["interest_cr"], 0),
                "closing_debt_cr": round(state.debt_cr, 0),
            }
        )

    return {
        "scenario": sc.name,
        "final_debt_cr": round(state.debt_cr, 0),
        "debt_change_cr": round(state.debt_cr - inp.opening_debt_cr, 0),
        "rows": rows,
    }


def consumer_bill_impact(inp: DiscomInputs, scenarios: Sequence[Scenario]) -> list[dict[str, Any]]:
    """Monthly bill (Rs) for a representative consumer under each scenario at year `horizon`."""
    out = []
    base_bill = inp.consumer_monthly_kwh * inp.arr_per_kwh
    for sc in scenarios:
        arr = inp.arr_per_kwh * ((1 + sc.tariff_hike_pct / PCT) ** inp.horizon_years)
        bill = inp.consumer_monthly_kwh * arr
        out.append(
            {
                "scenario": sc.name,
                "tariff_yr0": round(inp.arr_per_kwh, 2),
                f"tariff_yr{inp.horizon_years}": round(arr, 2),
                "monthly_bill_yr0": round(base_bill, 0),
                f"monthly_bill_yr{inp.horizon_years}": round(bill, 0),
                "bill_increase_pct": round((bill - base_bill) / base_bill * PCT, 1),
            }
        )
    return out


def compute(inp: DiscomInputs, scenarios: Sequence[Scenario]) -> dict[str, Any]:
    """Run every scenario; return ``{"results": [...], "bills": [...]}`` (pure, no I/O)."""
    return {
        "results": [project(inp, sc) for sc in scenarios],
        "bills": consumer_bill_impact(inp, scenarios),
    }


# ── Reporting ─────────────────────────────────────────────────────────────────


def _outcome_label(debt_change_cr: float, opening_debt_cr: float) -> str:
    if debt_change_cr < 0:
        return "▼ debt cut"
    if abs(debt_change_cr) < opening_debt_cr * FLAT_BAND_FRACTION:
        return "≈ flat"
    return "▲ debt grows"


def format_report(
    inp: DiscomInputs, results: Sequence[dict[str, Any]], bills: Sequence[dict[str, Any]]
) -> str:
    """Render the human-readable scenario report (same layout as the original CLI)."""
    h = inp.horizon_years
    lines: list[str] = []
    lines.append("")
    lines.append("=" * 78)
    lines.append("  DISCOM DEBT-REDUCTION SCENARIO CALCULATOR")
    lines.append("=" * 78)
    lines.append(
        f"  Opening debt: ₹{inp.opening_debt_cr:,.0f} Cr | Energy input: {inp.energy_input_mu:,.0f} MU"
    )
    lines.append(
        f"  ACS ₹{inp.acs_per_kwh}/kWh vs ARR ₹{inp.arr_per_kwh}/kWh "
        f"(gap ₹{inp.acs_per_kwh - inp.arr_per_kwh:.2f}/kWh) | AT&C loss {inp.atc_loss_pct}% | "
        f"collection {inp.collection_eff_pct}%"
    )
    lines.append(f"  Interest {inp.interest_rate_pct}% | horizon {h} yrs")

    lines.append(f"\n  {'Scenario':<28} {'Final debt ₹Cr':>15} {'Δ vs today ₹Cr':>16} {'Outcome'}")
    lines.append("  " + "─" * 74)
    for r in results:
        ch = r["debt_change_cr"]
        outcome = _outcome_label(ch, inp.opening_debt_cr)
        lines.append(f"  {r['scenario']:<28} {r['final_debt_cr']:>15,.0f} {ch:>+16,.0f}  {outcome}")

    best = min(results, key=lambda x: x["final_debt_cr"])
    lines.append(f"\n  Debt trajectory — best scenario: «{best['scenario']}»")
    lines.append(
        f"  {'Yr':>3} {'ARR':>6} {'ACS':>6} {'Gap':>6} {'Loss%':>6} {'OpGap ₹Cr':>11} {'Debt ₹Cr':>12}"
    )
    lines.append("  " + "─" * 58)
    for row in best["rows"]:
        lines.append(
            f"  {row['year']:>3} {row['ARR']:>6.2f} {row['ACS']:>6.2f} "
            f"{row['ACS_ARR_gap']:>6.2f} {row['AT&C_loss%']:>6.1f} "
            f"{row['op_gap_cr']:>+11,.0f} {row['closing_debt_cr']:>12,.0f}"
        )

    lines.append(f"\n  CONSUMER BILL IMPACT (household @ {inp.consumer_monthly_kwh:.0f} kWh/month):")
    lines.append(f"  {'Scenario':<28} {'Bill yr0':>10} {f'Bill yr{h}':>10} {'Increase':>10}")
    lines.append("  " + "─" * 60)
    for b in bills:
        lines.append(
            f"  {b['scenario']:<28} ₹{b['monthly_bill_yr0']:>8,.0f} "
            f"₹{b[f'monthly_bill_yr{h}']:>8,.0f} "
            f"{b['bill_increase_pct']:>9.1f}%"
        )

    lines.append("\n  ── INTERPRETATION ──")
    sq = next(r for r in results if "Status Quo" in r["scenario"])
    lines.append(
        f"  • Doing nothing: debt moves to ₹{sq['final_debt_cr']:,.0f} Cr "
        f"({sq['debt_change_cr']:+,.0f} Cr) as interest compounds on the ACS-ARR gap."
    )
    lines.append(
        f"  • Best scenario «{best['scenario']}»: ₹{best['final_debt_cr']:,.0f} Cr "
        f"({best['debt_change_cr']:+,.0f} Cr)."
    )
    bb = next(b for b in bills if b["scenario"] == best["scenario"])
    lines.append(
        f"    Cost to the consumer: +{bb['bill_increase_pct']:.0f}% on the monthly bill over {h} years."
    )
    lines.append("  • Operational levers (loss + collection + subsidy) cut debt WITHOUT the full")
    lines.append("    tariff burden on consumers — the key affordability trade-off.")
    lines.append("=" * 78)
    lines.append("  ⚠️  Illustrative model. NOT a tariff filing or audited DISCOM accounts.")
    lines.append("=" * 78)
    return "\n".join(lines)


def run(inp: DiscomInputs, scenarios: Sequence[Scenario], as_json: bool = False) -> dict[str, Any]:
    """Compute all scenarios and print either JSON or the text report; return the results."""
    out = compute(inp, scenarios)
    if as_json:
        payload = {"inputs": asdict(inp), "results": out["results"], "consumer_bills": out["bills"]}
        print(json.dumps(payload, indent=2))
    else:
        print(format_report(inp, out["results"], out["bills"]))
    return out


# ── CLI ───────────────────────────────────────────────────────────────────────

# CLI flag (argparse dest) -> DiscomInputs field it overrides.
_ARG_TO_FIELD = {
    "debt": "opening_debt_cr",
    "energy": "energy_input_mu",
    "acs": "acs_per_kwh",
    "arr": "arr_per_kwh",
    "loss": "atc_loss_pct",
    "collection": "collection_eff_pct",
    "interest": "interest_rate_pct",
    "horizon": "horizon_years",
    "monthly_kwh": "consumer_monthly_kwh",
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="DISCOM debt-reduction scenario calculator (power-bill levers).")
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
    return p


def inputs_from_args(a: argparse.Namespace) -> DiscomInputs:
    """Start from the illustrative defaults and apply only the flags that were given."""
    inp = DiscomInputs()
    for arg, field_name in _ARG_TO_FIELD.items():
        value = getattr(a, arg, None)
        if value is not None:
            setattr(inp, field_name, value)
    return inp


def main(argv: Sequence[str] | None = None) -> None:
    a = build_parser().parse_args(argv)
    run(inputs_from_args(a), default_scenarios(), as_json=a.json)


if __name__ == "__main__":
    main()
