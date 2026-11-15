"""Analog forecaster for posted GPU rental prices.

A forecast for (series, origin, horizon h) is the weighted empirical distribution of that
series' own past h-day log changes. Every hypothesis the scientist tests is a rule for
re-weighting those past windows: by recency, or by whether the market was in the same
observable state then as it is at the origin. Nothing dated after the origin is ever read.
"""
from __future__ import annotations

import dataclasses
import json
import warnings

import numpy as np
import pandas as pd

HORIZONS = (1, 3, 7)
QUANTILES = np.array([0.1, 0.5, 0.9])
EPOCH = pd.Timestamp("2026-01-01")
STATE_FEATURES = ("since_change", "last_dir", "offer_trend", "provider_change", "deviation", "peer_lead", "newgen_lead")
NEW_GENERATION = ("B200", "B300", "H200")


def day_index(date: str) -> int:
    return int((pd.Timestamp(date) - EPOCH).days)


def day_label(day: int) -> str:
    return (EPOCH + pd.Timedelta(days=int(day))).strftime("%Y-%m-%d")


@dataclasses.dataclass(frozen=True)
class Config:
    """One forecasting method. The scientist's hypotheses are edits to these fields."""

    lookback_days: int | None = None      # use only windows that start within this many days of the origin
    halflife_days: float | None = None    # exponential down-weighting of older windows
    center: str = "drift"                 # "drift": median of past changes; "last": keep the last value
    min_samples: float = 20.0             # below this effective sample the forecast is the flat last value
    pool: str | None = None               # borrow windows from "class" or "source_class" peers
    pool_weight: float = 20.0             # pseudo-observations given to the pooled windows
    condition: tuple[tuple[str, float], ...] = ()  # (state feature, weight for windows in a different state)
    width_scale: tuple[tuple[str, float], ...] = ()  # (instrument class or "*", multiplier on interval width)
    tail_scale: tuple[float, float] = (1.0, 1.0)  # separate multipliers for the downside and upside tails
    adaptive_rate: float = 0.0            # > 0: tail levels learn from the method's own past misses
    step_quantiles: bool = False          # True: a quantile is always a change that really happened (no interpolation)
    self_gate_days: int | None = None     # grade own past forecasts per series over this window; abstain where they lost
    self_gate_min: int = 9                # graded forecasts needed before the gate may close
    self_gate_start_closed: bool = False  # True: stay on the last value until the method has earned the right to move

    def with_(self, **changes) -> "Config":
        return dataclasses.replace(self, **changes)

    def with_condition(self, feature: str, mismatch_weight: float) -> "Config":
        kept = tuple(c for c in self.condition if c[0] != feature)
        return self.with_(condition=kept + ((feature, mismatch_weight),))

    def with_width(self, instrument_class: str, scale: float) -> "Config":
        kept = tuple(c for c in self.width_scale if c[0] != instrument_class)
        return self.with_(width_scale=kept + ((instrument_class, scale),))

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), sort_keys=True)


