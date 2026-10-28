#!/usr/bin/env python3
"""Validate Kaggle trace records and post-processing latency fields."""

import argparse
import json
import os

import jsonschema

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", nargs="+")
    args = parser.parse_args()
    with open(os.path.join(ROOT, "schemas", "trace_log.schema.json"), encoding="utf-8") as fh:
        schema = json.load(fh)
    counts = {"records": 0, "measured": 0, "estimated": 0, "bad_latency": 0, "post_parts": set()}
    for path in args.traces:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                jsonschema.validate(row, schema)
                counts["records"] += 1
                latency = row.get("latency", {})
                if "end_to_end_ms" in latency:
                    counts["measured"] += 1
                    if latency["end_to_end_ms"] < latency.get("total_ms", 0):
                        counts["bad_latency"] += 1
                else:
                    counts["estimated"] += 1
                if latency.get("post_ms", 0) < 0:
                    counts["bad_latency"] += 1
                counts["post_parts"].update(latency.get("post_parts_ms", {}))
    counts["post_parts"] = sorted(counts["post_parts"])
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    if counts["bad_latency"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
