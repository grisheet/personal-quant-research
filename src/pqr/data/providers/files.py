"""Explicit local data import; identifiers come from the user's dated mapping."""

from datetime import date
from pathlib import Path

import pandas as pd


class FilePriceProvider:
    def __init__(self, path: Path) -> None:
        self.path = path

    def fetch(self, symbol: str, asset_id: str, start: date, end: date) -> pd.DataFrame:
        frame = (
            pd.read_parquet(self.path) if self.path.suffix == ".parquet" else pd.read_csv(self.path)
        )
        days = pd.to_datetime(frame["session"])
        return frame.loc[
            (frame["asset_id"] == asset_id)
            & (days >= pd.Timestamp(start))
            & (days <= pd.Timestamp(end))
        ].copy()


class FileUniverseProvider:
    def __init__(self, path: Path) -> None:
        self.path = path

    def fetch(self) -> pd.DataFrame:
        return pd.read_csv(self.path)