class Panel:
    """Posted-rental daily medians as dense series-by-day arrays, plus observable market states."""

    def __init__(self, series_csv: str, catalog_csv: str):
        cols = ["series_id", "date", "value", "n_obs", "n_providers", "source_id", "instrument_class"]
        df = pd.read_csv(series_csv, usecols=cols)
        df = df[~df.series_id.str.startswith("aws_spot.")].copy()
        df["day"] = (pd.to_datetime(df.date) - EPOCH).dt.days
        self.ids = sorted(df.series_id.unique())
        self.n_days = int(df.day.max()) + 1
        self.last_day = self.n_days - 1
        row = {s: i for i, s in enumerate(self.ids)}
        shape = (len(self.ids), self.n_days)
        self.value = np.full(shape, np.nan)
        offers = np.full(shape, np.nan)
        providers = np.full(shape, np.nan)
        r, d = df.series_id.map(row).to_numpy(), df.day.to_numpy()
        self.value[r, d] = df.value.to_numpy()
        offers[r, d] = df.n_obs.to_numpy()
        providers[r, d] = df.n_providers.to_numpy()

        meta = df.drop_duplicates("series_id").set_index("series_id").loc[self.ids]
        catalog = pd.read_csv(catalog_csv, dtype=str, keep_default_na=False).set_index("series_id")
        self.instrument_class = meta.instrument_class.to_numpy()
        self.source = meta.source_id.to_numpy()
        self.gpu_model = catalog.reindex(self.ids).gpu_model.fillna("").to_numpy()
        self.pricing_tier = catalog.reindex(self.ids).pricing_tier.fillna("").to_numpy()

        wide = pd.DataFrame(self.value.T)
        self.last_value = wide.ffill().to_numpy().T
        self.observed = ~np.isnan(self.value)
        self.providers = pd.DataFrame(providers.T).ffill().to_numpy().T
        self.log_change = {h: self._forward_log_change(h) for h in HORIZONS}
        self.state = self._build_states(pd.DataFrame(offers.T).ffill())
        self._groups = {
            "class": self._group_index(self.instrument_class),
            "source_class": self._group_index(np.char.add(np.char.add(self.source.astype(str), "|"), self.instrument_class.astype(str))),
        }

    def _forward_log_change(self, h: int) -> np.ndarray:
        """log(value at t+h / last value known at t): exactly the quantity a forecast made at t must cover."""
        out = np.full(self.value.shape, np.nan)
        out[:, :-h] = np.log(self.value[:, h:] / self.last_value[:, :-h])
        return out

    @staticmethod
    def _group_index(labels: np.ndarray) -> list[np.ndarray]:
        members = {lab: np.flatnonzero(labels == lab) for lab in np.unique(labels)}
        return [members[lab] for lab in labels]

    def _build_states(self, offers_ffill: pd.DataFrame) -> dict[str, np.ndarray]:
        n, t = self.value.shape
        lv = pd.DataFrame(self.last_value.T)
        step = np.sign(lv.diff().fillna(0.0).to_numpy().T)
        step[np.abs(pd.DataFrame(self.last_value.T).pct_change(fill_method=None).fillna(0.0).to_numpy().T) < 1e-9] = 0
        changed = step != 0

        days = np.arange(t)[None, :]
        last_change_day = np.maximum.accumulate(np.where(changed, days, -10_000), axis=1)
        gap = days - last_change_day
        since_change = np.where(gap <= 2, 0, np.where(gap <= 13, 1, 2))

        last_dir = pd.DataFrame(np.where(changed, step, np.nan).T).ffill().fillna(0.0).to_numpy().T

        recent = offers_ffill.rolling(3, min_periods=1).mean()
        earlier = offers_ffill.shift(3).rolling(14, min_periods=3).mean()
        ratio = (recent / earlier).to_numpy().T
        offer_trend = np.where(ratio < 0.95, -1, np.where(ratio > 1.05, 1, 0))

        prov = pd.DataFrame(self.providers.T)
        provider_change = np.sign((prov - prov.shift(3)).fillna(0.0).to_numpy().T)

        dev = np.log(lv / lv.rolling(30, min_periods=10).median()).to_numpy().T
        deviation = np.where(dev < -0.02, -1, np.where(dev > 0.02, 1, 0))

        recent_step = pd.DataFrame(step.T).rolling(3, min_periods=1).sum().to_numpy().T
        peer_lead = np.zeros((n, t))
        key = np.char.add(np.char.add(self.gpu_model.astype(str), "|"), self.pricing_tier.astype(str))
        for k in np.unique(key):
            idx = np.flatnonzero(key == k)
            if len(idx) > 1:
                total = recent_step[idx].sum(axis=0, keepdims=True)
                peer_lead[idx] = np.sign(total - recent_step[idx])
        peer_lead = np.where(since_change == 0, 0, peer_lead)

        is_new = np.isin(self.gpu_model, NEW_GENERATION) & (self.instrument_class == "neocloud_rate_card")
        week_step = pd.DataFrame(step.T).rolling(7, min_periods=1).sum().to_numpy().T
        market = np.sign(week_step[is_new].sum(axis=0)) if is_new.any() else np.zeros(t)
        newgen_lead = np.where(is_new[:, None], 0, market[None, :])

        states = dict(since_change=since_change, last_dir=last_dir, offer_trend=offer_trend,
                      provider_change=provider_change, deviation=deviation, peer_lead=peer_lead, newgen_lead=newgen_lead)
        return {k: v.astype(np.int8) for k, v in states.items()}

    def moving_at(self, origin: int) -> np.ndarray:
        """Every posted series with a month of history, a fresh value and at least one price change in 90 days."""
        seen = self.observed[:, : origin + 1]
        history = seen.sum(axis=1) >= 30
        fresh = seen[:, max(0, origin - 3):].any(axis=1)
        window = self.value[:, max(0, origin - 89): origin + 1]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            moves = np.nanmax(window, axis=1) > np.nanmin(window, axis=1)
        return np.flatnonzero(history & fresh & moves)

    def headline_at(self, origin: int) -> np.ndarray:
        """The starter kit's headline gates, evaluated only on data up to the origin."""
        seen = self.observed[:, : origin + 1]
        history = seen.sum(axis=1) >= 60
        fresh = seen[:, max(0, origin - 3):].any(axis=1)
        window = self.value[:, max(0, origin - 89): origin + 1]
        moves = np.array([len(np.unique(r[~np.isnan(r)])) >= 5 for r in window])
        prov = np.where(seen, self.providers[:, : origin + 1], np.nan)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            enough_providers = np.nanmedian(prov, axis=1) >= 3
        return np.flatnonzero(history & fresh & moves & enough_providers)


