# Findings

## Question

What moves posted GPU rental prices over the next 1 to 7 days, and can a system find out by itself without fooling itself?

Targets are the daily medians of posted rental offers in `daily_statistics.csv`, one series per collector, instrument class, GPU model and pricing tier, in USD per GPU-hour. Instruments are never pooled or chained. AWS spot series are left out because they have no November truth.

## Method

1. **Forecaster.** The forecast distribution for a series is the weighted empirical distribution of its own past h-day log changes. Hypotheses change the weights.
2. **Research loop.** 26 seed hypotheses, then mechanical one-step refinements of whatever has been accepted, repeated until a round yields nothing, then two rounds in which a language model reads the results and writes eight hypotheses of its own each time. A scout gathers dated web evidence through Exa, and the scout, proposer, experimenter, critic and reporter share one memory on past.dev.
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

80 hypotheses were tested: 25 seeds, 42 mechanical refinements and 13 written by the language model. 19 improved the development dates. 3 survived the gate. 4 more refinements were never run, because the proposer read in shared memory that the critic had already rejected those ideas on unseen dates. The log is [results/research_log.md](results/research_log.md).

**Kept.**

| Hypothesis | Dev gain | Gate gain |
| --- | --- | --- |
| A series with little history should borrow the change distribution of its instrument class | +0.032 | +0.013 |
| Posted prices behave differently when they sit away from their 30-day median | +0.020 | +0.013 |
| The direction of the last step carries information about the next one | +0.052 | +0.020 |

**Rejected, and worth knowing.**

