"""Rà job kiểm tích hợp cấu hình đích (chạy trên Kaggle CPU, chỉ đọc trace). Chỉ xét các ca ĐÃ chạy (job dùng --only).

    python scripts/sim_review.py <run_dir> <out.json>      # run_dir chứa datagen_out_*/full.jsonl

In: TSR/lý do trượt theo ca đã chạy, guardrail theo ca, tool ghi, goal từng lượt của ca trượt, lỗi bộ hiểu, trạng thái audit,
block bị chặn, lý do chặn ghi, câu agent.
"""
import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "eval"))
import reference_eval as RE  # noqa: E402

SETS = {"datagen_out_v3_final_dev": "datagen/out_v3/final/dev", "datagen_out_redteam_dev": "datagen/out_redteam/dev",
        "datagen_out_jev1108_new_dev": "datagen/out_jev1108_new/dev", "holdout": "datagen/out_v3/final/holdout"}
WRITE = ("order.create", "order.update", "schedule.callback", "handoff.transfer")


def main():
    run_dir, out = sys.argv[1:3]
    doc = {}
    for sub, sdir in SETS.items():
        p = os.path.join(run_dir, sub, "full.jsonl")
        if not os.path.exists(p):
            continue
        trace = RE.load_trace(p)
        ran = sorted({k[0] for k in trace})
        scen = {k: v for k, v in RE.load_scenarios(os.path.join(ROOT, sdir)).items() if k in ran}
        tsr = RE.task_success_rate(scen, trace)
        gv = RE.guardrail_violations(scen, trace)
        hr = RE.hallucination_rate(scen, trace)
        rqr = RE.repeat_question_rate(scen, trace)
        rows = [r for rs in trace.values() for r in rs]
        c = collections.Counter
        audit = c((r.get("audit") or {}).get("status") for r in rows)
        uerr = [[r["scenario_id"], r["call"], r["turn"], (r.get("understanding") or {}).get("error")] for r in rows
                if (r.get("understanding") or {}).get("error")]
        blocked = c(b for r in rows for b in (r.get("request_state") or {}).get("blocked") or [])
        bblk = c(f"{b['kind']}:{b['why']}" for r in rows for b in ((r.get("guardrail") or {}).get("render") or {}).get("blocked") or [])
        gaction = c((r.get("guardrail") or {}).get("action") for r in rows)
        comp_rej = c(f"{x['part']}:{x['why']}" for r in rows for x in
                     (((r.get("guardrail") or {}).get("render") or {}).get("compose") or {}).get("rejected") or [])
        safety = c(w.get("reason", "")[:70] for r in rows for w in (r.get("planner") or {}).get("branches") or []
                   if w.get("branch") == "safety_policy")
        fails = {f["scenario"] for f in tsr["failures"]}
        detail = {}
        for sid in ran:
            turns = []
            for (s, call), rs in sorted(trace.items()):
                if s != sid:
                    continue
                for r in rs:
                    u = r.get("understanding") or {}
                    turns.append({"call": call, "turn": r["turn"], "customer": r["customer_text"][:160], "agent": r["agent_text"][:260],
                                  "intent": u.get("intent"), "requests": u.get("requests"), "resp": u.get("response"), "asks": u.get("asks"),
                                  "safety": u.get("safety"), "amb": (u.get("ambiguity") or {}).get("level"), "uerr": u.get("error"),
                                  "goals": r.get("goals"), "writes": [t["name"] for t in r.get("tool_calls") or [] if t["name"] in WRITE],
                                  "blocked": (r.get("request_state") or {}).get("blocked"),
                                  "events": [e.get("event") + ":" + str(e.get("kind") or e.get("status") or e.get("why") or "")
                                             for e in (r.get("request_state") or {}).get("events") or []],
                                  "questions": [(q["slot"], q["type"]) for q in r.get("questions") or []],
                                  "claims": [(cl["field"], cl["value"], cl.get("sku")) for cl in r.get("claims") or []],
                                  "audit": (r.get("audit") or {}).get("status"), "gaction": (r.get("guardrail") or {}).get("action"),
                                  "gproblems": (r.get("guardrail") or {}).get("problems")})
            detail[sid] = {"tsr": "FAIL" if sid in fails else "ok",
                           "reasons": [f["reasons"] for f in tsr["failures"] if f["scenario"] == sid], "turns": turns}
        doc[sub] = {"ran": ran, "tsr": {k: tsr[k] for k in ("value", "passed", "total")},
                    "failures": [f for f in tsr["failures"]], "guardrail": {k: gv[k] for k in ("total", "by_type", "examples")},
                    "hr": {"value": hr["value"], "price": hr["price_promo_only"], "examples": hr["examples"]},
                    "rqr": {k: rqr[k] for k in ("value", "redundant", "total_questions", "examples")},
                    "audit_status": dict(audit), "understanding_errors": uerr, "write_blocked": dict(blocked),
                    "blocks_blocked": dict(bblk), "guard_action": dict(gaction), "compose_rejected": dict(comp_rej),
                    "safety_policy": dict(safety), "detail": detail}
        print(f"== {sub}: ran {len(ran)} | TSR {tsr['value']} ({tsr['passed']}/{tsr['total']}) | guard {gv['total']} {gv['by_type']} | "
              f"HR {hr['value']} price {hr['price_promo_only']['value']} | RQR {rqr['value']} | audit {dict(audit)} | uerr {len(uerr)}")
        for f in tsr["failures"]:
            print("  TSR FAIL", f["scenario"], f["call"], f["reasons"])
        for e in gv["examples"]:
            print("  GUARD", e)
        print("  write_blocked", dict(blocked), "| blocks_blocked", dict(bblk), "| guard_action", dict(gaction))
        print("  compose_rejected", dict(comp_rej), "| safety", dict(safety))
        for sid in sorted(fails):
            print(f"  --- {sid}")
            for t in detail[sid]["turns"]:
                print("   ", json.dumps(t, ensure_ascii=False)[:900])
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    json.dump(doc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
