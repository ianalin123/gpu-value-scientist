"""Direct tests of each market-state hypothesis: how often does a posted price step up or down
within 7 days, given the state the series was in? Reported for the search period and the lockbox."""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from gvs.core import Panel, day_index
from gvs.scientist import LOCKBOX, START

LABELS = {
    "offer_trend": {-1: "offer count falling", 0: "offer count flat", 1: "offer count rising"},
    "deviation": {-1: "below 30-day median", 0: "near 30-day median", 1: "above 30-day median"},
    "last_dir": {-1: "last step was down", 0: "no step yet", 1: "last step was up"},
    "since_change": {0: "changed in last 2 days", 1: "changed 3 to 13 days ago", 2: "quiet for 14+ days"},
    "peer_lead": {-1: "same GPU fell elsewhere", 0: "no peer move", 1: "same GPU rose elsewhere"},
    "newgen_lead": {-1: "new-gen rate cards fell", 0: "new-gen flat", 1: "new-gen rate cards rose"},
    "provider_change": {-1: "a provider left", 0: "same providers", 1: "a provider joined"},
    "own_trend": {-1: "fell over 14 days", 0: "flat over 14 days", 1: "rose over 14 days"},
    "class_trend": {-1: "class fell over 7 days", 0: "class flat over 7 days", 1: "class rose over 7 days"},
    "news": {-1: "fewer price-rise articles than usual", 0: "usual news mix", 1: "more price-rise articles than usual"},
}


def step_table(panel: Panel, first: str, last: str, h: int = 7) -> list[dict]:
    rows = []
    for day in range(day_index(first), min(day_index(last), panel.last_day - h) + 1):
        ids = panel.moving_at(day)
        y = panel.log_change[h][ids, day]
        ok = ~np.isnan(y)
        for f in panel.state:
            rows.append(pd.DataFrame({"feature": f, "state": panel.state[f][ids, day][ok], "y": y[ok]}))
    df = pd.concat(rows)
    df["up"], df["down"] = df.y > 1e-9, df.y < -1e-9
    out = []
    for (f, s), g in df.groupby(["feature", "state"]):
        out.append({"feature": f, "state": LABELS[f][int(s)], "n": int(len(g)), "p_up_7d": round(float(g.up.mean()), 3),
                    "p_down_7d": round(float(g.down.mean()), 3), "mean_log_change": round(float(g.y.mean()), 4)})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--out", default="out/state_experiments.json")
    ap.add_argument("--news")
    args = ap.parse_args()
    panel = Panel(args.series, args.catalog, args.news)
    result = {"search_period": step_table(panel, START, "2026-10-12"), "lockbox": step_table(panel, *LOCKBOX)}
    json.dump(result, open(args.out, "w"), indent=2)
    for period, rows in result.items():
        print(f"== {period}: P(step within 7 days | state), posted series that move")
        print(pd.DataFrame(rows).to_string(index=False))
