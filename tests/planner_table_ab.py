#!/usr/bin/env python3
"""D51: so A/B offline — planner như trước D51 (PLANNER_SKIP_SINCE=D51; trước 06/11 là PLANNER_TABLE=0 = _plan cũ, trace trùng) với bảng đầy đủ D51 + tầng tra SP (PRODUCT_LEXICON=1).

    python tests/planner_table_ab.py --out-dir /tmp/ab

Offline (router rules, generator offline, extractor rules, transport direct): số TUYỆT ĐỐI không phải số báo cáo,
chỉ để xem thay đổi của planner theo từng kịch bản. Chấm bằng eval/reference_eval.py (bản BTC, import hàm).
Không dùng holdout. v3 dev là bộ rút ra các case mới → chỉ để xem; kết luận dựa trên các bộ khác (D38).
Exit 1 nếu có guardrail violation mới hoặc bộ nào TSR giảm.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "eval"))
import reference_eval as RE  # noqa: E402

SETS = [("sample", "test_set/public_sample"), ("nat_dev", "datagen/out_nat/dev"),
        ("v1_1_dev", "datagen/out_btc_like_final_v1_1/final/dev"), ("v2_1_dev", "datagen/out_btc_like_final_v2_1/final/dev"),
        ("d7_dev", "datagen/out_btc_like_d7/final/dev"), ("v3_dev(nguồn case)", "datagen/out_v3/final/dev")]
VARIANTS = {"old": {"PLANNER_SKIP_SINCE": "D51", "PRODUCT_LEXICON": "0"}, "table51": {"PLANNER_SKIP_SINCE": "", "PRODUCT_LEXICON": "1"}}


def run(out_dir, tag, scen, var, config, workers):
    out = os.path.join(out_dir, f"{tag}-{var}-{config}.jsonl")
    env = {**os.environ, **VARIANTS[var], "DATABASE_URL": f"sqlite:///{out_dir}/{tag}-{var}.db", "LLM_CACHE": "off",
           "IMPROVE_DIR": "", "PLANNER_BACKEND": "rules"}
    subprocess.run([sys.executable, os.path.join(ROOT, "run_eval.py"), "--scenarios", os.path.join(ROOT, scen), "--config", config,
                    "--out", out, "--router", "rules", "--generator", "offline", "--extractor", "rules", "--transport", "direct",
                    "--run-id", f"ab-{var}", "--workers", str(workers)], check=True, env=env, cwd=ROOT, stderr=subprocess.DEVNULL)
    return out


def passed(scen, trace):
    ok = {}
    for sid, s in scen.items():
        res = [RE.check_call(spec, trace.get((sid, call), []))[0] for call, spec in s["calls"].items()]
        res = [r for r in res if r is not None]
        if res:
            ok[sid] = all(res)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    out_dir = a.out_dir or tempfile.mkdtemp(prefix="table_ab_")
    os.makedirs(out_dir, exist_ok=True)
    report, fail = {}, []
    print("| Bộ | TSR cũ → bảng D51 | CCR | RQR | HR | vi phạm guardrail | KB đổi kết quả |")
    print("|---|---|---|---|---|---|---|")
    for name, scen_dir in SETS:
        if not os.path.isdir(os.path.join(ROOT, scen_dir)):
            print(f"| {name} | (không có bộ) |"); continue
        tag = name.split("(")[0]
        scen = RE.load_scenarios(os.path.join(ROOT, scen_dir))
        m, ok = {}, {}
        for var in VARIANTS:
            tr = RE.load_trace(run(out_dir, tag, scen_dir, var, "full", a.workers))
            m[var], ok[var] = RE.evaluate(scen, tr), passed(scen, tr)
        flips = {sid: ("+" if ok["table51"].get(sid) else "−") for sid in ok["old"] if ok["old"].get(sid) != ok["table51"].get(sid)}
        g = lambda v, k: m[v][k].get("value")
        viol = lambda v: m[v]["guardrail_violations"]["total"]
        print(f"| {name} | {g('old', 'task_success_rate')} → {g('table51', 'task_success_rate')} | "
              f"{g('old', 'context_carryover_rate')} → {g('table51', 'context_carryover_rate')} | "
              f"{g('old', 'repeat_question_rate')} → {g('table51', 'repeat_question_rate')} | "
              f"{g('old', 'hallucination_rate')} → {g('table51', 'hallucination_rate')} | {viol('old')} → {viol('table51')} | "
              + (", ".join(f"{k}{v}" for k, v in sorted(flips.items())) or "—") + " |")
        report[name] = {"old": {k: m["old"][k] for k in ("task_success_rate", "context_carryover_rate", "repeat_question_rate",
                                                       "hallucination_rate", "guardrail_violations")},
                        "table51": {k: m["table51"][k] for k in ("task_success_rate", "context_carryover_rate", "repeat_question_rate",
                                                               "hallucination_rate", "guardrail_violations")}, "flips": flips}
        if "nguồn case" not in name and (g("table51", "task_success_rate") or 0) < (g("old", "task_success_rate") or 0):
            fail.append(f"{name}: TSR giảm")
        if viol("table51") > viol("old"):
            fail.append(f"{name}: thêm vi phạm guardrail")
    json.dump(report, open(os.path.join(out_dir, "planner_table_ab.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    for f in fail:
        print("CẢNH BÁO:", f)
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
