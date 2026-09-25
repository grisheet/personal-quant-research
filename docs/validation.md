# Validation record — v0.1.0

Recorded 2026-09-25 UTC. All numerical inputs used in this release validation are explicitly
artificial test fixtures. No market-performance validation is claimed.

## Executed in the build environment

- Python 3.12.14, Linux x86_64; locked environment installed with uv 0.12.17.
- Ruff lint and formatting checks passed.
- Mypy passed across all 34 package Python files.
- **54 pytest cases passed**, including additional deterministic Hypothesis-generated scenarios.
- Combined statement/branch coverage: approximately **86%**. Coverage measures exercised code,
  not the probability of correctness. CI enforces a floor of 80%.
- Built both the source distribution and wheel; inspected the wheel to verify that provider modules
  and the HTML template are included.
- End-to-end repeated runs produced identical metrics, ledgers, feature CSVs and HTML for the same
  input/config/code state. Retrieval/creation timestamps are provenance, not performance inputs.
- Report includes five embedded SVG figures with unique DOM IDs, explicit synthetic labels, no
  external scripts, and a complete artifact checksum manifest.
- Rendered HTML through a print-layout renderer for visual inspection. A Chromium screenshot was
  unavailable because the browser binary download failed; responsive browser QA is not claimed.

The prebuilt report is generated from the source commit recorded in its own manifest. A subsequent
commit may add the report files without changing the generating source. The bundled report's run ID
need not match a fresh run after another Git commit; compare numeric outputs and source/data hashes.

## Public release provenance

On 2026-09-25, [GitHub Actions run 36177634848](https://github.com/grisheet/personal-quant-research/actions/runs/36177634848)
passed on both `ubuntu-latest` and `macos-latest` for publication commit
`3f140e3685bef64609d436adb1c2b8b30b5dcf60`. Both jobs passed frozen dependency installation,
Ruff lint/formatting, mypy, pytest with the 80% coverage gate, wheel/source builds, the offline demo,
and artifact verification. Subsequent publication edits affect documentation only.

The public repository is https://github.com/grisheet/personal-quant-research. Browser publication
created new Git commit IDs. A file comparison against build commit
`09ab1eeba90916c4564b8e8ce0d96286440d6c4d` found identical implementation and report files,
except that the browser editor added a newline to eleven otherwise empty `__init__.py` files.
Publication documentation is updated separately. The report still identifies the original source
commit `1692234058e395e929e78a887ee2849b2a8a905d` that generated its outputs.

The release asset `personal-quant-research.bundle` preserves the original eight build commits and
original build tag. To inspect that exact history without confusing it with the public release tag:

```bash
git clone personal-quant-research.bundle original-build
git -C original-build checkout 1692234058e395e929e78a887ee2849b2a8a905d
```

## What the tests establish

| Invariant | Evidence |
|---|---|
| Later records cannot change earlier features or targets | Future price/fundamental mutation test |
| Restatements are usable only after availability | Before/after revision test |
| A future-known removal does not erase earlier universe membership | Versioned membership test |
| Later price corrections cannot rewrite frozen valuation marks | Valuation cutoff test |
| Missing observations do not shorten lookbacks or become free held returns | Feature and held-quote failures |
| Dates respect holidays and daylight-saving transitions | Calendar and lag tests |
| New targets do not capture a return earned before execution | Next-close timing example |
| Holdings drift rather than rebalance daily | Hand-calculated two-asset path |
| Costs include buys, sells and initial entry; cash stays nonnegative | Scalar oracle and self-financing properties |
| Terminal settlements become cash and prohibit reentry | Engine and full-pipeline terminal tests |
| Splits preserve economic value; dividends count once | Artificial corporate-action example |
| Metrics use documented units and denominators | Hand-calculated volatility/Sharpe/Sortino/drawdown tests |
| Cash-only metrics remain well-defined | Null ratio and zero-return tests |
| Attribution reconciles exactly to simulated return | Daily and wealth-linked identities |
| Chronological folds have no overlapping tests | Window boundary/purge tests |
| Provider failures do not become observations | HTTP status, retry, context, pagination and cache tests |
| Historical research requires evidence fields | Negative gates and positive artificial-schema contract |
| Output tampering is detected | Checksum modification test |

## Not established by these checks

- Actual-source correctness, source timestamp truth, full historical membership or delisting coverage.
- Live API entitlement, service availability or exhaustive SEC taxonomy coverage.
- Real trading fills, achievable returns, capacity, alpha or statistical significance.
- Independence of a manually inspected holdout.
- Browser rendering on every screen size; use the included HTML and print stylesheet locally.

## Reproduce

```bash
uv sync --frozen
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest --cov=pqr --cov-report=term-missing
uv build
uv run pqr demo --output runs/validation-replay
uv run pqr verify-artifacts runs/validation-replay
```
