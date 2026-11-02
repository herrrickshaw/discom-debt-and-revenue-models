from __future__ import annotations

import numpy as np

import random_numbers_using_dirichlet as rd


def test_shares_sum_to_100_per_draw():
    k = rd.dirichlet_shares(rd.MONTHLY_ALPHA, 12, np.random.default_rng(0))
    assert k.shape == (12, 12)
    np.testing.assert_allclose(k.sum(axis=0), 100.0)
    assert (k >= 0).all()


def test_rate_matrix_rows_are_1_to_12():
    d = rd.rate_matrix()
    assert d.shape == (12, 12)
    assert (d == np.arange(1, 13)).all()


def test_revenue_equals_dot_product():
    k = rd.dirichlet_shares(rd.MONTHLY_ALPHA, 12, np.random.default_rng(1))
    rev = rd.revenue_at_rates(k)
    np.testing.assert_allclose(rev, np.dot(rd.rate_matrix(), k))
    # every row of the rate matrix is 1..12, so every result row is the same
    # rate-weighted sum of the monthly shares
    expected = (np.arange(1, 13)[:, None] * k).sum(axis=0)
    for row in rev:
        np.testing.assert_allclose(row, expected)


def test_stacked_barh_stacks_each_category(monkeypatch):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    calls = []
    monkeypatch.setattr(
        plt, "barh", lambda y, w, left=0, color=None: calls.append((list(w), list(left), color))
    )
    shares = np.array([[10.0, 20.0], [30.0, 40.0], [60.0, 40.0]])
    rd.stacked_barh(shares, "t")
    assert [c[2] for c in calls] == [None, "g", "r"]
    assert calls[0][1] == [0.0, 0.0]
    assert calls[2][1] == [40.0, 60.0]


def test_demo_runs_headless():
    import matplotlib

    matplotlib.use("Agg")
    rd.main()
