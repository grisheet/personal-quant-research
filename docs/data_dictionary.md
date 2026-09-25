# Data dictionary and point-in-time contract

All examples using `TEST` identifiers are artificial. A CIK identifies an issuer, not a tradable
share class. `asset_id` is a stable security/share-class identifier chosen by the data preparer.
Do not use a ticker as an immutable identity or map multiple share classes solely by CIK.

## Dataset layout

A dataset directory contains `bars.parquet`, `fundamentals.parquet`, `universe.parquet` and
`metadata.json`. CSV alternatives are supported. Parquet takes precedence if both exist.
Timezone-bearing columns normalize to nanosecond UTC. Session and reporting dates are timezone-free
calendar dates. A date is not a publication timestamp. Inputs are copied before validation.

### Bars

| Field | Type / unit | Meaning |
|---|---|---|
| asset_id | string | Stable security identity |
| session | date | XNYS session label; not midnight publication time |
| close | float, USD/share | Raw as-traded close; used for liquidity and price eligibility |
| volume | float, shares | Raw share volume; never combine adjusted price and raw volume for liquidity |
| tr_close | float, consistent index level | Total-return series; scale cancels in ratios |
| available_at | UTC timestamp | Earliest decision eligibility under the recorded basis |
| retrieved_at | UTC timestamp | Actual retrieval, or explicitly artificial fixture timestamp |
| availability_basis | enum | `observed`, `source_archive`, `assumed`, `fixture` |
| terminal | bool, optional; default false | Explicit final cash settlement after this session's return; no later bars |
| split_factor | float, optional | Vendor split factor; positive, retained for audit |
| cash_dividend | USD/share, optional | Vendor ex-date distribution; audit only, never credited twice |

Keys are `(asset_id, session, available_at)`. Multiple publication vintages coexist.
Zero price/index levels are accepted only for explicit terminal loss events. Missing daily
observations remain missing. Historical mode requires a consistent **forward-built** total-return
index. Independently observed back-adjusted closes can change their base after a split; blindly
joining those vintages produces false returns. The Tiingo retrospective adapter does not claim to
solve original-vintage reconstruction.

Valuation uses the latest stored vintage eligible by the following XNYS session at 08:00 New York.
A later correction cannot rewrite that mark. If the mark is missing when a position is held, the
run fails. This cutoff deliberately trades some data coverage for an auditable correction policy.
Signals use all information eligible by their decision, including properly timestamped revisions.

### Fundamentals

| Field | Type / unit | Meaning |
|---|---|---|
| asset_id | string | Security receiving an explicitly mapped issuer's facts |
| period_end | date | Annual accounting-period end |
| available_at | UTC timestamp | Filing acceptance plus the processing policy |
| retrieved_at | UTC timestamp | Snapshot retrieval |
| availability_basis | enum | Same evidence categories as bars |
| accession | string | SEC filing accession; artificial fixtures use an `ARTIFICIAL-` prefix |
| net_income | USD | Annual `us-gaap:NetIncomeLoss`, signed |
| assets_begin | USD | Total assets on the day before the annual period starts |
| assets_end | USD | Total assets on the annual period's end |

The SEC adapter requires all three facts in the same filing accession, standard USD tags,
330–380-day annual duration, unique contexts and positive assets. No silent synonym/tag guessing.
It reads old submission pages as well as recent metadata. Annual amendments become new records.
Unsupported custom tags, incomplete contexts and missing acceptance times are omitted with an
exclusion record. A later comparative value is never assigned an earlier publication timestamp.

Availability policy: find the first exchange session **after** the acceptance's New York calendar
date, let that entire session pass, and allow the next session's 09:00 decision. This is conservative,
including for filings accepted before the opening bell. Backfilled Company Facts still receives
`assumed`, since today's extraction cannot prove every originally disseminated API value.

### Universe

| Field | Meaning |
|---|---|
| asset_id | Stable identity |
| member_from | Inclusive effective start |
| member_to | Exclusive end; null means open |
| available_at | When this version of the membership interval was known |
| industry | Dated source label; use `Unknown` if unavailable |

An interval can be revised: preserve the original open interval and append a version with the same
asset/start, later `available_at`, and an explicit end. As-of queries first choose the latest known
version of each interval, then apply effective membership. Never overwrite an old interval with a
future-known removal. Active overlapping intervals are rejected. Industry classification changes
should be modeled as adjacent effective intervals with appropriately dated publication evidence.
No current GICS label is projected backward. SEC SIC is an industry classification, not GICS.

### Metadata and historical evidence

`kind`: `synthetic_fixture`, `retrospective`, or `point_in_time`.
`description`, `license`, `source`, `retrieved_at`, and `benchmark_id` are required provenance.
`total_return_convention`: `vendor_adjusted`, `forward_total_return`, or `synthetic`.

Historical mode also requires `membership_history=true`, `terminal_events_resolved=true`,
`original_vintages=true`, and `total_return_convention="forward_total_return"`. Bars and fundamentals
must have `observed` or `source_archive` availability. All three tables must include nonempty
`evidence_uri` and 64-character lowercase `evidence_sha256` fields. For `observed` records,
availability cannot precede retrieval. Source archive evidence must independently establish the
claimed publication timestamp. These are declarations and consistency checks, not source certification.
Never flip metadata flags just to bypass a failed gate.

## Ingest mapping

`examples/universe_mapping.csv` contains **headers only**, so no issuer mapping is fabricated.
Fill verified rows with these columns:

`asset_id,symbol,cik,member_from,member_to,available_at,industry,is_benchmark`

Exactly one benchmark row must have `is_benchmark=true`. Its CIK may be blank. Other rows require
verified numeric CIKs. The simple online command uses one symbol per security for the requested range;
it does not discover historical identities, delisted coverage, or ticker changes for you.

## Source snapshots

HTTP response bytes are retained by SHA-256. An append-only `retrievals.jsonl` records endpoint,
public query parameters, retrieval time, status, checksum and licensing note. A request index reuses
retained responses unless `--refresh` is supplied. Refresh appends retrieval history and retains old
content. Tokens live only in HTTP authorization headers. SEC uses an identifying User-Agent.
The default client throttles to two requests/second and retries transient failures with bounded
backoff; use a single process for that rate guarantee.
