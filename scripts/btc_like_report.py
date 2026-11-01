#!/usr/bin/env python3
"""Verify a frozen BTC-like benchmark and summarize paired full-agent runs.

Example: python scripts/btc_like_report.py --manifest datagen/out_btc_like_final_v1/manifest.json
    --split dev --run current=runs/.../current --run gate=runs/.../gate --out runs/.../comparison.json
"""

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path


def get(obj, *keys):
    for key in keys:
        obj = obj.get(key, {}) if isinstance(obj, dict) else {}
    return obj if obj != {} else None


def percentile(values, percent):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * percent
    low = math.floor(index)
    high = math.ceil(index)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (index - low), 2)


def distribution(values):
    return {"n": len(values), "p50_ms": percentile(values, .5), "p95_ms": percentile(values, .95)}


def verify_manifest(path, split):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    frozen = manifest.get("frozen") or {}
    source = frozen.get("source")
    if source not in ("raw", "final"):
        raise ValueError("Manifest has not been frozen")
    selected = [item for item in manifest["scenarios"] if item["split"] == split]
    if not selected:
        raise ValueError(f"No scenarios for split {split}")
    for item in selected:
        rel = f"{source}/{split}/{item['scenario_id']}.json"
        scenario = path.parent / rel
        if not scenario.is_file() or hashlib.sha256(scenario.read_bytes()).hexdigest() != frozen["sha256"].get(rel):
            raise ValueError(f"Scenario missing or changed after freeze: {rel}")
    return manifest, selected


def read_trace(path, selected):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected = {item["scenario_id"]: item["n_turns"] for item in selected}
    counts = Counter(row["scenario_id"] for row in rows)
    if counts != expected:
        raise ValueError(f"Trace mismatch in {path}: expected {expected}, found {counts}")
    keys = [(row["scenario_id"], row["call"], row["turn"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError(f"Duplicate scenario/call/turn in {path}")
    return rows


def side_metrics(report, side):
    d = report.get(side) or {}
    return {"TSR": get(d, "task_success_rate", "value"),
            "TSR_hard": get(d, "task_success_rate", "hard_cases", "value"),
            "CCR": get(d, "context_carryover_rate", "value"),
            "RQR": get(d, "repeat_question_rate", "value"),
            "HR_all": get(d, "hallucination_rate", "value"),
            "HR_price_promo": get(d, "hallucination_rate", "price_promo_only", "value"),
            "guardrail": get(d, "guardrail_violations", "total")}


def trace_metrics(rows):
    names = {"ttft": "ttft_ms", "total": "total_ms", "post": "post_ms", "end_to_end": "end_to_end_ms"}
    latencies = {name: distribution([row["latency"][key] for row in rows
                                     if isinstance(row.get("latency", {}).get(key), (int, float))])
                 for name, key in names.items()}
    brief_total, brief_e2e = [], []
    for row in rows:
        brief = row.get("call_brief_latency_ms") or 0
        if row.get("turn") == 1:
            brief_total.append(row["latency"]["total_ms"] + brief)
            if row["latency"].get("end_to_end_ms") is not None:
                brief_e2e.append(row["latency"]["end_to_end_ms"] + brief)
    latencies["call_brief_plus_total"] = distribution(brief_total)
    latencies["call_brief_plus_end_to_end"] = distribution(brief_e2e)
    extractor = [row.get("extractor") or {} for row in rows]
    return {"latency": latencies,
            "extractor": {"rule_certified_sentences": sum(x.get("rule_certified_sentences", 0) for x in extractor),
                          "customer_llm_requests": sum(x.get("customer_llm_requests", 0) for x in extractor),
                          "agent_llm_requests": sum(x.get("agent_llm_requests", 0) for x in extractor),
                          "jev_slot_requests": sum(x.get("jev_slot_requests", 0) for x in extractor),
                          "fallback_turns": sum(bool(x.get("fallback")) for x in extractor),
                          "customer_qwen_skipped_turns": sum(bool(x.get("customer_qwen_skipped")) for x in extractor),
                          "agent_qwen_skipped_turns": sum(bool(x.get("agent_qwen_skipped")) for x in extractor)}}


def summarize_run(root, split, selected):
    suite = json.loads((root / "suite.json").read_text(encoding="utf-8"))
    if suite.get("failed"):
        raise ValueError(f"Suite failed: {root}")
    report = json.loads((root / split / "report.json").read_text(encoding="utf-8"))
    if report["n_scenarios"] != len(selected):
        raise ValueError(f"Report scenario count mismatch: {root}")
    sides = {}
    for config, side in (("full", "system"), ("baseline_no_memory", "baseline")):
        rows = read_trace(root / split / f"{config}.jsonl", selected)
        sides[config] = {"score": side_metrics(report, side), **trace_metrics(rows)}
    return {"suite_seconds": suite.get("seconds"), "settings": suite.get("settings"), "sides": sides}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--split", choices=("dev", "holdout"), required=True)
    parser.add_argument("--run", action="append", required=True, help="NAME=SUITE_DIRECTORY")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest, selected = verify_manifest(args.manifest, args.split)
    runs = {}
    for spec in args.run:
        name, sep, path = spec.partition("=")
        if not sep or not name or not path or name in runs:
            parser.error("--run must be unique NAME=SUITE_DIRECTORY")
        runs[name] = summarize_run(Path(path), args.split, selected)
    result = {"split": args.split, "benchmark_source": manifest["frozen"]["source"],
              "n_scenarios": len(selected), "n_calls": sum(x["n_calls"] for x in selected),
              "n_turns": sum(x["n_turns"] for x in selected), "runs": runs}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Validated {len(selected)} scenarios and {result['n_turns']} turns per trace; wrote {args.out}")


if __name__ == "__main__":
    main()
