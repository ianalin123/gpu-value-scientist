# Research log

67 hypotheses tested, 17 improved the development dates, 3 also improved the unseen gate dates and were kept.

| ID | Hypothesis | Where it came from | Dev gain (p) | Gate gain (p) | Verdict | Web evidence the proposer read |
| --- | --- | --- | --- | --- | --- | --- |
| H01 | Price behaviour changed this autumn, so only the last 120 days of changes are informative. | X sweep: rental indices at highs since October (X-045, X-046) | -0.0591 (0.00) | not run | rejected on dev | [2026-11-02](https://www.insigtx.com/en/news/h100-rental-prices-show-signs-of-easing-this-week-about-19-504193/) [2026-10-19](https://www.aiminingco.com/insights/gpu-h100-sxm-deep-dive-week-of-october-12-2026) |
| H02 | Recent changes should count more than old ones (45-day half-life). | same as H01 | -0.0302 (0.00) | not run | rejected on dev |  |
| H03 | There is no short-run drift: the median forecast should stay on the last posted value. | brief: rate-card medians move in steps | +0.0022 (1.00) | -0.0005 (0.10) | rejected at the gate |  |
| H04 | A series with little history should borrow the change distribution of its instrument class. | brief: instruments differ, series within one behave alike | +0.0319 (1.00) | +0.0130 (1.00) | **kept** |  |
| H05 | Borrowing should stay inside one collector and instrument class. | brief: define targets per source | +0.0001 (0.71) | not run | rejected on dev | [2026-08-27](https://cloud.theai.com/blog/how-much-blackwell-actually-exists) [2026-10-17](https://www.tokenpost.com/news/technology/33728) |
| H06 | Steps cluster: a price that changed in the last two days is more likely to change again. | brief: step process; jump-hazard idea | -0.0124 (0.03) | not run | rejected on dev |  |
| H07 | Phantom capacity: a shrinking count of posted offers signals tightening supply and precedes a price step. | Maglev analog: quoted lead times reveal hidden utilization (C-18, X-034, X-053) | -0.0081 (0.07) | not run | rejected on dev | [2026-09-26](https://www.adamsioud.com/exemplars/gpu-prices/) [2026-10-10](https://www.cloudpe.com/blog/why-gpu-prices-spike-ai-compute-shortages/) |
| H08 | Posted prices revert toward their 30-day median. | spot-pricing literature cited in the brief | +0.0196 (0.99) | +0.0129 (0.99) | **kept** | [2026-09-24](https://www.silicondata.com/blog/b200-rental-price-august-2026-update) [2026-11-02](https://www.insigtx.com/en/news/h100-rental-prices-show-signs-of-easing-this-week-about-19-504193/) [2026-10-15](https://explainx.ai/blog/nvidia-b300-gpu-rental-prices-record-high-17-day-streak-compute-desk-claimed-vs-verified-2026) |
| H09 | The direction of the last step predicts the next one. | trend persistence (X-046) | +0.0522 (1.00) | +0.0199 (0.99) | **kept** |  |
| H10 | A provider entering or leaving the sample moves the median: a composition effect, not a price change. | brief: pooled medians move with the provider mix | -0.0038 (0.01) | not run | rejected on dev | [2026-11-04](https://novapod.io/blog/h100-rental-price-november-4-2026) |
| H11 | Collectors lag each other: when the same GPU moved in another collector, this one follows. | five collectors sample overlapping providers | -0.0043 (0.02) | not run | rejected on dev | [2026-10-24](https://www.linkedin.com/posts/a16z_zooming-out-gpus-are-still-renting-ahead-activity-7519778481266864129-LS8n) [2026-11-02](https://www.insigtx.com/en/news/h100-rental-prices-show-signs-of-easing-this-week-about-19-504193/) [2026-09-26](https://www.adamsioud.com/exemplars/gpu-prices/) |
| H12 | New-generation rate cards (B200, B300, H200) lead older chips. | X-047: newest-generation prices rising sharply | -0.0121 (0.02) | not run | rejected on dev | [2026-10-15](https://explainx.ai/blog/nvidia-b300-gpu-rental-prices-record-high-17-day-streak-compute-desk-claimed-vs-verified-2026) [2026-09-17](https://substack.com/@dhruva/note/c-339031770) [2026-09-25](https://www.datagravity.dev/p/the-gpu-depreciation-curve-is-broken) |
| H13 | Empirical intervals are too narrow: widen all by 25%. | starter kit: drift coverage 0.75 against a 0.80 target | -0.0213 (0.00) | not run | rejected on dev |  |
| H14 | Empirical intervals are too wide for step series: narrow all by 20%. | brief: rate cards rarely move inside a week | -0.0045 (0.23) | not run | rejected on dev |  |
| H15 | Ten past windows are enough to leave the flat forecast. | short histories in the pack | +0.0000 (0.00) | not run | rejected on dev |  |
| H16 | A posted price is a step process, so a quantile should be a change that really happened, never an interpolated one. | brief: one H100 rate-card median took six values in 235 days | -0.0002 (0.17) | not run | rejected on dev | [2026-10-17](https://www.tokenpost.com/news/technology/33728) [2026-10-29](https://dilikogluresearch.com/reports/old-gpu-worth-2026-10-29) |
| H17 | The method can tell where it is failing: grade its own last 45 days per series and abstain where it lost to the last value. | brief, direction A: learn from previous predictions; teams choose which series to forecast | +0.0330 (1.00) | -0.0148 (0.00) | rejected at the gate |  |
| H18 | A series should stay on its last value until the method has a winning record on it. | escalation idea: defer by default, act when earned | -0.0095 (0.35) | not run | rejected on dev |  |
| H19 | Prices are rising, so the upside tail is fatter than history says: stretch it by 25%. | X sweep: rental indices at highs (X-045 to X-048) | -0.0223 (0.00) | not run | rejected on dev | [2026-10-24](https://charg.cloud/articles/gpu-rental-vs-depreciation) [2026-10-23](https://dealroom.co/news/x-2113741008550990191-a16z-gpu-rental-prices-are-up-across-the-board-in-2026-even-for-six-year/) |
| H20 | Downward steps are rarer now than in the past: shrink the downside tail by 20%. | same as H19 | -0.0065 (0.00) | not run | rejected on dev | [2026-10-24](https://wccftech.com/nvidia-gpus-appreciating-assets-a100-rental-premium/) |
| H21 | Tail levels should learn from the method's own misses (adaptive conformal, rate 0.02). | brief, direction A; adaptive conformal inference | +0.0021 (0.69) | not run | rejected on dev |  |
| H22 | A posted median flickers around a level, so forecast from the 3-day median level instead of the last print. | error analysis: 97% of the loss sits in cells where the price moved | -0.2654 (0.00) | not run | rejected on dev |  |
| H23 | Volatility clusters: rescale past changes by how volatile the series is now versus then. | spot-pricing literature cited in the brief | -0.0248 (0.00) | not run | rejected on dev | [2026-10-10](https://www.cloudpe.com/blog/why-gpu-prices-spike-ai-compute-shortages/) |
| H24 | A series that rose over the last two weeks keeps rising. | X sweep: trend persistence into November (X-046) | -0.0173 (0.00) | not run | rejected on dev | [2026-10-19](https://www.aiminingco.com/insights/gpu-h100-sxm-deep-dive-week-of-october-12-2026) |
| H25 | When a whole instrument class has been rising for a week, its members keep stepping up. | X sweep: providers raising prices together (X-049) | -0.0161 (0.00) | not run | rejected on dev | [2026-10-19](https://www.aiminingco.com/insights/gpu-h100-sxm-deep-dive-week-of-october-12-2026) |
| H26 | Weeks with more public news about GPU price rises than price cuts are followed by upward steps. | Exa: weekly counts of dated articles, each published before the forecast origin | n/a | not run | not testable: Exa returned its 25-result cap in every week, so the count carries no signal |  |
| R1.01 | lookback of 60 days | refinement of the accepted method | -0.0934 (0.00) | not run | rejected on dev |  |
| R1.02 | lookback of 90 days | refinement of the accepted method | -0.0218 (0.00) | not run | rejected on dev |  |
| R1.03 | lookback of 180 days | refinement of the accepted method | +0.0009 (0.93) | -0.0003 (0.28) | rejected at the gate |  |
| R1.04 | half-life of 30.0 days | refinement of the accepted method | -0.0293 (0.00) | not run | rejected on dev |  |
| R1.05 | half-life of 90.0 days | refinement of the accepted method | -0.0054 (0.01) | not run | rejected on dev |  |
| R1.06 | minimum sample of 5.0 | refinement of the accepted method | +0.0000 (0.00) | not run | rejected on dev |  |
| R1.08 | minimum sample of 40.0 | refinement of the accepted method | -0.1197 (0.00) | not run | rejected on dev |  |
| R1.09 | pooled windows worth 5.0 observations | refinement of the accepted method | -0.1036 (0.00) | not run | rejected on dev |  |
| R1.10 | pooled windows worth 10.0 observations | refinement of the accepted method | -0.0526 (0.00) | not run | rejected on dev |  |
| R1.11 | pooled windows worth 40.0 observations | refinement of the accepted method | -0.0083 (0.06) | not run | rejected on dev |  |
| R1.12 | weight 0.0 on windows whose deviation state differs | refinement of the accepted method | -0.0470 (0.00) | not run | rejected on dev |  |
| R1.13 | weight 0.6 on windows whose deviation state differs | refinement of the accepted method | +0.0027 (0.81) | -0.0137 (0.00) | rejected at the gate |  |
| R1.14 | weight 0.0 on windows whose last_dir state differs | refinement of the accepted method | -0.0444 (0.00) | not run | rejected on dev |  |
| R1.15 | weight 0.6 on windows whose last_dir state differs | refinement of the accepted method | -0.0207 (0.00) | not run | rejected on dev |  |
| R1.22 | tail scale down x1.0, up x0.8 | refinement of the accepted method | +0.0020 (0.69) | not run | rejected on dev |  |
| R1.24 | tail scale down x1.25, up x1.0 | refinement of the accepted method | +0.0010 (0.71) | not run | rejected on dev |  |
| R1.25 | adaptive tail rate 0.01 | refinement of the accepted method | +0.0105 (1.00) | -0.0115 (0.00) | rejected at the gate |  |
| R1.26 | adaptive tail rate 0.05 | refinement of the accepted method | -0.0077 (0.12) | not run | rejected on dev |  |
| R1.27 | interval width x0.6 for aggregator_cheapest | refinement of the accepted method | +0.0022 (1.00) | -0.0049 (0.00) | rejected at the gate |  |
| R1.28 | interval width x0.8 for aggregator_cheapest | refinement of the accepted method | +0.0012 (1.00) | -0.0024 (0.00) | rejected at the gate |  |
| R1.29 | interval width x1.25 for aggregator_cheapest | refinement of the accepted method | -0.0019 (0.00) | not run | rejected on dev |  |
| R1.30 | interval width x1.5 for aggregator_cheapest | refinement of the accepted method | -0.0038 (0.00) | not run | rejected on dev |  |
| R1.31 | interval width x0.6 for hyperscaler_list | refinement of the accepted method | +0.0016 (1.00) | -0.0022 (0.00) | rejected at the gate |  |
| R1.32 | interval width x0.8 for hyperscaler_list | refinement of the accepted method | +0.0008 (1.00) | -0.0011 (0.00) | rejected at the gate |  |
| R1.33 | interval width x1.25 for hyperscaler_list | refinement of the accepted method | -0.0010 (0.00) | not run | rejected on dev |  |
| R1.34 | interval width x1.5 for hyperscaler_list | refinement of the accepted method | -0.0021 (0.00) | not run | rejected on dev |  |
| R1.35 | interval width x0.6 for hyperscaler_spot | refinement of the accepted method | -0.0102 (0.00) | not run | rejected on dev |  |
| R1.36 | interval width x0.8 for hyperscaler_spot | refinement of the accepted method | -0.0042 (0.00) | not run | rejected on dev |  |
| R1.37 | interval width x1.25 for hyperscaler_spot | refinement of the accepted method | +0.0013 (0.89) | -0.0000 (0.46) | rejected at the gate |  |
| R1.38 | interval width x1.5 for hyperscaler_spot | refinement of the accepted method | -0.0008 (0.35) | not run | rejected on dev |  |
| R1.39 | interval width x0.6 for marketplace_ask | refinement of the accepted method | -0.0397 (0.00) | not run | rejected on dev |  |
| R1.40 | interval width x0.8 for marketplace_ask | refinement of the accepted method | -0.0169 (0.00) | not run | rejected on dev |  |
| R1.41 | interval width x1.25 for marketplace_ask | refinement of the accepted method | +0.0001 (0.51) | not run | rejected on dev |  |
| R1.42 | interval width x1.5 for marketplace_ask | refinement of the accepted method | -0.0103 (0.01) | not run | rejected on dev |  |
| R1.43 | interval width x0.6 for neocloud_rate_card | refinement of the accepted method | +0.0204 (1.00) | -0.0098 (0.00) | rejected at the gate |  |
| R1.44 | interval width x0.8 for neocloud_rate_card | refinement of the accepted method | +0.0107 (1.00) | -0.0044 (0.00) | rejected at the gate |  |
| R1.45 | interval width x1.25 for neocloud_rate_card | refinement of the accepted method | -0.0144 (0.00) | not run | rejected on dev |  |
| R1.46 | interval width x1.5 for neocloud_rate_card | refinement of the accepted method | -0.0299 (0.00) | not run | rejected on dev |  |
| R1.47 | interval width x0.6 for neocloud_spot | refinement of the accepted method | +0.0077 (1.00) | -0.0063 (0.00) | rejected at the gate |  |
| R1.48 | interval width x0.8 for neocloud_spot | refinement of the accepted method | +0.0040 (1.00) | -0.0029 (0.00) | rejected at the gate |  |
| R1.49 | interval width x1.25 for neocloud_spot | refinement of the accepted method | -0.0053 (0.00) | not run | rejected on dev |  |
| R1.50 | interval width x1.5 for neocloud_spot | refinement of the accepted method | -0.0114 (0.00) | not run | rejected on dev |  |
