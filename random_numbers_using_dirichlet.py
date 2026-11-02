"""Dirichlet-distribution simulation of revenue spread across months.

Originally a Colab export
(https://colab.research.google.com/drive/1TNPiBGtAfhN9mwarpFr1O3BmnRsTpjF5).

Question modelled: a subscription is billed for only some of 12 months and
the free months vary at random. If each month's share of annual revenue is a
Dirichlet draw (summing to 100 %), what revenue does each month yield at a
per-month rate of 1 INR, 2 INR, ... 12 INR?

Running the module reproduces the Colab demo: random Dirichlet draws, two
stacked horizontal bar charts, and the rate x share revenue matrix.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

MONTHS = 12
# Concentration per month used in the Colab demo (higher = larger expected share).
MONTHLY_ALPHA = (1, 5, 3, 4, 5, 6, 7, 8, 10, 7, 2, 4)
DEMO_ALPHA = (10, 5, 3)
# None = matplotlib default (next colour in the cycle), exactly as the Colab demo did.
BAR_COLORS = (None, "g", "r", "m", "y", "b", "g", "r", "m", "y", "b", "g")


def dirichlet_shares(
    alpha: Sequence[float], n_draws: int, rng: np.random.Generator | None = None
) -> np.ndarray:
    """Draw `n_draws` Dirichlet vectors scaled to percentages.

    Returns an array of shape ``(len(alpha), n_draws)``: row i is category i's
    share (0-100) across the draws, so each column sums to 100.
    """
    rng = np.random.default_rng() if rng is None else rng
    return (rng.dirichlet(alpha, n_draws) * 100).transpose()


def rate_matrix(n_months: int = MONTHS) -> np.ndarray:
    """``(n_months, n_months)`` matrix whose every row is the rates 1..n_months INR."""
    return np.tile(np.arange(1, n_months + 1), (n_months, 1))


def revenue_at_rates(shares: np.ndarray, n_months: int = MONTHS) -> np.ndarray:
    """``rate_matrix(n_months) @ shares``: shape ``(n_months, n_draws)``.

    Every row of the rate matrix is the same ``1..n_months`` vector, so every row
    of the result is identical: month i's share weighted by i INR, summed over
    the months, for each draw (column).
    """
    return np.dot(rate_matrix(n_months), shares)


def stacked_barh(shares: np.ndarray, title: str, colors: Sequence[str | None] = BAR_COLORS) -> None:
    """Plot each draw as a horizontal bar stacked by category share."""
    import matplotlib.pyplot as plt  # imported lazily: plotting is optional

    n_categories, n_draws = shares.shape
    left = np.zeros(n_draws)
    for i in range(n_categories):
        plt.barh(range(n_draws), shares[i], left=left, color=colors[i % len(colors)])
        left = left + shares[i]
    plt.title(title)


def main() -> None:
    # This is dirichlet in Python, but most languages support the Dirichlet.
    print(np.random.dirichlet(np.ones(MONTHS)) * 100)

    rng = np.random.default_rng()

    k = dirichlet_shares(DEMO_ALPHA, 20, rng)
    stacked_barh(k, "Lengths of Strings")
    print(k)

    k = dirichlet_shares(MONTHLY_ALPHA, MONTHS, rng)
    stacked_barh(k, "Random numbers between 0 to 100 for 12 months")
    print(*k)

    d = rate_matrix()
    print(d)
    print(revenue_at_rates(k))


if __name__ == "__main__":
    main()
