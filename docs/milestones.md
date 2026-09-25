# Milestone walkthrough

The complete source files are supplied in this repository. This guide preserves the learning path,
exact file boundaries, copy-ready commands, acceptance checks and suggested commit messages.
Commands assume the repository root and an installed `uv`; setup is documented in README.
README and CHANGELOG describe the combined released state. Each stage below records its scope and
limitations; it is not a claim that the stage's isolated checkout is independently distributable.

## 1 — Foundation

Goal: establish repeatable configuration, typed package boundaries and quality gates.

Files: `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`, `.gitignore`,
`.github/workflows/ci.yml`, `src/pqr/__init__.py`, `src/pqr/configs/__init__.py`,
`src/pqr/configs/models.py`, `src/pqr/logging.py`, `README.md`, `CHANGELOG.md`, `LICENSE`.

```bash
uv sync --frozen
uv run python -c 'from pqr.configs.models import ResearchConfig; print(ResearchConfig().name)'
uv run ruff check src tests
uv run mypy src
```

Expected: `momentum-quality`; lint and type checks pass. Dependencies install from the committed
public-PyPI lock. Limitation: a new platform still needs to run its own checks.

Commit: `chore: establish reproducible Python research foundation`

## 2 — Provider contracts and source provenance

Goal: normalize prices and annual facts, retaining immutable source evidence.

Files: `src/pqr/data/__init__.py`, `src/pqr/data/schemas.py`,
`src/pqr/data/providers/{__init__,base,files,http,tiingo,sec}.py`,
`examples/universe_mapping.csv`, `docs/data_dictionary.md`, `docs/data_sources.md`,
`tests/test_providers.py`.

```bash
uv run pytest tests/test_providers.py -q
uv run pqr ingest --help
```

Expected: provider tests pass without contacting live APIs; help explains required inputs. For an
actual download use README's `.env` and mapping workflow. Limitation: live entitlement, issuer
mapping, taxonomy coverage and vendor licensing must be verified with actual sources.

Commit: `feat: add provenance-aware price and filing ingestion`

## 3 — Point-in-time research views

Goal: select eligible vintages and dated universe state without knowledge of future revisions.

Files: `src/pqr/data/calendar.py`, `src/pqr/data/point_in_time.py`,
`src/pqr/data/fixtures.py`, `tests/conftest.py`, `tests/test_point_in_time.py`.

```bash
uv run pytest tests/test_point_in_time.py -q
```

Expected: all leakage, revision, membership, holiday and DST tests pass. Limitation: correctness
of source timestamps must be independently established; the included fixtures are artificial.

Commit: `feat: enforce as-of data and versioned universe membership`

## 4 — Transparent features and portfolio targets

Goal: isolate finance formulas from rank selection and target construction.

Files: `src/pqr/features/{__init__,core}.py`, `src/pqr/signals/{__init__,ranking}.py`,
`src/pqr/portfolios/{__init__,construction}.py`, `configs/demo.toml`,
`configs/research.toml`, `docs/methodology.md`.

```bash
uv run pytest tests/test_point_in_time.py -k 'momentum or features or missing_session' -q
```

Expected: momentum off-by-one, future mutation and incomplete-history tests pass. Limitations:
quality is imperfect across industries; incomplete fundamentals exclude an asset; a small universe
and 10% cap can leave substantial cash. No tuning to the synthetic fixture was performed.

Commit: `feat: add transparent momentum-quality portfolio specification`

## 5 — Self-financing backtest accounting

Goal: reproduce portfolio drift, next-close timing, costs, cash and terminal settlements.

Files: `src/pqr/execution/{__init__,costs}.py`,
`src/pqr/backtesting/{__init__,engine}.py`, `tests/test_accounting.py`.

```bash
uv run pytest tests/test_accounting.py -q
```

Expected: hand calculations and independent scalar accounting agree; randomized scenarios preserve
cash and costs. Hypothesis examples run in addition to the named test count. Limitations: fractional
TR units and assumed close fills; no market impact, taxes or raw-share distribution ledger.

Commit: `feat: implement cash-conserving vectorized backtesting`

## 6 — Evaluation and experiment identity

Goal: calculate interpretable risk metrics and preserve the exact research inputs.

Files: `src/pqr/evaluation/{__init__,metrics,windows}.py`,
`src/pqr/experiments/{__init__,registry}.py`, `tests/test_metrics.py`.

```bash
uv run pytest tests/test_metrics.py -q
```

Expected: finance formulas match hand calculations, costs and drawdowns include initial entry,
chronological folds remain separated, and linked contributions reconcile. Limitations: zero cash/risk-
free rate and no formal factor regression; manual holdout access is not independently policed.

Commit: `feat: add research evaluation and experiment provenance`

## 7 — End-to-end research release

Goal: make the entire workflow reproducible and reviewable without credentials.

Files: `src/pqr/pipeline.py`, `src/pqr/cli.py`,
`src/pqr/reporting/{__init__,report}.py`, `src/pqr/reporting/templates/report.html`,
`tests/test_integration.py`, `docs/architecture.md`, `docs/risk_register.md`,
`docs/validation.md`, `docs/milestones.md`, `reports/verification/*`.

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest --cov=pqr --cov-report=term-missing
uv build
uv run pqr demo --output runs/reviewer-demo
uv run pqr verify-artifacts runs/reviewer-demo
open runs/reviewer-demo/report.html
```

Expected: all checks pass, a portable report is generated and output checksums verify. The source
and built wheel both include the report template. `docs/validation.md` records actual results.
Limitation: no market-performance claim and no public repository URL until an authenticated push.

Commit: `feat: ship auditable research notebook and release documentation`

## Review prompts

- Why are period end, availability and retrieval separate fields?
- Why can a current adjusted-price snapshot be reproducible yet not truly point-in-time?
- Why does a vectorized target-weight dot product accidentally imply daily rebalancing?
- Why solve for post-cost NAV instead of subtracting a cost after allocating all capital?
- Why is a cash-heavy strategy's lower volatility not necessarily an improvement over a benchmark?
- Which source evidence would be needed before describing a result as survivorship-aware?
