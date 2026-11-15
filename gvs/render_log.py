"""Render the research log as a Markdown table, one row per hypothesis tested."""
from __future__ import annotations

import json
import sys

rows = [json.loads(line) for line in open(sys.argv[1])]
kept = [r for r in rows if r["verdict"] == "kept"]
dev_pass = [r for r in rows if r["gate_gain"] is not None]
print(f"# Research log\n\n{len(rows)} hypotheses tested, {len(dev_pass)} improved the development dates, "
      f"{len(kept)} also improved the unseen gate dates and were kept.\n")
print("| ID | Hypothesis | Where it came from | Dev gain (p) | Gate gain (p) | Verdict |\n| --- | --- | --- | --- | --- | --- |")
for r in rows:
    gate = "not run" if r["gate_gain"] is None else f"{r['gate_gain']:+.4f} ({r['gate_p']:.2f})"
    verdict = f"**{r['verdict']}**" if r["verdict"] == "kept" else r["verdict"]
    print(f"| {r['id']} | {r['claim']} | {r['source']} | {r['dev_gain']:+.4f} ({r['dev_p']:.2f}) | {gate} | {verdict} |")
