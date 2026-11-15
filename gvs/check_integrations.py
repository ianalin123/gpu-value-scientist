"""Check the shared memory end to end: three agents write, two of them read another's note.

    python -m gvs.check_integrations

Exits 0 when `proposer` recalled what `critic` wrote and `critic` recalled what `scout` wrote.
The log it appends to is the evidence of those cross-agent reads; it also says whether each
call was served by past.dev or by the local fallback.
"""
from __future__ import annotations

import json
import sys
import time

from .memory import SharedMemory

LOG_PATH = "results/memory_check_log.jsonl"
NAMESPACE = "gpu-value-scientist-check"
FACTS = {
    "scout": ("evidence", "Web evidence dated 2026-10-20: a neocloud announced a price increase on Blackwell B200 "
                          "rentals, citing data center power constraints.",
              {"date": "2026-10-20", "source": "integration check"}),
    "critic": ("critique", "The peer-lead hypothesis failed the gate: conditioning on marketplace peers moving first "
                           "did not lower pinball loss on H100 series, so it was rejected.",
               {"date": "2026-10-24", "verdict": "rejected", "hypothesis": "peer_lead"}),
    "proposer": ("hypothesis", "Proposal: weight past windows by days since the last posted price change, because "
                               "posted GPU prices move in rare steps.",
                 {"date": "2026-10-25", "feature": "since_change"}),
}
READS = (
    ("proposer", "critic", "Which hypothesis was rejected at the gate, and why?"),
    ("critic", "scout", "What dated web evidence is there of a B200 rental price increase?"),
)


def served_by(log_path: str, since_line: int) -> list[str]:
    lines = []
    with open(log_path) as handle:
        for entry in map(json.loads, handle.readlines()[since_line:]):
            if entry.get("op") == "write":
                lines.append(f"  write  {entry['agent']:<9} served by {entry['backend']}")
            elif entry.get("op") == "recall":
                writers = sorted({h["agent"] for h in entry["hits"]})
                lines.append(f"  recall {entry['agent']:<9} served by {entry['backend']}: {entry['n_hits']} hits, "
                             f"written by {writers}")
    return lines


def main() -> int:
    try:
        with open(LOG_PATH) as handle:
            already = len(handle.readlines())
    except OSError:
        already = 0
    mem = SharedMemory(log_path=LOG_PATH, namespace=NAMESPACE)
    for agent, (kind, text, data) in FACTS.items():
        mem.write(agent, kind, text, data)

    wrote = time.time()
    passed = True
    for reader, writer, query in READS:
        used = None
        while used is None and time.time() - wrote < 30:   # a note is searchable about a second after its write
            hits = mem.recall(reader, query, limit=5)
            used = next((h for h in hits if h["agent"] == writer), None)
            if used is None:
                time.sleep(1.0)
        print(f"{reader} asked: {query}")
        if used is None:
            passed = False
            print(f"  FAIL: no hit written by {writer}")
            continue
        print(f"  read after {time.time() - wrote:.1f}s, written by {used['agent']} ({used['kind']}, "
              f"backend {used['backend']}): {used['text']}")
        print(f"  {reader} uses it: data={json.dumps(used['data'], sort_keys=True)}")

    indexed = mem.wait_until_indexed()
    print(f"derived memory indexed: {json.dumps(indexed)}")
    print("summary:", json.dumps(mem.summary(), indent=1, sort_keys=True))
    print("served by:")
    print("\n".join(served_by(LOG_PATH, already)))
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
