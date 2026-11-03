#!/usr/bin/env python3
"""D22: chạy lại guardrail khẳng định khuyến mãi trên trace có sẵn (không gọi LLM), đếm câu bị bắt.

Trạng thái KM gom theo cả cuộc gọi từ `tool_calls` trong trace, giống `CallSession._call_promos`.
In JSON: số lượt bị bắt theo config, và danh sách lượt (để đọc tay: bắt đúng hay bắt nhầm).

    python scripts/promo_guard_audit.py runs/.../c5r1/dev/full.jsonl [thêm trace...]
"""
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("RAG_MODE", "bm25")

from harness import guardrails  # noqa: E402
from harness.agent import CallSession  # noqa: E402


def audit(path):
    rows = [json.loads(x) for x in open(path, encoding="utf-8") if x.strip()]
    rows.sort(key=lambda r: (r["scenario_id"], r["call"], r["turn"]))
    sessions, hits, n = {}, [], Counter()
    for r in rows:
        key = (r["scenario_id"], r["call"])
        if key not in sessions:
            s = CallSession.__new__(CallSession)
            s.call_promo_active, s.call_promo_expired = set(), set()
            sessions[key] = s
        promos = sessions[key]._call_promos(r.get("tool_calls") or [])
        n[r["config"]] += 1
        p = guardrails.promo_problems(r.get("agent_text") or "", promos)
        if p:
            hits.append({"config": r["config"], "turn": f"{r['scenario_id']}/{r['call']}/{r['turn']}",
                         "goals": r.get("goals"), "guard_action": (r.get("guardrail") or {}).get("action"),
                         "active": [x["promo_code"] for x in promos["active"]], "problem": p[0], "text": r.get("agent_text")})
    return {"trace": path, "turns": dict(n), "flagged": dict(Counter(h["config"] for h in hits)), "hits": hits}


def main():
    out = [audit(p) for p in sys.argv[1:]]
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
