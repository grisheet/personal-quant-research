# Source register

Documentation reviewed 2026-09-25 UTC (2026-09-24 in America/New_York).
No live market dataset was acquired for the included verification release.

| Source | Official reference | Use | License/access boundary |
|---|---|---|---|
| Tiingo EOD | https://www.tiingo.com/documentation/end-of-day | Daily raw and adjusted prices; dividend and split audit fields | Personal token and appropriate entitlement; no bundled raw vendor data |
| Tiingo developer program | https://www.tiingo.com/documentation/appendix/developers | Redistribution guidance | Redistribution requires appropriate permission; users supply their own account |
| Tiingo terms | https://app.tiingo.com/tos/ | Governs data and permitted derived products | Review your current plan and intended public outputs before publication |
| SEC EDGAR APIs | https://www.sec.gov/search-filings/edgar-application-programming-interfaces | Submissions, acceptance metadata and Company Facts | Public endpoints; retain attribution and source provenance |
| SEC access rules | https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data | Fair-access policy | Identifying User-Agent, caching, conservative request rate |

The SEC API documentation describes facts aggregated across filings and the distinction between
Company Facts and latest-filed Frames. PQR does not use Frames to reconstruct historical observations.
Tiingo documents evening corrections and both raw and adjusted EOD prices. Provider documentation
does not establish original-vintage coverage, historical investable membership or every terminal event.

Provider contract tests use clearly artificial response-shaped fixtures. They verify parsing,
pagination, authentication-header handling, retries, cache integrity and exclusions; they do not
verify current account entitlement or real-world coverage. No test fixture is represented as a
retrieved API response. Credentials and source snapshots are excluded from the repository.

Code uses the MIT license. Data licenses remain separate. An HTML report containing derived vendor
results is not automatically permitted just because the code is open source. The included synthetic
verification report contains no vendor data and may be redistributed under the project license.
