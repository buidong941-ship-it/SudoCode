#!/usr/bin/env python3
"""Audit rule certificates on labeled extractor examples, outside runtime.

This older label set is a sanity check, not the new benchmark holdout.
"""

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.extractor import agent_questions, customer_slots_rules
from harness.rule_confidence import customer, question


def upper_error_bound(errors, n, alpha=.05):
    if not n:
        return None
    if errors == n:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(60):
        p = (lo + hi) / 2
        cdf = sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i)
                  for i in range(errors + 1))
        if cdf > alpha:
            lo = p
        else:
            hi = p
    return round((lo + hi) / 2, 4)


def read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    folder = ROOT / "tests" / "extract_eval"
    customers = read(folder / "customer.jsonl")
    agents = read(folder / "agent.jsonl")
    c_cert = []
    for item in customers:
        rules = customer_slots_rules(item["text"], "2026-10-15")
        if customer(item["text"], rules, item.get("context"))["certified"]:
            c_cert.append(rules == item["slots"])
    q_cert = []
    for item in agents:
        rules = agent_questions(item["sentence"], {})
        if question(item["sentence"], rules)["certified"]:
            correct = len(rules) == 1 and rules[0]["slot"] == item["ask"] and rules[0]["type"] == item["qtype"]
            q_cert.append(correct)
    result = {"source": "tests/extract_eval (previously used labels; not independent holdout)",
              "customer_slots": {"labeled": len(customers), "certified": len(c_cert), "wrong": c_cert.count(False),
                                 "upper_error_95pct": upper_error_bound(c_cert.count(False), len(c_cert))},
              "agent_questions": {"labeled": len(agents), "certified": len(q_cert), "wrong": q_cert.count(False),
                                  "upper_error_95pct": upper_error_bound(q_cert.count(False), len(q_cert))},
              "agent_claims": {"certified": 0, "reason": "claim rules abstain until independently validated"}}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