def weighted_quantiles(values: np.ndarray, weights: np.ndarray, levels: np.ndarray = QUANTILES,
                       step: bool = False) -> np.ndarray:
    order = np.argsort(values, kind="stable")
    v, w = values[order], weights[order]
    cum = np.cumsum(w)
    if step:
        return v[np.minimum(np.searchsorted(cum, levels * cum[-1], side="left"), len(v) - 1)]
    return np.interp(levels, (cum - 0.5 * w) / cum[-1], v)


def forecast_log_quantiles(panel: Panel, cfg: Config, i: int, origin: int, h: int,
                           levels: np.ndarray = QUANTILES) -> np.ndarray:
    """q10, q50, q90 of the h-day log change for series i, from windows that closed on or before the origin."""
    stop = origin - h + 1
    start = 0 if cfg.lookback_days is None else max(0, stop - cfg.lookback_days)
    if stop <= start:
        return np.zeros(3)
    age = (stop - 1) - np.arange(start, stop)
    recency = np.ones(stop - start) if cfg.halflife_days is None else 0.5 ** (age / cfg.halflife_days)

    def state_match(rows) -> np.ndarray:
        w = np.ones((len(rows), stop - start)) if not np.isscalar(rows) else np.ones(stop - start)
        for feature, mismatch in cfg.condition:
            s = panel.state[feature]
            w = w * np.where(s[rows, start:stop] == s[i, origin], 1.0, mismatch)
        return w

    y = panel.log_change[h][i, start:stop]
    ok = ~np.isnan(y)
    values, weights = y[ok], (recency * state_match(i))[ok]

    if cfg.pool is not None:
        peers = panel._groups[cfg.pool][i]
        peers = peers[peers != i]
        if len(peers):
            yp = panel.log_change[h][peers, start:stop]
            wp = recency[None, :] * state_match(peers)
            okp = ~np.isnan(yp)
            if okp.any() and wp[okp].sum() > 0:
                wp = wp[okp] * (cfg.pool_weight / wp[okp].sum())
                values, weights = np.concatenate([values, yp[okp]]), np.concatenate([weights, wp])

    if weights.sum() < cfg.min_samples or len(values) < 3:
        return np.zeros(3)
    a = weighted_quantiles(values, weights, levels, cfg.step_quantiles)
    if cfg.center == "last":
        a[1] = 0.0
    scale = dict(cfg.width_scale)
    k = scale.get(panel.instrument_class[i], scale.get("*", 1.0))
    down, up = cfg.tail_scale
    return np.sort(np.array([a[1] + k * down * (a[0] - a[1]), a[1], a[1] + k * up * (a[2] - a[1])]))


