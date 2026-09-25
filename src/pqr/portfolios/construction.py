"""Portfolio targets are post-cost NAV fractions, with residual cash."""

import math
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class StrategySpec:
    name: str
    top_fraction: float
    max_weight: float
    rebalance: str = "monthly"
    execution: str = "next_session_close"


def select_weights(ranks: pd.DataFrame, spec: StrategySpec) -> pd.Series:
    if ranks.empty:
        return pd.Series(dtype=float)
    count = max(1, math.ceil(len(ranks) * spec.top_fraction))
    selected = ranks.head(count)["asset_id"]
    weight = min(1 / count, spec.max_weight)
    return pd.Series(weight, index=selected.to_list(), dtype=float)


def equal_weights(ranks: pd.DataFrame, max_weight: float = 1.0) -> pd.Series:
    if ranks.empty:
        return pd.Series(dtype=float)
    return pd.Series(min(1 / len(ranks), max_weight), index=ranks["asset_id"].to_list())