- **Recent data is not better data.** Restricting to the last 60, 90 or 120 days, or down-weighting old changes, hurt every time (for example -0.059 for a 120-day lookback). Prices rose through the autumn, but the older record of how each series steps was still informative.
- **Self-grading failed out of sample.** Letting the method grade its own last 45 days per series and abstain where it had lost gained +0.033 on the development dates and lost -0.015 at the gate. In the first run of the loop, before the agents shared memory, windows of 21, 30, 60 and 90 days all showed the same reversal (that log is in this repository's first commit). A system that trusted its own track record would have adopted this.
- **Narrower intervals for rate cards looked right and were wrong.** Shrinking rate-card intervals by 20% to 40% gained on the development dates and lost at the gate: widths that fit the earlier months were too narrow for the later ones.
- **Adaptive tails did not help.** Adaptive conformal adjustment of the tail levels passed development at one rate and failed the gate.
- **Step-aware quantiles made no difference** (-0.0002).

**What the language model tried.** Shown the results so far, it proposed 16 hypotheses in two rounds; 13 were new tests. Its ideas were more specific than our seeds: wider intervals for new-generation marketplace asks; prices "cut quickly and raised slowly" as Blackwell supply ramps; a stale price under a shrinking offer count as a joint signal; a 2-day median for the aggregator's flickering cheapest-offer series. All were rejected on the development dates. The only two that gained there both narrowed rate-card intervals (+0.017 and +0.016) and both lost at the gate (-0.009 and -0.007). A model reasoning from the same development results walked into the same overfit that the mechanical search had, and the gate caught it both times.

## Does the gate make the forecasts better, or does it only reject more?

We reran the identical loop with the gate switched off, so that any hypothesis that improved the development dates was kept, and scored both final methods on the lockbox.

| Loop | Hypotheses kept | Skill on development dates | Skill on lockbox dates |
| --- | --- | --- | --- |
| With the gate (submitted) | 3 | +0.135 | **+0.251** |
| Without the gate | 7 | +0.174 | +0.228 |

Without the gate the loop kept more than twice as many ideas and looked better on the dates it could see. On the untouched dates it was worse by 0.023 skill (90% interval 0.015 to 0.030). Among the four extra ideas it kept was self-grading with a 90-day window, the largest false win in the log.

**The same comparison across 6 orderings of the hypothesis list, run in parallel on Modal.** The loop is greedy, so one run is one path. We shuffled the seed list 6 ways and ran the gated loop and the no-gate loop on each, one container per run, each scoring its own final method on the lockbox.

| Ordering | Gate: kept | Gate: dev | Gate: lockbox | No gate: kept | No gate: dev | No gate: lockbox | Difference |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 3 | +0.131 | +0.236 | 8 | +0.160 | +0.221 | +0.015 |
| 1 | 4 | +0.131 | +0.236 | 7 | +0.120 | +0.212 | +0.025 |
| 4 | 2 | +0.090 | +0.224 | 6 | +0.114 | +0.210 | +0.014 |
| 5 | 3 | +0.136 | +0.254 | 11 | +0.136 | +0.230 | +0.024 |
| 6 | 4 | +0.136 | +0.254 | 7 | +0.120 | +0.212 | +0.042 |
| 7 | 2 | +0.090 | +0.224 | 10 | +0.148 | +0.212 | +0.012 |

The gated loop won on the lockbox in 6 of 6 orderings, by +0.022 skill on average (+0.238 against +0.216). The no-gate loop kept 8.2 hypotheses on average against 3.0.

**What this also shows about our own result.** Across these orderings the gated loop's lockbox skill ranged from +0.224 to +0.254. The submitted run, in the order we happened to write the hypotheses, scored +0.251, at the top of that range. So the fair statement is: the gate reliably beats no gate, the gated loop reliably beats the drift baseline (+0.204), and the size of the gain depends on the path, with +0.251 on the favourable end.

## Why the gain is modest, and where the error is

After the first run we measured where the remaining error sits, on the gate dates only.

- **The error is in the timing of steps, not in the intervals.** 97% of the method's loss comes from forecasts where the price moved. Its median forecast equals the last value in 98% of forecasts.
- **A few expensive series carry most of it.** Ten series hold 55% of the last-value loss, led by marketplace asks for B300, H200 and B200.
- **There is headroom, but it needs knowledge of the future.** A hindsight method that knows each series' change distribution over the gate window in advance scores +0.44, against +0.20 for the accepted method.
- **Posted prices are persistent steps, not noise around a level.** We tested the obvious way to move the median: forecast from the 3-day median level instead of the last print. It lost 0.265 skill on the development dates. Trend signals (own two-week trend, class one-week trend) and volatility scaling were also rejected.

So the last posted value is the right centre, and a short-horizon forecaster for this market earns its skill from intervals. Predicting which day a provider re-prices would need information that is not in posted prices.

## Phantom capacity: a negative result

Posted offers are asks, not transactions, so we tested whether the number of live offers behind a median is an outside signal of utilization, the way a quoted lead time is for a factory. The hypothesis: a shrinking offer count means supply is tightening, and an upward price step follows.

**As a forecasting rule it was rejected on the development dates (-0.008).** The direct test shows why. Probability of a price step within 7 days, by offer-count trend:

| Offer count over the last 3 days vs the 2 weeks before | Search period: up / down | Lockbox: up / down |
| --- | --- | --- |
| Falling by more than 5% | 0.25 / 0.10 | 0.38 / 0.30 |
| Flat | 0.28 / 0.14 | 0.36 / 0.19 |
| Rising by more than 5% | 0.22 / 0.10 | 0.31 / 0.25 |

A falling offer count did not raise the chance of an upward step in the search period. On the lockbox it came with more steps in both directions. In this data a changing offer count signals that a price is about to move, not which way. Full tables for every state are in [results/state_experiments.json](results/state_experiments.json).

**One series, to make it concrete.** The series that carries the most error is one collector's marketplace ask for the B300, on demand. Its posted median went from $4.99 on August 4 to $11.52 on November 6, 2026. On that one series the hypothesis looks right: when the offer count was falling, the price was higher a week later 54% of the time and lower 12% of the time; when the offer count was rising, it was lower 57% of the time. On the same collector's H100 marketplace ask it reverses: a rising offer count came before a higher price 78% of the time. Each series has under 90 days, and week-ahead windows from neighbouring days overlap, so neither pattern can be told from chance. Pooled across series the direction washes out and only "a price is about to move" is left. A person looking at the B300 chart would have believed the hypothesis. The loop tested it on every series and on unseen dates, and dropped it.

The same tables show what did carry direction. A series below its 30-day median stepped up within a week 42% of the time in the search period, against 18% for a series near its median.

## What someone pricing GPU capacity could act on

1. **Short-run intervals should be set per instrument, from the series' own step history plus its class.** One width for all series is wrong in both directions: too wide for list prices, too narrow for marketplace asks in an active month.
2. **Do not shorten the history window because the market "changed".** It cost accuracy here every time.
3. **Offer counts are a volatility signal.** Use them to widen an interval, not to shift a price.
4. **Be suspicious of any rule tuned on the last few months of this market.** 16 of 19 improvements found on one period did not hold on the next, whether a person, a mechanical search or a language model proposed them.

## The 2 to 3 year view

This part cannot be scored. It is an argument from the pack, with each instrument cited separately.

**Evidence.**

- **Posted rental prices rose across generations over the past year.** In the GetDeploying weekly on-demand medians, the H100 went from $2.98 in the week of November 3, 2025 to a low of $2.49 in the week of March 2, 2026 and to $3.85 in the week of October 26, 2026. The A100 went from $1.60 to a low of $1.45 to $1.79 over the same weeks.
- **Newer chips rose most in the last three months.** In one collector's neocloud rate-card medians from August 4 to November 6, 2026: B300 $8.25 to $9.75, B200 $6.69 to $7.89, H100 SXM $3.23 to $3.55, A100 SXM $1.79 to $1.95, H200 $4.38 to $4.59.
- **Older chips are not priced at capability parity.** The brief gives an H100 2.46 times the inference throughput of an A100. At the November 6 rate-card medians above, an A100 hour costs $1.95 and an H100 hour $3.55, so the A100 costs about 35% more per unit of inference work. Its rental price is holding a floor that throughput alone does not explain.

- **Public sources dated before November 6, 2026, found by the scout through Exa, point the same way, with early signs of easing.** Headlines only; we did not verify their numbers. Rising: ["Nvidia B200 Rental Prices Surge Toward $8 per GPU-Hour as Blackwell Compute Tightens"](https://aiindustrytoday.com/news/nvidia-b200-rental-prices-surge-toward-8-per-gpu-hour-as-blackwell-compute-tightens/) (September 23); ["AI compute crunch deepens as chip rental costs jump 60% and rivals scramble for power"](https://investinglive.com/stocks/ai-compute-crunch-deepens-as-chip-rental-costs-jump-60-and-rivals-scramble-for-power/) (October 13); ["NVIDIA GPUs Are Becoming Appreciating Assets In The ..."](https://wccftech.com/nvidia-gpus-appreciating-assets-a100-rental-premium/) (October 24). Cause: ["Power and Cooling Are the New GPU Shortage"](https://datastorage.com/articles/power-and-cooling-are-the-new-gpu-shortage-inside-the-data-center-bottleneck/) (August 12). Easing: ["H100 Rental Prices Show Signs of Easing This Week, About 19% Below October Average"](https://www.insigtx.com/en/news/h100-rental-prices-show-signs-of-easing-this-week-about-19-504193/) (November 2); ["Ax3 Pulse — B300 rental index slides below $7 — on-demand is softening, term is not"](https://www.ax3.ai/news-b300-rental-slide) (November 4). All 33 results are in [results/exa_evidence.md](results/exa_evidence.md).

**Reading.** A depreciation schedule that marks an older chip down in proportion to the capability of its successors would have been wrong over this year: the older chips' posted prices went up. What they earn appears to be set by scarcity of any usable capacity, not by relative throughput.

**Ranges for the H100 posted on-demand median in late 2028 to late 2029, under stated assumptions.**

| Scenario | Assumption | H100, USD per GPU-hour |
| --- | --- | --- |
| Capacity stays scarce | Posted prices hold or keep drifting up as in 2026 | 3.5 to 4.3 |
| Supply catches up | Prices return to the range of the March 2026 low | 2.0 to 2.9 |
| Central | Between the two | about 3 |

Resale value follows the rental stream a buyer expects, so the same split applies: in the scarce case a three-year-old H100 keeps most of its earning power, and in the catch-up case it loses a third or more. We did not model resale directly; the pack holds pointers to resale sources but no values. Which scenario holds depends on power and data center supply, which this pack does not measure.

## Limits

See the README. The main ones: the lockbox is 11 consecutive days and was scored three times with an unchanged method; everything that was kept came from seed hypotheses written by people working with an AI coding agent, and none of the language model's 13 survived; web evidence is cited but does not decide what is accepted; the event forecast for November 7, 9 and 13 was unscored when this was written.
