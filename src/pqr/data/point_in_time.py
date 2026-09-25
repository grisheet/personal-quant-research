"""As-of selection: publication eligibility precedes period/vintage selection."""

import duckdb
import pandas as pd

from pqr.data.schemas import DataError


def eligible_bars(bars: pd.DataFrame, decision_at: pd.Timestamp) -> pd.DataFrame:
    if decision_at.tzinfo is None:
        raise DataError("decision_at must be timezone-aware")
    eligible = bars.loc[bars["available_at"] <= decision_at]
    return eligible.sort_values(["session", "available_at"]).drop_duplicates(
        ["asset_id", "session"], keep="last"
    )


def eligible_fundamentals(
    fundamentals: pd.DataFrame, decision_at: pd.Timestamp, max_age_days: int
) -> pd.DataFrame:
    """DuckDB as-of filter followed by latest eligible period and revision per asset."""
    if decision_at.tzinfo is None:
        raise DataError("decision_at must be timezone-aware")
    cutoff = decision_at.tz_convert("America/New_York").normalize().tz_localize(None)
    oldest = cutoff - pd.Timedelta(days=max_age_days)
    with duckdb.connect(":memory:") as con:
        con.register("facts", fundamentals)
        return con.execute(
            """
            SELECT * FROM facts
            WHERE available_at <= ? AND period_end >= ? AND period_end <= ?
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY asset_id ORDER BY period_end DESC, available_at DESC
            ) = 1
            ORDER BY asset_id
        """,
            [decision_at.to_pydatetime(), oldest.to_pydatetime(), cutoff.to_pydatetime()],
        ).df()


def members_at(universe: pd.DataFrame, decision_at: pd.Timestamp) -> pd.DataFrame:
    if decision_at.tzinfo is None:
        raise DataError("decision_at must be timezone-aware")
    day = decision_at.tz_convert("America/New_York").normalize().tz_localize(None)
    known = (
        universe.loc[universe["available_at"] <= decision_at]
        .sort_values("available_at")
        .drop_duplicates(["asset_id", "member_from"], keep="last")
    )
    eligible = known.loc[
        (known["member_from"] <= day) & (known["member_to"].isna() | (known["member_to"] > day))
    ]
    if eligible["asset_id"].duplicated().any():
        raise DataError("Multiple active memberships")
    return eligible.sort_values("asset_id")
