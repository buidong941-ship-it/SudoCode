"""G: chi phí mỗi cuộc gọi lấy từ trace (`llm_usage` của generator + số lần gọi Jev / LLM extractor / router).

Không có giá nào viết cứng là "chính thức": đơn giá truyền bằng tham số (VND hoặc USD tùy bạn), ghi rõ trong báo cáo.
  --gen-in / --gen-out   đơn giá generator trên 1 triệu token vào / ra (Qwen tự host: quy đổi từ giá GPU; DeepSeek: giá API)
  --jev-call             đơn giá một lần gọi Jev (system_one)
  --gpu-hour + --gpu-calls-per-hour   (tùy chọn) quy đổi thời gian GPU cho Qwen tự host

    python scripts/cost_report.py --trace runs/.../dev/full.jsonl --gen-in 0.07 --gen-out 0.28 --jev-call 0.0004 --currency USD
"""
import argparse
import json
from collections import defaultdict


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trace", required=True)
    ap.add_argument("--gen-in", type=float, default=0.0)
    ap.add_argument("--gen-out", type=float, default=0.0)
    ap.add_argument("--jev-call", type=float, default=0.0)
    ap.add_argument("--currency", default="USD")
    ap.add_argument("--json")
    a = ap.parse_args()
    calls = defaultdict(lambda: {"turns": 0, "prompt_tokens": 0, "completion_tokens": 0, "jev_calls": 0, "llm_extract_calls": 0,
                                 "router_llm_calls": 0, "total_ms": 0})
    for line in open(a.trace, encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        c = calls[(r["scenario_id"], r["call"])]
        c["turns"] += 1
        u = r.get("llm_usage") or {}
        c["prompt_tokens"] += u.get("prompt_tokens") or 0
        c["completion_tokens"] += u.get("completion_tokens") or 0
        ex = r.get("extractor") or {}
        c["jev_calls"] += (ex.get("jev_label_requests") or 0) + (ex.get("jev_slot_requests") or 0)
        c["llm_extract_calls"] += (ex.get("customer_llm_requests") or 0) + (ex.get("agent_llm_requests") or 0)
        ro = r.get("router") or {}
        c["router_llm_calls"] += int(ro.get("backend") not in (None, "rules"))
        if (r.get("planner") or {}).get("llm"):
            c["jev_calls"] += int(r["planner"]["llm"].get("backend") == "jev")
        c["total_ms"] += (r.get("latency") or {}).get("total_ms") or 0
    n = len(calls)
    if not n:
        raise SystemExit("trace rỗng")
    tot = {k: sum(c[k] for c in calls.values()) for k in next(iter(calls.values()))}
    per = {k: round(v / n, 2) for k, v in tot.items()}
    cost = (per["prompt_tokens"] * a.gen_in + per["completion_tokens"] * a.gen_out) / 1e6 + per["jev_calls"] * a.jev_call
    out = {"calls": n, "per_call": per, "cost_per_call": round(cost, 6), "currency": a.currency,
           "unit_prices": {"gen_in_per_1M": a.gen_in, "gen_out_per_1M": a.gen_out, "jev_per_call": a.jev_call}}
    print(f"{n} cuộc gọi · mỗi cuộc: {per['turns']} lượt, {per['prompt_tokens']:.0f} token vào / {per['completion_tokens']:.0f} ra "
          f"(generator), {per['jev_calls']} lần gọi Jev, {per['llm_extract_calls']} lần LLM extractor, "
          f"{per['total_ms'] / 1000:.1f}s tổng xử lý")
    print(f"chi phí ước tính mỗi cuộc: {cost:.6f} {a.currency} (đơn giá: {out['unit_prices']})")
    if a.json:
        json.dump(out, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
