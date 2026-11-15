"""A language-model proposer: it reads what the loop has learned and writes the next hypotheses itself.

The model answers in a small typed grammar of edits to the forecasting method, so every proposal is
something the loop can backtest and nothing it says is trusted without the dev and gate tests.
The model has no web access here and is told the data cutoff. Responses are cached by prompt in
results/llm_cache.json, so a rerun without any model replays the same proposals.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request

from gvs.core import STATE_FEATURES, Config
from gvs.memory import env_value

CACHE_PATH = "results/llm_cache.json"
CLASSES = ("aggregator_cheapest", "hyperscaler_list", "hyperscaler_spot", "marketplace_ask", "neocloud_rate_card", "neocloud_spot")
CUTOFF = "2026-11-06"

GRAMMAR = f"""Each hypothesis is a JSON object: {{"claim": str, "rationale": str, "edits": [edit, ...]}} with 1 or 2 edits.
An edit is one of:
  {{"op": "set", "field": "lookback_days", "value": null or integer 30..400}}   only use price changes from this many recent days
  {{"op": "set", "field": "halflife_days", "value": null or number 10..400}}    down-weight older changes
  {{"op": "set", "field": "min_samples", "value": number 3..60}}               below this many past changes, stay on the last price
  {{"op": "set", "field": "pool", "value": null, "class" or "source_class"}}    borrow past changes from similar series
  {{"op": "set", "field": "pool_weight", "value": number 2..100}}              how many observations the borrowed changes are worth
  {{"op": "set", "field": "step_quantiles", "value": true or false}}           quantiles are real past changes, never interpolated
  {{"op": "set", "field": "vol_scale", "value": true or false}}                rescale past changes by current versus past volatility
  {{"op": "condition", "feature": F, "weight": number 0..1}}                    give past days in a different market state this weight (1 = ignore the state)
        F is one of: {", ".join(STATE_FEATURES)}
  {{"op": "width", "class": C, "scale": number 0.4..2.5}}                       scale the q10-q90 interval for an instrument class
  {{"op": "tail", "down": number 0.4..2.5, "up": number 0.4..2.5}}              scale the downside and upside tails separately
  {{"op": "anchor", "class": C, "days": null or integer 2..14}}                 forecast from the k-day median level instead of the last price
        C is "*" or one of: {", ".join(CLASSES)}"""

STATE_MEANING = """Market states (each is known on the forecast day): since_change = days since the series last changed (0-2, 3-13, 14+);
last_dir = direction of its last step; offer_trend = count of posted offers falling/flat/rising; provider_change = a provider joined or left;
deviation = price below/near/above its own 30-day median; peer_lead = same GPU moved in another collector; newgen_lead = B200/B300/H200
rate cards moved in the last week; own_trend = series fell/flat/rose over 14 days; class_trend = its instrument class fell/flat/rose over 7 days."""


def build_prompt(current: Config, rows: list[dict], n: int) -> str:
    table = "\n".join(f"{r['id']} | {r.get('family')} | {r['claim']} | dev gain {r['dev_gain']:+.4f} | {r['verdict']}"
                      for r in rows if r.get("dev_gain") is not None)
    return f"""You are the proposer in an automated research loop that forecasts posted GPU cloud rental prices (daily medians of
posted offers, USD per GPU-hour) 1, 3 and 7 days ahead as quantiles q10, q50, q90. Use only what was publicly known on or before {CUTOFF}.

How the forecaster works: the forecast distribution for a series is the weighted empirical distribution of its own past h-day log
changes. A hypothesis is a rule for re-weighting or reshaping those past changes. Skill is 1 - pinball loss / loss of the flat last value.
A hypothesis is kept only if it improves skill on development dates AND on later dates you cannot see.

{STATE_MEANING}

The method accepted so far: {current.to_json()}

Everything tested so far (development-date gain, then verdict):
{table}

Known facts from the error analysis: 97% of the remaining loss is in forecasts where the price moved; the median forecast is the last
price 98% of the time; forecasting from a smoothed level failed badly; shorter history windows always hurt; self-grading abstention
overfit. Marketplace asks for B300, H200 and B200 carry most of the loss.

Propose {n} NEW hypotheses about what moves posted GPU rental prices over the next week. Each must be a different test from every
row above and from each other. Prefer ideas that explain WHY, combine two mechanisms, or apply a mechanism to one instrument class.
{GRAMMAR}

