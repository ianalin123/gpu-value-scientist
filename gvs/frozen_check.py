"""Write our forecast from a history file truncated at a cutoff, for the organisers' frozen-mode scorer."""
from __future__ import annotations

import argparse
import json
import os

import pandas as pd

from gvs.core import Panel, day_index
from gvs.report import forecast_at
from gvs.scientist import config_from_json

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    for name in ("--history", "--catalog", "--config", "--cutoff", "--out"):
        ap.add_argument(name, required=True)
    args = ap.parse_args()
    panel = Panel(args.history, args.catalog)
    origin = day_index(args.cutoff)
    assert panel.last_day == origin, "the history file must end at the cutoff"
    forecast_at(panel, config_from_json(json.load(open(args.config))), origin).to_csv(
        os.path.join(args.out, "ours.csv"), index=False, float_format="%.10g")
    catalog = pd.read_csv(args.catalog, dtype=str, keep_default_na=False)
    headline = [s for s in catalog[catalog.tier == "headline"].series_id if not s.startswith("aws_spot.")]
    moving = [panel.ids[i] for i in panel.moving_at(origin)]
    for name, ids in (("headline_posted", headline), ("moving_posted", moving)):
        with open(os.path.join(args.out, f"ids_{name}.txt"), "w") as f:
            f.write("\n".join(ids) + "\n")
    print(f"posted headline series at {args.cutoff}: {len(headline)} | posted series that move: {len(moving)}")
