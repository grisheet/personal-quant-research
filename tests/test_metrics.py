import numpy as np
import pandas as pd
import pytest

from pqr.backtesting.engine import VectorizedBacktest
from pqr.evaluation.metrics import (
    concentration,
    linked_contributions,
    performance_metrics,
    rolling_returns,
)
from pqr.evaluation.windows import chronological_years, rolling_folds
from pqr.execution.costs import CostModel


def test_metrics_match_hand_calculation() -> None:
    days = pd.bdate_range("2024-01-02", periods=4)
    returns = pd.DataFrame({"A": [0.0, 0.1, -0.2, 0.05]}, index=days)
    result = VectorizedBacktest().run(
        returns, pd.DataFrame({"A": [1.0]}, index=days[:1]), CostModel(0, 0), 100
    )
    metrics = performance_metrics(result)
    daily = np.array([0.0, 0.1, -0.2, 0.05])
    total = 1.1 * 0.8 * 1.05 - 1
    assert metrics["total_return"] == pytest.approx(total)
    assert metrics["cagr"] == pytest.approx((1 + total) ** (365.25 / 4) - 1)
    assert metrics["max_drawdown"] == pytest.approx(0.2)
    assert metrics["annualized_volatility"] == pytest.approx(np.std(daily, ddof=1) * np.sqrt(252))
    assert metrics["sharpe"] == pytest.approx(daily.mean() / np.std(daily, ddof=1) * np.sqrt(252))
    assert metrics["sortino"] == pytest.approx(daily.mean() / np.sqrt(0.2**2 / 4) * np.sqrt(252))
    assert metrics["hit_rate"] == 0.5
    assert metrics["total_turnover"] == 1
    assert metrics["total_half_turnover"] == 0.5
    assert linked_contributions(result).sum() == pytest.approx(total)
    assert concentration(result.weights)["effective_names"].eq(1).all()


def test_initial_cost_counts_as_drawdown() -> None:
    days = pd.bdate_range("2024-01-02", periods=2)
    result = VectorizedBacktest().run(
        pd.DataFrame({"A": [0.0, 0.0]}, index=days),
        pd.DataFrame({"A": [1.0]}, index=days[:1]),
        CostModel(0, 100),
        100,
    )
    assert performance_metrics(result)["max_drawdown"] == pytest.approx(1 - 1 / 1.01)
    assert linked_contributions(result).sum() == pytest.approx(
        result.ledger.iloc[-1]["nav"] / 100 - 1
    )


def test_undefined_ratios_are_null(small_returns: pd.DataFrame) -> None:
    result = VectorizedBacktest().run(
        small_returns, pd.DataFrame(columns=small_returns.columns), CostModel(), 100
    )
    metrics = performance_metrics(result)
    assert metrics["sharpe"] is None
    assert metrics["sortino"] is None
    assert metrics["calmar"] is None
    assert metrics["max_drawdown"] == 0


def test_rolling_returns_and_yearly_windows() -> None:
    days = pd.bdate_range("2020-01-01", periods=300)
    returns = pd.Series(0.001, index=days)
    rolling = rolling_returns(returns)
    assert rolling["21_session"].iloc[:20].isna().all()
    assert rolling["21_session"].iloc[20] == pytest.approx(1.001**21 - 1)
    annual = chronological_years(returns)
    assert annual["sessions"].sum() == 300


def test_fold_boundaries_and_purging() -> None:
    days = pd.bdate_range("2010-01-01", periods=2000)
    folds = rolling_folds(days, train=756, validation=252, test=252, gap=21)
    assert folds
    for fold in folds:
        assert (
            fold.train_start
            <= fold.train_end
            < fold.validation_start
            <= fold.validation_end
            < fold.test_start
            <= fold.test_end
        )
        assert days.get_loc(fold.validation_start) - days.get_loc(fold.train_end) == 22
    for first, second in zip(folds, folds[1:], strict=False):
        assert first.test_end < second.test_start
    with pytest.raises(ValueError):
        rolling_folds(days, gap=-1)