Answer with a JSON array of {n} hypothesis objects and nothing else."""


def ask(prompt: str) -> dict:
    """Return {"content", "citations", "model"} for a prompt, from the cache or from a model.

    Order of preference: an OpenAI-compatible endpoint (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL), then the
    `claude` command line if it is installed and signed in. With neither, and no cached answer, the
    proposer returns nothing and the loop simply stops after its mechanical rounds.
    """
    cache = json.load(open(CACHE_PATH)) if os.path.exists(CACHE_PATH) else {}
    key = hashlib.sha256(prompt.encode()).hexdigest()
    if key in cache:
        return cache[key]
    try:
        if env_value("LLM_API_KEY") and env_value("LLM_BASE_URL"):
            answer = _ask_endpoint(prompt)
        elif shutil.which("claude"):
            answer = _ask_claude_cli(prompt)
        else:
            return {"content": "[]", "citations": [], "model": None}
    except Exception as error:  # the loop must survive a failed call; it simply gets no proposals
        print(f"language-model proposer: call failed ({type(error).__name__}); no proposals this round")
        return {"content": "[]", "citations": [], "model": None}
    cache[key] = answer
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=1, ensure_ascii=False)
    return answer


def _ask_endpoint(prompt: str) -> dict:
    api_key, model = env_value("LLM_API_KEY"), env_value("LLM_MODEL") or "gpt-4.1"
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}]}).encode()
    request = urllib.request.Request(env_value("LLM_BASE_URL").rstrip("/") + "/chat/completions", data=body, method="POST",
                                     headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        message = json.load(response)["choices"][0]["message"]
    return {"content": message.get("content") or "[]", "model": model, "citations": []}


def _ask_claude_cli(prompt: str) -> dict:
    """One plain question to the Claude command line, from an empty folder so it reads no project files."""
    with tempfile.TemporaryDirectory() as empty:
        done = subprocess.run(["claude", "-p", prompt, "--output-format", "json"], cwd=empty, capture_output=True,
                              text=True, timeout=300, check=True)
    reply = json.loads(done.stdout)
    model = next(iter(reply.get("modelUsage") or {}), "claude")
    return {"content": reply.get("result") or "[]", "model": f"{model} via the claude CLI", "citations": []}


def parse(content: str) -> list[dict]:
    match = re.search(r"\[.*\]", content, re.S)
    try:
        items = json.loads(match.group(0)) if match else []
    except json.JSONDecodeError:
        return []
    return [x for x in items if isinstance(x, dict) and isinstance(x.get("claim"), str) and isinstance(x.get("edits"), list)]


def _number(v, lo, hi):
    return float(min(max(float(v), lo), hi))


def apply_edits(cfg: Config, edits: list[dict]) -> Config | None:
    """Apply a proposal's edits. Anything outside the grammar makes the whole proposal invalid."""
    try:
        for e in edits[:2]:
            op = e.get("op")
            if op == "set":
                field, v = e["field"], e["value"]
                if field == "lookback_days":
                    cfg = cfg.with_(lookback_days=None if v is None else int(_number(v, 30, 400)))
                elif field == "halflife_days":
                    cfg = cfg.with_(halflife_days=None if v is None else _number(v, 10, 400))
                elif field == "min_samples":
                    cfg = cfg.with_(min_samples=_number(v, 3, 60))
                elif field == "pool" and v in (None, "class", "source_class"):
                    cfg = cfg.with_(pool=v)
                elif field == "pool_weight":
                    cfg = cfg.with_(pool_weight=_number(v, 2, 100))
                elif field in ("step_quantiles", "vol_scale") and isinstance(v, bool):
                    cfg = cfg.with_(**{field: v})
                else:
                    return None
            elif op == "condition" and e["feature"] in STATE_FEATURES:
                w = _number(e["weight"], 0, 1)
                cfg = cfg.with_(condition=tuple(c for c in cfg.condition if c[0] != e["feature"])) if w >= 1 else cfg.with_condition(e["feature"], w)
            elif op == "width" and e["class"] in CLASSES + ("*",):
                cfg = cfg.with_width(e["class"], _number(e["scale"], 0.4, 2.5))
            elif op == "tail":
                cfg = cfg.with_(tail_scale=(_number(e["down"], 0.4, 2.5), _number(e["up"], 0.4, 2.5)))
            elif op == "anchor" and e["class"] in CLASSES + ("*",):
                cfg = cfg.with_anchor(e["class"], None if e["days"] is None else int(_number(e["days"], 2, 14)))
            else:
                return None
        return cfg
    except (KeyError, TypeError, ValueError):
        return None


def propose(current: Config, rows: list[dict], n: int = 8) -> tuple[list[dict], list[dict], str | None]:
    """Hypotheses in the loop's own format, plus the sources the model cited and the model's name."""
    answer = ask(build_prompt(current, rows, n))
    proposals = []
    for item in parse(answer["content"]):
        edits = item["edits"]
        family = "llm:" + "+".join(sorted({str(e.get("op")) + ":" + str(e.get("field") or e.get("feature") or e.get("class") or "") for e in edits if isinstance(e, dict)}))
        proposals.append(dict(claim=item["claim"].strip()[:300], rationale=str(item.get("rationale", "")).strip()[:300], family=family,
                              edits=edits, edit=lambda c, edits=edits: apply_edits(c, edits)))
    return proposals, answer["citations"], answer["model"]
