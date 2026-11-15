"""Dated web evidence from Exa, cached on disk so a rerun needs neither a key nor a network.

Every search is bounded by a published-date window, and a result is kept only when Exa reports
a `publishedDate` on or before the window's end: the forecasting rules forbid reading anything
published after a forecast origin, and an undated page cannot be shown to respect that. Exa's
`/answer` endpoint takes no published-date bound, so it is not used.

The published date bounds when a page first appeared, not when Exa last read it: the excerpt
comes from Exa's latest crawl, and a page that is updated in place (a price tracker, say) can
carry a mid-October published date and text about mid-November. Pinning the text to the window
needs Exa Snapshot (`contents.snapshotAsOf`), which the free plan refuses. So `search` drops a
result whose title or excerpt names a date after the window's end, reading a bare "Nov 2026" as
the month's last day. That catches the pages that say they were updated; it cannot catch one
that was updated without saying so. `weekly_news` reads no text and counts on Exa's published
date alone.

The cache stores the request body and the result fields we read, keyed by a hash of the body.
It never stores the key.
"""
from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from .memory import env_value

EXA_SEARCH = "https://api.exa.ai/search"
TIMEOUT_S = 20
USER_AGENT = "gpu-value-scientist/0.1"
BUDGET_DOLLARS = 3.0
ASSUMED_COST = 0.01          # charged against the budget when a response reports no cost
HIGHLIGHT_CHARS = 160
MAX_CONSECUTIVE_FAILURES = 3
MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), start=1)}
_MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
ISO_DATE = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MONTH},?\s+(20\d\d)\b", re.I)
MONTH_DAY = re.compile(rf"\b{_MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", re.I)
MONTH_YEAR = re.compile(rf"\b{_MONTH}\s+(20\d\d)\b", re.I)


def latest_date_named(text: str) -> str | None:
    """The latest calendar date the text names, as YYYY-MM-DD. A bare month counts as its last day."""
    found = [f"{y}-{m}-{d}" for y, m, d in ISO_DATE.findall(text)]
    found += [f"{y}-{MONTHS[m.lower()]:02d}-{int(d):02d}" for d, m, y in DAY_MONTH.findall(text)]
    found += [f"{y}-{MONTHS[m.lower()]:02d}-{int(d):02d}" for m, d, y in MONTH_DAY.findall(text)]
    found += [f"{y}-{MONTHS[m.lower()]:02d}-{calendar.monthrange(int(y), MONTHS[m.lower()])[1]:02d}"
              for m, y in MONTH_YEAR.findall(text)]
    return max(found) if found else None


