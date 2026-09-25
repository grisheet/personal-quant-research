import json
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from pqr.cli import app
from pqr.configs.models import ResearchConfig
from pqr.data.calendar import sessions
from pqr.data.schemas import DataError, Dataset, load_dataset, save_dataset, validate_dataset
from pqr.experiments.registry import output_hashes
from pqr.pipeline import run_research, valuation_returns


def test_split_and_dividend_not_double_counted(fixture_data: Dataset) -> None:
    # Artificial economic path: a 2:1 split preserves wealth, then a $1 distribution.
    days = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
    bars = fixture_data.bars.loc[
        (fixture_data.bars["asset_id"] == "TEST01") & fixture_data.bars["session"].isin(days)
    ].copy()
    bars["close"] = [100.0, 50.0, 50.0]
    bars["tr_close"] = [100.0, 100.0, 102.0]
    bars["cash_dividend"] = [0.0, 0.0, 1.0]
    bars["split_factor"] = [1.0, 2.0, 1.0]
    # valuation_returns uses TR once; raw prices and distributions are not credited again.
    result = valuation_returns(replace(fixture_data, bars=bars), pd.DatetimeIndex(days))
    assert result.loc[days[1], "TEST01"] == 0
    assert result.loc[days[2], "TEST01"] == pytest.approx(0.02)


def test_dataset_roundtrip_and_duplicate_write(tmp_path: Path, fixture_data: Dataset) -> None:
    path = tmp_path / "dataset"
    save_dataset(fixture_data, path)
    actual = load_dataset(path)
    pd.testing.assert_frame_equal(actual.bars, fixture_data.bars)
    with pytest.raises(FileExistsError):
        save_dataset(fixture_data, path)
    assert CliRunner().invoke(app, ["validate", "--dataset", str(path)]).exit_code == 0
    assert (
        CliRunner().invoke(app, ["validate", "--dataset", str(path), "--historical"]).exit_code != 0
    )


def test_end_to_end_and_numeric_reproduction(tmp_path: Path, fixture_data: Dataset) -> None:
    config = ResearchConfig(start="2020-01-02", end="2020-12-31")
    root = Path(__file__).parents[1]
    first = run_research(fixture_data, config, tmp_path / "one", root)
    second = run_research(fixture_data, config, tmp_path / "two", root)
    assert first.manifest["run_id"] == second.manifest["run_id"]
    assert first.metrics == second.metrics
    for name in first.results:
        pd.testing.assert_frame_equal(first.results[name].ledger, second.results[name].ledger)
    for filename in ("strategy_ledger.csv", "features.csv", "metrics.json", "report.html"):
        assert (first.output / filename).read_bytes() == (second.output / filename).read_bytes()
    report = (first.output / "report.html").read_text()
    assert "SYNTHETIC VERIFICATION" in report
    assert "NO MARKET DATA" in report
    assert "<svg" in report and "<script" not in report
    import re

    ids = re.findall(r'id="([^"]+)"', report)
    assert len(ids) == len(set(ids)), "Embedded charts must not share DOM IDs"
    expected = json.loads((first.output / "checksums.json").read_text())
    assert output_hashes(first.output) == expected
    assert CliRunner().invoke(app, ["verify-artifacts", str(first.output)]).exit_code == 0
    (first.output / "metrics.json").write_text("{}")
    assert CliRunner().invoke(app, ["verify-artifacts", str(first.output)]).exit_code != 0
    with pytest.raises(DataError, match="already exists"):
        run_research(fixture_data, config, first.output, root)


def test_cli_help_and_invalid_dates() -> None:
    assert CliRunner().invoke(app, ["--help"]).exit_code == 0
    with pytest.raises(ValueError, match="start must precede"):
        ResearchConfig(start="2025-01-01", end="2024-01-01")
    with pytest.raises(ValueError, match="momentum_skip"):
        ResearchConfig(momentum_skip=252)


def test_nan_volume_and_overlapping_universe_fail(fixture_data: Dataset) -> None:
    bars = fixture_data.bars.copy()
    bars.loc[0, "volume"] = float("nan")
    with pytest.raises(DataError, match="volume"):
        validate_dataset(replace(fixture_data, bars=bars))
    universe = pd.concat([fixture_data.universe, fixture_data.universe.iloc[:1]], ignore_index=True)
    with pytest.raises(DataError, match="Overlapping"):
        validate_dataset(replace(fixture_data, universe=universe))


def test_holiday_not_present_in_evaluation_calendar() -> None:
    assert pd.Timestamp("2024-07-04") not in sessions("2024-07-01", "2024-07-08")


def test_historical_gate_accepts_complete_artificial_evidence_contract(
    fixture_data: Dataset,
) -> None:
    # Tests the schema contract only. This fixture is NOT published as a historical dataset.
    frames = []
    for original in (fixture_data.bars, fixture_data.fundamentals, fixture_data.universe):
        frame = original.copy()
        frame["evidence_uri"] = "fixture://not-a-real-source"
        frame["evidence_sha256"] = "a" * 64
        if "availability_basis" in frame:
            frame["availability_basis"] = "source_archive"
        frames.append(frame)
    metadata = fixture_data.metadata.model_copy(
        update={
            "kind": "point_in_time",
            "membership_history": True,
            "terminal_events_resolved": True,
            "original_vintages": True,
            "total_return_convention": "forward_total_return",
        }
    )
    checked = validate_dataset(Dataset(*frames, metadata), historical=True)
    assert len(checked.bars) == len(fixture_data.bars)
    frames[0]["evidence_sha256"] = "not-a-hash"
    with pytest.raises(DataError, match="SHA-256"):
        validate_dataset(Dataset(*frames, metadata), historical=True)


def test_terminal_event_through_full_pipeline(tmp_path: Path, fixture_data: Dataset) -> None:
    bars = fixture_data.bars.copy()
    day = pd.Timestamp("2020-02-14")
    terminal_mask = bars["asset_id"].eq("TEST01") & bars["session"].eq(day)
    bars.loc[terminal_mask, "terminal"] = True
    after = bars["asset_id"].eq("TEST01") & (bars["session"] > day)
    data = replace(fixture_data, bars=bars.loc[~after])
    config = ResearchConfig(start="2020-01-02", end="2020-03-31", top_fraction=1.0)
    result = run_research(data, config, tmp_path / "terminal", Path(__file__).parents[1])
    ledger = result.results["Strategy"].ledger
    assert ledger.loc[day, "terminal_settlement_usd"] > 0
    assert result.results["Strategy"].weights.loc[day:, "TEST01"].eq(0).all()
