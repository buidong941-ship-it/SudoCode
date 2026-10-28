#!/usr/bin/env python3
"""Count hybrid customer LLM calls saved by the candidate gate on labeled dev rows."""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("RAG_MODE", "bm25")

from harness import extractor  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    path = os.path.join(ROOT, "tests", "extract_eval", "customer.jsonl")
    with open(path, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    skipped = 0
    missed = []
    for row in rows:
        rules = extractor.customer_slots_rules(row["text"], "2026-10-20")
        candidate = extractor.customer_llm_candidate(row["text"], row.get("context"))
        if not candidate:
            skipped += 1
            missing = set(row["slots"]) - set(rules) - set(row.get("skip") or [])
            if missing:
                missed.append({"id": row["id"], "slots": sorted(missing)})
    report = {"split": "labeled_dev", "rows": len(rows), "llm_calls_without_gate": len(rows),
              "llm_calls_with_gate": len(rows) - skipped, "saved_calls": skipped,
              "gold_slots_missed_by_gate": missed}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if missed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
