# GPU Value Scientist

Track 2 (Recursive Self-Improvement by Pacific: An AI Scientist for GPU Value), SF AI Research Hackathon, November 14 to 15, 2026. Direction A, self-improving forecasts.

A research loop that proposes hypotheses about what moves posted GPU rental prices, tests each one on dates it is allowed to see, and keeps a change only if it also improves forecasts on dates it has never seen. It starts from hypotheses we wrote, refines what survives, and then a language model reads the results and writes its own. It forecasts the 0.1, 0.5 and 0.9 quantiles of posted rental medians 1, 3 and 7 days ahead.

## Result

Scored once, after the loop stopped, on forecast origins from October 20 to 30, 2026 that the loop never used (5,451 forecast cells, every posted series that moves):

| Method | Pooled skill vs last value | Coverage of the 80% interval |
| --- | --- | --- |
| Starter kit `drift` baseline, run unchanged | +0.204 | 0.78 |
| This system's final method | **+0.251** | 0.81 |

The gain over `drift` is +0.047 skill, with a 90% bootstrap interval of +0.030 to +0.062 (resampling whole origin dates).

The organisers' own `scorer.py`, in frozen mode at their demo cutoff of October 24, 2026 with history truncated at the cutoff, gives +0.303 for this method against +0.242 for `drift` on the 183 posted series that move. On the 17 posted series in the headline tier at that cutoff it gives +0.221 against +0.228: no gain on that small set (51 cells).

Of 80 hypotheses tested, 19 improved the development dates. Only 3 of those also improved the unseen gate dates and were kept. The other 16 would have been accepted by a loop without a held-out gate. 13 of the 80 were written by a language model, not by us; none of those survived. The full record is [results/research_log.md](results/research_log.md), and the findings are in [FINDINGS.md](FINDINGS.md).

