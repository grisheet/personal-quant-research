from dataclasses import replace

import pandas as pd
import pytest

from pqr.configs.models import ResearchConfig
from pqr.data.calendar import at_new_york, filing_availability, next_session, sessions
from pqr.data.point_in_time import eligible_bars, eligible_fundamentals, members_at
from pqr.data.schemas import DataError, Dataset, validate_dataset
from pqr.features.core import feature_snapshot, momentum
from pqr.pipeline import build_targets, valuation_returns


def test_restatement_only_enters_after_publication(fixture_data: Dataset) -> None:
    facts = fixture_data.fundamentals.iloc[:1].copy()
    original = facts.iloc[0]["available_at"]
    revised = facts.copy()
    revised["available_at"] = original + pd.Timedelta(days=60)
    revised["net_income"] = 999999
    all_facts = pd.concat([facts, revised], ignore_index=True)
    old = eligible_fundamentals(all_facts, original + pd.Timedelta(days=1), 550)
    new = eligible_fundamentals(all_facts, original + pd.Timedelta(days=61), 550)
    assert old.iloc[0]["net_income"] == facts.iloc[0]["net_income"]
    assert new.iloc[0]["net_income"] == 999999


def test_future_mutation_cannot_change_features_or_targets(fixture_data: Dataset) -> None:
    decision = pd.Timestamp("2022-01-03T14:00:00Z")
    cfg = ResearchConfig()
    before = feature_snapshot(fixture_data, decision, cfg)
    bars = fixture_data.bars.copy()
    facts = fixture_data.fundamentals.copy()
    bars.loc[bars["available_at"] > decision, ["close", "tr_close"]] *= 100
    facts.loc[facts["available_at"] > decision, "net_income"] *= -1000
    mutated = replace(fixture_data, bars=bars, fundamentals=facts)
    pd.testing.assert_frame_equal(before, feature_snapshot(mutated, decision, cfg))
    days = sessions("2021-01-04", "2021-12-31")
    assets = pd.Index(sorted(bars["asset_id"].unique()))
    original_targets = build_targets(fixture_data, cfg, days, assets)[0]
    changed_targets = build_targets(mutated, cfg, days, assets)[0]
    pd.testing.assert_frame_equal(original_targets, changed_targets)


def test_later_price_revision_cannot_rewrite_valuation(fixture_data: Dataset) -> None:
    dates = sessions("2020-01-02", "2020-02-28")
    original = valuation_returns(fixture_data, dates)
    revision = fixture_data.bars.loc[
        fixture_data.bars["session"].between(dates[0], dates[-1])
    ].copy()
    revision["available_at"] = pd.Timestamp("2026-01-01T00:00:00Z")
    revision["tr_close"] *= 7
    mutated = replace(
        fixture_data, bars=pd.concat([fixture_data.bars, revision], ignore_index=True)
    )
    pd.testing.assert_frame_equal(original, valuation_returns(mutated, dates))


def test_future_membership_not_available_early(fixture_data: Dataset) -> None:
    universe = fixture_data.universe.iloc[:1].copy()
    universe["member_from"] = pd.Timestamp("2020-01-01")
    universe["available_at"] = pd.Timestamp("2020-02-01T00:00:00Z")
    assert members_at(universe, pd.Timestamp("2020-01-15T14:00:00Z")).empty
    assert len(members_at(universe, pd.Timestamp("2020-02-03T14:00:00Z"))) == 1
    universe["member_to"] = pd.Timestamp("2020-02-03")
    assert members_at(universe, pd.Timestamp("2020-02-03T14:00:00Z")).empty


def test_missing_session_does_not_shorten_lookback(fixture_data: Dataset) -> None:
    decision = pd.Timestamp("2021-01-04T14:00:00Z")
    bars = fixture_data.bars.copy()
    mask = bars["asset_id"].eq("TEST01") & bars["session"].eq(pd.Timestamp("2020-12-31"))
    result = feature_snapshot(
        replace(fixture_data, bars=bars.loc[~mask]), decision, ResearchConfig()
    )
    row = result.set_index("asset_id").loc["TEST01"]
    assert not row["eligible"]
    assert row["exclusion_reason"] == "insufficient_or_missing_price_history"


