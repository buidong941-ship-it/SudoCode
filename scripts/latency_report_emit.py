#!/usr/bin/env python3
"""Báo cáo latency RIÊNG (13/11, người dùng duyệt) — không thay, không sửa evaluator BTC (eval/reference_eval.py).

    python scripts/latency_report_emit.py --trace full=runs/x/full.jsonl --trace baseline=runs/x/baseline.jsonl --out runs/x/latency

Quy ước:
- Đo tại ranh giới backend / harness thật: trace `measure=emit_v1` → total_ms = tới lần emit câu trả lời (callback on_emit);
  không streaming nên TTFT = Total. Trace kiểu cũ (không có `measure`) được báo là KHÔNG hợp lệ cho báo cáo này.
- Bỏ 3 lượt warm-up đầu của MỖI trace (một trace = một config / một job), theo thứ tự emit thực tế (latency.emit_wall_ts).
- p50 = statistics.median, p95 = hàm p95 của BTC (nạp từ eval/reference_eval.py) — cùng công thức với bộ chấm.
- Báo số mẫu hợp lệ; < 100 lượt → cảnh báo (như BTC).
- Call Brief: mọi cuộc gọi có call_brief_latency_ms (runtime trong start(); phần nạp offline ghi riêng ở call_brief_offline).
- Chỉ số chẩn đoán riêng, KHÔNG trộn vào TTFT / Total: response_ready (câu xong, chưa gửi), emit, post (việc đồng bộ sau
  gửi), end_to_end (turn() trả về), audit (nền, tính từ lúc gửi audit), audit_run, turn_complete (cả lượt kể cả audit).
- Không trừ / ước lượng latency API: chỉ dùng số đo trong trace.
"""
import argparse
import importlib.util
import json
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WARMUP = 3
DIAG = ("response_ready_ms", "emit_ms", "post_ms", "end_to_end_ms", "audit_ms", "audit_run_ms", "turn_complete_ms")


