"""Shared long-term memory for the research agents, stored on past.dev.

Every agent writes to and recalls from one past.dev project. A data point sent without an
`audience` is readable by every identity of the project, so each agent keeps its own identity
(`<namespace>:<agent>`) both as author and as reader, and still reads what the others wrote.
The writer and the kind of every note travel three ways so they survive recall: in the source
id (`<namespace>:<agent>:<kind>:<hash>`), in `metadata`, and as a prefix of the content.

Every write and every recall is appended to a JSONL log. That log is the public record of
which agent read which other agent's notes, and it is also the offline backend: with no key,
or when the API errors or times out, recall is served by keyword overlap over the same log.
Nothing here raises into the caller.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PAST_API = "https://app.past.dev/api/v1"
TIMEOUT_S = 10
USER_AGENT = "gpu-value-scientist/0.1"
MAX_CONSECUTIVE_FAILURES = 2
RECENT_WRITE_S = 20.0
PREFIX = re.compile(r"^\[agent=(?P<agent>\S+) kind=(?P<kind>\S+) ns=(?P<ns>\S+)\]\s*")
WORD = re.compile(r"[a-z0-9][a-z0-9.\-]*")
STOPWORDS = frozenset(
    "a an and are as at be by did do does for from had has have how in is it its of on or that the "
    "their this to was were what when which who why will with".split()
)


def env_value(name: str) -> str | None:
    """The environment variable, or the value in the repo's git-ignored .env file."""
    value = os.environ.get(name)
    if value:
        return value
    try:
        lines = (REPO_ROOT / ".env").read_text().splitlines()
    except OSError:
        return None
    for line in lines:
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        if line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        if key.strip() == name:
            return raw.strip().strip('"').strip("'") or None
    return None


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tokens(text: str) -> list[str]:
    return [w for w in WORD.findall(text.lower()) if w not in STOPWORDS and len(w) > 1]


def _timestamp_from(data: dict) -> str | None:
    """A note about a dated observation is filed at that date, not at the time of writing."""
    for key in ("timestamp", "date", "origin", "as_of"):
        value = data.get(key)
        if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}", value):
            return value if "T" in value else value[:10] + "T00:00:00Z"
    return None


