"""Vectorized across assets; sequential across sessions for correct drift/accounting.

A fully vectorized target-weight dot-product would silently rebalance daily.
"""

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd

from pqr.data.schemas import DataError
from pqr.execution.costs import CostModel, execute_target


@dataclass(frozen=True)
class BacktestResult:
    ledger: pd.DataFrame
    weights: pd.DataFrame
    contributions: pd.DataFrame
    trades: pd.DataFrame
    initial_nav: float


class BacktestAdapter(Protocol):
    def run(
        self, returns: pd.DataFrame, targets: pd.DataFrame, costs: CostModel, initial_nav: float
    ) -> BacktestResult: ...


class VectorizedBacktest:
    def run(
        self,
        returns: pd.DataFrame,
        targets: pd.DataFrame,
        costs: CostModel,
        initial_nav: float = 100_000,
        terminal_events: pd.DataFrame | None = None,
    ) -> BacktestResult:
        if (
            returns.empty
            or not returns.index.is_monotonic_increasing
            or returns.index.has_duplicates
        ):
            raise DataError("Returns require a nonempty, unique, increasing session index")
        if not isinstance(returns.index, pd.DatetimeIndex):
            raise DataError("Returns index must contain exchange-session dates")
        if returns.columns.has_duplicates or targets.index.has_duplicates:
            raise DataError("Duplicate assets or target sessions")
        if not targets.index.isin(returns.index).all():
            raise DataError("Execution targets fall outside evaluation sessions")
        if not targets.columns.isin(returns.columns).all():
            raise DataError("Targets contain unknown assets")
        if not np.isfinite(initial_nav) or initial_nav <= 0:
            raise ValueError("Initial NAV must be finite and positive")
        target_frame = targets.reindex(columns=returns.columns, fill_value=0.0).astype(float)
        if not np.isfinite(target_frame.to_numpy()).all():
            raise DataError("Targets contain missing or infinite weights")
        if (target_frame < 0).any().any() or (target_frame.sum(axis=1) > 1 + 1e-12).any():
            raise DataError("Targets must be long-only and unlevered")
        terminal_frame = (
            terminal_events.reindex(index=returns.index, columns=returns.columns, fill_value=False)
            .fillna(False)
            .astype(bool)
            if terminal_events is not None
            else pd.DataFrame(False, index=returns.index, columns=returns.columns)
        )
        terminated = np.zeros(len(returns.columns), dtype=bool)
        holdings = np.zeros(len(returns.columns), dtype=float)
        cash, previous_nav = float(initial_nav), float(initial_nav)
        ledger, weight_rows, contribution_rows, trade_rows = [], [], [], []
        for day_value, row in returns.iterrows():
            day = pd.Timestamp(str(day_value))
            daily = row.to_numpy(dtype=float)
            held = holdings > 1e-10
            if (~np.isfinite(daily[held])).any():
                raise DataError(f"Missing/nonfinite return for held asset at {day}")
            finite = np.isfinite(daily)
            if (daily[finite] < -1).any():
                raise DataError("Simple return cannot be below -100%")
            clean = np.where(finite, daily, 0.0)
            contributions = holdings * clean / previous_nav
            holdings = holdings * (1 + clean)
            terminal_today = terminal_frame.loc[day].to_numpy(dtype=bool)
            if (terminal_today & terminated).any():
                raise DataError("Repeated terminal event")
            settlement = float(holdings[terminal_today].sum())
            cash += settlement
            holdings[terminal_today] = 0.0
            terminated |= terminal_today
            pretrade_nav = float(holdings.sum() + cash)
            if pretrade_nav <= 0:
                raise DataError("Portfolio insolvent; CAGR and continued execution undefined")
            cost = 0.0
            trades = np.zeros(len(holdings))
            if day in target_frame.index:
                target = target_frame.loc[day].to_numpy(dtype=float)
                if (target[terminated] > 0).any():
                    raise DataError("Cannot buy a terminated security")
                needs_quote = (holdings > 1e-10) | (target > 1e-12)
                if not finite[needs_quote].all():
                    raise DataError(f"Cannot execute without a valid mark at {day}")
                holdings, cash, cost, trades = execute_target(holdings, pretrade_nav, target, costs)
            nav = float(holdings.sum() + cash)
            daily_return = nav / previous_nav - 1
            if abs(daily_return - (contributions.sum() - cost / previous_nav)) > 1e-10:
                raise ArithmeticError("Return attribution does not reconcile")
            weight = holdings / nav
            traded = float(np.abs(trades).sum())
            ledger.append(
                {
                    "nav": nav,
                    "return": daily_return,
                    "gross_return": float(contributions.sum()),
                    "cost_usd": cost,
                    "terminal_settlement_usd": settlement,
                    "cost_return": -cost / previous_nav,
                    "traded_notional_usd": traded,
                    "turnover": traded / pretrade_nav,
                    "half_turnover": traded / (2 * pretrade_nav),
                    "gross_exposure": float(np.abs(weight).sum()),
                    "net_exposure": float(weight.sum()),
                    "cash_weight": cash / nav,
                    "rebalance": day in target_frame.index,
                }
            )
            weight_rows.append(weight.copy())
            contribution_rows.append(contributions.copy())
            trade_rows.append(trades.copy())
            previous_nav = nav
        return BacktestResult(
            pd.DataFrame(ledger, index=returns.index),
            pd.DataFrame(weight_rows, index=returns.index, columns=returns.columns),
            pd.DataFrame(contribution_rows, index=returns.index, columns=returns.columns),
            pd.DataFrame(trade_rows, index=returns.index, columns=returns.columns),
            initial_nav,
        )
