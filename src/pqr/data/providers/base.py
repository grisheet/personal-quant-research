"""Provider contracts return canonical data or immutable source payloads."""

from datetime import date
from typing import Protocol

import pandas as pd


class PriceProvider(Protocol):
    def fetch(self, symbol: str, asset_id: str, start: date, end: date) -> pd.DataFrame: ...


class FundamentalsProvider(Protocol):
    def fetch(self, cik: str, asset_id: str) -> pd.DataFrame: ...


class UniverseProvider(Protocol):
    def fetch(self) -> pd.DataFrame: ...