class SharedMemory:
    def __init__(self, log_path: str, namespace: str = "gpu-value-scientist"):
        self.log_path = Path(log_path)
        self.namespace = namespace
        self._key = env_value("PAST_API_KEY")
        self._failures = 0
        self._pending: dict[str, float] = {}   # ingestionId -> time of the write
        self._last_write = 0.0
        self._writes: Counter = Counter()
        self._recalls: Counter = Counter()
        self._backends: Counter = Counter()
        self._hits = 0
        self._cross_hits = 0
        self._cross_pairs: Counter = Counter()

    # ------------------------------------------------------------------ public

    def write(self, agent: str, kind: str, text: str, data: dict | None = None) -> None:
        try:
            self._write(agent, kind, text, dict(data or {}))
        except Exception as error:  # the research loop must never stop on its memory
            self._log({"op": "write", "backend": "none", "agent": agent, "kind": kind, "text": text,
                       "error": self._clean(error)})

    def recall(self, agent: str, query: str, limit: int = 8, kind: str | None = None) -> list[dict]:
        try:
            return self._recall(agent, query, limit, kind)
        except Exception as error:
            self._log({"op": "recall", "backend": "none", "agent": agent, "query": query, "kind": kind,
                       "hits": [], "error": self._clean(error)})
            return []

    def wait_until_indexed(self, timeout: float = 45.0, poll: float = 1.5) -> dict:
        """Block until past.dev has finished deriving memory from every write of this run.

        A written note is recallable as a `source` document about a second after the write;
        the claims past.dev derives from it take longer (about 14 s measured for one note).
        """
        start = time.time()
        failed: list[str] = []
        while self._pending and self._past_on() and time.time() - start < timeout:
            for ingestion_id in list(self._pending):
                try:
                    _, body = self._http("GET", "/ingest/" + urllib.parse.quote(ingestion_id, safe=""))
                except Exception:
                    continue
                status = body.get("status") if isinstance(body, dict) else None
                if status in ("completed", "failed"):
                    self._pending.pop(ingestion_id, None)
                    if status == "failed":
                        failed.append(ingestion_id)
            if self._pending:
                time.sleep(poll)
        result = {"backend": "past" if self._past_on() else "local", "waited_s": round(time.time() - start, 2),
                  "pending": len(self._pending), "failed": failed}
        self._log({"op": "wait_until_indexed", **result})
        return result

    def summary(self) -> dict:
        return {
            "namespace": self.namespace,
            "log_path": str(self.log_path),
            "writes_per_agent": dict(self._writes),
            "recalls_per_agent": dict(self._recalls),
            "recalled_hits": self._hits,
            "cross_agent_hits": self._cross_hits,
            "cross_agent_reads": {pair: n for pair, n in sorted(self._cross_pairs.items())},
            "calls_per_backend": dict(self._backends),
        }

    # ------------------------------------------------------------------ write

    def _write(self, agent: str, kind: str, text: str, data: dict) -> None:
        digest = hashlib.sha256("\x1f".join((self.namespace, agent, kind, text)).encode()).hexdigest()[:16]
        source_id = f"{self.namespace}:{agent}:{kind}:{digest}"
        timestamp = _timestamp_from(data) or self._first_timestamp(source_id) or _now()
        entry = {"op": "write", "backend": "local", "namespace": self.namespace, "agent": agent, "kind": kind,
                 "id": source_id, "text": text, "data": data, "timestamp": timestamp, "error": None}
        if self._past_on():
            body = {
                "id": source_id,
                "content": f"[agent={agent} kind={kind} ns={self.namespace}] {text}",
                "label": f"{self.namespace} / {agent} / {kind}",
                "timestamp": timestamp,
                "identity": f"{self.namespace}:{agent}",
                "metadata": {"namespace": self.namespace, "agent": agent, "kind": kind, "data": data},
            }
            try:
                status, receipt = self._http("POST", "/ingest", body)
                entry["backend"] = "past"
                entry["past"] = {"http": status, "status": receipt.get("status"),
                                 "unchanged": receipt.get("unchanged"), "ingestionId": receipt.get("ingestionId")}
                if receipt.get("status") == "queued" and receipt.get("ingestionId"):
                    self._pending[receipt["ingestionId"]] = time.time()
                    self._last_write = time.time()
                self._failures = 0
            except Exception as error:
                self._failures += 1
                entry["error"] = self._clean(error)
        self._writes[agent] += 1
        self._backends[entry["backend"]] += 1
        self._log(entry)

    # ------------------------------------------------------------------ recall

    def _recall(self, agent: str, query: str, limit: int, kind: str | None) -> list[dict]:
        hits, backend, error = None, "local", None
        if self._past_on():
            try:
                hits = self._recall_past(agent, query, limit, kind)
                attempts = 0
                while not hits and attempts < 3 and time.time() - self._last_write < RECENT_WRITE_S:
                    time.sleep(1.5)   # a note written seconds ago may not be searchable yet
                    attempts += 1
                    hits = self._recall_past(agent, query, limit, kind)
                backend = "past"
                self._failures = 0
            except Exception as failure:
                self._failures += 1
                error = self._clean(failure)
                hits = None
        if hits is None:
            hits = self._recall_local(query, limit, kind)
        for hit in hits:
            hit["backend"] = backend
            hit["cross_agent"] = hit["agent"] not in (agent, None)
        cross = [h for h in hits if h["cross_agent"]]
        self._recalls[agent] += 1
        self._backends[backend] += 1
        self._hits += len(hits)
        self._cross_hits += len(cross)
        for hit in cross:
            self._cross_pairs[f"{agent} read {hit['agent']}"] += 1
        self._log({"op": "recall", "backend": backend, "namespace": self.namespace, "agent": agent, "query": query,
                   "kind": kind, "limit": limit, "n_hits": len(hits), "cross_agent_hits": len(cross),
                   "hits": hits, "error": error})
        return hits

    def _recall_past(self, agent: str, query: str, limit: int, kind: str | None) -> list[dict]:
        # past.dev has no metadata filter, so the namespace and kind filters run here.
        body = {"query": query if kind is None else f"{query} (kind={kind})",
                "identity": f"{self.namespace}:{agent}", "level": "high",
                "limit": min(200, max(40, limit * 6))}
        _, page = self._http("POST", "/recall", body)
        by_source: dict[str, dict] = {}
        for doc in page.get("results", []):
            is_source = (doc.get("artifact") or {}).get("kind") == "source"
            for source in doc.get("sources") or []:
                source_id = str(source.get("sourceId") or "")
                meta = source.get("metadata") or {}
                parsed = self._parse_id(source_id)
                if meta.get("namespace", parsed.get("namespace")) != self.namespace:
                    continue
                hit = by_source.setdefault(source_id, {
                    "text": "", "agent": meta.get("agent") or parsed.get("agent"),
                    "kind": meta.get("kind") or parsed.get("kind"), "data": meta.get("data") or {},
                    "score": None, "rank": doc.get("rank"), "id": source_id,
                    "occurred_at": source.get("occurredAt"), "derived": []})
                raw = doc.get("content") if is_source else next(iter(source.get("excerpts") or []), "")
                if raw and not hit["text"]:
                    hit["text"] = PREFIX.sub("", raw)
                if not is_source and doc.get("content"):
                    hit["derived"].append(doc["content"])
        hits = [h for h in by_source.values() if kind is None or h["kind"] == kind]
        for hit in hits:
            if not hit["text"]:
                hit["text"] = (self._logged_write(hit["id"]) or {}).get("text") or " ".join(hit["derived"])
        hits.sort(key=lambda h: h["rank"] if h["rank"] is not None else 10**6)
        return hits[:limit]

    def _recall_local(self, query: str, limit: int, kind: str | None) -> list[dict]:
        wanted = set(_tokens(query))
        scored = []
        for entry in self._logged_writes().values():
            if kind is not None and entry.get("kind") != kind:
                continue
            words = set(_tokens(f"{entry.get('text', '')} {entry.get('kind', '')} {entry.get('agent', '')}"))
            overlap = len(wanted & words)
            if overlap:
                score = round(overlap / (len(wanted) ** 0.5 * len(words) ** 0.5), 4)
                scored.append((score, entry))
        scored.sort(key=lambda pair: -pair[0])
        return [{"text": e.get("text", ""), "agent": e.get("agent"), "kind": e.get("kind"),
                 "data": e.get("data") or {}, "score": score, "rank": rank, "id": e.get("id"),
                 "occurred_at": e.get("timestamp"), "derived": []}
                for rank, (score, e) in enumerate(scored[:limit], start=1)]

    # ------------------------------------------------------------------ plumbing

    def _past_on(self) -> bool:
        return bool(self._key) and self._failures < MAX_CONSECUTIVE_FAILURES

    def _http(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        request = urllib.request.Request(
            PAST_API + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": "Bearer " + (self._key or ""), "Content-Type": "application/json",
                     "User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                payload = json.loads(response.read() or b"{}")
                return response.status, payload if isinstance(payload, dict) else {}
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"past.dev {method} {path} returned {error.code}: {detail}") from None

    def _parse_id(self, source_id: str) -> dict:
        prefix = self.namespace + ":"
        if not source_id.startswith(prefix):
            return {}
        parts = source_id[len(prefix):].split(":")
        return {"namespace": self.namespace, "agent": parts[0], "kind": parts[1]} if len(parts) == 3 else {}

    def _logged_writes(self) -> dict[str, dict]:
        """Every note of this namespace in the log, newest version of each id."""
        notes: dict[str, dict] = {}
        try:
            with self.log_path.open() as handle:
                for line in handle:
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    if entry.get("op") == "write" and entry.get("namespace") == self.namespace and entry.get("id"):
                        notes[entry["id"]] = entry
        except OSError:
            pass
        return notes

    def _logged_write(self, source_id: str) -> dict | None:
        return self._logged_writes().get(source_id)

    def _first_timestamp(self, source_id: str) -> str | None:
        """Reuse the first write's timestamp so a rerun sends an identical, unchanged data point."""
        try:
            with self.log_path.open() as handle:
                for line in handle:
                    if source_id in line:
                        entry = json.loads(line)
                        if entry.get("op") == "write" and entry.get("id") == source_id and entry.get("timestamp"):
                            return entry["timestamp"]
        except (OSError, ValueError):
            pass
        return None

    def _clean(self, error: Exception) -> str:
        message = f"{type(error).__name__}: {error}"[:400]
        return message.replace(self._key, "<key>") if self._key else message

    def _log(self, entry: dict) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a") as handle:
                handle.write(json.dumps({"ts": _now(), **entry}, sort_keys=True, default=str) + "\n")
        except OSError:
            pass
