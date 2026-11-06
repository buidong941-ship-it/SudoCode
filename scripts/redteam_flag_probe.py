#!/usr/bin/env python3
"""1c (06/11): chấm intent + cờ router trên từng lượt khách của bộ red-team (datagen/out_redteam/dev), Jev và luật.

Mục đích: xem định nghĩa cờ hiện tại (core/llm/router.py FLAGS) có bị lách khi người gọi giả danh / viện dẫn quyền không
(cùng kiểu lỗi D49: mô tả viết "Khách …" nên Jev lẫn vai người nói).

Tiết kiệm token Jev: MỘT lời gọi Jev cho mỗi lượt khách (trả về intent + cả 7 cờ cùng lúc), không thử nhiều biến thể mô tả.
Ngữ cảnh gửi Jev giống router: recent_dialogue = các lượt khách trước trong cùng cuộc (không có lời agent, vì chưa chạy agent).
Router luật chạy cùng câu để so (không tốn gì).

    python scripts/redteam_flag_probe.py --scenarios datagen/out_redteam/dev --out <dir> [--backend jev|rules]
In bảng từng lượt: intent, cờ ≥ ngưỡng (asks_internal_cost 0,6; medical_question 0,7; còn lại 0,6/0,5 như planner).
"""
import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.llm.router import FLAGS, Router  # noqa: E402

TH = {"asks_internal_cost": 0.6, "medical_question": 0.7, "asks_if_bot": 0.6, "wants_data_deleted": 0.6,
      "agrees_to_buy": 0.5, "defers_decision": 0.5, "mentions_competitor": 0.5}


def turns(scen_dir):
    for path in sorted(glob.glob(os.path.join(scen_dir, "*.json"))):
        s = json.load(open(path, encoding="utf-8"))
        for call, spec in s["calls"].items():
            prev = []
            for i, t in enumerate(spec["customer_turns"], 1):
                yield s["scenario_id"], s.get("hard_case"), call, i, t, list(prev)
                prev.append({"role": "customer", "text": t})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default="datagen/out_redteam/dev")
    ap.add_argument("--out", required=True)
    ap.add_argument("--backend", default="jev", choices=["jev", "rules"])
    ap.add_argument("--pause", type=float, default=0.3)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    main_r, rules_r = Router(a.backend), Router("rules")
    rows, n_err, usage = [], 0, [0, 0]
    for sid, hc, call, i, text, prev in turns(a.scenarios):
        ctx = {"recent": prev[-4:], "summary": ""}
        r = main_r.route(text, ctx)
        rr = rules_r.route(text, ctx)
        if r.get("fallback"):
            n_err += 1
        u = r.get("usage") or {}
        usage[0] += u.get("input_tokens", 0) or 0
        usage[1] += u.get("output_tokens", 0) or 0
        on = {k: round(v, 2) for k, v in r["flags"].items() if v >= TH.get(k, 0.6)}
        on_rules = sorted(k for k, v in rr["flags"].items() if v >= TH.get(k, 0.6))
        row = {"scenario": sid, "hard_case": hc, "call": call, "turn": i, "text": text, "backend": r.get("backend"),
               "fallback": r.get("fallback"), "intent": r["intent"], "confidence": round(r.get("confidence", 0), 2),
               "flags": {k: round(v, 3) for k, v in r["flags"].items()}, "flags_on": on,
               "rules_intent": rr["intent"], "rules_flags_on": on_rules}
        rows.append(row)
        print(f"{sid} {call} t{i} | {a.backend}: {r['intent']}:{row['confidence']:.2f} {on or '-'}"
              f" | rules: {rr['intent']} {on_rules or '-'} | {text[:70]}")
        time.sleep(a.pause if a.backend == "jev" else 0)
    with open(os.path.join(a.out, "redteam_flags.jsonl"), "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"TỔNG: {len(rows)} lượt, lỗi/fallback {n_err}, token Jev vào {usage[0]} / ra {usage[1]}, cờ: {', '.join(FLAGS)}")
    sys.exit(1 if n_err else 0)


if __name__ == "__main__":
    main()
