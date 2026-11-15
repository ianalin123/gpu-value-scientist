"""Run the research loop under several acceptance rules at once on Modal, one container per rule.

    modal run modal_ablation.py

The question: does the held-out gate produce better forecasts, or does it only reject more ideas?
Each container reruns the whole loop (seed hypotheses, then one round of refinements) from an empty
log under one rule. The final methods are then scored locally on the lockbox with gvs.ablation.
"""
import json
import os

import modal

app = modal.App("gpu-value-scientist-ablation")
DATA = os.environ.get("GVS_DATA", "out")
image = (modal.Image.debian_slim(python_version="3.12").pip_install("pandas", "numpy")
         .add_local_dir("gvs", "/root/gvs")
         .add_local_file(f"{DATA}/series_daily.csv", "/root/data/series_daily.csv")
         .add_local_file(f"{DATA}/series_catalog.csv", "/root/data/series_catalog.csv"))

RULES = [("gate_p90", "gate", 0.90), ("gate_p80", "gate", 0.80), ("gate_p95", "gate", 0.95), ("gate_any_gain", "gate", 0.0),
         ("dev_only", "dev_only", 0.0)]


@app.function(image=image, cpu=2, memory=4096, timeout=3000)
def run_rule(name: str, rule: str, gate_p: float) -> dict:
    import sys
    sys.path.insert(0, "/root")
    from gvs.scientist import run
    log = f"/tmp/{name}.jsonl"
    final = run("/root/data/series_daily.csv", "/root/data/series_catalog.csv", log, max_rounds=1, accept_rule=rule, gate_p=gate_p)
    return {"name": name, "rule": rule, "gate_p": gate_p, "config": json.loads(final.to_json()), "log": open(log).read()}


@app.local_entrypoint()
def main(out: str = "results/ablation"):
    os.makedirs(out, exist_ok=True)
    for result in run_rule.starmap(RULES, order_outputs=False):
        with open(os.path.join(out, f"{result['name']}_research_log.jsonl"), "w") as f:
            f.write(result.pop("log"))
        with open(os.path.join(out, f"{result['name']}.json"), "w") as f:
            json.dump(result, f, indent=1)
        print("finished", result["name"])
