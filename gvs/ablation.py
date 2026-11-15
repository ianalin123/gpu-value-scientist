"""Does the held-out gate produce better forecasts, or does it only reject more ideas?

Scores the final method of each acceptance rule (run by modal_ablation.py) on the lockbox dates.
"""
from __future__ import annotations

import argparse
import glob
import json
import os

from gvs.core import Panel, paired_gain, pooled_skill
from gvs.scientist import DEV, GATE, LOCKBOX, config_from_json, evaluate, in_span

LABEL = {"dev_only": "No gate: keep anything that improves the development dates",
         "gate_any_gain": "Gate, any gain on unseen dates", "gate_p80": "Gate, 80% confidence",
         "gate_p90": "Gate, 90% confidence (the submitted rule)", "gate_p95": "Gate, 95% confidence"}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--dir", default="results/ablation")
    args = ap.parse_args()
    panel = Panel(args.series, args.catalog)
    rows, cells = [], {}
    for path in sorted(glob.glob(os.path.join(args.dir, "*.json"))):
        r = json.load(open(path))
        if "config" not in r:
            continue
        log = [json.loads(line) for line in open(os.path.join(args.dir, f"{r['name']}_research_log.jsonl"))]
        full = evaluate(panel, config_from_json(r["config"]), LOCKBOX[1])
        cells[r["name"]] = in_span(full, LOCKBOX)
        rows.append({"rule": r["name"], "label": LABEL.get(r["name"], r["name"]),
                     "hypotheses_tested": sum(1 for e in log if e["dev_gain"] is not None),
                     "kept": sum(1 for e in log if e["verdict"] == "kept"),
                     "dev_skill": round(pooled_skill(in_span(full, DEV)), 4), "gate_skill": round(pooled_skill(in_span(full, GATE)), 4),
                     "lockbox_skill": round(pooled_skill(cells[r["name"]]), 4),
                     "lockbox_coverage": round(float(cells[r["name"]].inside.mean()), 3)})
    out = {"rows": rows}
    if "gate_p90" in cells and "dev_only" in cells:
        out["gate_p90_minus_dev_only_on_lockbox"] = {k: round(v, 4) for k, v in paired_gain(cells["gate_p90"], cells["dev_only"]).items()}
    json.dump(out, open(os.path.join(args.dir, "summary.json"), "w"), indent=1)
    print("| Acceptance rule | Tested | Kept | Dev skill | Gate skill | Lockbox skill | Lockbox coverage |\n| --- | --- | --- | --- | --- | --- | --- |")
    for r in sorted(rows, key=lambda r: r["rule"]):
        print(f"| {r['label']} | {r['hypotheses_tested']} | {r['kept']} | {r['dev_skill']:+.3f} | {r['gate_skill']:+.3f} | {r['lockbox_skill']:+.3f} | {r['lockbox_coverage']:.2f} |")
    print(json.dumps(out.get("gate_p90_minus_dev_only_on_lockbox")))
