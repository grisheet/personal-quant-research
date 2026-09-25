"""Hand calculations, a separate scalar oracle, and self-financing properties."""

import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pqr.backtesting.engine import VectorizedBacktest
from pqr.data.schemas import DataError
from pqr.execution.costs import CostModel, execute_target


def test_entry_cost_and_timing(small_returns: pd.DataFrame) -> None:
    targets = pd.DataFrame({"A": [1.0], "B": [0.0]}, index=small_returns.index[:1])
    result = VectorizedBacktest().run(small_returns, targets, CostModel(0, 100), 100)
    assert result.ledger.iloc[0]["nav"] == pytest.approx(100 / 1.01)
    assert result.ledger.iloc[0]["cost_usd"] == pytest.approx(100 - 100 / 1.01)
    assert result.ledger.iloc[1]["nav"] == pytest.approx(100 / 1.01 * 1.1)
    assert result.ledger.iloc[1]["turnover"] == 0


def test_rebalance_does_not_capture_same_session_return(small_returns: pd.DataFrame) -> None:
    targets = pd.DataFrame({"A": [1.0]}, index=small_returns.index[1:2])
    result = VectorizedBacktest().run(small_returns, targets, CostModel(0, 0), 100)
    assert result.ledger.iloc[1]["nav"] == 100  # 10% A gain occurred before purchase
    assert result.ledger.iloc[2]["nav"] == pytest.approx(95)


def test_weights_drift_without_daily_rebalance(small_returns: pd.DataFrame) -> None:
    targets = pd.DataFrame({"A": [0.5], "B": [0.5]}, index=small_returns.index[:1])
    result = VectorizedBacktest().run(small_returns, targets, CostModel(0, 0), 100)
    assert result.weights.iloc[1]["A"] == pytest.approx(0.55)
    assert result.weights.iloc[1]["B"] == pytest.approx(0.45)
    assert result.ledger.iloc[2]["nav"] == pytest.approx(55 * 0.95 + 45 * 1.05)
    assert result.trades.iloc[1:].abs().sum().sum() == 0


def test_liquidation_and_both_sides_are_charged(small_returns: pd.DataFrame) -> None:
    targets = pd.DataFrame({"A": [1.0, 0.0], "B": [0.0, 1.0]}, index=small_returns.index[:2])
    result = VectorizedBacktest().run(small_returns, targets, CostModel(0, 100), 100)
    trade = result.trades.iloc[1]
    assert trade["A"] < 0 < trade["B"]
    assert result.ledger.iloc[1]["cost_usd"] == pytest.approx(trade.abs().sum() * 0.01)
    assert result.ledger.iloc[1]["cash_weight"] == pytest.approx(0, abs=1e-12)


def test_cash_and_missing_unheld_quotes(small_returns: pd.DataFrame) -> None:
    small_returns["B"] = np.nan
    targets = pd.DataFrame({"A": [0.25]}, index=small_returns.index[:1])
    result = VectorizedBacktest().run(small_returns, targets, CostModel(0, 0), 100)
    assert result.ledger.iloc[1]["nav"] == pytest.approx(102.5)
    assert result.ledger.iloc[1]["cash_weight"] == pytest.approx(75 / 102.5)


def test_missing_held_quote_stops(small_returns: pd.DataFrame) -> None:
    small_returns.loc[small_returns.index[2], "A"] = np.nan
    targets = pd.DataFrame({"A": [1.0]}, index=small_returns.index[:1])
    with pytest.raises(DataError, match="held asset"):
        VectorizedBacktest().run(small_returns, targets, CostModel())


def test_missing_buy_quote_stops(small_returns: pd.DataFrame) -> None:
    small_returns.loc[small_returns.index[0], "A"] = np.nan
    with pytest.raises(DataError, match="Cannot execute"):
        VectorizedBacktest().run(
            small_returns, pd.DataFrame({"A": [1.0]}, index=small_returns.index[:1]), CostModel()
        )


@pytest.mark.parametrize("target", [-0.1, 1.1, np.nan, np.inf])
def test_invalid_targets_fail(target: float, small_returns: pd.DataFrame) -> None:
    with pytest.raises(DataError):
        VectorizedBacktest().run(
            small_returns, pd.DataFrame({"A": [target]}, index=small_returns.index[:1]), CostModel()
        )


