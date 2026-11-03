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
from harness.rule_confidence import customer, empty, question


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


def audit_trace(path):
    """A1: recompute CERT with the current rules on a trace and count why it fails."""
    from collections import Counter, defaultdict
    from harness.extractor import _sentences

    rows = read(Path(path))
    side = {"customer": defaultdict(Counter), "agent": defaultdict(Counter)}
    sole = {"customer": Counter(), "agent": Counter()}
    total = {"customer": Counter(), "agent": Counter()}
    prev_q, slot_cert = {}, Counter()
    slot_fail, slot_examples, x_examples = defaultdict(Counter), defaultdict(list), []
    for r in sorted(rows, key=lambda x: (x["scenario_id"], x["call"], x["turn"])):
        has_context = r["turn"] > 1 or r["call"] != "call_1"
        text = r.get("customer_text") or ""
        rules = customer_slots_rules(text, "2026-10-15")
        # CERT v2 (3.3): slot agent hỏi ở lượt trước trong cùng cuộc gọi (question_slot của planner, ghi trong trace)
        asked = prev_q.get((r["scenario_id"], r["call"]))
        prev_q[(r["scenario_id"], r["call"])] = r.get("question_slot")
        cert = customer(text, rules, "ctx" if has_context else None, asked)
        slot_cert.update(cert.get("certified_slots") or [])
        for k, p in (cert.get("slots") or {}).items():          # D27: check con nào trượt, theo từng slot (CERT v2)
            if not p["certified"]:
                bad = [c for c, v in p["checks"].items() if not v]
                slot_fail[k].update(bad)
                if len(slot_examples[k]) < 4:
                    slot_examples[k].append({"turn": f"{r['scenario_id']}/{r['call']}/{r['turn']}", "text": text[:140],
                                             "value": rules.get(k), "failed": bad, "asked": asked})
        if cert.get("version") == 2 and cert["checks"].get("S") and not cert["checks"].get("X"):
            x_examples.append({"turn": f"{r['scenario_id']}/{r['call']}/{r['turn']}", "text": text[:140],
                               "slots": sorted(rules), "extra_cues": cert.get("extra_cues")})
        slot = next(iter(rules), "-") if len(rules) == 1 else ("none" if not rules else "multi")
        _tally(side["customer"][slot], sole["customer"], total["customer"], cert)
        for s in _sentences(r.get("agent_text") or ""):
            q = agent_questions(s, {})
            cert = question(s, q)
            slot = q[0]["slot"] if len(q) == 1 else ("none" if not q else "multi")
            _tally(side["agent"][slot], sole["agent"], total["agent"], cert)
    from core.config import settings
    out = {"trace": str(path), "rows": len(rows), "cert_version": settings.extractor_cert_version,
           "cert_v2_relax": settings.cert_v2_relax,
           "customer_slots_certified": dict(slot_cert.most_common()),
           "slot_failed_checks": {k: dict(c.most_common()) for k, c in sorted(slot_fail.items())},
           "slot_failed_examples": dict(sorted(slot_examples.items())), "x_failed_examples": x_examples[:10]}
    jev_empty = [not ((r.get("extractor") or {}).get("jev_customer_labels") or []) for r in rows
                 if empty(r.get("customer_text") or "", customer_slots_rules(r.get("customer_text") or "", "2026-10-15"),
                          "ctx" if r["turn"] > 1 or r["call"] != "call_1" else None)["certified"]]
    out["customer_empty_vs_jev"] = {"certified": len(jev_empty), "jev_disagrees": jev_empty.count(False)}
    for k in ("customer", "agent"):
        out[k] = {"items": sum(side[k][s]["_n"] for s in side[k]),
                  "certified": sum(side[k][s]["certified"] for s in side[k]),
                  "failed_check": dict(total[k].most_common()),
                  "sole_blocker": dict(sole[k].most_common()),
                  "by_slot": {s: dict(c.most_common()) for s, c in sorted(side[k].items())}}
    print(json.dumps(out, ensure_ascii=False, indent=2))


def _tally(slot_counter, sole, total, cert):
    slot_counter["_n"] += 1
    if cert["certified"]:
        slot_counter["certified"] += 1
        return
    failed = [k for k, v in cert["checks"].items() if not v]
    slot_counter[cert["reason"]] += 1
    total.update(failed)
    if len(failed) == 1:
        sole[failed[0]] += 1


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--trace":
        return audit_trace(sys.argv[2])
    folder = ROOT / "tests" / "extract_eval"
    customers = read(folder / "customer.jsonl")
    agents = read(folder / "agent.jsonl")
    c_cert = []
    for item in customers:
        rules = customer_slots_rules(item["text"], "2026-10-15")
        if customer(item["text"], rules, item.get("context"))["certified"]:
            c_cert.append(rules == item["slots"])
    e_cert = [item["slots"] == {} for item in customers
              if empty(item["text"], customer_slots_rules(item["text"], "2026-10-15"), item.get("context"))["certified"]]
    q_cert = []
    for item in agents:
        rules = agent_questions(item["sentence"], {})
        if question(item["sentence"], rules)["certified"]:
            correct = len(rules) == 1 and rules[0]["slot"] == item["ask"] and rules[0]["type"] == item["qtype"]
            q_cert.append(correct)
    result = {"source": "tests/extract_eval (previously used labels; not independent holdout)",
              "customer_slots": {"labeled": len(customers), "certified": len(c_cert), "wrong": c_cert.count(False),
                                 "upper_error_95pct": upper_error_bound(c_cert.count(False), len(c_cert))},
              "customer_empty": {"labeled": len(customers), "certified": len(e_cert), "wrong": e_cert.count(False),
                                 "upper_error_95pct": upper_error_bound(e_cert.count(False), len(e_cert))},
              "agent_questions": {"labeled": len(agents), "certified": len(q_cert), "wrong": q_cert.count(False),
                                  "upper_error_95pct": upper_error_bound(q_cert.count(False), len(q_cert))},
              "agent_claims": {"certified": 0, "reason": "claim rules abstain until independently validated"}}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
