"""Local research commands. No order routing, brokerage connection or live trading."""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from pqr.configs.models import Settings, load_config
from pqr.data.fixtures import FIXTURE_WARNING, verification_dataset
from pqr.data.providers.http import SnapshotClient
from pqr.data.providers.sec import SecFundamentalsProvider
from pqr.data.providers.tiingo import TiingoPriceProvider
from pqr.data.schemas import DataError, Dataset, DatasetMetadata, load_dataset, save_dataset
from pqr.logging import configure_logging
from pqr.pipeline import run_research

app = typer.Typer(
    no_args_is_help=True, help="Auditable hypothetical equity research. No live trading."
)


@app.command()
def demo(
    output: Annotated[Path, typer.Option(help="Fresh run directory")] = Path("runs/verification"),
    config: Annotated[Path, typer.Option()] = Path("configs/demo.toml"),
) -> None:
    """Run an offline SYNTHETIC verification fixture, never a market backtest."""
    configure_logging()
    typer.echo(FIXTURE_WARNING)
    cfg = load_config(config)
    try:
        run = run_research(verification_dataset(cfg.seed), cfg, output, Path.cwd())
    except (DataError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Report: {run.output / 'report.html'}")


@app.command()
def run(
    dataset: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    output: Annotated[Path, typer.Option()] = Path("runs/research"),
    config: Annotated[Path, typer.Option(exists=True)] = Path("configs/research.toml"),
) -> None:
    """Run real input data under the explicitly selected research mode."""
    configure_logging()
    cfg = load_config(config)
    try:
        result = run_research(
            load_dataset(dataset, historical=cfg.mode == "historical"), cfg, output, Path.cwd()
        )
    except (DataError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Report: {result.output / 'report.html'}")


@app.command()
def validate(
    dataset: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    historical: Annotated[bool, typer.Option()] = False,
) -> None:
    """Validate schemas and provenance gates without running a strategy."""
    try:
        data = load_dataset(dataset, historical=historical)
    except (DataError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Valid: {len(data.bars):,} bar vintages; kind={data.metadata.kind}")


@app.command()
def ingest(
    mapping: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    start: Annotated[str, typer.Option()] = "2013-01-01",
    end: Annotated[str, typer.Option()] = "2025-12-31",
    output: Annotated[Path, typer.Option()] = Path("data/retrospective"),
    snapshots: Annotated[Path, typer.Option()] = Path("data/raw"),
    refresh: Annotated[bool, typer.Option(help="Fetch new source snapshots")] = False,
) -> None:
    """Fetch licensed Tiingo + public SEC inputs for a RETROSPECTIVE demonstration.

    Mapping fields: asset_id, symbol, cik, member_from, member_to,
    available_at, industry, is_benchmark.
    Exactly one row must have is_benchmark=true. Membership assertions remain user-supplied.
    """
    configure_logging()
    if output.exists():
        raise typer.BadParameter("Output already exists; ingestion will not overwrite a snapshot")
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first >= last:
        raise typer.BadParameter("start must precede end")
    settings = Settings()
    entries = pd.read_csv(mapping, dtype={"cik": str, "asset_id": str, "symbol": str})
    required = {
        "asset_id",
        "symbol",
        "cik",
        "member_from",
        "member_to",
        "available_at",
        "industry",
        "is_benchmark",
    }
    if not required.issubset(entries.columns) or entries["asset_id"].duplicated().any():
        raise typer.BadParameter(
            "Invalid mapping schema or duplicate asset IDs; see docs/data_dictionary.md"
        )
    benchmark = entries["is_benchmark"].astype(str).str.lower().eq("true")
    if benchmark.sum() != 1:
        raise typer.BadParameter("Exactly one benchmark row is required")
    client = SnapshotClient(snapshots, refresh=refresh)
    try:
        prices = TiingoPriceProvider(settings.tiingo_token, client)
        sec = SecFundamentalsProvider(settings.sec_user_agent, client)
        bars, facts = [], []
        for row in entries.itertuples(index=False):
            bars.append(prices.fetch(str(row.symbol), str(row.asset_id), first, last))
            if str(row.is_benchmark).lower() != "true":
                facts.append(sec.fetch(str(row.cik), str(row.asset_id)))
        metadata = DatasetMetadata(
            kind="retrospective",
            description="User watchlist; selection/survivorship bias and revised history remain",
            source="Tiingo EOD + SEC EDGAR; immutable raw retrievals stored separately",
            license="Tiingo account terms; SEC public EDGAR. No raw vendor redistribution.",
            retrieved_at=datetime.now(UTC).isoformat(),
            benchmark_id=str(entries.loc[benchmark, "asset_id"].iloc[0]),
        )
        universe = entries.loc[
            ~benchmark, ["asset_id", "member_from", "member_to", "available_at", "industry"]
        ]
        save_dataset(
            Dataset(
                pd.concat(bars, ignore_index=True),
                pd.concat(facts, ignore_index=True),
                universe,
                metadata,
            ),
            output,
        )
        (output / "fundamental_exclusions.json").write_text(
            json.dumps(sec.exclusions, indent=2) + "\n"
        )
        entries.to_csv(output / "identifier_mapping.csv", index=False)
    except DataError as exc:
        raise typer.BadParameter(str(exc)) from exc
    finally:
        client.close()
    typer.echo(
        f"Saved retrospective dataset: {output}. Historical mode will intentionally reject it."
    )


@app.command()
def verify_artifacts(
    directory: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
) -> None:
    """Verify retained run outputs against their SHA-256 checksums."""
    from pqr.experiments.registry import output_hashes

    expected = json.loads((directory / "checksums.json").read_text())
    actual = output_hashes(directory)
    if expected != actual:
        raise typer.BadParameter("Artifact integrity failed: files were changed, added or removed")
    typer.echo(f"Verified {len(expected)} artifact checksums")


if __name__ == "__main__":
    app()
