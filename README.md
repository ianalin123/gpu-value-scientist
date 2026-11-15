# GPU Value Scientist

Track 2 (Recursive Self-Improvement by Pacific: An AI Scientist for GPU Value), SF AI Research Hackathon, November 14 to 15, 2026. Direction A, self-improving forecasts.

A research loop that proposes hypotheses about what moves posted GPU rental prices, tests each one on dates it is allowed to see, and keeps a change only if it also improves forecasts on dates it has never seen. It forecasts the 0.1, 0.5 and 0.9 quantiles of posted rental medians 1, 3 and 7 days ahead.

## Result

Scored once, after the loop stopped, on forecast origins from October 20 to 30, 2026 that the loop never used (5,451 forecast cells, every posted series that moves):

| Method | Pooled skill vs last value | Coverage of the 80% interval |
| --- | --- | --- |
| Starter kit `drift` baseline, run unchanged | +0.204 | 0.78 |
| This system's final method | **+0.251** | 0.81 |

The gain over `drift` is +0.047 skill, with a 90% bootstrap interval of +0.030 to +0.062 (resampling whole origin dates).

The organisers' own `scorer.py`, in frozen mode at their demo cutoff of October 24, 2026 with history truncated at the cutoff, gives +0.303 for this method against +0.242 for `drift` on the 183 posted series that move. On the 17 posted series in the headline tier at that cutoff it gives +0.221 against +0.228: no gain on that small set (51 cells).

Of 67 hypotheses tested, 21 improved the development dates. Only 3 of those also improved the unseen gate dates and were kept. The other 18 would have been accepted by a loop without a held-out gate. The full record is [results/research_log.md](results/research_log.md), and the findings are in [FINDINGS.md](FINDINGS.md).

## Reproduce

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
PYTHON=.venv/bin/python bash reproduce.sh /path/to/gpu-price-pack-v0.1.1-handover out
```

That one command rebuilds the series from the pack, reruns the research loop from an empty memory (about 5 minutes on a laptop CPU), scores the surviving method on the lockbox, checks it with the organisers' scorer, and writes `out/forecast_2026-11-06.csv`. It reads only the pack. No network, no GPU, no API key.

The submitted forecast is [results/forecast_2026-11-06.csv](results/forecast_2026-11-06.csv): origin 2026-11-06, horizons 1, 3 and 7, all 592 posted rental series in the pack. 174 series get a non-flat forecast; the rest are held at their last value because they have not moved in 90 days or have too little history.

## How it works

**The forecaster** ([gvs/core.py](gvs/core.py)). A forecast for a series is the weighted empirical distribution of its own past h-day log changes. Every hypothesis is a rule for re-weighting those past windows: by age, by borrowing windows from similar series, or by whether the market was in the same observable state then as now (above or below its 30-day median, direction of the last step, offer count rising or falling, and so on). Nothing dated after the forecast origin is read.

**The loop** ([gvs/scientist.py](gvs/scientist.py)). Three sets of forecast origins were fixed before any score was looked at:

| Set | Origins | Who sees the scores |
| --- | --- | --- |
| dev | April 1 to September 16, 2026 | The proposer. It uses them to decide what to try next |
| gate | September 24 to October 12, 2026 | Only the accept-or-reject test |
| lockbox | October 20 to 30, 2026 | Nobody until the loop has stopped |

A hypothesis is kept only if it improves pooled skill on dev (bootstrap probability of a gain at least 0.80) and on gate (at least 0.90). After the 21 seed hypotheses, the loop proposes one-step refinements of whatever it has accepted and repeats until a full round produces nothing that survives. Every verdict is appended to a log, which the next run reads first so a rejected idea is not retried.

**The report** ([gvs/report.py](gvs/report.py)) scores the final method once on the lockbox against the organisers' `baselines.py`, run unchanged on the same cells.

## Files

| Path | What it is |
| --- | --- |
| `reproduce.sh` | The one command |
| `gvs/core.py` | Data panel, market states, forecaster, pinball scoring, bootstrap |
| `gvs/scientist.py` | Hypotheses, refinement proposals, the dev and gate tests, the log |
| `gvs/report.py` | Lockbox scoring and the event forecast writer |
| `gvs/experiments.py` | Direct tests of each market-state hypothesis |
| `gvs/frozen_check.py` | Our forecast from a truncated history, for the organisers' frozen scorer |
| `results/` | Outputs of the run submitted: forecast, scores, research log, state experiments |
| `ATTRIBUTION.md` | The data pack's attribution file, kept with this work as its licence asks |

## Limits, stated plainly

- **The proposer is not a language model.** The 21 seed hypotheses were written before the loop ran, by the team working with an AI coding agent, from the track brief and a sweep of recent public discussion. The loop then tests, accepts, rejects and refines on its own. An LLM proposer would plug in where `seed_hypotheses` and `refinements` are called.
- **The split dates were moved once.** The first draft put dev in April to August. Counting series per day (not scores) showed most collectors in the pack only start in late summer, so the splits were moved to where the scored series have data. An early smoke test of two methods also included one lockbox date, October 21, among 15 weekly origins.
- **The lockbox is 11 consecutive days.** Forecasts at 1, 3 and 7 days from neighbouring origins overlap, so the bootstrap interval is approximate.
- **Posted prices are asks, not transactions.** Every number here is about what providers list.
- **AWS spot series are not forecast.** The brief says they have no November truth and are not scored on Sunday.
- **The event forecast is unscored.** Truth for November 7, 9 and 13 was not available to us.
- **No sponsor API is used.** Modal, Exa and past.dev were not integrated in the time available.

## Credits

Data: Pacific Machines (2026), gpu-price-pack v0.1.1-handover, data cutoff 6 November 2026, CC BY 4.0 on the compilation; see [ATTRIBUTION.md](ATTRIBUTION.md) for every source. Baselines and scorer: the pack's starter kit, run unchanged. Libraries: pandas, numpy, duckdb. Code written during the event with an AI coding agent (Claude Code).
