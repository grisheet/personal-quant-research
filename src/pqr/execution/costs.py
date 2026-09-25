"""Self-financing target execution including proportional trading costs."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class CostModel:
    commission_bps: float = 1.0
    slippage_bps: float = 5.0

    def __post_init__(self) -> None:
        if not all(np.isfinite([self.commission_bps, self.slippage_bps])):
            raise ValueError("Costs must be finite")
        if min(self.commission_bps, self.slippage_bps) < 0 or self.rate >= 1:
            raise ValueError("Cost rate must be in [0, 1)")

    @property
    def rate(self) -> float:
        return (self.commission_bps + self.slippage_bps) / 10_000


def execute_target(
    holdings: NDArray[np.float64],
    nav: float,
    weights: NDArray[np.float64],
    model: CostModel,
) -> tuple[NDArray[np.float64], float, float, NDArray[np.float64]]:
    if nav <= 0 or not np.isfinite(nav):
        raise ValueError("NAV must be positive and finite")
    if not np.isfinite(weights).all() or (weights < 0).any() or weights.sum() > 1 + 1e-12:
        raise ValueError("Targets must be finite, long-only and unlevered")
    # Solve N_after + rate * sum(abs(w*N_after - h_before)) = N_before.
    # Strictly increasing for rate < 1 and sum(weights) <= 1.
    low, high = 0.0, nav
    for _ in range(70):
        midpoint = (low + high) / 2
        value = midpoint + model.rate * np.abs(weights * midpoint - holdings).sum()
        if value > nav:
            high = midpoint
        else:
            low = midpoint
    post_nav = (low + high) / 2
    next_holdings = weights * post_nav
    trades = next_holdings - holdings
    cost = float(np.abs(trades).sum() * model.rate)
    cash = float(nav - cost - next_holdings.sum())
    if cash < -1e-8:
        raise ArithmeticError("Execution created borrowing")
    return next_holdings, max(0.0, cash), cost, trades
