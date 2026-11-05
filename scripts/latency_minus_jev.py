#!/usr/bin/env python3
"""Latency đã trừ thời gian Jev nằm trên đường sinh câu trả lời.

Dùng khi Jev đi qua proxy (vd `TYPESAFE_BASE_URL=https://www.portixapi.com`), để tách
chậm do mạng/proxy khỏi chậm do hệ thống. Script CHỈ đọc trace, không sửa gì; số chính
thức vẫn là số của `eval/reference_eval.py`, số ở đây là dòng tham khảo đi kèm.

Jev nằm trên đường sinh câu trả lời (trước `t_ready`, nên nằm trong `total_ms` và `ttft_ms`) ở:
  - `latency.parts.slots_ms`: extractor hybrid gọi Jev đồng bộ trong
    `extractor.customer_slots_start` (khi `extractor_jev_hybrid` bật). Phần luật + CERT
    trong cùng khoảng này chỉ vài ms; Qwen trích chạy nền nên không nằm ở đây.
  - `router.ms` khi `router.backend == "jev"`.
  - `planner.llm.ms` khi planner LLM dùng Jev.
Phần Jev trích lời agent (`post_parts_ms.agent_extraction_wall_ms`) nằm SAU `t_ready`,
không thuộc `total_ms`, nên không trừ.

Hai chế độ:
  - mặc định: bỏ hẳn thời gian Jev ("nếu Jev tức thì") → cận dưới, tức mức tối đa mà
    proxy có thể làm chậm `total_ms`;
  - `--jev-ref-ms N`: giữ lại N ms cho mỗi chặng Jev, chỉ trừ phần vượt N (vd so một lần
    chạy với một lần chạy mốc). Lấy N từ trace mốc bằng `--jev-ref-trace <trace>` (p50 một
    chặng Jev). Lưu ý: các lần chạy của nhóm đều gọi Jev qua proxy, nên trace mốc cũng đã
    gồm thời gian proxy; chế độ này chỉ đo phần chậm THÊM so với mốc.

p95 tính đúng như `eval/reference_eval.py` (không bỏ lượt warm-up, trừ khi `--skip-warmup`).

Ví dụ:
  python scripts/latency_minus_jev.py runs/kaggle/<job>/.../full.jsonl
  python scripts/latency_minus_jev.py <trace proxy> --jev-ref-trace <trace Jev trực tiếp>
"""

import argparse
import json
import os
import statistics
import sys


def p95(xs):                                   # giống eval/reference_eval.py
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(0.95 * len(xs) + 0.5)) - 1)]


def stats(xs):
    xs = [x for x in xs if x is not None]
    return None if not xs else {"n": len(xs), "p50_ms": int(statistics.median(xs)), "p95_ms": int(p95(xs))}


