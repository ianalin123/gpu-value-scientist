"""The research loop: propose a hypothesis about what moves posted GPU prices, test it, keep what survives.

Three sets of forecast origins, fixed before any result was seen:
  dev      the proposer sees these scores and uses them to decide what to try next
  gate     a change is kept only if it also improves here; the proposer never sees these scores
  lockbox  scored once, after the loop has stopped, for the reported result
Every verdict is appended to a log that the next run reads first, so a rejected idea is not retried.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time

from gvs.core import Config, Panel, apply_self_gate, backtest, day_index, paired_gain, pooled_skill

# Most collectors in the pack start in late summer, so the splits sit where the scored series have data.
# A week separates each set from the next, so no forecast target in one set is an origin in another.
START = "2026-03-01"
DEV = ("2026-04-01", "2026-09-16")
GATE = ("2026-09-24", "2026-10-12")
LOCKBOX = ("2026-10-20", "2026-10-30")
DEV_P, GATE_P = 0.80, 0.90


def evaluate(panel: Panel, cfg: Config, last_origin: str):
    """Forecast every day from START to `last_origin` on every posted series that moves, then self-gate."""
    days = list(range(day_index(START), day_index(last_origin) + 1))
    return apply_self_gate(backtest(panel, cfg, days), cfg)


def in_span(cells, span):
    return cells[(cells.origin >= day_index(span[0])) & (cells.origin <= day_index(span[1]))].reset_index(drop=True)


def origin_range(span: tuple[str, str]) -> list[int]:
    return list(range(day_index(span[0]), day_index(span[1]) + 1))


def seed_hypotheses() -> list[dict]:
    """Claims about the market, each written as one edit to the forecasting method."""
    return [
        dict(id="H01", claim="Price behaviour changed this autumn, so only the last 120 days of changes are informative.",
             source="X sweep: rental indices at highs since October (X-045, X-046)", edit=lambda c: c.with_(lookback_days=120)),
        dict(id="H02", claim="Recent changes should count more than old ones (45-day half-life).",
             source="same as H01", edit=lambda c: c.with_(halflife_days=45.0)),
        dict(id="H03", claim="There is no short-run drift: the median forecast should stay on the last posted value.",
             source="brief: rate-card medians move in steps", edit=lambda c: c.with_(center="last")),
        dict(id="H04", claim="A series with little history should borrow the change distribution of its instrument class.",
             source="brief: instruments differ, series within one behave alike", edit=lambda c: c.with_(pool="class")),
        dict(id="H05", claim="Borrowing should stay inside one collector and instrument class.",
             source="brief: define targets per source", edit=lambda c: c.with_(pool="source_class")),
        dict(id="H06", claim="Steps cluster: a price that changed in the last two days is more likely to change again.",
             source="brief: step process; jump-hazard idea", edit=lambda c: c.with_condition("since_change", 0.3)),
        dict(id="H07", claim="Phantom capacity: a shrinking count of posted offers signals tightening supply and precedes a price step.",
             source="Maglev analog: quoted lead times reveal hidden utilization (C-18, X-034, X-053)",
             edit=lambda c: c.with_condition("offer_trend", 0.3)),
        dict(id="H08", claim="Posted prices revert toward their 30-day median.",
             source="spot-pricing literature cited in the brief", edit=lambda c: c.with_condition("deviation", 0.3)),
        dict(id="H09", claim="The direction of the last step predicts the next one.",
             source="trend persistence (X-046)", edit=lambda c: c.with_condition("last_dir", 0.3)),
        dict(id="H10", claim="A provider entering or leaving the sample moves the median: a composition effect, not a price change.",
             source="brief: pooled medians move with the provider mix", edit=lambda c: c.with_condition("provider_change", 0.3)),
        dict(id="H11", claim="Collectors lag each other: when the same GPU moved in another collector, this one follows.",
             source="five collectors sample overlapping providers", edit=lambda c: c.with_condition("peer_lead", 0.3)),
        dict(id="H12", claim="New-generation rate cards (B200, B300, H200) lead older chips.",
             source="X-047: newest-generation prices rising sharply", edit=lambda c: c.with_condition("newgen_lead", 0.3)),
        dict(id="H13", claim="Empirical intervals are too narrow: widen all by 25%.",
             source="starter kit: drift coverage 0.75 against a 0.80 target", edit=lambda c: c.with_width("*", 1.25)),
        dict(id="H14", claim="Empirical intervals are too wide for step series: narrow all by 20%.",
             source="brief: rate cards rarely move inside a week", edit=lambda c: c.with_width("*", 0.8)),
        dict(id="H15", claim="Ten past windows are enough to leave the flat forecast.",
             source="short histories in the pack", edit=lambda c: c.with_(min_samples=10.0)),
        dict(id="H16", claim="A posted price is a step process, so a quantile should be a change that really happened, never an interpolated one.",
             source="brief: one H100 rate-card median took six values in 235 days", edit=lambda c: c.with_(step_quantiles=True)),
        dict(id="H17", claim="The method can tell where it is failing: grade its own last 45 days per series and abstain where it lost to the last value.",
             source="brief, direction A: learn from previous predictions; teams choose which series to forecast",
             edit=lambda c: c.with_(self_gate_days=45)),
        dict(id="H18", claim="A series should stay on its last value until the method has a winning record on it.",
             source="escalation idea: defer by default, act when earned", edit=lambda c: c.with_(self_gate_days=45, self_gate_start_closed=True)),
        dict(id="H19", claim="Prices are rising, so the upside tail is fatter than history says: stretch it by 25%.",
             source="X sweep: rental indices at highs (X-045 to X-048)", edit=lambda c: c.with_(tail_scale=(1.0, 1.25))),
        dict(id="H20", claim="Downward steps are rarer now than in the past: shrink the downside tail by 20%.",
             source="same as H19", edit=lambda c: c.with_(tail_scale=(0.8, 1.0))),
        dict(id="H21", claim="Tail levels should learn from the method's own misses (adaptive conformal, rate 0.02).",
             source="brief, direction A; adaptive conformal inference", edit=lambda c: c.with_(adaptive_rate=0.02)),
        dict(id="H22", claim="A posted median flickers around a level, so forecast from the 3-day median level instead of the last print.",
             source="error analysis: 97% of the loss sits in cells where the price moved", edit=lambda c: c.with_anchor("*", 3)),
        dict(id="H23", claim="Volatility clusters: rescale past changes by how volatile the series is now versus then.",
             source="spot-pricing literature cited in the brief", edit=lambda c: c.with_(vol_scale=True)),
        dict(id="H24", claim="A series that rose over the last two weeks keeps rising.",
             source="X sweep: trend persistence into November (X-046)", edit=lambda c: c.with_condition("own_trend", 0.3)),
        dict(id="H25", claim="When a whole instrument class has been rising for a week, its members keep stepping up.",
             source="X sweep: providers raising prices together (X-049)", edit=lambda c: c.with_condition("class_trend", 0.3)),
        dict(id="H26", claim="Weeks with more public news about GPU price rises than price cuts are followed by upward steps.",
             source="Exa: weekly counts of dated articles, each published before the forecast origin",
             needs="news", edit=lambda c: c.with_condition("news", 0.3)),
    ]


SEED_FAMILY = {"H01": "lookback", "H02": "halflife", "H03": "center", "H04": "pool", "H05": "pool", "H06": "state:since_change",
               "H07": "state:offer_trend", "H08": "state:deviation", "H09": "state:last_dir", "H10": "state:provider_change",
               "H11": "state:peer_lead", "H12": "state:newgen_lead", "H13": "width", "H14": "width", "H15": "min_samples",
               "H16": "step", "H17": "self_gate", "H18": "self_gate", "H19": "tail", "H20": "tail", "H21": "adaptive",
               "H22": "anchor", "H23": "vol", "H24": "state:own_trend", "H25": "state:class_trend", "H26": "state:news"}


def refinements(cfg: Config, classes: list[str]) -> list[dict]:
    """Second-round proposals: one-step changes around whatever the loop has accepted so far."""
    out = []

    def add(family, claim, new):
        if new != cfg:
            out.append(dict(claim=claim, family=family, source="refinement of the accepted method", edit=lambda _c, new=new: new))

    for v in (60, 90, 180, None):
        add("lookback", f"lookback of {v} days", cfg.with_(lookback_days=v))
    for v in (None, 30.0, 90.0):
        add("halflife", f"half-life of {v} days", cfg.with_(halflife_days=v))
    for v in (5.0, 10.0, 40.0):
        add("min_samples", f"minimum sample of {v}", cfg.with_(min_samples=v))
    if cfg.pool:
        for v in (5.0, 10.0, 40.0):
            add("pool", f"pooled windows worth {v} observations", cfg.with_(pool_weight=v))
    for feature, w in cfg.condition:
        for v in (0.0, 0.6):
            add(f"state:{feature}", f"weight {v} on windows whose {feature} state differs", cfg.with_condition(feature, v))
    add("step", "step quantiles switched", cfg.with_(step_quantiles=not cfg.step_quantiles))
    for v in (None, 21, 30, 60, 90):
        add("self_gate", f"self-grading window of {v} days", cfg.with_(self_gate_days=v))
    if cfg.self_gate_days:
        for v in (6, 15, 30):
            add("self_gate", f"{v} graded forecasts before the gate may close", cfg.with_(self_gate_min=v))
        add("self_gate", "gate start switched", cfg.with_(self_gate_start_closed=not cfg.self_gate_start_closed))
    for v in ((1.0, 1.25), (1.0, 0.8), (0.8, 1.0), (1.25, 1.0)):
        add("tail", f"tail scale down x{v[0]}, up x{v[1]}", cfg.with_(tail_scale=v))
    for v in (0.0, 0.01, 0.05):
        add("adaptive", f"adaptive tail rate {v}", cfg.with_(adaptive_rate=v))
    for cls in classes:
        for v in (0.6, 0.8, 1.25, 1.5):
            add("width", f"interval width x{v} for {cls}", cfg.with_width(cls, v))
    return out


def config_from_json(d: dict) -> Config:
    def freeze(v):
        return tuple(freeze(x) for x in v) if isinstance(v, list) else v
    return Config(**{k: freeze(v) for k, v in d.items()})


def config_key(cfg: Config) -> str:
    return hashlib.sha1(cfg.to_json().encode()).hexdigest()[:10]


def run(series_csv: str, catalog_csv: str, log_path: str, max_rounds: int = 3, news_csv: str | None = None,
        memory=None, evidence: list[dict] | None = None) -> Config:
    """`memory` is the agents' shared store (gvs.memory.SharedMemory); `evidence` is what the scout found on the web."""
    panel = Panel(series_csv, catalog_csv, news_csv)
    if memory is not None:
        for item in evidence or []:
            memory.write("scout", "evidence", f"{item['published']} | {item['title'][:140]} | {item['text'][:160]}",
                         {"url": item["url"], "published": item["published"], "query": item.get("query", "")})
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    history = [json.loads(line) for line in open(log_path)] if os.path.exists(log_path) else []
    tried = {m["config_key"] for m in history}
    current = Config()
    for m in history:
        if m["verdict"] == "kept":
            current = config_from_json(m["config"])

    cache: dict[str, tuple] = {}

    def cells(cfg: Config):
        k = config_key(cfg)
        if k not in cache:
            full = evaluate(panel, cfg, GATE[1])
            cache[k] = (in_span(full, DEV), in_span(full, GATE))
        return cache[k]

    def record(entry: dict):
        entry["time"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        history.append(entry)
        if memory is not None and entry["dev_gain"] is not None:
            memory.write("experimenter", "result", f"{entry['id']} {entry['claim']} | dev gain {entry['dev_gain']:+.4f} "
                         f"(p={entry['dev_p']:.2f})", {"id": entry["id"], "family": entry["family"], "dev_gain": entry["dev_gain"]})
            memory.write("critic", "verdict", f"verdict on {entry['family']}: {entry['verdict']} | {entry['claim']} | dev "
                         f"{entry['dev_gain']:+.4f}" + (f", gate {entry['gate_gain']:+.4f}" if entry.get("gate_gain") is not None else ""),
                         {"id": entry["id"], "family": entry["family"], "verdict": entry["verdict"]})
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        if entry["dev_gain"] is None:
            print(f"[{entry['id']}] {entry['verdict'].upper()} | {entry['claim']}")
            return
        tag = entry["verdict"].upper()
        print(f"[{entry['id']}] {tag:<22} dev {entry['dev_gain']:+.4f} (p={entry['dev_p']:.2f})"
              + (f" gate {entry['gate_gain']:+.4f} (p={entry['gate_p']:.2f})" if entry.get("gate_gain") is not None else "")
              + f" | {entry['claim']}")

    def test(hyp: dict, hyp_id: str) -> bool:
        nonlocal current
        if hyp.get("needs") == "news" and "news" not in panel.state:
            if news_csv and hyp_id not in {h["id"] for h in history}:
                record(dict(id=hyp_id, claim=hyp["claim"], source=hyp["source"], family=hyp.get("family"), config_key=hyp_id,
                            config=None, web_evidence=[], base_dev_skill=None, dev_gain=None, dev_p=None, gate_gain=None,
                            gate_p=None, verdict="not testable: Exa returned its 25-result cap in every week, so the count carries no signal"))
            return False
        candidate = hyp["edit"](current)
        key = config_key(candidate)
        if key in tried or candidate == current:
            return False
        tried.add(key)
        support = []
        if memory is not None and hyp_id.startswith("H"):
            # Before spending a backtest on a seed hypothesis, the proposer reads what the scout found on the web about it.
            support = [h for h in memory.recall("proposer", hyp["claim"], limit=3, kind="evidence") if h.get("agent") == "scout"]
        dev_new, gate_new = cells(candidate)
        dev_old, gate_old = cells(current)
        d = paired_gain(dev_new, dev_old)
        entry = dict(id=hyp_id, claim=hyp["claim"], source=hyp["source"], family=hyp.get("family"), config_key=key,
                     web_evidence=[{"url": h["data"].get("url"), "published": h["data"].get("published")} for h in support],
                     config=json.loads(candidate.to_json()), base_dev_skill=pooled_skill(dev_old),
                     dev_gain=d["gain"], dev_p=d["p_positive"], gate_gain=None, gate_p=None)
        if not (d["gain"] > 0 and d["p_positive"] >= DEV_P):
            record({**entry, "verdict": "rejected on dev"})
            return False
        g = paired_gain(gate_new, gate_old)
        entry.update(gate_gain=g["gain"], gate_p=g["p_positive"])
        if not (g["gain"] > 0 and g["p_positive"] >= GATE_P):
            record({**entry, "verdict": "rejected at the gate"})
            return False
        record({**entry, "verdict": "kept"})
        current = candidate
        return True

    if not history:
        base_dev, base_gate = cells(current)
        print(f"start: empirical-change forecaster, all history | dev skill {pooled_skill(base_dev):+.4f} "
              f"({len(base_dev)} cells) | gate cells {len(base_gate)}")
    def families_the_critic_failed_at_the_gate() -> set[str]:
        """The proposer asks the shared memory what the critic rejected on unseen dates, and stops refining those ideas."""
        if memory is None:
            return set()
        hits = [h for q in ("verdict: rejected at the gate", "verdict: kept")
                for h in memory.recall("proposer", q, limit=20, kind="verdict") if h.get("agent") == "critic"]
        failed = {h["data"].get("family") for h in hits if h.get("data", {}).get("verdict") == "rejected at the gate"}
        kept = {h["data"].get("family") for h in hits if h.get("data", {}).get("verdict") == "kept"}
        return failed - kept - {None}

    for hyp in seed_hypotheses():
        test({**hyp, "family": SEED_FAMILY[hyp["id"]]}, hyp["id"])
    classes = sorted(set(panel.instrument_class[i] for o in origin_range(GATE)[::5] for i in panel.moving_at(o)))
    skipped = []
    for rnd in range(1, max_rounds + 1):
        kept_any = False
        avoid = families_the_critic_failed_at_the_gate()
        if avoid:
            print(f"round {rnd}: proposer read the critic's verdicts and will not refine {sorted(avoid)}")
        for n, hyp in enumerate(refinements(current, classes), start=1):
            if hyp["family"] in avoid:
                skipped.append(f"R{rnd}.{n:02d} {hyp['claim']}")
                continue
            kept_any |= test(hyp, f"R{rnd}.{n:02d}")
        if not kept_any:
            print(f"round {rnd}: nothing survived the gate; stopping")
            break
    print("final method:", current.to_json())
    if memory is not None:
        memory.wait_until_indexed()
        kept = [h for h in memory.recall("reporter", "verdict: kept", limit=10, kind="verdict")
                if h.get("agent") == "critic" and h.get("data", {}).get("verdict") == "kept"]
        sources = [h for h in memory.recall("reporter", "why GPU rental prices are rising", limit=5, kind="evidence")
                   if h.get("agent") == "scout"]
        lines = ["# What the agents left in shared memory", "",
                 f"The proposer skipped {len(skipped)} refinements because the critic had rejected that idea on unseen dates.", "",
                 "## Kept verdicts the reporter recalled (written by the critic)", ""]
        lines += [f"- {h['text']}" for h in kept] + ["", "## Web evidence the reporter recalled (written by the scout)", ""]
        lines += [f"- {h['data'].get('published')} {h['data'].get('url')}" for h in sources]
        lines += ["", "## Refinements skipped", ""] + [f"- {x}" for x in skipped]
        with open(os.path.join(os.path.dirname(log_path), "memory_report.md"), "w") as f:
            f.write("\n".join(lines) + "\n")
    return current


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--log", default="logs/research_log.jsonl")
    ap.add_argument("--out-config", default="logs/final_config.json")
    ap.add_argument("--news", help="weekly news counts from the Exa scout (results/exa_news_weekly.csv)")
    ap.add_argument("--scout", action="store_true", help="let the scout gather dated web evidence through Exa (cached)")
    ap.add_argument("--memory-log", help="turn on the shared agent memory and mirror every write and recall here")
    ap.add_argument("--memory-namespace", default=time.strftime("gvs-run-%Y%m%dT%H%M%S"))
    args = ap.parse_args()
    memory = evidence = None
    if args.memory_log:
        from gvs.memory import SharedMemory
        memory = SharedMemory(args.memory_log, namespace=args.memory_namespace)
    if args.scout:
        from gvs.scout import EVIDENCE_QUERIES, EVIDENCE_START, LAST_DAY, Scout
        scout = Scout()
        evidence = [{**item, "query": q} for q in EVIDENCE_QUERIES for item in scout.search(q, EVIDENCE_START, LAST_DAY, n=6)]
        print(f"scout: {len(evidence)} dated web results from Exa, ${scout.spent():.2f} spent this run")
    final = run(args.series, args.catalog, args.log, news_csv=args.news, memory=memory, evidence=evidence)
    if memory is not None:
        print("shared memory:", json.dumps(memory.summary()))
    with open(args.out_config, "w") as f:
        f.write(final.to_json() + "\n")