def _btc():
    spec = importlib.util.spec_from_file_location("btc_reference_eval", os.path.join(ROOT, "eval", "reference_eval.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def stats(xs, p95):
    xs = [x for x in xs if isinstance(x, (int, float))]
    if not xs:
        return None
    return {"n": len(xs), "p50_ms": int(statistics.median(xs)), "p95_ms": int(p95(xs)), "max_ms": int(max(xs))}


def load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, ln in enumerate(f):
            if ln.strip():
                r = json.loads(ln)
                r["_line"] = i
                rows.append(r)
    return rows


def report(rows, p95, warmup):
    turns = [r for r in rows if not r.get("error") and isinstance(r.get("latency"), dict)]
    errors = sum(1 for r in rows if r.get("error"))
    measured = [r for r in turns if r["latency"].get("measure") == "emit_v1"]
    order = sorted(measured, key=lambda r: (r["latency"].get("emit_wall_ts") or 0, r["_line"]))
    kept = order[warmup:]
    lat = lambda k: [r["latency"].get(k) for r in kept]
    briefs = [r.get("call_brief_latency_ms") for r in turns if r.get("call_brief_latency_ms") is not None]
    offline = [(r.get("call_brief_offline") or {}).get("ms") for r in turns if r.get("call_brief_offline")]
    audit = {}
    for r in turns:
        st = r.get("audit_status") or "missing"
        audit[st] = audit.get(st, 0) + 1
    emit_bad = sum(1 for r in turns if r.get("emit_check") and not (r["emit_check"].get("received") and r["emit_check"].get("sha_match")))
    n = len(kept)
    return {
        "n_rows": len(rows), "n_turn_errors": errors, "n_turns": len(turns), "n_old_measure": len(turns) - len(measured),
        "warmup_excluded": min(warmup, len(order)), "warmup_turns": [f"{r.get('scenario_id')}/{r.get('call')}/t{r.get('turn')}" for r in order[:warmup]],
        "n_valid_turns": n,
        "warning": None if n >= 100 else f"chỉ {n} lượt hợp lệ (< 100): p95 chưa đủ ý nghĩa",
        "ttft": stats(lat("ttft_ms"), p95), "total": stats(lat("total_ms"), p95),
        "call_brief": stats(briefs, p95), "call_brief_offline_not_counted": stats(offline, p95),
        "diagnostic": {k: stats(lat(k), p95) for k in DIAG},
        "audit_status": audit, "emit_check_failed": emit_bad,
        "ttft_equals_total": all(r["latency"].get("ttft_ms") == r["latency"].get("total_ms") for r in kept),
    }


def md(rep, args):
    L = ["# Báo cáo latency riêng (bỏ warm-up, p95 công thức BTC)", "",
         f"Trace: {', '.join(args.trace)}. Bỏ {args.warmup} lượt warm-up đầu mỗi trace theo thứ tự emit. Không streaming → TTFT = Total "
         "(đo tới lần emit thật). Chỉ số chẩn đoán báo riêng, không thay TTFT / Total.", ""]
    L += ["| Config | n hợp lệ | TTFT p50 / p95 | Total p50 / p95 | Call Brief p50 / p95 (n) | Cảnh báo |", "|---|---|---|---|---|---|"]
    f = lambda s: "—" if not s else f"{s['p50_ms']} / {s['p95_ms']}"
    for name, r in rep.items():
        cb = r["call_brief"]
        L.append(f"| {name} | {r['n_valid_turns']} | {f(r['ttft'])} | {f(r['total'])} | {f(cb)} ({cb['n'] if cb else 0}) | {r['warning'] or ''} |")
    L += ["", "## Chẩn đoán (ms, p50 / p95)", "", "| Config | " + " | ".join(DIAG) + " |", "|---|" + "---|" * len(DIAG)]
    for name, r in rep.items():
        L.append(f"| {name} | " + " | ".join(f(r["diagnostic"][k]) for k in DIAG) + " |")
    L += ["", "## Trạng thái audit / emit", ""]
    for name, r in rep.items():
        L.append(f"- {name}: audit {r['audit_status']}, emit_check lỗi {r['emit_check_failed']}, lượt lỗi {r['n_turn_errors']}, "
                 f"trace đo kiểu cũ {r['n_old_measure']}, warm-up bỏ: {', '.join(r['warmup_turns'])}")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", action="append", required=True, help="tên=đường_dẫn.jsonl (lặp lại cho mỗi config)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--warmup", type=int, default=WARMUP)
    ap.add_argument("--strict", action="store_true",
                    help="thoát mã 3 nếu còn audit pending / thiếu, emit_check lỗi, hoặc trace đo kiểu cũ (kiểm tích hợp)")
    args = ap.parse_args()
    btc = _btc()
    rep = {}
    for t in args.trace:
        name, _, path = t.partition("=")
        rep[name] = report(load(path), btc.p95, args.warmup)
    os.makedirs(args.out, exist_ok=True)
    json.dump({"warmup": args.warmup, "p95": "eval/reference_eval.p95 (BTC)", "configs": rep},
              open(os.path.join(args.out, "latency_report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(os.path.join(args.out, "latency_report.md"), "w", encoding="utf-8").write(md(rep, args))
    print(md(rep, args))
    if args.strict:
        bad = {n: {"audit_unfinished": sum(v for k, v in r["audit_status"].items() if k in ("pending", "missing")),
                   "emit_check_failed": r["emit_check_failed"], "old_measure": r["n_old_measure"]} for n, r in rep.items()}
        bad = {n: b for n, b in bad.items() if any(b.values())}
        if bad:
            print("KIỂM TÍCH HỢP EMIT / AUDIT LỖI:", json.dumps(bad, ensure_ascii=False))
            raise SystemExit(3)
        print("KIỂM TÍCH HỢP EMIT / AUDIT: OK (mọi lượt đã emit đúng sha, audit đã ghi kết quả cuối, đo kiểu emit_v1)")


if __name__ == "__main__":
    main()