def test_momentum_off_by_one() -> None:
    history = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0])
    assert momentum(history, lookback=5, skip=1) == pytest.approx(14 / 10 - 1)
    assert pd.isna(momentum(history.iloc[1:], lookback=5, skip=1))


def test_calendar_holidays_dst_and_filing_lag() -> None:
    assert next_session(pd.Timestamp("2024-07-03")) == pd.Timestamp("2024-07-05")
    assert next_session(pd.Timestamp("2024-07-06")) == pd.Timestamp("2024-07-08")
    assert at_new_york(pd.Timestamp("2024-03-08"), 9).hour == 14
    assert at_new_york(pd.Timestamp("2024-03-11"), 9).hour == 13
    assert filing_availability(pd.Timestamp("2024-07-03T20:30:00Z")) == pd.Timestamp(
        "2024-07-08T13:00:00Z"
    )
    with pytest.raises(ValueError, match="timezone"):
        filing_availability(pd.Timestamp("2024-07-03"))


def test_historical_gate_rejects_retrospective(fixture_data: Dataset) -> None:
    with pytest.raises(DataError, match="Historical mode"):
        validate_dataset(fixture_data, historical=True)
    claimed = fixture_data.metadata.model_copy(
        update={
            "kind": "point_in_time",
            "membership_history": True,
            "terminal_events_resolved": True,
            "original_vintages": True,
            "total_return_convention": "forward_total_return",
        }
    )
    with pytest.raises(DataError, match="assumed availability"):
        validate_dataset(replace(fixture_data, metadata=claimed), historical=True)


def test_timezone_naive_and_duplicate_vintage_rejected(fixture_data: Dataset) -> None:
    bars = fixture_data.bars.iloc[:1].copy()
    bars["available_at"] = pd.Timestamp("2020-01-01")
    with pytest.raises(DataError, match="timezone-naive"):
        validate_dataset(replace(fixture_data, bars=bars))
    duplicate = pd.concat([fixture_data.bars, fixture_data.bars.iloc[:1]], ignore_index=True)
    with pytest.raises(DataError, match="duplicate bar"):
        validate_dataset(replace(fixture_data, bars=duplicate))


def test_asof_rejects_naive_decision(fixture_data: Dataset) -> None:
    with pytest.raises(DataError, match="timezone-aware"):
        eligible_bars(fixture_data.bars, pd.Timestamp("2020-01-01"))


def test_future_revision_does_not_resurrect_stale_facts(fixture_data: Dataset) -> None:
    facts = fixture_data.fundamentals.iloc[:1]
    old_period = facts.iloc[0]["period_end"]
    decision = (old_period + pd.Timedelta(days=1000)).tz_localize("UTC")
    assert eligible_fundamentals(facts, decision, 550).empty


def test_future_membership_removal_does_not_rewrite_past(fixture_data: Dataset) -> None:
    original = fixture_data.universe.iloc[:1].copy()
    revised = original.copy()
    revised["member_to"] = pd.Timestamp("2022-06-01")
    revised["available_at"] = pd.Timestamp("2022-05-15T12:00:00Z")
    universe = pd.DataFrame(original.to_dict("records") + revised.to_dict("records"))
    universe["member_to"] = pd.to_datetime(universe["member_to"])
    validated = validate_dataset(replace(fixture_data, universe=universe))
    earlier = members_at(validated.universe, pd.Timestamp("2021-01-04T14:00:00Z"))
    assert len(earlier) == 1 and pd.isna(earlier.iloc[0]["member_to"])
    assert members_at(validated.universe, pd.Timestamp("2022-06-01T13:00:00Z")).empty