class Scout:
    def __init__(self, cache_path: str = "results/exa_cache.json"):
        self.cache_path = Path(cache_path)
        self._key = env_value("EXA_API_KEY")
        self._spent = 0.0
        self._failures = 0
        self.calls = 0                      # uncached requests made this run
        self.dropped: list[dict] = []       # results refused because they name a date after the window
        self.errors: list[str] = []
        try:
            self._cache: dict[str, dict] = json.loads(self.cache_path.read_text())
        except (OSError, ValueError):
            self._cache = {}

    # ------------------------------------------------------------------ public

    def search(self, query: str, start: str, end: str, n: int = 5) -> list[dict]:
        """Results published from `start` to `end` (YYYY-MM-DD, both inclusive), with a short excerpt."""
        return self._dated(query, start, end, n, with_text=True) or []

    def weekly_news(self, queries: dict[str, str], first_week: str, last_day: str, n: int = 25):
        """One row per (week_start, name): how many results Exa dates inside that Monday-to-Sunday week.

        The count is capped at `n`. It is empty (NA), not zero, when a search could not be served.
        """
        import pandas as pd

        first = dt.date.fromisoformat(first_week)
        last = dt.date.fromisoformat(last_day)
        monday = first - dt.timedelta(days=first.weekday())
        rows = []
        while monday <= last:
            week_end = min(monday + dt.timedelta(days=6), last)
            for name, query in queries.items():
                found = self._dated(query, monday.isoformat(), week_end.isoformat(), n, with_text=False)
                count = None if found is None else sum(monday.isoformat() <= r["published"] for r in found)
                rows.append({"week_start": monday.isoformat(), "name": name, "count": count})
            monday += dt.timedelta(days=7)
        frame = pd.DataFrame(rows, columns=["week_start", "name", "count"])
        frame["count"] = frame["count"].astype("Int64")
        return frame

    def spent(self) -> float:
        return round(self._spent, 4)

    # ------------------------------------------------------------------ plumbing

    def _dated(self, query: str, start: str, end: str, n: int, with_text: bool) -> list[dict] | None:
        """None when the search could be served by neither the cache nor the API."""
        body = {"query": query, "numResults": int(n),
                "startPublishedDate": f"{start[:10]}T00:00:00.000Z",
                "endPublishedDate": f"{end[:10]}T23:59:59.000Z"}
        if with_text:
            body["contents"] = {"highlights": {"maxCharacters": HIGHLIGHT_CHARS}}
        raw = self._fetch(body)
        if raw is None:
            return None
        kept = []
        for item in raw:
            published = str(item.get("publishedDate") or "")[:10]
            if len(published) != 10 or published > end[:10]:
                continue
            named = latest_date_named(f"{item.get('title') or ''} {item.get('text') or ''}") if with_text else None
            if named and named > end[:10]:
                self.dropped.append({"url": item.get("url"), "published": published, "names": named, "end": end[:10]})
                continue
            kept.append({"title": item.get("title") or "", "url": item.get("url") or "",
                         "published": published, "text": item.get("text") or ""})
        return kept

    def _fetch(self, body: dict) -> list[dict] | None:
        key = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        if key in self._cache:
            return self._cache[key]["results"]
        if not self._key or self._spent >= BUDGET_DOLLARS or self._failures >= MAX_CONSECUTIVE_FAILURES:
            return None
        payload = self._post(body)
        if payload is None:
            self._failures += 1
            return None
        self._failures = 0
        self.calls += 1
        cost = (payload.get("costDollars") or {}).get("total")
        cost = float(cost) if isinstance(cost, (int, float)) else ASSUMED_COST
        self._spent += cost
        results = [{"title": r.get("title"), "url": r.get("url"), "publishedDate": r.get("publishedDate"),
                    "text": " ... ".join(h.strip() for h in (r.get("highlights") or []) if h).strip()}
                   for r in payload.get("results") or []]
        self._cache[key] = {"body": body, "fetched": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "costDollars": cost, "results": results}
        self._save()
        return results

    def _post(self, body: dict) -> dict | None:
        for attempt in range(2):
            request = urllib.request.Request(
                EXA_SEARCH, method="POST", data=json.dumps(body).encode(),
                headers={"x-api-key": self._key or "", "Content-Type": "application/json", "User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                    payload = json.loads(response.read())
                    return payload if isinstance(payload, dict) else None
            except urllib.error.HTTPError as error:
                detail = error.read().decode("utf-8", "replace")[:200]
                self._note(f"HTTP {error.code} for {body['query']!r}: {detail}")
                if error.code not in (429, 500, 502, 503, 504) or attempt == 1:
                    return None
                time.sleep(2.0)
            except Exception as error:
                self._note(f"{type(error).__name__} for {body['query']!r}: {error}")
                return None
        return None

    def _note(self, message: str) -> None:
        self.errors.append(message.replace(self._key, "<key>") if self._key else message)

    def _save(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            scratch = self.cache_path.with_name(self.cache_path.name + ".tmp")
            scratch.write_text(json.dumps(self._cache, indent=1, sort_keys=True))
            os.replace(scratch, self.cache_path)
        except OSError as error:
            self._note(f"cache not saved: {error}")


# ---------------------------------------------------------------------- the two saved outputs

NEWS_QUERIES = {
    "price_up": "GPU cloud rental prices rising, H100 or B200 price increase",
    "price_down": "GPU cloud rental price cut, cheaper GPU rental prices falling",
}
EVIDENCE_QUERIES = (
    "what drives GPU cloud rental price changes",
    "H100 rental price trend 2026",
    "GPU marketplace spot price volatility Vast.ai RunPod",
    "neocloud price increase B200 B300 Blackwell rental",
    "GPU supply shortage data center power constraints rental prices",
    "GPU rental price forecast depreciation older chips A100 H100",
)
FIRST_WEEK, EVIDENCE_START, LAST_DAY = "2026-03-02", "2026-08-01", "2026-11-06"


def evidence_markdown(scout: Scout, queries=EVIDENCE_QUERIES, start=EVIDENCE_START, end=LAST_DAY, n=6) -> str:
    lines = ["# Web evidence from Exa", "",
             f"Each search is limited to pages Exa dates from {start} to {end}; a result with no published date, "
             f"a later one, or text naming a later date is dropped. Raw responses: `results/exa_cache.json`.", ""]
    for query in queries:
        lines += [f"## {query}", ""]
        results = scout.search(query, start, end, n)
        if not results:
            lines += ["No dated result.", ""]
        for r in results:
            text = " ".join(r["text"].split())
            lines += [f"- **{r['published']}** [{r['title'] or r['url']}]({r['url']})", f"  {text}" if text else "  (no excerpt)"]
        lines.append("")
    if scout.dropped:
        lines += ["## Dropped: published in the window, but the text names a later date", "",
                  "Exa's excerpt is from its latest crawl, so a page that names a later date was either updated after "
                  "the window closed or looks past it. Either way it is not used.", ""]
        lines += sorted({f"- {d['url']} (published {d['published']}, names {d['names']})" for d in scout.dropped})
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    """Rebuild results/exa_news_weekly.csv and results/exa_evidence.md (from the cache when it is complete)."""
    scout = Scout()
    weekly = scout.weekly_news(NEWS_QUERIES, FIRST_WEEK, LAST_DAY, n=25)
    weekly.to_csv("results/exa_news_weekly.csv", index=False)
    Path("results/exa_evidence.md").write_text(evidence_markdown(scout))
    print(f"weeks: {weekly['week_start'].nunique()}  rows: {len(weekly)}  unserved: {int(weekly['count'].isna().sum())}")
    print(f"uncached calls: {scout.calls}  spent: ${scout.spent():.3f}  errors: {len(scout.errors)}  "
          f"dropped for a later date: {len(scout.dropped)}")
    for message in scout.errors[:5]:
        print("  ", message)


if __name__ == "__main__":
    main()
