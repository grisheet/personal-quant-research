# Risk register

| Risk | Control | Residual limitation |
|---|---|---|
| Look-ahead | As-of filtering before vintage selection; explicit lags; future-mutation tests | Source availability assertions require verification |
| Survivorship/selection | Dated, versioned membership; historical-mode gate | Included fixture has no real investable universe; current watchlists remain biased |
| Revisions | Retained snapshots; late facts and corrections cannot overwrite earlier state | Today's API backfill is still retrospective |
| Corporate actions | Consistent TR series; one dividend treatment; explicit terminal settlements | Stock conversions/spin-offs need upstream normalization |
| Missing observations | No implicit return filling; eligibility exclusion or fail-closed held position | Can reduce coverage or halt runs; no fabricated replacement |
| Identity | Stable IDs, explicit CIK/symbol mapping | Simple online ingestion does not resolve ticker reuse or class changes |
| Timezones | UTC timestamps, New York decision clock, exchange calendar and DST tests | Historical calendar corrections rely on pinned package |
| Fundamental comparability | Standard annual tags, same-accession assets, contexts, units and exclusions | Industry economics/custom taxonomy may require specialized models |
| Execution realism | Delayed close, drift, positive cash, cost sensitivities | No intraday impact, auction simulation, capacity or fill guarantees |
| Cash/baseline mismatch | Exposures disclosed; same-universe baseline plus benchmark-only | Fully invested benchmark is not risk-adjusted alpha evidence |
| Leakage/overfitting | Fixed parameters; chronological folds and optional purging | Human holdout access and multiple experimentation need external governance |
| Licensing | Source register; no bundled vendor observations | Actual plan terms must permit intended public derived outputs |
| Reproduction | Lockfile, deterministic fixtures, hashes, manifests, replay tests | Fresh vendor downloads can change; restricted snapshots cannot be publicly bundled |
| Operational failure | Bounded retries, explicit errors, immutable outputs, secret separation | CLI is single-user/single-process; no distributed cache locking or service SLA |
| Environment | Linux tests/build executed; macOS CI configured | macOS CI not executed before authenticated repository publication |
| Misinterpretation | Synthetic/hypothetical labels in README and report | Good software validation does not establish investment value |
