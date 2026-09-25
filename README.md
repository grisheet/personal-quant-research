# Personal Quant Research

[![Research quality](https://github.com/grisheet/personal-quant-research/actions/workflows/ci.yml/badge.svg)](https://github.com/grisheet/personal-quant-research/actions/workflows/ci.yml)

**A small, auditable operating system for systematic equity research.**

Point-in-time data contracts · transparent signals · self-financing backtests · reproducible reports

PQR connects source observations to research conclusions through explicit availability rules,
portfolio accounting, and an inspectable experiment manifest. It is designed for a reviewer to
understand and reproduce in VS Code on a Mac.

> **Educational research software. All results are hypothetical. No investment advice, lending
> decisions, brokerage integration, or automated real-money trading.** The included demonstration
> uses **synthetic verification fixtures**, not market observations. It makes no alpha claim.

## Start in five minutes

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then open this folder in VS Code.
On a Mac with Homebrew:

```bash
brew install uv
git clone https://github.com/grisheet/personal-quant-research.git
cd personal-quant-research
uv sync --frozen
uv run pqr demo --output runs/verification
open runs/verification/report.html
uv run pqr verify-artifacts runs/verification
```

The first dependency installation requires network access. The demo and test suite then work
offline. Expected console output includes:

```text
SYNTHETIC VERIFICATION FIXTURE — no real securities, market observations or investment evidence.
Report: runs/verification/report.html
Verified ... artifact checksums
```

Run directories are immutable by convention: choose another name when re-running. The demo uses
seed 42, 20 artificial equities, an artificial benchmark, and actual XNYS session dates. It evaluates
2020–2025 with earlier warm-up data. The calendar is real; every price and fundamental is artificial.

A prebuilt report is included at [`reports/verification/report.html`](reports/verification/report.html).
Its source commit, input hashes and assumptions are embedded. Numerical results are intentionally
not advertised here as investment performance.

## What you can inspect

| Capability | Implementation |
|---|---|
| Provider abstraction | Typed price/fundamental/universe protocols; Tiingo, SEC, file adapters |
| Provenance | Content-addressed raw responses, retrieval history, source terms, checksums |
| Point-in-time views | Publication eligibility before period/vintage selection; dated membership revisions |
| Signals | 12-minus-1-month momentum and annual ROA proxy; no ML or fitted normalization |
| Portfolio | Monthly top-quintile selection, equal weights, 10% name cap, residual cash |
| Execution | Next-session close, drifted holdings, self-financing proportional costs |
| Corporate actions | Total-return accounting once; supplied terminal cash settlement/total-loss handling |
| Baselines | Same-universe equal weight; fully invested benchmark buy-and-hold |
| Evaluation | Chronological walk-forward windows, separate rolling fold generator, cost sensitivities |
| Risk | CAGR, volatility, Sharpe, Sortino, drawdown, Calmar, turnover, exposure, hit rate, rolling returns |
| Attribution | Reconciled security/industry contributions, concentration and descriptive signal exposures |
| Reproduction | Frozen dependency lock, deterministic fixtures, config/data/code hashes, artifact verification |
| Delivery | Self-contained HTML, SVG figures, CSV ledgers and JSON manifests |

The strategy's 10% cap and top-20% selection can leave substantial cash in a small universe.
That is intentional and visible. Fully invested benchmarks are not exposure-matched alpha tests.

## Research on actual observations

You need a Tiingo account with the appropriate entitlement and a verified identifier/universe file.
No subscription purchase is required to use the offline verification demo. Never paste tokens into
source files, command arguments or Git.

```bash
cp .env.example .env
cp examples/universe_mapping.csv examples/my_universe.csv
# Edit .env locally and populate verified mapping rows; see docs/data_dictionary.md.
uv run pqr ingest --mapping examples/my_universe.csv \
  --start 2013-01-01 --end 2025-12-31 --output data/retrospective
uv run pqr validate --dataset data/retrospective
cp configs/research.toml configs/retrospective.toml
# In configs/retrospective.toml, explicitly set mode = "demonstration".
uv run pqr run --dataset data/retrospective \
  --config configs/retrospective.toml --output runs/retrospective
open runs/retrospective/report.html
```

Online ingestion preserves source bytes and caches exact requests. Use `--refresh` and a new output
directory to acquire another vintage. Exclusion records identify unsupported SEC facts.
**Live API entitlement and actual-source coverage were not tested for the bundled release.**
The automated provider tests use labeled artificial contract fixtures.

For an evidenced historical dataset:

```bash
uv run pqr validate --dataset data/historical --historical
uv run pqr run --dataset data/historical \
  --config configs/research.toml --output runs/historical
```

Historical mode intentionally refuses today's backfilled watchlist download. It requires original
availability evidence, dated membership including inactive securities, resolved terminal events, and
a consistently forward-built total-return index. Do not change metadata just to pass a gate.
See [data contracts](docs/data_dictionary.md) and [source licensing](docs/data_sources.md).

## Run the quality gates

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest --cov=pqr --cov-report=term-missing
uv build
```

Tests cover future-data mutation, amendments, unavailable membership/removals, calendar/DST issues,
missing held quotes, price-history gaps, drift, execution timing, buy/sell costs, cash conservation,
terminal settlement, split/dividend accounting, hand-calculated metrics, and exact numeric replay.
A separate scalar oracle checks the vectorized engine using property-based scenarios.

GitHub Actions runs the locked environment, lint, formatting, type checks, tests, package build,
offline demo, and artifact verification on Python 3.12 on Ubuntu and macOS. The badge links to
current results. See the dated [validation record](docs/validation.md).

## Repository map

```text
src/pqr/
  data/          providers, schemas, calendars, as-of datasets, fixtures
  features/      transparent feature calculations
  signals/       cross-sectional ranks
  portfolios/    strategy specification and targets
  execution/     cost model and cash-conserving execution
  backtesting/   adapter protocol and vectorized engine
  evaluation/    metrics, attribution and chronological windows
  experiments/   provenance, hashes and output verification
  reporting/     self-contained HTML and embedded SVG figures
  configs/       validated typed configuration
  cli.py         demo, ingest, validate, run, verify-artifacts
  pipeline.py    reproducible orchestration
configs/         demonstration and historical-research TOML
examples/        empty verified-mapping template
reports/         explicitly synthetic verification report and audit outputs
tests/          unit, integration, contract and property tests
docs/           methodology, data contracts, risks, validation, milestones
```

## Publication

The code is MIT-licensed; vendor data licenses are separate. Do not push `.env`, `data/`, or private
run directories. Publish only outputs you are entitled to distribute. The bundled synthetic report
contains no vendor observations.

The release is ready for a public repository named `personal-quant-research`. If this folder came
from the ZIP and has no Git history:

```bash
brew install gh
# Authenticate interactively; never put a token in the script.
gh auth login
git init -b main
git add .
git commit -m "Release auditable personal quant research framework v0.1.0"
gh repo create personal-quant-research --public --source=. --remote=origin --push
```

If you cloned the supplied Git bundle instead, skip `git init`, `git add`, and the initial commit.
A public repository has **not** been claimed as created until an authenticated push is verified.

## Read the research contract

- [Methodology and equations](docs/methodology.md)
- [Architecture and engineering decisions](docs/architecture.md)
- [Data dictionary and availability rules](docs/data_dictionary.md)
- [Official source register and licensing](docs/data_sources.md)
- [Risk register and remaining limitations](docs/risk_register.md)
- [Validation evidence](docs/validation.md)
- [Milestone walkthrough and exact commands](docs/milestones.md)
- [Changelog](CHANGELOG.md)

To add a provider, implement its protocol and test normalization with explicit source contracts.
To add a feature, consume only eligible data, specify units and lags, and add a future-mutation test.
To add a fitted model, use chronological training/validation/test folds and purge overlapping labels;
never fit preprocessing on validation or test data.
