# Findings

## Question

What moves posted GPU rental prices over the next 1 to 7 days, and can a system find out by itself without fooling itself?

Targets are the daily medians of posted rental offers in `daily_statistics.csv`, one series per collector, instrument class, GPU model and pricing tier, in USD per GPU-hour. Instruments are never pooled or chained. AWS spot series are left out because they have no November truth.

## Method

1. **Forecaster.** The forecast distribution for a series is the weighted empirical distribution of its own past h-day log changes. Hypotheses change the weights.
2. **Research loop.** 21 seed hypotheses, then mechanical one-step refinements of whatever has been accepted, repeated until a round yields nothing.
3. **Gate.** A hypothesis is kept only if it improves pooled skill on the development origins and on gate origins the proposer never sees.
4. **Lockbox.** Origins from October 20 to 30, 2026 were scored once, after the loop had stopped.

## Evaluation

Pinball loss at quantiles 0.1, 0.5 and 0.9, averaged per (series, origin, horizon) cell, with skill measured against the flat last value, as in the starter kit. Every daily origin is used. The universe at each origin is every posted series with 30 days of history, a value in the last 3 days and at least one price change in 90 days, decided from data up to that origin only. Uncertainty is a bootstrap that resamples whole origin dates.

The comparison baseline is the starter kit's `drift`, produced by running the organisers' `baselines.py` unchanged and scored on the same cells.

## Results

| Set | Origins | Cells | `drift` skill | Final method skill | Gain (90% interval) |
| --- | --- | --- | --- | --- | --- |
| dev | Apr 1 to Sep 16 | 17,254 | +0.053 | +0.135 | +0.082 (+0.065 to +0.097) |
| gate | Sep 24 to Oct 12 | 7,313 | +0.163 | +0.205 | +0.041 (+0.024 to +0.065) |
| **lockbox** | **Oct 20 to 30** | **5,451** | **+0.204** | **+0.251** | **+0.047 (+0.030 to +0.062)** |

Only the lockbox row is a clean estimate. Interval coverage on the lockbox is 0.81 for the final method and 0.78 for `drift`, against a target of 0.80.

**Lockbox by instrument class.**

| Instrument class | Cells | Share of last-value loss | Cells where price moved | `drift` skill | Final skill |
| --- | --- | --- | --- | --- | --- |
| marketplace_ask | 834 | 40% | 60% | +0.203 | +0.270 |
| neocloud_rate_card | 1,851 | 30% | 38% | +0.157 | +0.189 |
| hyperscaler_spot | 1,069 | 18% | 62% | +0.221 | +0.219 |
| neocloud_spot | 883 | 7% | 72% | +0.430 | +0.434 |
| aggregator_cheapest | 432 | 4% | 15% | +0.326 | +0.484 |
| hyperscaler_list | 382 | 1% | 7% | -0.523 | -0.141 |

The gain comes from marketplace asks, neocloud rate cards and the aggregator's cheapest-offer series. Spot series are unchanged. Hyperscaler list prices almost never move, and both methods lose to the last value there: any interval at all is a cost on a series that stays put.

**By horizon on the lockbox:** 1 day +0.282 against +0.205, 3 days +0.256 against +0.249, 7 days +0.237 against +0.179.

**Organisers' scorer, frozen at October 24, 2026.** +0.303 against +0.242 on the 183 posted series that move (544 cells). On the 17 posted headline-tier series at that cutoff, +0.221 against +0.228 (51 cells): no gain. On the 37 posted series that pass the headline gates on November 6, across all lockbox origins, +0.097 against +0.072, a gain of +0.025 (+0.006 to +0.045); membership of that set uses data after the lockbox, so that row is descriptive.

## What the system learned across iterations

67 hypotheses were tested. 21 improved the development dates. 3 survived the gate. The log is [results/research_log.md](results/research_log.md).

**Kept.**

| Hypothesis | Dev gain | Gate gain |
| --- | --- | --- |
| A series with little history should borrow the change distribution of its instrument class | +0.032 | +0.013 |
| Posted prices behave differently when they sit away from their 30-day median | +0.020 | +0.013 |
| The direction of the last step carries information about the next one | +0.052 | +0.020 |

**Rejected, and worth knowing.**

