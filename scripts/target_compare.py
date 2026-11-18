"""Phép đo tích hợp cấu hình đích ARCH=target (11/11) — chạy trên Kaggle CPU, chỉ đọc trace đã có.

    python scripts/target_compare.py <traces_dir> <out_dir>

<traces_dir>/<run>/<set>.jsonl, run ∈ {tt (đích full), ttb (đích baseline_no_memory), r0, base, tg, tgb}; set ∈ {v3, rt, jn}.
1) M1 bằng eval/reference_eval.py của BTC (tt so ttb; r0 so base; tg so tgb).
2) So cặp theo ca r0→tt, tg→tt: TSR mới trượt / mới qua, tool ghi thay đổi.
3) Thống kê đường đích: bộ hiểu (lời gọi/lượt, lỗi, mơ hồ, căn cứ bị loại), state yêu cầu (sự kiện, lý do chặn, trạng thái),
   chính sách an toàn, renderer (block, block bị chặn, compose dùng / bị loại), audit (status, Jev thật / giả lập, lời gọi, lỗi,
   recall ứng viên số tiền), lời gọi model mỗi lượt, độ trễ.
4) K09: bảng rà claim HR sai (scripts/hr_review.py) cho tt.
"""
import collections
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from m1_compare import SETS, evaluate, load, pick, ustats, writes  # noqa: E402

SETS = {**SETS, "ho": "datagen/out_v3/final/holdout"}          # V3 holdout (người dùng giao đo cấu hình đích 11/11)
BASE_OF = {"tt": "ttb", "r0": "base", "tg": "tgb"}


def q(xs, f):
    xs = sorted(x for x in xs if x is not None)
    return xs[min(len(xs) - 1, int(f * len(xs)))] if xs else None


def tstats(rows):
    c = collections.Counter
    ev, blk, status, branches, blocks, blocked, rej = c(), c(), c(), c(), c(), c(), c()
    audit_status, qback, cback, aerr = c(), c(), c(), []
    n = qcalls = ccalls = compose_used = compose_calls = 0
    money_c = money_claimed = 0
    ttft, total, post, ams, e2e = [], [], [], [], []
    unavailable_turns = []
    dup_tools, dup_turns = 0, 0
    for r in rows:
        n += 1
        seen_tc, d = set(), 0
        for tc in r.get("tool_calls") or []:          # lời gọi tool trùng trong một lượt (cùng tên + cùng tham số)
            key = (tc.get("name"), json.dumps(tc.get("args") or {}, sort_keys=True, ensure_ascii=False))
            d += key in seen_tc
            seen_tc.add(key)
        dup_tools += d
        dup_turns += bool(d)
        rs = r.get("request_state") or {}
        for e in rs.get("events") or []:
            ev[e.get("event")] += 1
        for item in rs.get("items") or []:
            pass
        if rs.get("hold"):
            blk[f"hold:{rs['hold']}"] += 1
        for b in rs.get("blocked") or []:
            blk[b] += 1
        for w in (r.get("planner") or {}).get("branches") or []:
            if w.get("branch") in ("safety_policy", "request_blocked", "exchange_return_conflict", "address_complete"):
                branches[f"{w['branch']}:{(w.get('reason') or '')[:60]}"] += 1
        g = (r.get("guardrail") or {}).get("render") or {}
        for b in g.get("blocks") or []:
            blocks[b["kind"]] += 1
        for b in g.get("blocked") or []:
            blocked[f"{b['kind']}:{b['why']}"] += 1
        comp = g.get("compose") or {}
        if comp.get("used"):
            compose_used += 1
            compose_calls += int(bool(comp.get("compose_ms") is not None))
            for x in comp.get("rejected") or []:
                rej[f"{x['part']}:{x['why'].split(':')[0]}"] += 1
        a = r.get("audit") or {}
        if a:
            audit_status[a.get("status")] += 1
            qm, cm = a.get("question") or {}, a.get("claim") or {}
            qback[qm.get("backend")] += 1
            cback[cm.get("backend")] += 1
            qcalls += qm.get("calls") or 0
            ccalls += cm.get("calls") or 0
            money_c += cm.get("money_candidates") or 0
            money_claimed += cm.get("money_candidates_claimed") or 0
            ams.append(a.get("ms"))
            if a.get("status") != "ok":
                unavailable_turns.append([r["scenario_id"], r["call"], r["turn"], a.get("status"),
                                          (qm.get("errors") or [])[:2], cm.get("error")])
        lat = r.get("latency") or {}
        ttft.append(lat.get("ttft_ms")); total.append(lat.get("total_ms")); post.append(lat.get("post_ms"))
        e2e.append(lat.get("end_to_end_ms"))     # turn() đợi audit xong mới nhận lượt sau → thời gian thực tới khi sẵn sàng
        for item in rs.get("items") or []:
            status[f"{item.get('kind')}:{item.get('status')}"] += 0     # trạng thái cuối được đếm ở dưới
    final = {}
    for r in rows:
        for item in (r.get("request_state") or {}).get("items") or []:
            final[(r["scenario_id"], r["call"], item["id"])] = f"{item.get('kind')}:{item.get('status')}"
    status = c(final.values())
    u = ustats(rows)
    return {"turns": n, "understanding": u, "request_events": dict(ev), "request_final_status": dict(status), "write_blocked": dict(blk),
            "policy_branches": dict(branches.most_common(30)), "blocks": dict(blocks), "blocks_blocked": dict(blocked),
            "compose": {"turns_used": compose_used, "llm_calls": compose_calls, "rejected": dict(rej)},
            "audit": {"status": dict(audit_status), "question_backend": dict(qback), "claim_backend": dict(cback),
                      "question_calls": qcalls, "claim_calls": ccalls, "ms_p50": q(ams, .5), "ms_p95": q(ams, .95),
                      "money_candidates": money_c, "money_candidates_claimed": money_claimed,
                      "not_ok_turns": unavailable_turns[:30], "not_ok_count": len(unavailable_turns)},
            "model_calls_per_turn": {"deepseek_understanding": u.get("calls_per_turn"),
                                     "jev_or_sim_question": round(qcalls / n, 3) if n else None,
                                     "qwen_claim": round(ccalls / n, 3) if n else None,
                                     "qwen_compose": round(compose_calls / n, 3) if n else None},
            "latency": {"ttft_p50": q(ttft, .5), "ttft_p95": q(ttft, .95), "total_p50": q(total, .5), "total_p95": q(total, .95),
                        "post_p95": q(post, .95), "end_to_end_p50": q(e2e, .5), "end_to_end_p95": q(e2e, .95),
                        "ttft_le_3s_share": round(sum(1 for x in ttft if x is not None and x <= 3000) / n, 3) if n else None},
            "duplicate_tool_calls": {"calls": dup_tools, "turns": dup_turns}}


