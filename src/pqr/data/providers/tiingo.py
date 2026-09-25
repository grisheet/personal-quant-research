"""Tiingo EOD adapter; today's backfilled history is explicitly retrospective."""

from datetime import date
from urllib.parse import quote

import pandas as pd

from pqr.data.calendar import bar_availability
from pqr.data.providers.http import SnapshotClient
from pqr.data.schemas import DataError


class TiingoPriceProvider:
    def __init__(self, token: str, snapshots: SnapshotClient) -> None:
        if not token:
            raise DataError("Set PQR_TIINGO_TOKEN in .env; never put it in a command argument")
        self.token = token
        self.snapshots = snapshots

    def fetch(self, symbol: str, asset_id: str, start: date, end: date) -> pd.DataFrame:
        url = f"https://api.tiingo.com/tiingo/daily/{quote(symbol, safe='')}/prices"
        payload, retrieved = self.snapshots.get_json(
            url,
            headers={"Authorization": f"Token {self.token}"},
            params={
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "resampleFreq": "daily",
            },
            license_note="Tiingo account terms; redistribution not granted by this software",
        )
        if not isinstance(payload, list) or not payload:
            raise DataError("Tiingo returned no observations; check entitlement and symbol")
        source = pd.DataFrame(payload)
        required = {"date", "close", "volume", "adjClose", "splitFactor", "divCash"}
        if not required.issubset(source.columns):
            raise DataError(
                f"Tiingo response missing fields: {sorted(required - set(source.columns))}"
            )
        source["session"] = (
            pd.to_datetime(source["date"], utc=True).dt.tz_localize(None).dt.normalize()
        )
        result = pd.DataFrame(
            {
                "asset_id": asset_id,
                "session": source["session"],
                "close": source["close"],
                "volume": source["volume"],
                "tr_close": source["adjClose"],
                "split_factor": source["splitFactor"],
                "cash_dividend": source["divCash"],
                "retrieved_at": pd.Timestamp(retrieved),
                "availability_basis": "assumed",
            }
        )
        result["available_at"] = result["session"].map(bar_availability)
        return result
