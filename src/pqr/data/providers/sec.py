"""Conservative annual US-GAAP quality extraction with filing-level provenance.

Custom tags, fiscal-period ambiguity and missing beginning assets are omitted,
with a machine-readable exclusion log. CIK is issuer identity, not security identity.
"""

from typing import Any

import pandas as pd

from pqr.data.calendar import filing_availability
from pqr.data.providers.http import SnapshotClient
from pqr.data.schemas import DataError


class SecFundamentalsProvider:
    def __init__(self, user_agent: str, snapshots: SnapshotClient) -> None:
        if "@" not in user_agent:
            raise DataError("PQR_SEC_USER_AGENT must identify you and include a contact email")
        self.headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
        self.snapshots = snapshots
        self.exclusions: list[dict[str, str]] = []

    def _get(self, url: str) -> tuple[Any, Any]:
        return self.snapshots.get_json(
            url,
            headers=self.headers,
            license_note="SEC public EDGAR; retain attribution and provenance",
        )

    def fetch(self, cik: str, asset_id: str) -> pd.DataFrame:
        if not cik.isdigit() or len(cik) > 10:
            raise DataError("CIK must be at most ten digits")
        identity = cik.zfill(10)
        submissions, _ = self._get(f"https://data.sec.gov/submissions/CIK{identity}.json")
        batches = [pd.DataFrame(submissions["filings"]["recent"])]
        for entry in submissions["filings"].get("files", []):
            older, _ = self._get(f"https://data.sec.gov/submissions/{entry['name']}")
            batches.append(pd.DataFrame(older))
        filing_rows = pd.concat(batches, ignore_index=True)
        if filing_rows["accessionNumber"].duplicated().any():
            filing_rows = filing_rows.drop_duplicates("accessionNumber", keep="first")
        facts, retrieved = self._get(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{identity}.json"
        )
        return extract_annual_quality(
            facts, filing_rows, asset_id, pd.Timestamp(retrieved), self.exclusions
        )


def extract_annual_quality(
    payload: dict[str, Any],
    filings: pd.DataFrame,
    asset_id: str,
    retrieved_at: pd.Timestamp,
    exclusions: list[dict[str, str]],
) -> pd.DataFrame:
    gaap = payload.get("facts", {}).get("us-gaap", {})
    incomes = pd.DataFrame(gaap.get("NetIncomeLoss", {}).get("units", {}).get("USD", []))
    assets = pd.DataFrame(gaap.get("Assets", {}).get("units", {}).get("USD", []))
    columns = [
        "asset_id",
        "period_end",
        "available_at",
        "retrieved_at",
        "accession",
        "net_income",
        "assets_begin",
        "assets_end",
        "availability_basis",
    ]
    if incomes.empty or assets.empty:
        exclusions.append({"asset_id": asset_id, "reason": "missing standard USD tags"})
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for _, filing in filings.loc[filings["form"].isin(["10-K", "10-K/A"])].iterrows():
        accession = str(filing["accessionNumber"])
        accepted = filing.get("acceptanceDateTime")
        if not accepted or pd.isna(accepted):
            exclusions.append({"asset_id": asset_id, "reason": f"{accession}: missing acceptance"})
            continue
        accepted_time = pd.Timestamp(accepted)
        if accepted_time.tzinfo is None:
            raise DataError("SEC acceptance timestamp lacks explicit timezone")
        eligible_income = incomes.loc[incomes["accn"].eq(accession)].copy()
        if eligible_income.empty:
            continue
        durations = (
            pd.to_datetime(eligible_income["end"]) - pd.to_datetime(eligible_income["start"])
        ).dt.days
        eligible_income = eligible_income.loc[durations.between(330, 380)]
        if eligible_income.empty:
            continue
        latest_end = eligible_income["end"].max()
        current = eligible_income.loc[eligible_income["end"].eq(latest_end)].drop_duplicates(
            ["start", "end", "val"]
        )
        if len(current) != 1:
            exclusions.append(
                {"asset_id": asset_id, "reason": f"{accession}: ambiguous annual income"}
            )
            continue
        fact = current.iloc[0]
        start, end = pd.Timestamp(fact["start"]), pd.Timestamp(fact["end"])
        same_filing = assets.loc[assets["accn"].eq(accession)]
        begin = same_filing.loc[
            pd.to_datetime(same_filing["end"]).eq(start - pd.Timedelta(days=1)), "val"
        ].unique()
        finish = same_filing.loc[pd.to_datetime(same_filing["end"]).eq(end), "val"].unique()
        if len(begin) != 1 or len(finish) != 1 or begin[0] <= 0 or finish[0] <= 0:
            exclusions.append(
                {"asset_id": asset_id, "reason": f"{accession}: missing/ambiguous assets"}
            )
            continue
        rows.append(
            {
                "asset_id": asset_id,
                "period_end": end,
                "available_at": filing_availability(accepted_time),
                "retrieved_at": retrieved_at,
                "accession": accession,
                "net_income": float(fact["val"]),
                "assets_begin": float(begin[0]),
                "assets_end": float(finish[0]),
                "availability_basis": "assumed",
            }
        )
    return pd.DataFrame(rows, columns=columns)
