"""Score the final method once on the lockbox, compare it with the starter kit's own drift baseline,
and write the forecast file for the event origin."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

from gvs.core import (HORIZONS, Config, Panel, day_index, day_label, forecast_quantiles, paired_gain,
                      pinball_cell, pooled_skill)
from gvs.scientist import DEV, GATE, LOCKBOX, config_from_json, evaluate, in_span


def official_drift(panel: Panel, pack: str, series_csv: str, span: tuple[str, str], workdir: str) -> pd.DataFrame:
    """Run the organisers' baselines.py (method drift) for every origin in the span, unchanged."""
    ids_file, out = os.path.join(workdir, "posted_series_ids.txt"), os.path.join(workdir, "official_drift.csv")
    with open(ids_file, "w") as f:
        f.write("\n".join(panel.ids) + "\n")
    origins = ",".join(day_label(d) for d in range(day_index(span[0]), day_index(span[1]) + 1))
    subprocess.run([sys.executable, "-I", "-B", os.path.join(pack, "starter", "baselines.py"), "--history", series_csv,
                    "--origins", origins, "--method", "drift", "--horizons", "1,3,7", "--series-ids", "@" + ids_file,
                    "--out", out], check=True, stdout=subprocess.DEVNULL)
    df = pd.read_csv(out)
    row = {s: i for i, s in enumerate(panel.ids)}
    df["series"] = df.series_id.map(row)
    df["origin"] = (pd.to_datetime(df.origin_date) - pd.Timestamp("2026-01-01")).dt.days
    return df.rename(columns={"horizon_days": "h"})[["series", "origin", "h", "q10", "q50", "q90"]]


def with_official(cells: pd.DataFrame, drift: pd.DataFrame) -> pd.DataFrame:
    """The same cells, forecast by the organisers' drift baseline."""
    m = cells[["series", "origin", "h", "truth", "last", "base_loss"]].merge(drift, on=["series", "origin", "h"], how="left")
    for col in ("q10", "q50", "q90"):
        m[col] = m[col].fillna(m["last"])
    m["loss"] = pinball_cell(m.truth.to_numpy(), m[["q10", "q50", "q90"]].to_numpy())
    m["inside"] = (m.truth >= m.q10 - 1e-12) & (m.truth <= m.q90 + 1e-12)
    return m


def summary(cells: pd.DataFrame) -> dict:
    return {"cells": int(len(cells)), "pooled_skill": round(pooled_skill(cells), 4),
            "coverage_q10_q90": round(float(cells.inside.mean()), 3)}


def forecast_at(panel: Panel, cfg: Config, origin: int) -> pd.DataFrame:
    """Forecast rows for every posted series at one origin. Series that never move stay on their last value."""
    if cfg.self_gate_days is not None or cfg.adaptive_rate > 0:
        raise SystemExit("the event forecast writer supports methods without self-gating or adaptive tails; "
                         "the accepted method uses neither")
    moving = set(panel.moving_at(origin).tolist())
    rows = []
    for i, sid in enumerate(panel.ids):
        last = panel.last_value[i, origin]
        if np.isnan(last):
            continue
        for h in HORIZONS:
            q = forecast_quantiles(panel, cfg, i, origin, h) if i in moving else np.full(3, last)
            note = "flat_last_value" if np.allclose(q, last) else "analog_forecast"
            rows.append((sid, day_label(origin), h, q[0], q[1], q[2], day_label(origin + h), note))
    return pd.DataFrame(rows, columns=["series_id", "origin_date", "horizon_days", "q10", "q50", "q90", "target_date", "method_note"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    ap.add_argument("--series", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--origin", default="2026-11-06")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    panel = Panel(args.series, args.catalog)
    final = config_from_json(json.load(open(args.config)))
    start = Config()

    full_final, full_start = evaluate(panel, final, LOCKBOX[1]), evaluate(panel, start, LOCKBOX[1])
    drift = official_drift(panel, args.pack, args.series, (DEV[0], LOCKBOX[1]), args.out)
    results = {"final_method": json.loads(final.to_json()), "splits": {"dev": DEV, "gate": GATE, "lockbox": LOCKBOX}, "sets": {}}
    for name, span in (("dev", DEV), ("gate", GATE), ("lockbox", LOCKBOX)):
        f, s = in_span(full_final, span), in_span(full_start, span)
        d = with_official(f, drift)
        results["sets"][name] = {
            "official_drift": summary(d), "our_starting_point": summary(s), "final_method": summary(f),
            "gain_over_official_drift": {k: round(v, 4) for k, v in paired_gain(f, d).items()},
        }

    lock_final = in_span(full_final, LOCKBOX)
    lock_drift = with_official(lock_final, drift)
    cls = pd.Series(panel.instrument_class)
    by_class = []
    for c, idx in lock_final.groupby(cls[lock_final.series].to_numpy()).indices.items():
        f, d = lock_final.iloc[idx], lock_drift.iloc[idx]
        by_class.append({"instrument_class": c, "cells": int(len(f)), "share_of_last_value_loss": round(float(f.base_loss.sum() / lock_final.base_loss.sum()), 3),
                         "moved": round(float((f.truth != f["last"]).mean()), 3),
                         "drift_skill": round(pooled_skill(d), 3), "final_skill": round(pooled_skill(f), 3)})
    results["lockbox_by_instrument_class"] = by_class
    results["lockbox_by_horizon"] = [
        {"h": int(h), "drift_skill": round(pooled_skill(lock_drift[lock_drift.h == h]), 3),
         "final_skill": round(pooled_skill(lock_final[lock_final.h == h]), 3)} for h in HORIZONS]

    headline_now = set(panel.headline_at(day_index(args.origin)).tolist())
    hf = lock_final[lock_final.series.isin(headline_now)].reset_index(drop=True)
    hd = lock_drift[lock_drift.series.isin(headline_now)].reset_index(drop=True)
    results["lockbox_on_event_headline_series"] = {
        "note": f"the {len(headline_now)} posted series that pass the starter kit's headline gates on {args.origin}; "
                "membership uses data after the lockbox, so this row is descriptive",
        "official_drift": summary(hd), "final_method": summary(hf),
        "gain_over_official_drift": {k: round(v, 4) for k, v in paired_gain(hf, hd).items()}}

    fc = forecast_at(panel, final, day_index(args.origin))
    fc_path = os.path.join(args.out, f"forecast_{args.origin}.csv")
    fc.to_csv(fc_path, index=False, float_format="%.10g")
    results["event_forecast"] = {"file": os.path.basename(fc_path), "rows": int(len(fc)), "series": int(fc.series_id.nunique()),
                                 "series_with_a_non_flat_forecast": int(fc[fc.method_note == "analog_forecast"].series_id.nunique())}
    with open(os.path.join(args.out, "results.json"), "w") as f:
        json.dump(results, f, indent=2)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
