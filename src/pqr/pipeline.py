"""Reproducible orchestration from dataset to audited research artifacts."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

from pqr.backtesting.engine import BacktestResult, VectorizedBacktest
from pqr.configs.models import ResearchConfig
from pqr.data.calendar import at_new_york, monthly_execution_sessions, sessions
from pqr.data.point_in_time import members_at
from pqr.data.schemas import DataError, Dataset, validate_dataset
from pqr.evaluation.metrics import (
    concentration,
    linked_contributions,
    performance_metrics,
    rolling_returns,
)
from pqr.evaluation.windows import chronological_years, rolling_folds
from pqr.execution.costs import CostModel
from pqr.experiments.registry import make_manifest, output_hashes, write_json
from pqr.features.core import feature_snapshot
from pqr.portfolios.construction import StrategySpec, equal_weights, select_weights
from pqr.signals.ranking import ranked_signals

log = structlog.get_logger()


@dataclass(frozen=True)
class ResearchRun:
    results: dict[str, BacktestResult]
    metrics: dict[str, dict[str, Any]]
    features: pd.DataFrame
    target_exposures: pd.DataFrame
    sensitivity: pd.DataFrame
    yearly: pd.DataFrame
    manifest: dict[str, Any]
    output: Path


def valuation_returns(data: Dataset, evaluation: pd.DatetimeIndex) -> pd.DataFrame:
    """Freeze each session's mark at next-session 08:00; later revisions cannot rewrite it.

    Retrospective adjusted bars remain retrospectively adjusted. This cutoff is a
    correction-window policy, not proof that an API backfill is an original vintage.
    """
    start = pd.Timestamp(data.bars["session"].min())
    all_days = sessions(str(start.date()), str((evaluation[-1] + pd.Timedelta(days=14)).date()))
    deadlines = {day: at_new_york(all_days[i + 1], 8) for i, day in enumerate(all_days[:-1])}
    bars = data.bars.copy()
    bars["deadline"] = bars["session"].map(deadlines)
    bars = bars.loc[bars["available_at"] <= bars["deadline"]]
    bars = bars.sort_values("available_at").drop_duplicates(["session", "asset_id"], keep="last")
    marks = bars.pivot(index="session", columns="asset_id", values="tr_close").reindex(all_days)
    returns = marks.pct_change(fill_method=None)
    # Starting with cash requires an execution mark, not a fictitious prior-day return.
    if len(marks):
        returns.loc[all_days[0]] = np.where(marks.loc[all_days[0]].notna(), 0.0, np.nan)
    return returns.reindex(evaluation)


def build_targets(
    data: Dataset,
    config: ResearchConfig,
    dates: pd.DatetimeIndex,
    columns: pd.Index,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    spec = StrategySpec(config.name, config.top_fraction, config.max_weight)
    strategy, baseline, features, exposure_rows = [], [], [], []
    days = monthly_execution_sessions(dates)
    for day in days:
        decision = at_new_york(day, 9)
        snapshot = feature_snapshot(data, decision, config)
        ranks = ranked_signals(snapshot)
        weights = select_weights(ranks, spec).reindex(columns, fill_value=0.0)
        equal = equal_weights(ranks, config.max_weight).reindex(columns, fill_value=0.0)
        strategy.append(weights)
        baseline.append(equal)
        if not snapshot.empty:
            snapshot["execution_session"] = day
            features.append(snapshot)
        if not ranks.empty:
            ranked = ranks.set_index("asset_id")
            aligned = weights.reindex(ranked.index).fillna(0)
            exposure_rows.append(
                {
                    "session": day,
                    "eligible_assets": len(ranks),
                    "selected_assets": int((weights > 0).sum()),
                    "cash_target": 1 - weights.sum(),
                    "momentum_rank_exposure": float((aligned * ranked["momentum_rank"]).sum()),
                    "quality_rank_exposure": float((aligned * ranked["quality_rank"]).sum()),
                }
            )
        else:
            exposure_rows.append(
                {
                    "session": day,
                    "eligible_assets": 0,
                    "selected_assets": 0,
                    "cash_target": 1.0,
                    "momentum_rank_exposure": 0.0,
                    "quality_rank_exposure": 0.0,
                }
            )
    return (
        pd.DataFrame(strategy, index=days),
        pd.DataFrame(baseline, index=days),
        pd.concat(features, ignore_index=True) if features else pd.DataFrame(),
        pd.DataFrame(exposure_rows),
    )


def industry_outputs(data: Dataset, result: BacktestResult) -> tuple[pd.DataFrame, pd.Series]:
    exposures: list[dict[str, Any]] = []
    contributions: dict[str, float] = {}
    previous_nav = result.initial_nav
    for day in result.weights.index:
        known = members_at(data.universe, at_new_york(day, 9)).set_index("asset_id")
        row: dict[str, Any] = {"session": day}
        for asset in result.weights.columns:
            label = str(known.loc[asset, "industry"]) if asset in known.index else "Unknown"
            row[label] = row.get(label, 0.0) + float(result.weights.loc[day, asset])
            contributions[label] = contributions.get(label, 0.0) + float(
                result.contributions.loc[day, asset] * previous_nav / result.initial_nav
            )
        previous_nav = float(result.ledger.loc[day, "nav"])
        exposures.append(row)
    return pd.DataFrame(exposures).set_index("session").fillna(0), pd.Series(contributions)


def run_research(data: Dataset, config: ResearchConfig, output: Path, root: Path) -> ResearchRun:
    data = validate_dataset(data, historical=config.mode == "historical")
    dates = sessions(config.start, config.end)
    if len(dates) < 2:
        raise DataError("At least two evaluation sessions are required")
    manifest = make_manifest(data, config, root)
    if output.exists():
        raise DataError(f"Output already exists; choose a fresh directory: {output}")
    log.info("research_started", run_id=manifest["run_id"], data_kind=data.metadata.kind)
    returns = valuation_returns(data, dates)
    from pqr.data.calendar import bar_availability

    terminal_rows = data.bars.loc[data.bars["terminal"]].copy()
    if not terminal_rows.empty:
        cutoff = terminal_rows["session"].map(bar_availability)
        terminal_rows = terminal_rows.loc[terminal_rows["available_at"] <= cutoff]
    terminal_events = (
        terminal_rows.drop_duplicates(["session", "asset_id"])
        .pivot(index="session", columns="asset_id", values="terminal")
        .reindex(index=dates, columns=returns.columns, fill_value=False)
        .fillna(False)
        .astype(bool)
    )
    strategy, equal, features, exposures = build_targets(data, config, dates, returns.columns)
    if not (strategy > 0).any().any():
        raise DataError("No eligible strategy holdings; inspect dates, warm-up and fundamentals")
    benchmark = pd.DataFrame(0.0, index=dates[:1], columns=returns.columns)
    benchmark.loc[dates[0], data.metadata.benchmark_id] = 1.0
    engine = VectorizedBacktest()
    costs = CostModel(config.commission_bps, config.slippage_bps)
    results = {
        name: engine.run(returns, targets, costs, config.initial_nav, terminal_events)
        for name, targets in [
            ("Strategy", strategy),
            ("Equal weight", equal),
            ("Benchmark", benchmark),
        ]
    }
    metrics = {
        name: performance_metrics(result, config.periods_per_year)
        for name, result in results.items()
    }
    sensitivity = pd.DataFrame(
        [
            {
                "total_cost_bps": bps,
                **performance_metrics(
                    engine.run(
                        returns, strategy, CostModel(0, bps), config.initial_nav, terminal_events
                    ),
                    config.periods_per_year,
                ),
            }
            for bps in (0.0, 6.0, 15.0, 30.0)
        ]
    )
    yearly_frames = []
    for name, result in results.items():
        frame = chronological_years(result.ledger["return"])
        frame["strategy"] = name
        frame["window_role"] = np.where(frame["year"] >= 2024, "reserved_holdout", "development")
        yearly_frames.append(frame)
    yearly = pd.concat(yearly_frames, ignore_index=True)
    manifest["evaluation"] = {
        "method": "fixed-rule chronological walk-forward; no fitting",
        "holdout_start": "2024-01-01",
        "automated_selection": "none",
        "researcher_holdout_access": "not tracked; requires external governance",
        "risk_free_daily": 0,
        "cash_daily": 0,
        "mark_cutoff": "next_session_08:00_America/New_York",
        "fold_template": [fold.__dict__ for fold in rolling_folds(dates)],
    }
    output.mkdir(parents=True)
    write_json(output / "manifest.json", manifest)
    write_json(output / "metrics.json", metrics)
    features.to_csv(output / "features.csv", index=False)
    exposures.to_csv(output / "target_exposures.csv", index=False)
    strategy.to_csv(output / "targets.csv", index_label="session")
    sensitivity.to_csv(output / "cost_sensitivity.csv", index=False)
    yearly.to_csv(output / "walk_forward.csv", index=False)
    for name, result in results.items():
        prefix = name.lower().replace(" ", "_")
        for label in ("ledger", "weights", "trades", "contributions"):
            getattr(result, label).to_csv(output / f"{prefix}_{label}.csv", index_label="session")
    primary = results["Strategy"]
    linked_contributions(primary).to_csv(output / "linked_attribution.csv", header=["contribution"])
    rolling_returns(primary.ledger["return"]).to_csv(output / "rolling_returns.csv")
    concentration(primary.weights).to_csv(output / "concentration.csv")
    industry_exposures, industry_contributions = industry_outputs(data, primary)
    industry_exposures.to_csv(output / "industry_exposures.csv")
    industry_contributions.to_csv(output / "industry_attribution.csv", header=["contribution"])
    run = ResearchRun(results, metrics, features, exposures, sensitivity, yearly, manifest, output)
    from pqr.reporting.report import render_report

    render_report(run)
    write_json(output / "checksums.json", output_hashes(output))
    log.info("research_completed", run_id=manifest["run_id"], sessions=len(dates))
    return run
