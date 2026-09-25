# Research methodology

This document describes an educational, hypothetical simulation. It does not recommend investments.

## Information and execution clock

1. Store exchange-session labels as dates; store eligibility and retrieval timestamps in UTC.
2. Resolve sessions with XNYS, not generic weekdays. Use America/New_York for the decision clock.
3. Backfilled prices become eligible at 08:00 on the next exchange session (explicit assumption).
4. Filing facts wait one full subsequent trading session; see the exact rule in the data dictionary.
5. At 09:00 on the first evaluation session of each month, calculate eligible features and targets.
   A partial first month gets one initial rebalance; subsequent rebalances are first-session monthly.
6. Existing holdings earn that day's close-to-close return; execute target changes at that close.
7. Charge costs and carry post-cost weights forward. New holdings earn subsequent returns.

This uses observed closing prices as hypothetical fills with assumed slippage; it does not model
auction order constraints, intraday availability, impact or actual execution. The engine uses
fractional normalized total-return units and assumes frictionless reinvestment of distributions
inside those units. It does not claim to be a raw-share dividend cash-flow ledger.

## Universe and eligibility

U.S. common-equity membership is supplied with stable security identities and dated evidence;
the program does not certify asset type or discover an investable universe from current tickers.
Default numerical filters: raw close >= $5; median raw close × raw share volume over the preceding
60 sessions >= $10 million/session; complete 253-observation momentum history; eligible annual
fundamentals no more than 550 calendar days old. Price gaps fail eligibility rather than shortening
the lookback. Held-asset gaps fail the backtest. Filters run on eligible observations only.

## Features and portfolio

For the last eligible session t and a consistent total-return index TR:

$$M_{i,t}=TR_{i,t-21}/TR_{i,t-252}-1.$$

There must be 253 observations including t. Values are unitless simple returns. Annual quality is:

$$Q_{i,t}=NI_i / ((A_{i,begin}+A_{i,end})/2).$$

NI and A are USD from a single eligible filing accession; NI is signed and average assets must be
positive. Standard-tag coverage and cross-industry comparability are limitations. No estimated
analyst data or current shares outstanding are used.

Rank each feature within the eligible cross-section, with tied values receiving average percentile
rank. Score = (momentum rank + quality rank)/2. Choose ceil(20% × eligible count), with asset ID as a
deterministic tie-break. Each selected asset receives min(1/count, 10%) of post-cost NAV. Cash is the
residual. Equal-weight baseline uses the same eligible cross-section and cap. Benchmark-only is
fully invested after its first execution. All use the same proportional cost assumptions.

## Accounting and costs

Let H[i,t-1] be previous close dollar holdings, B[t-1] cash, r[i,t] daily total returns and V previous
NAV. Gross asset contributions are H[i,t-1] × r[i,t] / V[t-1]. Before trading:

$$H^-_{i,t}=H_{i,t-1}(1+r_{i,t}),\qquad V^-_t=\sum_i H^-_{i,t}+B_{t-1}.$$

For post-cost target weights w, cost rate k = (commission_bps + slippage_bps)/10,000, solve:

$$V^+_t + k\sum_i|w_{i,t}V^+_t-H^-_{i,t}|=V^-_t.$$

Then H+ = w × V+, C = k × absolute traded notional, and B+ = V+ − sum(H+).
The monotonic solve is bounded and cash-conserving for long-only unlevered weights and k < 1.
Defaults are 1 bp commission + 5 bps slippage **per dollar traded**, not per round trip.
No fixed ticket fee or minimum lot size is modeled. Initial entry costs are included; the final
portfolio is marked to market without forced liquidation or exit costs. Sensitivities use 0, 6,
15 and 30 bps total. Targets stay fixed, while holdings naturally differ as costs change NAV.

Terminal events require explicit input. Apply the supplied terminal return, convert remaining
terminal holdings into cash, and prohibit reentry. This mandatory settlement has no assumed trade
commission; voluntary transactions are costed normally. Total loss is return −1. Missing delisting
prices are never interpreted as −1, zero return, or the last available quote. Stock-for-stock
transformations are not implemented. Insolvent portfolios halt rather than continue undefined metrics.

## Metrics and units

- Daily portfolio return: V[t]/V[t−1] − 1; costs reduce returns.
- Elapsed years: ((last session date − first session date).days + 1)/365.25. Initial capital is
  deemed available at the start of the first evaluation day. CAGR = (V[last]/V[0])^(1/years) − 1.
  Annualization over short windows is mathematically valid but economically unstable.
- Annualized volatility: sample std(daily returns, ddof=1) × sqrt(252).
- Sharpe: sqrt(252) × mean(r−rf) / sample std(r−rf), with rf=0 per day in v1.
- Sortino: sqrt(252) × mean(r) / sqrt(mean(min(r,0)^2)); target=0; denominator includes all days.
- Drawdown: V[t]/max(V[0], previous/current peaks) − 1. Maximum drawdown is a positive loss magnitude.
- Calmar: CAGR / maximum drawdown. Undefined ratios are null, never infinite.
- Traded-notional turnover: sum(abs(trade USD))/pretrade NAV. Half-turnover is half that value;
  cash is excluded. Initial entry is included. Annualized turnover divides cumulative turnover
  by evaluation sessions/252, not by the number of rebalances.
- Gross exposure: sum(abs(asset weights)); net exposure: sum(asset weights); cash shown separately.
- Hit rate: fraction of all evaluated daily returns strictly >0, including zero-return cash days.
- Rolling return: product(1+r)−1 over 21, 63, or 252 sessions; insufficient history returns null.
- HHI: sum((asset weight / invested fraction)^2); effective names=1/HHI; cash-only HHI is null.
- Name/industry concentration and weighted feature-rank exposure are descriptive risk summaries,
  not estimated factor betas, return causation, or an alpha decomposition.

Dollar costs, trades, settlements and NAV are USD. Percentages in reports multiply decimal quantities
by 100. Cash and risk-free return are assumed zero, not sourced interest rates. Fees, taxes, lending
fees and financing are not estimated. Gross/net exposure coincide for this long-only example.

## Attribution

Daily security contributions c[i,t] and negative cost contribution reconcile to daily net return.
Wealth-linked contribution = sum_t(c[i,t] × V[t−1]/V[0]); summing across assets, costs and zero-yield
cash exactly equals total portfolio return. Industry attribution groups these daily contributions
using classifications available that morning. Unknown classifications stay in an explicit bucket.
Linked contributions need not equal compounded stand-alone asset returns.

## Chronological evaluation

The fixed example has no fitting, optimization, learned scaling or automated parameter selection.
Generate monthly decisions sequentially and show continuous strategy results in chronological yearly
windows. Configured default dates reserve 2024–2025 as a holdout; no code-selected parameters depend
on those results. The software cannot prove that a person has never viewed a holdout.

`rolling_folds` provides 756-session training, 252-session validation and nonoverlapping 252-session
test windows for future fitted extensions. Optional gaps separate each boundary. A label spanning H
future sessions requires at least an H-session purge appropriate to the labeling convention. Fit
imputers, scalers and parameters inside the training fold; select on validation; evaluate once on the
next test fold. Historical feature warm-up is allowed; future observations and shuffled splits are not.
Overlapping training windows are expected. Formal multiple-testing correction and significance
analysis are outside v1 because no strategy-performance claim is made.