- **Recent data is not better data.** Restricting to the last 60, 90 or 120 days, or down-weighting old changes, hurt every time (for example -0.059 for a 120-day lookback). Prices rose through the autumn, but the older record of how each series steps was still informative.
- **Self-grading failed out of sample.** Letting the method grade its own last 45 days per series and abstain where it had lost gained +0.033 on the development dates and lost -0.015 at the gate. Every window length tried (21, 30, 60, 90 days) showed the same reversal. A system that trusted its own track record would have adopted this.
- **Narrower intervals for rate cards looked right and were wrong.** Shrinking rate-card intervals by 20% to 40% gained on the development dates and lost at the gate: widths that fit the earlier months were too narrow for the later ones.
- **Adaptive tails did not help.** Adaptive conformal adjustment of the tail levels passed development at one rate and failed the gate.
- **Step-aware quantiles made no difference** (-0.0002).

## Phantom capacity: a negative result

Posted offers are asks, not transactions, so we tested whether the number of live offers behind a median is an outside signal of utilization, the way a quoted lead time is for a factory. The hypothesis: a shrinking offer count means supply is tightening, and an upward price step follows.

**As a forecasting rule it was rejected on the development dates (-0.008).** The direct test shows why. Probability of a price step within 7 days, by offer-count trend:

| Offer count over the last 3 days vs the 2 weeks before | Search period: up / down | Lockbox: up / down |
| --- | --- | --- |
| Falling by more than 5% | 0.25 / 0.10 | 0.38 / 0.30 |
| Flat | 0.28 / 0.14 | 0.36 / 0.19 |
| Rising by more than 5% | 0.22 / 0.10 | 0.31 / 0.25 |

A falling offer count did not raise the chance of an upward step in the search period. On the lockbox it came with more steps in both directions. In this data a changing offer count signals that a price is about to move, not which way. Full tables for every state are in [results/state_experiments.json](results/state_experiments.json).

The same tables show what did carry direction. A series below its 30-day median stepped up within a week 42% of the time in the search period, against 18% for a series near its median.

## What someone pricing GPU capacity could act on

1. **Short-run intervals should be set per instrument, from the series' own step history plus its class.** One width for all series is wrong in both directions: too wide for list prices, too narrow for marketplace asks in an active month.
2. **Do not shorten the history window because the market "changed".** It cost accuracy here every time.
3. **Offer counts are a volatility signal.** Use them to widen an interval, not to shift a price.
4. **Be suspicious of any rule tuned on the last few months of this market.** 18 of 21 improvements found on one period did not hold on the next.

## The 2 to 3 year view

This part cannot be scored. It is an argument from the pack, with each instrument cited separately.

**Evidence.**

- **Posted rental prices rose across generations over the past year.** In the GetDeploying weekly on-demand medians, the H100 went from $2.98 in the week of November 3, 2025 to a low of $2.49 in the week of March 2, 2026 and to $3.85 in the week of October 26, 2026. The A100 went from $1.60 to a low of $1.45 to $1.79 over the same weeks.
- **Newer chips rose most in the last three months.** In one collector's neocloud rate-card medians from August 4 to November 6, 2026: B300 $8.25 to $9.75, B200 $6.69 to $7.89, H100 SXM $3.23 to $3.55, A100 SXM $1.79 to $1.95, H200 $4.38 to $4.59.
- **Older chips are not priced at capability parity.** The brief gives an H100 2.46 times the inference throughput of an A100. At the November 6 rate-card medians above, an A100 hour costs $1.95 and an H100 hour $3.55, so the A100 costs about 35% more per unit of inference work. Its rental price is holding a floor that throughput alone does not explain.

**Reading.** A depreciation schedule that marks an older chip down in proportion to the capability of its successors would have been wrong over this year: the older chips' posted prices went up. What they earn appears to be set by scarcity of any usable capacity, not by relative throughput.

**Ranges for the H100 posted on-demand median in late 2028 to late 2029, under stated assumptions.**

| Scenario | Assumption | H100, USD per GPU-hour |
| --- | --- | --- |
| Capacity stays scarce | Posted prices hold or keep drifting up as in 2026 | 3.5 to 4.3 |
| Supply catches up | Prices return to the range of the March 2026 low | 2.0 to 2.9 |
| Central | Between the two | about 3 |

Resale value follows the rental stream a buyer expects, so the same split applies: in the scarce case a three-year-old H100 keeps most of its earning power, and in the catch-up case it loses a third or more. We did not model resale directly; the pack holds pointers to resale sources but no values. Which scenario holds depends on power and data center supply, which this pack does not measure.

## Limits

See the README. The main ones: the lockbox is 11 consecutive days; the seed hypotheses were written by people working with an AI coding agent, not generated by the loop; the event forecast for November 7, 9 and 13 was unscored when this was written.
