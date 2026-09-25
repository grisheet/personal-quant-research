"""Canonical dataset validation. Revisions coexist; ambiguous duplicates fail."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict

from pqr.data.calendar import sessions


class DataError(ValueError):
    """An input cannot support the requested research claim."""


class DatasetMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["synthetic_fixture", "retrospective", "point_in_time"]
    description: str
    membership_history: bool = False
    terminal_events_resolved: bool = False
    original_vintages: bool = False
    license: str
    source: str
    retrieved_at: str
    benchmark_id: str = "SPY"
    total_return_convention: Literal["vendor_adjusted", "forward_total_return", "synthetic"] = (
        "vendor_adjusted"
    )


@dataclass(frozen=True)
class Dataset:
    bars: pd.DataFrame
    fundamentals: pd.DataFrame
    universe: pd.DataFrame
    metadata: DatasetMetadata


def require_columns(frame: pd.DataFrame, columns: set[str], name: str) -> None:
    missing = columns - set(frame.columns)
    if missing:
        raise DataError(f"{name}: missing columns {sorted(missing)}")


def utc_column(series: pd.Series, name: str) -> pd.Series:
    # utc=True alone would silently accept naive timestamps as UTC.
    for value in series.dropna():
        if pd.Timestamp(value).tzinfo is None:
            raise DataError(f"{name}: timezone-naive timestamp")
    return pd.to_datetime(series, utc=True).astype("datetime64[ns, UTC]")


def validate_dataset(dataset: Dataset, *, historical: bool = False) -> Dataset:
    bars, facts, universe = (
        x.copy() for x in (dataset.bars, dataset.fundamentals, dataset.universe)
    )
    require_columns(
        bars,
        {
            "asset_id",
            "session",
            "close",
            "volume",
            "tr_close",
            "available_at",
            "retrieved_at",
            "availability_basis",
        },
        "bars",
    )
    require_columns(
        facts,
        {
            "asset_id",
            "period_end",
            "available_at",
            "retrieved_at",
            "accession",
            "net_income",
            "assets_begin",
            "assets_end",
            "availability_basis",
        },
        "fundamentals",
    )
    require_columns(
        universe, {"asset_id", "member_from", "member_to", "available_at", "industry"}, "universe"
    )
    for name, frame in [("bars", bars), ("fundamentals", facts), ("universe", universe)]:
        if frame.empty:
            raise DataError(f"{name}: empty dataset")
        if frame["asset_id"].isna().any() or (frame["asset_id"].astype(str).str.len() == 0).any():
            raise DataError(f"{name}: missing asset identity")
        frame["asset_id"] = frame["asset_id"].astype(str)
        frame["available_at"] = utc_column(frame["available_at"], name)
        if frame["available_at"].isna().any():
            raise DataError(f"{name}: missing availability")
    bars["session"] = pd.to_datetime(bars["session"]).dt.normalize()
    if bars["session"].dt.tz is not None:
        raise DataError("session must be a timezone-free exchange-session date")
    if bars["session"].isna().any():
        raise DataError("Missing session date")
    calendar_days = sessions(str(bars["session"].min().date()), str(bars["session"].max().date()))
    if not bars["session"].isin(calendar_days).all():
        raise DataError("Bar outside the XNYS session calendar")
    facts["period_end"] = pd.to_datetime(facts["period_end"]).dt.normalize()
    if facts["period_end"].isna().any() or facts["period_end"].dt.tz is not None:
        raise DataError("Reporting periods must be nonmissing timezone-free dates")
    if facts["accession"].isna().any():
        raise DataError("Missing filing accession")
    for frame in (bars, facts):
        frame["retrieved_at"] = utc_column(frame["retrieved_at"], "retrieved_at")
        if frame["retrieved_at"].isna().any():
            raise DataError("Missing retrieval timestamp")
        if (
            not frame["availability_basis"]
            .isin(["observed", "source_archive", "assumed", "fixture"])
            .all()
        ):
            raise DataError("Unknown availability evidence")
        observed = frame["availability_basis"].eq("observed")
        if (frame.loc[observed, "available_at"] < frame.loc[observed, "retrieved_at"]).any():
            raise DataError("Observed availability cannot precede retrieval")
    if bars.duplicated(["asset_id", "session", "available_at"]).any():
        raise DataError("Ambiguous duplicate bar vintage")
    if facts.duplicated(["asset_id", "period_end", "available_at"]).any():
        raise DataError("Ambiguous duplicate fundamental vintage")
    for col in ("close", "tr_close", "volume"):
        values = pd.to_numeric(bars[col], errors="raise")
        if not np.isfinite(values).all() or (values < 0).any():
            raise DataError(f"Invalid {col}")
        bars[col] = values.astype(float)
    if "terminal" not in bars:
        bars["terminal"] = False
    if not bars["terminal"].isin([True, False]).all():
        raise DataError("terminal must be a boolean")
    bars["terminal"] = bars["terminal"].astype(bool)
    if ((bars[["close", "tr_close"]] <= 0).any(axis=1) & ~bars["terminal"]).any():
        raise DataError("Zero prices require an explicit terminal event")
    for asset, group in bars.groupby("asset_id"):
        events = group.loc[group["terminal"], "session"].unique()
        if len(events) > 1 or (len(events) and (group["session"] > events[0]).any()):
            raise DataError(f"Observations after terminal settlement: {asset}")
    if "split_factor" in bars:
        if not np.isfinite(bars["split_factor"]).all() or (bars["split_factor"] <= 0).any():
            raise DataError("Split factors must be finite and positive")
    if (bars["available_at"] < bars["session"].dt.tz_localize("UTC")).any():
        raise DataError("Bar available before its session")
    if (facts["available_at"] < facts["period_end"].dt.tz_localize("UTC")).any():
        raise DataError("Fundamental available before its reporting period ended")
    for col in ("net_income", "assets_begin", "assets_end"):
        facts[col] = pd.to_numeric(facts[col], errors="raise")
        if not np.isfinite(facts[col]).all():
            raise DataError(f"Nonfinite fundamental: {col}")
    for col in ("member_from", "member_to"):
        universe[col] = pd.to_datetime(universe[col])
    universe["industry"] = universe["industry"].fillna("Unknown")
    if universe["member_from"].isna().any():
        raise DataError("Missing membership start")
    if (universe["member_to"] <= universe["member_from"]).any():
        raise DataError("Membership intervals must be nonempty and half-open")
    if universe.duplicated(["asset_id", "member_from", "available_at"]).any():
        raise DataError("Overlapping or duplicate membership vintages")
    latest_membership = universe.sort_values("available_at").drop_duplicates(
        ["asset_id", "member_from"], keep="last"
    )
    for _, group in latest_membership.groupby("asset_id"):
        ordered = group.sort_values("member_from")
        ends = ordered["member_to"].fillna(pd.Timestamp.max)
        if (
            len(ordered) > 1
            and (ordered["member_from"].iloc[1:].to_numpy() < ends.iloc[:-1].to_numpy()).any()
        ):
            raise DataError("Overlapping membership intervals")
    if dataset.metadata.benchmark_id not in set(bars["asset_id"]):
        raise DataError("Benchmark is absent")
    if historical:
        meta = dataset.metadata
        if meta.kind != "point_in_time" or not all(
            (meta.membership_history, meta.terminal_events_resolved, meta.original_vintages)
        ):
            raise DataError(
                "Historical mode requires evidenced vintages, membership and terminal events"
            )
        if meta.total_return_convention != "forward_total_return":
            raise DataError(
                "Historical mode requires a forward-built consistent total-return index"
            )
        for frame in (bars, facts):
            if frame["availability_basis"].isin(["assumed", "fixture"]).any():
                raise DataError("Historical mode rejects assumed availability")
            require_columns(frame, {"evidence_uri", "evidence_sha256"}, "historical provenance")
            if (
                frame["evidence_uri"].isna().any()
                or not frame["evidence_sha256"].astype(str).str.fullmatch(r"[a-f0-9]{64}").all()
            ):
                raise DataError("Historical records require source evidence and SHA-256")
        require_columns(universe, {"evidence_uri", "evidence_sha256"}, "historical universe")
        if (
            universe["evidence_uri"].isna().any()
            or not universe["evidence_sha256"].astype(str).str.fullmatch(r"[a-f0-9]{64}").all()
        ):
            raise DataError("Historical membership requires source evidence and SHA-256")
    return Dataset(bars, facts, universe, dataset.metadata)


def load_dataset(path: Path, *, historical: bool = False) -> Dataset:
    def read(name: str) -> pd.DataFrame:
        parquet = path / f"{name}.parquet"
        return pd.read_parquet(parquet) if parquet.exists() else pd.read_csv(path / f"{name}.csv")

    data = Dataset(
        read("bars"),
        read("fundamentals"),
        read("universe"),
        DatasetMetadata.model_validate_json((path / "metadata.json").read_text()),
    )
    return validate_dataset(data, historical=historical)


def save_dataset(dataset: Dataset, path: Path) -> None:
    checked = validate_dataset(dataset)
    path.mkdir(parents=True, exist_ok=False)
    for name in ("bars", "fundamentals", "universe"):
        getattr(checked, name).to_parquet(path / f"{name}.parquet", index=False)
    (path / "metadata.json").write_text(json.dumps(checked.metadata.model_dump(), indent=2) + "\n")
