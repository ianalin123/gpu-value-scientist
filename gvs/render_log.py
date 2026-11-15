"""Render the research log as a Markdown table, one row per hypothesis tested."""
from __future__ import annotations

import json
import sys

rows = [json.loads(line) for line in open(sys.argv[1])]
tested = [r for r in rows if r["dev_gain"] is not None]
kept = [r for r in tested if r["verdict"] == "kept"]
dev_pass = [r for r in tested if r["gate_gain"] is not None]
print(f"# Research log\n\n{len(tested)} hypotheses tested, {len(dev_pass)} improved the development dates, "
      f"{len(kept)} also improved the unseen gate dates and were kept.\n")
print("| ID | Hypothesis | Where it came from | Dev gain (p) | Gate gain (p) | Verdict | Web evidence the proposer read |\n"
      "| --- | --- | --- | --- | --- | --- | --- |")
for r in rows:
    dev = "n/a" if r["dev_gain"] is None else f"{r['dev_gain']:+.4f} ({r['dev_p']:.2f})"
    gate = "not run" if r["gate_gain"] is None else f"{r['gate_gain']:+.4f} ({r['gate_p']:.2f})"
    verdict = f"**{r['verdict']}**" if r["verdict"] == "kept" else r["verdict"]
    cites = " ".join(f"[{e['published']}]({e['url']})" for e in r.get("web_evidence") or [] if e.get("url"))
    print(f"| {r['id']} | {r['claim']} | {r['source']} | {dev} | {gate} | {verdict} | {cites} |")
