# DISCOM debt and revenue models

Two small, self-contained Python models of electricity-distribution economics in India.
`discom_debt_calculator.py` projects how a DISCOM's (electricity Distribution Company's)
accumulated debt evolves over a multi-year horizon under different consumer-billing levers
(tariff hikes, AT&C loss reduction, collection-efficiency gains, subsidy timeliness) and
shows the monthly-bill cost of each scenario to a representative household.
`random_numbers_using_dirichlet.py` is a Dirichlet-distribution toy for spreading subscription
revenue across months when some months are billed free. Outputs are a console report or JSON
(calculator) and console arrays plus two matplotlib bar charts (Dirichlet demo).

> Status: research-only. Illustrative models with simplifying assumptions and made-up default
> inputs; for education only — not a regulatory tariff filing, audited DISCOM accounts, or
> investment advice.

<!-- how-to-use-with-ai -->
> **New here?** See [How to use this repo with AI (Claude, Gemini, ChatGPT)](HOW_TO_USE_WITH_AI.md) — clone it, paste it into an AI tool, and ask in plain English.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/herrrickshaw/discom-debt-and-revenue-models/blob/main/notebooks/colab_test.ipynb)

## What it does
- Projects year-by-year ARR, ACS, AT&C loss, collection %, operating gap, interest and closing debt for a DISCOM over a configurable horizon (`project()`).
- Compares five built-in scenarios: status quo, tariff hike only (5 %/yr), loss + collection reform, combined UDAY-style, aggressive turnaround (`default_scenarios()`).
- Reports the monthly bill of a representative consumer (default 250 kWh/month) at year 0 and at the horizon for each scenario (`consumer_bill_impact()`).
- Prints a text report or, with `--json`, a machine-readable dump of inputs, per-year rows and bills.
- Draws Dirichlet revenue shares across 12 months that sum to 100 % and multiplies them by per-month rates of 1..12 INR (`dirichlet_shares()`, `revenue_at_rates()`).

## Quick start
```bash
git clone https://github.com/herrrickshaw/discom-debt-and-revenue-models.git
cd discom-debt-and-revenue-models
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python discom_debt_calculator.py                          # illustrative DISCOM, text report
```

Other invocations:
```bash
python discom_debt_calculator.py --debt 50000 --acs 7.2 --arr 6.1 --loss 18
python discom_debt_calculator.py --json                   # machine-readable
python discom_debt_calculator.py --help                   # all flags
python random_numbers_using_dirichlet.py                  # Dirichlet demo (needs a matplotlib backend)
```

## How it works

Per year, in Rs crore (1 MU x Rs 1/kWh = Rs 0.1 crore):

```
billed_units      = energy_input x (1 - AT&C_loss%)
revenue_billed    = billed_units x ARR
revenue_collected = revenue_billed x collection_efficiency%
cost_of_supply    = energy_input x ACS
operating_gap     = revenue_collected + subsidy_received - cost_of_supply
interest          = opening_debt x interest_rate
closing_debt      = opening_debt - operating_gap + interest
```

A positive operating gap pays down debt; interest accrues on the opening balance. Each year the
scenario's levers are applied first (tariff compounding, loss reduction, collection and subsidy
gains clamped to 0–100 %), then ACS inflation and demand growth from the inputs.

| Stage | Function (`discom_debt_calculator.py`) | Output |
|---|---|---|
| Inputs | `DiscomInputs`, `Scenario`, `default_scenarios()` | dataclasses with illustrative defaults |
| Advance one year | `apply_levers()` on a `YearState` | updated tariff, loss, collection, subsidy, ACS, energy |
| Annual P&L | `annual_pnl()` | operating gap and interest (Rs crore) |
| Horizon projection | `project()` | per-year rows + final debt for one scenario |
| Consumer view | `consumer_bill_impact()` | yr-0 vs yr-N monthly bill per scenario |
| All scenarios, no I/O | `compute()` | `{"results": [...], "bills": [...]}` |
| Rendering | `format_report()` / `run()` | text report or JSON on stdout |
| CLI | `build_parser()`, `inputs_from_args()`, `main()` | flag overrides of the defaults |

Design choices: computation is pure (no printing) so it can be tested against pinned numbers;
the CLI maps each flag to a `DiscomInputs` field through one table instead of an if-chain; the
Dirichlet module imports matplotlib lazily so the numeric helpers work headless.

Model assumptions (unchanged from the original): a single blended tariff, flat annual ACS
inflation and demand growth, no demand elasticity, subsidy booked as a fixed annual amount,
interest on the opening balance only.

## Repository layout
| Path | Purpose |
|---|---|
| `discom_debt_calculator.py` | DISCOM debt-reduction scenario calculator (library + CLI) |
| `random_numbers_using_dirichlet.py` | Dirichlet revenue-seasonality demo (library + CLI) |
| `tests/` | pytest characterisation and unit tests; numeric outputs are pinned to the pre-refactor values |
| `notebooks/colab_test.ipynb` | Colab smoke test: clones the repo, installs deps, byte-compiles modules |
| `from-global-market-data/` | historical copy of the Dirichlet script imported from the `global-market-data` repo (not maintained; excluded from lint) |
| `HOW_TO_USE_WITH_AI.md` | plain-language guide to exploring the repo with an AI assistant |
| `pyproject.toml`, `requirements.txt` | ruff/pytest config and runtime deps (numpy, matplotlib) |
| `.github/workflows/ci.yml` | ruff + compileall + pytest on Python 3.9 and 3.12 |

## Data sources
None. All inputs are illustrative defaults in `DiscomInputs` (opening debt Rs 40,000 crore,
60,000 MU, ACS Rs 6.80/kWh, ARR Rs 6.20/kWh, 15 % AT&C loss, 98 % collection, Rs 9,000 crore
subsidy at 85 % realisation, 9.5 % interest, 7-year horizon) or supplied on the command line.
They are not taken from any regulator or utility filing.

## Configuration
No environment variables, config files or secrets. All calculator inputs are CLI flags
(`--debt --energy --acs --arr --loss --collection --interest --horizon --monthly-kwh --json`);
anything not given keeps its `DiscomInputs` default. Subsidy amount, subsidy realisation, ACS
growth and demand growth are only settable from Python (`DiscomInputs(...)`).

## Testing
```bash
pip install pytest ruff
pytest -q
ruff check .
```

## Limitations and known issues
- Illustrative model only; the defaults are not any real DISCOM.
- Scenarios are fixed in `default_scenarios()`; custom scenarios need a few lines of Python.
- The debt can go negative (a surplus) — the model does not stop at zero debt.
- `random_numbers_using_dirichlet.py` draws fresh random numbers each run (unseeded) and draws both
  charts on the same matplotlib figure, as the original Colab notebook did.
- `python -m compileall` is the only check the Colab notebook runs; it does not execute the models.

## Licence
No licence file yet — all rights reserved.
