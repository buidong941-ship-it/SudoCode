#!/usr/bin/env python3
"""Summarize response-ready, post-processing, and end-to-end latency from a trace JSONL."""

import argparse
import json
import statistics


def p95(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    return values[min(len(values) - 1, int(round(0.95 * len(values) + 0.5)) - 1)]


def stats(values):
    values = [v for v in values if v is not None]
    return None if not values else {
        "n": len(values),
        "p50_ms": int(statistics.median(values)),
        "p95_ms": int(p95(values)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", help="Trace JSONL emitted by run_eval.py")
    args = parser.parse_args()
    with open(args.trace, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]

    report = {
        "trace": args.trace,
        "n_turns": len(rows),
        "response_ready": stats([r.get("latency", {}).get("total_ms") for r in rows]),
        "post_processing": stats([r.get("latency", {}).get("post_ms") for r in rows]),
        "end_to_end": stats([
            r.get("latency", {}).get("end_to_end_ms",
                                     (r.get("latency", {}).get("total_ms") or 0)
                                     + (r.get("latency", {}).get("post_ms") or 0))
            for r in rows
        ]),
        "end_to_end_measured_turns": sum("end_to_end_ms" in r.get("latency", {}) for r in rows),
        "end_to_end_estimated_turns": sum("end_to_end_ms" not in r.get("latency", {}) for r in rows),
    }
    for field in ("parts", "post_parts_ms"):
        keys = sorted({k for r in rows for k in r.get("latency", {}).get(field, {})})
        report[field] = {
            key: stats([r.get("latency", {}).get(field, {}).get(key) for r in rows])
            for key in keys
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