def find_key(obj, key):
    """Tìm khóa ở mọi mức lồng của config.json (settings.describe() có thể lồng nhóm)."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            hit = find_key(v, key)
            if hit is not None:
                return hit
    return None


def load_config(trace_path):
    base = trace_path[:-len(".jsonl")] if trace_path.endswith(".jsonl") else trace_path
    path = base + ".config.json"
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def jev_legs(row, slots_is_jev):
    """→ list thời gian (ms) từng chặng Jev trên đường sinh câu trả lời của một lượt."""
    lat = row.get("latency") or {}
    parts = lat.get("parts") or {}
    legs = []
    if slots_is_jev and parts.get("slots_ms"):
        legs.append(("slots", int(parts["slots_ms"])))
    router = row.get("router") or {}
    if router.get("backend") == "jev" and router.get("ms"):
        legs.append(("router", int(router["ms"])))
    llm_plan = (row.get("planner") or {}).get("llm") or {}
    if str(llm_plan.get("backend", "")).startswith("jev") and llm_plan.get("ms"):
        legs.append(("planner", int(llm_plan["ms"])))
    return legs


def read_trace(path, skip_warmup):
    with open(path, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    rows = [r for r in rows if (r.get("latency") or {}).get("total_ms") is not None]
    return rows[skip_warmup:]


def slots_counts_as_jev(cfg, path, warn):
    if cfg is None:
        warn(f"{path}: không thấy .config.json → coi slots_ms là thời gian Jev")
        return True
    backend = find_key(cfg, "extractor_backend") or find_key(cfg, "extractor")
    jev_on = find_key(cfg, "extractor_jev_hybrid")
    if backend != "hybrid" or not jev_on:
        return False
    if find_key(cfg, "extractor_async") is False:
        warn(f"{path}: extractor_async tắt → slots_ms gồm cả Qwen trích, số trừ sẽ lớn hơn phần Jev")
    return True


def ref_ms_from_trace(path, skip_warmup, warn):
    cfg = load_config(path)
    slots_is_jev = slots_counts_as_jev(cfg, path, warn)
    legs = [ms for r in read_trace(path, skip_warmup) for _, ms in jev_legs(r, slots_is_jev)
            if ms >= 20]                       # bỏ lượt CERT bỏ qua Jev (chỉ còn vài ms của luật)
    if not legs:
        sys.exit(f"{path}: không có chặng Jev nào để lấy mốc tham chiếu")
    return int(statistics.median(legs)), len(legs)


def analyze(path, ref_ms, skip_warmup, warn):
    cfg = load_config(path)
    slots_is_jev = slots_counts_as_jev(cfg, path, warn)
    rows = read_trace(path, skip_warmup)
    ttft, ttft_adj, tot, tot_adj, removed, jev_turn = [], [], [], [], [], []
    by_leg = {}
    for r in rows:
        lat = r["latency"]
        legs = jev_legs(r, slots_is_jev)
        cut = 0
        for name, ms in legs:
            by_leg.setdefault(name, []).append(ms)
            cut += max(0, ms - ref_ms)
        jev_turn.append(sum(ms for _, ms in legs))
        removed.append(cut)
        tot.append(lat["total_ms"])
        tot_adj.append(max(0, lat["total_ms"] - cut))
        if lat.get("ttft_ms") is not None:
            ttft.append(lat["ttft_ms"])
            ttft_adj.append(max(0, lat["ttft_ms"] - cut))
    s_tot, s_tot_adj = stats(tot), stats(tot_adj)
    return {
        "trace": path,
        "n_turns": len(rows),
        "slots_ms_counted_as_jev": slots_is_jev,
        "router_backend": (find_key(cfg, "router_backend") if cfg else None),
        "jev_ref_ms": ref_ms,
        "turns_with_jev_on_path": sum(1 for x in jev_turn if x > 0),
        "jev_on_path_per_turn": stats(jev_turn),
        "jev_by_leg": {k: stats(v) for k, v in sorted(by_leg.items())},
        "removed_per_turn": stats(removed),
        "ttft": {"raw": stats(ttft), "adjusted": stats(ttft_adj)},
        "total": {"raw": s_tot, "adjusted": s_tot_adj},
        "total_p95_delta_ms": (s_tot_adj["p95_ms"] - s_tot["p95_ms"]) if s_tot and s_tot_adj else None,
    }


def fmt_s(st, key):
    return "—" if not st else f"{st[key] / 1000:.2f}"


def print_table(reports):
    head = ("trace", "lượt", "lượt có Jev", "Jev/lượt p50", "Jev/lượt p95", "đã trừ p50",
            "TTFT p95 gốc→trừ", "Total p50 gốc→trừ", "Total p95 gốc→trừ")
    print("| " + " | ".join(head) + " |")
    print("|" + "---|" * len(head))
    for rep in reports:
        name = rep["trace"].replace("\\", "/")
        name = "/".join(name.split("/")[-4:])
        t, tt = rep["total"], rep["ttft"]
        print("| " + " | ".join([
            name, str(rep["n_turns"]), str(rep["turns_with_jev_on_path"]),
            fmt_s(rep["jev_on_path_per_turn"], "p50_ms"), fmt_s(rep["jev_on_path_per_turn"], "p95_ms"),
            fmt_s(rep["removed_per_turn"], "p50_ms"),
            f"{fmt_s(tt['raw'], 'p95_ms')} → {fmt_s(tt['adjusted'], 'p95_ms')}",
            f"{fmt_s(t['raw'], 'p50_ms')} → {fmt_s(t['adjusted'], 'p50_ms')}",
            f"{fmt_s(t['raw'], 'p95_ms')} → {fmt_s(t['adjusted'], 'p95_ms')}",
        ]) + " |")
    print("\nĐơn vị: giây. 'trừ' = bỏ thời gian Jev trên đường sinh câu trả lời"
          + (f", giữ lại {reports[0]['jev_ref_ms']} ms mỗi chặng (mốc Jev)." if reports and reports[0]["jev_ref_ms"]
             else " (cận dưới: coi như Jev tức thì).")
          + " Số chính thức vẫn là cột gốc (eval/reference_eval.py).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("traces", nargs="+", help="trace JSONL của run_eval.py")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--jev-ref-ms", type=int, default=0,
                   help="ms giữ lại cho mỗi chặng Jev (ước lượng gọi trực tiếp); mặc định 0 = bỏ hẳn")
    g.add_argument("--jev-ref-trace", help="trace mốc; lấy p50 một chặng Jev của nó làm --jev-ref-ms")
    ap.add_argument("--skip-warmup", type=int, default=0,
                    help="bỏ N lượt đầu mỗi trace (hướng dẫn đo latency: 3); mặc định 0 như reference_eval.py")
    ap.add_argument("--json", action="store_true", help="in JSON thay cho bảng")
    args = ap.parse_args()

    warnings = []
    ref_ms = args.jev_ref_ms
    if args.jev_ref_trace:
        ref_ms, n = ref_ms_from_trace(args.jev_ref_trace, args.skip_warmup, warnings.append)
        warnings.append(f"mốc Jev: p50 {ref_ms} ms trên {n} chặng của {args.jev_ref_trace}")
    reports = [analyze(p, ref_ms, args.skip_warmup, warnings.append) for p in args.traces]
    if args.json:
        print(json.dumps({"warnings": warnings, "reports": reports}, ensure_ascii=False, indent=2))
    else:
        for w in warnings:
            print(f"[!] {w}", file=sys.stderr)
        print_table(reports)


if __name__ == "__main__":
    main()
