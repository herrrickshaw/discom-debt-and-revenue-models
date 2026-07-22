# subscription-model-revenue

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/herrrickshaw/discom-debt-and-revenue-models/blob/main/notebooks/colab_test.ipynb)

Revenue & cost-recovery modelling experiments.

## Contents

| File | What it does |
|------|--------------|
| `discom_debt_calculator.py` | **DISCOM debt-reduction scenario calculator** — models how consumer-billing levers (tariff hikes, AT&C loss reduction, collection efficiency, subsidy timeliness) close the ACS-ARR gap and pay down electricity-distribution-company debt over a multi-year horizon. Includes a consumer-bill affordability view. |
| `random_numbers_using_dirichlet.py` | Dirichlet-distribution simulation for allocating subscription revenue across off-peak months (probabilistic seasonality). |

## DISCOM debt calculator

```bash
python3 discom_debt_calculator.py                          # illustrative DISCOM
python3 discom_debt_calculator.py --debt 50000 --acs 7.2 --arr 6.1 --loss 18
python3 discom_debt_calculator.py --json                   # machine-readable
```

Models the core DISCOM economics — `closing_debt = opening_debt − operating_gap + interest`,
where `operating_gap = revenue_collected + subsidy − cost_of_supply` — across five
scenarios (status quo, tariff-only, operational reform, UDAY-style combined, aggressive
turnaround) and shows the consumer monthly-bill impact of each, making the debt-relief
vs affordability trade-off explicit.

⚠️ Illustrative models with simplifying assumptions. For education only — not a
regulatory tariff filing, audited accounts, or investment advice.