def scalar_reference(returns: pd.DataFrame, targets: pd.DataFrame, rate: float) -> list[float]:
    """Independent scalar dollar ledger with a piecewise-linear closed-form cost solve."""
    holdings = dict.fromkeys(returns.columns, 0.0)
    cash = 100.0
    values = []
    for day, row in returns.iterrows():
        for asset in holdings:
            holdings[asset] *= 1 + float(row[asset])
        nav = sum(holdings.values()) + cash
        if day in targets.index:
            weights = targets.loc[day].to_dict()
            breaks = sorted(
                {
                    0.0,
                    nav,
                    *[
                        holdings[a] / weights[a]
                        for a in holdings
                        if weights[a] > 0 and 0 < holdings[a] / weights[a] < nav
                    ],
                }
            )
            net = None
            for lower, upper in zip(breaks[:-1], breaks[1:], strict=True):
                middle = (lower + upper) / 2
                signs = {a: (1 if weights[a] * middle >= holdings[a] else -1) for a in holdings}
                candidate = (nav + rate * sum(signs[a] * holdings[a] for a in holdings)) / (
                    1 + rate * sum(signs[a] * weights[a] for a in holdings)
                )
                if lower - 1e-10 <= candidate <= upper + 1e-10:
                    net = candidate
                    break
            assert net is not None
            trades = {a: weights[a] * net - holdings[a] for a in holdings}
            cash -= sum(trades.values()) + rate * sum(abs(v) for v in trades.values())
            for asset in holdings:
                holdings[asset] += trades[asset]
        values.append(sum(holdings.values()) + cash)
    return values


@given(seed=st.integers(0, 10000), bps=st.floats(0, 100, allow_nan=False))
@settings(max_examples=35, deadline=None, derandomize=True)
def test_matches_independent_reference(seed: int, bps: float) -> None:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2024-01-02", periods=12)
    returns = pd.DataFrame(rng.uniform(-0.15, 0.15, (12, 3)), index=days, columns=list("ABC"))
    weights = rng.dirichlet(np.ones(4), 4)[:, :3]
    targets = pd.DataFrame(weights, index=days[::3], columns=returns.columns)
    actual = VectorizedBacktest().run(returns, targets, CostModel(0, bps), 100)
    expected = scalar_reference(returns, targets, bps / 10000)
    np.testing.assert_allclose(actual.ledger["nav"], expected, rtol=1e-12, atol=1e-10)
    assert (actual.ledger["cash_weight"] >= -1e-12).all()


@given(weight=st.floats(0, 1, allow_nan=False), bps=st.floats(0, 100, allow_nan=False))
@settings(max_examples=30, derandomize=True)
def test_self_financing_identity(weight: float, bps: float) -> None:
    before = np.array([25.0, 20.0])
    target = np.array([weight, 1 - weight])
    after, cash, cost, trades = execute_target(before, 100, target, CostModel(0, bps))
    assert math.isclose(float(after.sum()) + cash + cost, 100, abs_tol=1e-10)
    assert cost == pytest.approx(np.abs(trades).sum() * bps / 10000)
    assert cash >= 0


def test_cash_only_and_total_loss(small_returns: pd.DataFrame) -> None:
    cash = VectorizedBacktest().run(
        small_returns, pd.DataFrame(columns=small_returns.columns), CostModel(), 100
    )
    assert cash.ledger["nav"].eq(100).all()
    small_returns.loc[small_returns.index[1], "A"] = -1
    targets = pd.DataFrame({"A": [0.5]}, index=small_returns.index[:1])
    result = VectorizedBacktest().run(small_returns, targets, CostModel(0, 0), 100)
    assert result.ledger.iloc[1]["nav"] == 50
    assert result.weights.iloc[1]["A"] == 0


def test_terminal_cash_settlement_and_no_reentry() -> None:
    days = pd.bdate_range("2024-01-02", periods=4)
    returns = pd.DataFrame({"A": [0.0, 0.2, np.nan, np.nan]}, index=days)
    events = pd.DataFrame({"A": [False, True, False, False]}, index=days)
    targets = pd.DataFrame({"A": [1.0]}, index=days[:1])
    result = VectorizedBacktest().run(returns, targets, CostModel(0, 0), 100, events)
    assert result.ledger.iloc[-1]["nav"] == pytest.approx(120)
    assert result.ledger.iloc[1]["terminal_settlement_usd"] == pytest.approx(120)
    assert result.ledger.iloc[1:]["cash_weight"].eq(1).all()
    reentry = pd.DataFrame({"A": [1.0, 1.0]}, index=days[:2])
    with pytest.raises(DataError, match="terminated"):
        VectorizedBacktest().run(returns, reentry, CostModel(0, 0), 100, events)


def test_zero_turnover_at_unchanged_drifted_target() -> None:
    days = pd.bdate_range("2024-01-02", periods=2)
    returns = pd.DataFrame({"A": [0.0, 0.1], "B": [0.0, -0.1]}, index=days)
    targets = pd.DataFrame({"A": [0.5, 0.55], "B": [0.5, 0.45]}, index=days)
    result = VectorizedBacktest().run(returns, targets, CostModel(0, 0), 100)
    assert result.ledger.iloc[1]["turnover"] == pytest.approx(0.0, abs=1e-14)
