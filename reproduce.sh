#!/usr/bin/env bash
# One command: rebuild the series from the pack, rerun the research loop from an empty research log,
# score the surviving method once on the lockbox, check it with the organisers' scorer at their
# demo cutoff, and write the forecast file for the event origin (2026-11-06, horizons 1, 3, 7).
# Usage: bash reproduce.sh <path to gpu-price-pack-v0.1.1-handover> [out_dir]
set -euo pipefail
PACK="${1:?usage: reproduce.sh <pack_dir> [out_dir]}"
OUT="${2:-out}"
PY="${PYTHON:-python3}"
STARTER="$PACK/starter"
DEMO_CUTOFF=2026-10-24
EVENT_ORIGIN=2026-11-06
mkdir -p "$OUT/frozen"
export PYTHONDONTWRITEBYTECODE=1

echo "== 1. series from the pack (posted rental medians; nothing is dated after $EVENT_ORIGIN)"
$PY -I -B "$STARTER/build_series.py" --pack "$PACK" --out "$OUT/series_daily.csv" --catalog "$OUT/series_catalog.csv" --as-of "$EVENT_ORIGIN"
$PY -I -B "$STARTER/build_series.py" --pack "$PACK" --cutoff "$DEMO_CUTOFF" --members-from "$OUT/series_catalog.csv" \
    --out "$OUT/frozen/history_$DEMO_CUTOFF.csv" --catalog "$OUT/frozen/catalog_$DEMO_CUTOFF.csv"

echo "== 2. research loop (dev and gate origins only; about 5 minutes)"
rm -f "$OUT/research_log.jsonl"
# The scout reads dated web evidence through Exa (served from results/exa_cache.json when there is no key),
# and the agents share one memory on past.dev (a local file stands in when there is no key).
rm -f "$OUT/memory_log.jsonl"
$PY -m gvs.scientist --series "$OUT/series_daily.csv" --catalog "$OUT/series_catalog.csv" \
    --log "$OUT/research_log.jsonl" --out-config "$OUT/final_config.json" \
    --scout --news results/exa_news_weekly.csv --memory-log "$OUT/memory_log.jsonl"
$PY -m gvs.render_log "$OUT/research_log.jsonl" > "$OUT/research_log.md"

echo "== 3. lockbox score against the organisers' drift baseline, and the event forecast"
$PY -m gvs.report --pack "$PACK" --series "$OUT/series_daily.csv" --catalog "$OUT/series_catalog.csv" \
    --config "$OUT/final_config.json" --origin "$EVENT_ORIGIN" --out "$OUT" > "$OUT/report.log"
$PY -m gvs.experiments --series "$OUT/series_daily.csv" --catalog "$OUT/series_catalog.csv" --out "$OUT/state_experiments.json" > "$OUT/state_experiments.txt"

echo "== 4. organisers' scorer, frozen at $DEMO_CUTOFF (a lockbox date), history truncated at the cutoff"
$PY -m gvs.frozen_check --history "$OUT/frozen/history_$DEMO_CUTOFF.csv" --catalog "$OUT/frozen/catalog_$DEMO_CUTOFF.csv" \
    --config "$OUT/final_config.json" --cutoff "$DEMO_CUTOFF" --out "$OUT/frozen"
for set in headline_posted moving_posted; do
  $PY -I -B "$STARTER/baselines.py" --history "$OUT/frozen/history_$DEMO_CUTOFF.csv" --origin "$DEMO_CUTOFF" --method drift --frozen \
      --horizons 1,3,7 --series-ids "@$OUT/frozen/ids_$set.txt" --out "$OUT/frozen/drift_$set.csv" > /dev/null
  for m in "drift_$set" ours; do
    $PY -I -B "$STARTER/scorer.py" --forecast "$OUT/frozen/$m.csv" --truth "$OUT/series_daily.csv" \
        --history "$OUT/frozen/history_$DEMO_CUTOFF.csv" --frozen-cutoff "$DEMO_CUTOFF" --series-ids "@$OUT/frozen/ids_$set.txt" \
        --horizons 1,3,7 --out "$OUT/frozen/report_${m}_$set.json" | sed "s/^/[$set | $m] /"
  done
done

echo "== 5. validate the event forecast file with the organisers' scorer (no truth exists yet, so nothing is scored)"
$PY -I -B "$STARTER/scorer.py" --forecast "$OUT/forecast_$EVENT_ORIGIN.csv" --truth "$OUT/series_daily.csv" \
    --history "$OUT/series_daily.csv" --frozen-cutoff "$EVENT_ORIGIN" --horizons 1,3,7 --out "$OUT/event_forecast_validation.json" || true
echo "done: $OUT/forecast_$EVENT_ORIGIN.csv, $OUT/results.json, $OUT/research_log.md"
