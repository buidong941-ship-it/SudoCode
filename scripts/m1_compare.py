"""M1 + so cặp cấu hình đích (chạy trên Kaggle CPU, chỉ đọc trace đã có).

    python scripts/m1_compare.py <traces_dir> <out_dir>

<traces_dir>/<run>/<set>.jsonl với run ∈ {r0, r1, base, c4, rg, tg, tgb}; set ∈ {v3, rt, jn}.
tg/tgb = kiến trúc đích (UNDERSTANDING=deepseek) full/baseline; rg = cổng yêu cầu 10/11.
1) reference_eval của BTC: full (r0, r1) + baseline (base) → report M1 cho từng set.
2) So cặp theo ca: TSR qua/trượt, tool ghi, guardrail, ca đổi kết quả giữa r0/r1/c4.
"""
import collections
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETS = {"v3": "datagen/out_v3/final/dev", "rt": "datagen/out_redteam/dev", "jn": "datagen/out_jev1108_new/dev"}
WRITE = ("order.create", "order.update", "schedule.callback", "handoff.transfer", "memory.forget")


def load(p):
    return [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()] if os.path.exists(p) else None


def evaluate(scen, full, base, out):
    cmd = [sys.executable, os.path.join(ROOT, "eval/reference_eval.py"), "--scenarios", os.path.join(ROOT, scen), "--trace", full, "--out", out]
    if base and os.path.exists(base):
        cmd += ["--baseline", base]
    subprocess.run(cmd, check=True, capture_output=True)
    return json.load(open(out, encoding="utf-8"))


def pick(rep, side):
    m = rep.get(side) or {}
    v = lambda k, *sub: (lambda x: [x := (x or {}).get(s) for s in sub][-1] if sub else x)(m.get(k))
    return {"TSR": v("task_success_rate", "value"), "CCR": v("context_carryover_rate", "value"), "RQR": v("repeat_question_rate", "value"),
            "HR_price": v("hallucination_rate", "price_promo_only", "value"), "HR": v("hallucination_rate", "value"),
            "guard": v("guardrail_violations", "total"), "turns": m.get("avg_turns_per_call"),
            "tsr_fail": sorted({f.get("scenario") for f in (v("task_success_rate", "failures") or [])}),
            "guard_by_type": v("guardrail_violations", "by_type"), "guard_cases": sorted({(g.get("scenario"), g.get("type")) for g in (v("guardrail_violations", "examples") or [])})}


def writes(rows):
    c, per = collections.Counter(), collections.defaultdict(list)
    for r in rows:
        for tc in r.get("tool_calls") or []:
            if tc.get("name") in WRITE:
                c[tc["name"]] += 1
                per[r["scenario_id"]].append(tc["name"])
    return dict(c), per


BASE_OF = {"r0": "base", "r1": "base", "rg": "base", "tg": "tgb"}


def ustats(rows):
    """Bộ hiểu thống nhất + cổng yêu cầu: số lượt, lần gọi, lỗi, slot bỏ, chặn ghi, độ trễ."""
    n = calls = err = 0
    ms, drop, blocked, errs, amb, inten = [], collections.Counter(), collections.defaultdict(list), [], 0, collections.Counter()
    gate_turns = 0
    for r in rows:
        u, g = r.get("understanding"), r.get("request_gate")
        if g:
            gate_turns += 1
            for b in g.get("blocked") or []:
                blocked[r["scenario_id"]].append(b)
        if not u:
            continue
        n += 1
        calls += u.get("calls") or 0
        if u.get("error"):
            err += 1
            errs.append([r["scenario_id"], u["error"][:120]])
            continue
        ms.append(u.get("ms") or 0)
        inten[u.get("intent")] += 1
        amb += (u.get("ambiguity") or {}).get("level") == "needs_clarification"
        for d in u.get("dropped") or []:
            drop[f"{d.get('slot')}:{d.get('why')}"] += 1
    ms.sort()
    q = lambda f: ms[min(len(ms) - 1, int(f * len(ms)))] if ms else None
    return {"turns_understood": n, "turns_with_gate": gate_turns, "deepseek_calls": calls, "calls_per_turn": round(calls / n, 3) if n else None,
            "errors": err, "error_examples": errs[:10], "ms_p50": q(.5), "ms_p95": q(.95), "ambiguous_turns": amb,
            "dropped": dict(drop.most_common(20)), "gate_blocked": {k: v for k, v in sorted(blocked.items())}, "intents": dict(inten)}


def main():
    tdir, out = sys.argv[1:3]
    os.makedirs(out, exist_ok=True)
    res = {}
    for s, scen in SETS.items():
        res[s] = {}
        wr = {}
        for run in ("r0", "r1", "c4", "rg", "tg"):
            full = os.path.join(tdir, run, f"{s}.jsonl")
            if not os.path.exists(full):
                continue
            b = os.path.join(tdir, BASE_OF[run], f"{s}.jsonl") if run in BASE_OF else None
            rep = evaluate(scen, full, b, os.path.join(out, f"report_{run}_{s}.json"))
            res[s][run] = {"system": pick(rep, "system")}
            if b and os.path.exists(b):
                res[s][run]["baseline"] = pick(rep, "baseline")
                res[s][run]["comparison"] = rep.get("comparison")
            res[s][run]["latency"] = (rep.get("system") or {}).get("latency")
            wr[run] = writes(load(full))
            res[s][run]["writes"] = wr[run][0]
            if run in ("rg", "tg"):
                res[s][run]["understanding"] = ustats(load(full))
                if os.path.exists(os.path.join(tdir, "tgb", f"{s}.jsonl")) and run == "tg":
                    res[s][run]["understanding_baseline"] = ustats(load(os.path.join(tdir, "tgb", f"{s}.jsonl")))
        diff = {}
        for a, b in (("r0", "r1"), ("c4", "r0"), ("c4", "r1"), ("r0", "rg"), ("r0", "tg"), ("rg", "tg")):
            if a in res[s] and b in res[s]:
                fa, fb = set(res[s][a]["system"]["tsr_fail"]), set(res[s][b]["system"]["tsr_fail"])
                ws = sorted(k for k in set(wr[a][1]) | set(wr[b][1]) if sorted(wr[a][1].get(k, [])) != sorted(wr[b][1].get(k, [])))
                diff[f"{a}->{b}"] = {"newly_failed": sorted(fb - fa), "newly_passed": sorted(fa - fb),
                                     "write_changed": {k: [wr[a][1].get(k, []), wr[b][1].get(k, [])] for k in ws}}
        res[s]["diff"] = diff
    json.dump(res, open(os.path.join(out, "m1_compare.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1)[:20000])


if __name__ == "__main__":
    main()
