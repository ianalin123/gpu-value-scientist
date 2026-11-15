"""Gate versus no gate across many orderings of the hypothesis list, all at once on Modal.

    modal run modal_orderings.py

The loop is greedy, so one run is one path. Here the gated loop and the no-gate loop are each rerun
from an empty log under N random orderings of the seed hypotheses, one container per run, and each
container scores its own final method on the lockbox dates.
"""
import json
import os

import modal

app = modal.App("gpu-value-scientist-orderings")
DATA = os.environ.get("GVS_DATA", "out")
N = int(os.environ.get("GVS_ORDERINGS", "10"))
START = int(os.environ.get("GVS_ORDER_START", "0"))
image = (modal.Image.debian_slim(python_version="3.12").pip_install("pandas", "numpy")
         .add_local_dir("gvs", "/root/gvs")
         .add_local_file(f"{DATA}/series_daily.csv", "/root/data/series_daily.csv")
         .add_local_file(f"{DATA}/series_catalog.csv", "/root/data/series_catalog.csv"))


@app.function(image=image, cpu=2, memory=4096, timeout=3000, max_containers=50)
def run_one(rule: str, order_seed: int) -> dict:
    import sys
    sys.path.insert(0, "/root")
    from gvs.core import Panel, pooled_skill
    from gvs.scientist import DEV, GATE, LOCKBOX, evaluate, in_span, run
    series, catalog, log = "/root/data/series_daily.csv", "/root/data/series_catalog.csv", f"/tmp/{rule}_{order_seed}.jsonl"
    final = run(series, catalog, log, max_rounds=1, accept_rule=rule, order_seed=order_seed)
    rows = [json.loads(line) for line in open(log)]
    full = evaluate(Panel(series, catalog), final, LOCKBOX[1])
    lock = in_span(full, LOCKBOX)
    return {"rule": rule, "order_seed": order_seed, "config": json.loads(final.to_json()),
            "tested": sum(1 for r in rows if r["dev_gain"] is not None), "kept": sum(1 for r in rows if r["verdict"] == "kept"),
            "dev_skill": pooled_skill(in_span(full, DEV)), "gate_skill": pooled_skill(in_span(full, GATE)),
            "lockbox_skill": pooled_skill(lock), "lockbox_coverage": float(lock.inside.mean())}


@app.local_entrypoint()
def main(out: str = "results/ablation/orderings.json"):
    jobs = [(rule, seed) for seed in range(START, START + N) for rule in ("gate", "dev_only")]
    results = []
    for r in run_one.starmap(jobs, order_outputs=False):
        results.append(r)
        print(f"finished {r['rule']:8s} order {r['order_seed']}: kept {r['kept']:2d}  dev {r['dev_skill']:+.3f}  lockbox {r['lockbox_skill']:+.3f}")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        json.dump(sorted(results, key=lambda r: (r["order_seed"], r["rule"])), open(out, "w"), indent=1)
