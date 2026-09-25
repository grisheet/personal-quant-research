"""Explicit decimal daily return metrics and exact wealth-linked contributions."""

from typing import Any

import numpy as np
import pandas as pd

from pqr.backtesting.engine import BacktestResult


def performance_metrics(result: BacktestResult, periods: int = 252) -> dict[str, Any]:
    ledger = result.ledger
    returns = ledger["return"]
    n = len(returns)
    wealth = ledger["nav"] / result.initial_nav
    # Initial capital is a peak; entry costs therefore count as drawdown.
    peak = wealth.cummax().clip(lower=1.0)
    drawdowns = wealth / peak - 1
    max_dd = float(-drawdowns.min())
    # Include first session's exposure interval by using previous calendar day at inception.
    elapsed_days = int((ledger.index[-1] - ledger.index[0]).days) + 1
    years = elapsed_days / 365.25
    cagr = float(wealth.iloc[-1] ** (1 / years) - 1) if n > 1 else None
    sigma = float(returns.std(ddof=1)) if n > 1 else 0.0
    downside = float(np.sqrt(np.mean(np.minimum(returns.to_numpy(), 0) ** 2)))
    sharpe = float(np.sqrt(periods) * returns.mean() / sigma) if sigma > 1e-15 else None
    sortino = float(np.sqrt(periods) * returns.mean() / downside) if downside > 1e-15 else None
    return {
        "sessions": n,
        "total_return": float(wealth.iloc[-1] - 1),
        "cagr": cagr,
        "annualized_volatility": sigma * np.sqrt(periods),
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "calmar": cagr / max_dd if cagr is not None and max_dd > 1e-15 else None,
        "total_turnover": float(ledger["turnover"].sum()),
        "annualized_turnover": float(ledger["turnover"].sum() / (n / periods)),
        "total_half_turnover": float(ledger["half_turnover"].sum()),
        "mean_gross_exposure": float(ledger["gross_exposure"].mean()),
        "mean_net_exposure": float(ledger["net_exposure"].mean()),
        "hit_rate": float((returns > 0).mean()),
        "cost_usd": float(ledger["cost_usd"].sum()),
    }


def rolling_returns(returns: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(
        {
            f"{window}_session": (1 + returns)
            .rolling(window, min_periods=window)
            .apply(np.prod, raw=True)
            - 1
            for window in (21, 63, 252)
        }
    )


def linked_contributions(result: BacktestResult) -> pd.Series:
    """Sum c[i,t] * V[t-1]/V[0], including costs, exactly equals total return."""
    lagged_wealth = (
        result.ledger["nav"].shift(1, fill_value=result.initial_nav) / result.initial_nav
    )
    values = result.contributions.mul(lagged_wealth, axis=0).sum()
    values.loc["TRANSACTION_COSTS"] = float((result.ledger["cost_return"] * lagged_wealth).sum())
    values.loc["CASH"] = 0.0
    total_return = result.ledger["nav"].iloc[-1] / result.initial_nav - 1
    if not np.isclose(values.sum(), total_return, atol=1e-10):
        raise ArithmeticError("Linked contributions do not reconcile")
    return values.sort_values(ascending=False)


def concentration(weights: pd.DataFrame) -> pd.DataFrame:
    exposure = weights.sum(axis=1)
    normalized = weights.div(exposure.replace(0, np.nan), axis=0)
    hhi = normalized.pow(2).sum(axis=1).where(exposure > 0)
    return pd.DataFrame(
        {
            "largest_name": weights.max(axis=1),
            "hhi_invested": hhi,
            "effective_names": 1 / hhi,
            "invested_fraction": exposure,
        }
    )