## Reproduce

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
PYTHON=.venv/bin/python bash reproduce.sh /path/to/gpu-price-pack-v0.1.1-handover out
```

That one command rebuilds the series from the pack, reruns the research loop from an empty research log (about 12 minutes on a laptop CPU with the agents' memory on past.dev, less without), scores the surviving method on the lockbox, checks it with the organisers' scorer, and writes `out/forecast_2026-11-06.csv`. No GPU is needed.

Keys are optional. With `PAST_API_KEY` and `EXA_API_KEY` in the environment or in a git-ignored `.env`, the agents share memory on past.dev and the scout can run new Exa searches. Without them the same command runs offline: the scout serves its searches from `results/exa_cache.json` and a local file stands in for the shared memory. The forecast and the scores are the same either way.

The submitted forecast is [results/forecast_2026-11-06.csv](results/forecast_2026-11-06.csv): origin 2026-11-06, horizons 1, 3 and 7, all 592 posted rental series in the pack. 174 series get a non-flat forecast; the rest are held at their last value because they have not moved in 90 days or have too little history.

## How it works

**The forecaster** ([gvs/core.py](gvs/core.py)). A forecast for a series is the weighted empirical distribution of its own past h-day log changes. Every hypothesis is a rule for re-weighting those past windows: by age, by borrowing windows from similar series, or by whether the market was in the same observable state then as now (above or below its 30-day median, direction of the last step, offer count rising or falling, and so on). Nothing dated after the forecast origin is read.

**The loop** ([gvs/scientist.py](gvs/scientist.py)). Three sets of forecast origins were fixed before any score was looked at:

| Set | Origins | Who sees the scores |
| --- | --- | --- |
| dev | April 1 to September 16, 2026 | The proposer. It uses them to decide what to try next |
| gate | September 24 to October 12, 2026 | Only the accept-or-reject test |
| lockbox | October 20 to 30, 2026 | Nobody until the loop has stopped |

A hypothesis is kept only if it improves pooled skill on dev (bootstrap probability of a gain at least 0.80) and on gate (at least 0.90). The loop has three stages: 26 seed hypotheses written by us; one-step mechanical refinements of whatever has been accepted, repeated until a full round produces nothing that survives; then two rounds in which a language model writes the hypotheses. Every verdict is appended to a log, which the next run reads first so a rejected idea is not retried.

**The language-model proposer** ([gvs/llm_proposer.py](gvs/llm_proposer.py)). The model is shown the accepted method, every seed result with its development gain and verdict (never a gate score), and the error analysis, and is asked for eight new hypotheses about what moves posted prices. It must answer in a small typed grammar of edits to the forecaster, so every proposal is backtestable and nothing it claims is trusted without the dev and gate tests. Its second round also sees how its first round did. In the submitted run the model (Claude Opus 5.5, through the `claude` command line, with no web access) proposed 16 hypotheses; 3 duplicated methods already tested, and 13 were run. Two improved the development dates, both by narrowing rate-card intervals, and both failed the gate, the same trap the mechanical refinements fell into. None was kept. Its claims, rationales and edits are in the research log, and its raw answers are in [results/llm_cache.json](results/llm_cache.json), from which a rerun without any model replays the same proposals.

**The agents and their shared memory** ([gvs/memory.py](gvs/memory.py), past.dev). Five roles write to and read from one memory:

| Agent | Writes | Reads |
| --- | --- | --- |
| scout | 33 dated web results found through Exa | |
| proposer | | The scout's evidence before each seed hypothesis; the critic's verdicts before each refinement round |
| experimenter | The development-date result of every test | |
| critic | The verdict on every test | |
| reporter | | The critic's kept verdicts and the scout's evidence, for the end-of-run summary |

In the submitted run, three agents made 167 writes and two agents made 29 recalls, every call served by past.dev. All 52 recalled items had been written by a different agent. The proposer used what it read: before the refinement round it recalled the critic's verdicts, saw that self-grading had been rejected on unseen dates, and skipped the 4 refinements of it. Every write and recall is mirrored in [results/memory_log.jsonl](results/memory_log.jsonl), and the reporter's summary is [results/memory_report.md](results/memory_report.md). Did memory improve the result? It saved 4 backtests and changed no verdict. What past.dev returns for a query varies a little from run to run (an earlier run recalled 130 items and also flagged a second rejected idea), but the accepted method and the forecast file are byte-identical with past.dev, with the local fallback, and with no memory at all.

**The scout** ([gvs/scout.py](gvs/scout.py), Exa). Every search is bounded by published date, so nothing dated after a forecast origin is used, and a result whose text names a later date is dropped because Exa's excerpt comes from its latest crawl (3 of 36 were). The proposer attaches the evidence it read to each hypothesis: the last column of [results/research_log.md](results/research_log.md) links the sources. The sources are listed in [results/exa_evidence.md](results/exa_evidence.md), and they back the long-run argument in the findings. Published files keep each source's headline, link, date and an excerpt of at most 160 characters. One Exa-driven hypothesis could not be tested: weekly counts of price-rise and price-cut articles hit the 25-result cap in every week, so the count carries no signal. It is logged as not testable.

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
| `gvs/llm_proposer.py` | The language-model proposer: prompt, typed edit grammar, validation, response cache |
| `gvs/memory.py` | Shared agent memory on past.dev, with a local fallback and a full call log |
| `gvs/scout.py` | Dated web search through Exa, cached on disk, with the date-leak filter |
| `gvs/check_integrations.py` | A three-agent write and cross-read check against the real past.dev API |
| `results/` | Outputs of the run submitted: forecast, scores, research log, state experiments |
| `ATTRIBUTION.md` | The data pack's attribution file, kept with this work as its licence asks |

## Limits, stated plainly

- **Everything that was kept came from the seed list.** The 26 seed hypotheses were written by the team working with an AI coding agent, from the track brief, a sweep of recent public discussion and an error analysis of the first run. The language model's 13 hypotheses were all rejected, so its contribution to the result is evidence that the remaining headroom is not easy to reach, not a better forecast. It also chooses within a fixed grammar of edits; it cannot invent a new kind of model.
- **Web evidence informs and documents; it does not decide.** The scout's evidence is read by the proposer and cited per hypothesis, but acceptance depends only on the backtests. The evidence is dated up to November 6, 2026, so it could not be used to choose a method for earlier backtest dates without leaking, and it was not.
- **The lockbox was scored after each of three versions of the loop.** After the first run, after five more seed hypotheses were added, and after the language-model rounds were added. Every added hypothesis was rejected, the accepted method never changed, and the lockbox numbers are identical each time.
- **The split dates were moved once.** The first draft put dev in April to August. Counting series per day (not scores) showed most collectors in the pack only start in late summer, so the splits were moved to where the scored series have data. An early smoke test of two methods also included one lockbox date, October 21, among 15 weekly origins.
- **The lockbox is 11 consecutive days.** Forecasts at 1, 3 and 7 days from neighbouring origins overlap, so the bootstrap interval is approximate.
- **Posted prices are asks, not transactions.** Every number here is about what providers list.
- **AWS spot series are not forecast.** The brief says they have no November truth and are not scored on Sunday.
- **The event forecast is unscored.** Truth for November 7, 9 and 13 was not available to us.
- **Modal is not used.** Everything runs on a laptop CPU.

## Credits

Data: Pacific Machines (2026), gpu-price-pack v0.1.1-handover, data cutoff 6 November 2026, CC BY 4.0 on the compilation; see [ATTRIBUTION.md](ATTRIBUTION.md) for every source. Baselines and scorer: the pack's starter kit, run unchanged. Libraries: pandas, numpy, duckdb. Services: Exa (web search), past.dev (agent memory). Language model for the proposer rounds: Claude Opus 5.5 (Anthropic), called through the `claude` command line; any OpenAI-compatible endpoint can be used instead by setting `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL`. Code written during the event with an AI coding agent (Claude Code).
