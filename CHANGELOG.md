# Changelog

## 0.1.0 — 2026-09-25 UTC

- Added Python 3.12 package, typed configuration, JSON logging and frozen dependencies.
- Added file, Tiingo EOD and SEC annual-fundamentals provider contracts with source snapshots.
- Added explicit historical/demonstration gates, as-of facts and versioned universe intervals.
- Added momentum/annual-ROA ranking, liquidity filters, monthly targets and two baselines.
- Added vectorized daily accounting, drift, self-financing costs and explicit terminal settlement.
- Added finance metrics, exact linked attribution, chronological windows and cost sensitivity.
- Added deterministic offline verification, experiment manifests and output checksum verification.
- Added a portable HTML research notebook, method/data/risk documentation and CI configuration.
- Validated against hand calculations, an independent scalar ledger, and leakage/regression tests.

### Known limits

Bundled results use artificial test fixtures, not market data. Live provider entitlement and coverage
remain unverified. Public GitHub publication requires authenticated access. macOS CI is configured
but unexecuted until a push. Complex corporate transformations and formal factor regression are not
implemented. Vendor data is not licensed by the code's MIT license.
