"""Chronological folds; no fitted transforms or parameter selection in the example."""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Fold:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def rolling_folds(
    index: pd.DatetimeIndex,
    train: int = 756,
    validation: int = 252,
    test: int = 252,
    gap: int = 0,
) -> list[Fold]:
    if min(train, validation, test) <= 0 or gap < 0:
        raise ValueError("Window lengths must be positive; gap must be nonnegative")
    if index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("Fold index must be ordered and unique")
    folds = []
    offset = 0
    while offset + train + validation + test + 2 * gap <= len(index):
        va = offset + train + gap
        te = va + validation + gap
        folds.append(
            Fold(
                index[offset],
                index[offset + train - 1],
                index[va],
                index[va + validation - 1],
                index[te],
                index[te + test - 1],
            )
        )
        offset += test
    return folds


def chronological_years(returns: pd.Series) -> pd.DataFrame:
    """Continuous predeclared strategy, sliced into sequential yearly evaluation windows."""
    rows = []
    for year, group in returns.groupby(pd.DatetimeIndex(returns.index).year):
        rows.append(
            {
                "year": int(str(year)),
                "start": str(group.index[0].date()),
                "end": str(group.index[-1].date()),
                "sessions": len(group),
                "return": float((1 + group.to_numpy(dtype=float)).prod() - 1),
            }
        )
    return pd.DataFrame(rows)