def pinball_cell(truth: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Mean pinball loss over the three quantiles, the starter kit's cell loss."""
    diff = truth[:, None] - q
    return np.maximum(QUANTILES * diff, (QUANTILES - 1) * diff).mean(axis=1)


class TailLearner:
    """Adaptive conformal tails: after each miss the method asks for a more extreme quantile next time.

    One pair of levels per (instrument class, horizon). A forecast made at day t for day t+h is graded
    on day t+h, and only then moves the levels, so nothing from the future leaks into a forecast.
    """

    def __init__(self, rate: float):
        self.rate = rate
        self.levels: dict[tuple[str, int], np.ndarray] = {}
        self.pending: dict[int, list[tuple[tuple[str, int], bool, bool]]] = {}

    def levels_for(self, key: tuple[str, int]) -> np.ndarray:
        lo, hi = self.levels.setdefault(key, np.array([0.1, 0.9]))
        return np.array([lo, 0.5, hi])

    def remember(self, target_day: int, key: tuple[str, int], below: bool, above: bool) -> None:
        self.pending.setdefault(target_day, []).append((key, below, above))

    def learn_up_to(self, day: int) -> None:
        for target in [d for d in self.pending if d <= day]:
            graded = pd.DataFrame(self.pending.pop(target), columns=["key", "below", "above"])
            for key, g in graded.groupby("key"):
                lo, hi = self.levels[key]
                lo = np.clip(lo - self.rate * (g.below.mean() - 0.1), 0.01, 0.45)
                hi = np.clip(hi + self.rate * (g.above.mean() - 0.1), 0.55, 0.99)
                self.levels[key] = np.array([lo, hi])


def backtest(panel: Panel, cfg: Config, origins: list[int], series_at=None, warmup_from: int | None = None,
             learner: "TailLearner | None" = None) -> pd.DataFrame:
    """One row per scored cell: forecast, truth, loss and the last-value loss it is compared with.

    With adaptive tails the method is first run day by day from `warmup_from`, grading itself as it
    goes, so the levels it uses at each scored origin are the ones it would really have had.
    """
    series_at = series_at or panel.moving_at
    scored = set(origins)
    adaptive = cfg.adaptive_rate > 0
    if adaptive and learner is None:
        learner = TailLearner(cfg.adaptive_rate)
    first = min(origins) if not adaptive else min(min(origins), warmup_from if warmup_from is not None else 75)
    days = range(first, max(origins) + 1) if adaptive else sorted(scored)
    rows = []
    for origin in days:
        if adaptive:
            learner.learn_up_to(origin)
        ids = series_at(origin)
        for h in HORIZONS:
            for i in ids:
                last = panel.last_value[i, origin]
                if np.isnan(last):
                    continue
                key = (panel.instrument_class[i], h)
                levels = learner.levels_for(key) if adaptive else QUANTILES
                a = forecast_log_quantiles(panel, cfg, i, origin, h, levels)
                q = last * np.exp(a)
                known = origin + h <= panel.last_day and not np.isnan(panel.value[i, origin + h])
                if not known:
                    continue
                truth = panel.value[i, origin + h]
                if adaptive:
                    learner.remember(origin + h, key, truth < q[0], truth > q[2])
                if origin in scored:
                    rows.append((i, origin, h, truth, last, q[0], q[1], q[2]))
    cells = pd.DataFrame(rows, columns=["series", "origin", "h", "truth", "last", "q10", "q50", "q90"])
    q = cells[["q10", "q50", "q90"]].to_numpy()
    cells["loss"] = pinball_cell(cells.truth.to_numpy(), q)
    cells["base_loss"] = pinball_cell(cells.truth.to_numpy(), np.repeat(cells["last"].to_numpy()[:, None], 3, axis=1))
    cells["inside"] = (cells.truth >= cells.q10 - 1e-12) & (cells.truth <= cells.q90 + 1e-12)
    return cells


def apply_self_gate(cells: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """The method grades its own earlier forecasts and abstains, series by series, where they lost.

    `cells` must hold the ungated forecast for every day, because the method keeps forecasting in the
    background while it abstains: that is how a closed gate can reopen. A forecast made on day t for
    day t+h counts only from day t+h, when its truth is public. Abstaining means posting the last value,
    which is also what the scorer fills in for a series a team leaves out.
    """
    if cfg.self_gate_days is None or cells.empty:
        return cells
    out = cells.copy()
    abstain = np.zeros(len(out), dtype=bool)
    for _, idx in out.groupby("series").indices.items():
        g = out.iloc[idx]
        graded_day = (g.origin + g.h).to_numpy()
        order = np.argsort(graded_day, kind="stable")
        day_sorted = graded_day[order]
        edge = np.concatenate([[0.0], np.cumsum((g.loss - g.base_loss).to_numpy()[order])])
        hi = np.searchsorted(day_sorted, g.origin.to_numpy(), side="right")
        lo = np.searchsorted(day_sorted, g.origin.to_numpy() - cfg.self_gate_days, side="right")
        n_graded, excess = hi - lo, edge[hi] - edge[lo]
        enough = n_graded >= cfg.self_gate_min
        abstain[idx] = np.where(enough, excess >= 0, cfg.self_gate_start_closed)
    for col in ("q10", "q50", "q90"):
        out.loc[abstain, col] = out.loc[abstain, "last"]
    out.loc[abstain, "loss"] = out.loc[abstain, "base_loss"]
    out["inside"] = (out.truth >= out.q10 - 1e-12) & (out.truth <= out.q90 + 1e-12)
    out["abstained"] = abstain
    return out


def pooled_skill(cells: pd.DataFrame) -> float:
    return float(1.0 - cells.loss.sum() / cells.base_loss.sum())


def paired_gain(new: pd.DataFrame, old: pd.DataFrame, n_boot: int = 400, seed: int = 0) -> dict:
    """Skill gain of `new` over `old` on the same cells, with a bootstrap that resamples whole origins."""
    assert len(new) == len(old) and (new.origin.to_numpy() == old.origin.to_numpy()).all()
    g = pd.DataFrame({"origin": new.origin, "new": new.loss, "old": old.loss, "base": new.base_loss}).groupby("origin").sum()
    point = (g.old.sum() - g.new.sum()) / g.base.sum()
    rng = np.random.default_rng(seed)
    arr = g.to_numpy()
    draws = rng.integers(0, len(arr), size=(n_boot, len(arr)))
    s = arr[draws].sum(axis=1)
    gains = (s[:, 1] - s[:, 0]) / s[:, 2]
    return {"gain": float(point), "p_positive": float((gains > 0).mean()),
            "lo": float(np.quantile(gains, 0.05)), "hi": float(np.quantile(gains, 0.95))}