def main():
    tdir, out = sys.argv[1:3]
    os.makedirs(out, exist_ok=True)
    res = {}
    for s, scen in SETS.items():
        res[s] = {}
        wr = {}
        for run in ("tt", "r0", "tg"):
            full = os.path.join(tdir, run, f"{s}.jsonl")
            if not os.path.exists(full):
                continue
            b = os.path.join(tdir, BASE_OF[run], f"{s}.jsonl")
            rep = evaluate(scen, full, b, os.path.join(out, f"report_{run}_{s}.json"))
            res[s][run] = {"system": pick(rep, "system")}
            if os.path.exists(b):
                res[s][run]["baseline"] = pick(rep, "baseline")
                res[s][run]["comparison"] = rep.get("comparison")
            res[s][run]["latency"] = (rep.get("system") or {}).get("latency")
            wr[run] = writes(load(full))
            res[s][run]["writes"] = wr[run][0]
        for run in ("tt", "ttb", "tg", "tgb"):
            p = os.path.join(tdir, run, f"{s}.jsonl")
            if os.path.exists(p):
                res[s][f"{run}_stats"] = tstats(load(p))
        if "tt" in wr:
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts/hr_review.py"), os.path.join(ROOT, scen),
                            os.path.join(tdir, "tt", f"{s}.jsonl"), os.path.join(out, f"hr_review_tt_{s}.json")], check=False)
        diff = {}
        for a, b in (("r0", "tt"), ("tg", "tt")):
            if a in res[s] and b in res[s]:
                fa, fb = set(res[s][a]["system"]["tsr_fail"]), set(res[s][b]["system"]["tsr_fail"])
                ws = sorted(k for k in set(wr[a][1]) | set(wr[b][1]) if sorted(wr[a][1].get(k, [])) != sorted(wr[b][1].get(k, [])))
                diff[f"{a}->{b}"] = {"newly_failed": sorted(fb - fa), "newly_passed": sorted(fa - fb),
                                     "write_changed": {k: [wr[a][1].get(k, []), wr[b][1].get(k, [])] for k in ws}}
        res[s]["diff"] = diff
    json.dump(res, open(os.path.join(out, "target_compare.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str)[:30000])


if __name__ == "__main__":
    main()
