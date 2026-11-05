"""Kiểm scripts/latency_minus_jev.py trên trace tổng hợp (không cần mạng, không cần GPU).

- chỉ trừ slots_ms khi config bật extractor hybrid + Jev; router/planner Jev luôn trừ;
- --jev-ref-ms giữ lại N ms mỗi chặng, chặng ngắn hơn N không bị trừ;
- TTFT và Total trừ cùng một lượng, không âm;
- p95 trùng với eval/reference_eval.py;
- trace không có .config.json → coi slots_ms là Jev (kèm cảnh báo).
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "eval"))

import latency_minus_jev as L  # noqa: E402

FAILS = []


def ok(c, m):
    if not c:
        FAILS.append(m)
        print("FAIL:", m)


def row(total, ttft, slots, router=None, planner=None):
    r = {"latency": {"total_ms": total, "ttft_ms": ttft, "parts": {"slots_ms": slots}},
         "router": {"backend": "jev" if router is not None else "rules", "ms": router or 0},
         "planner": {"backend": "rules"}}
    if planner is not None:
        r["planner"]["llm"] = {"backend": "jev", "ms": planner}
    return r


def write(d, name, rows, cfg):
    path = os.path.join(d, name + ".jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    if cfg is not None:
        with open(os.path.join(d, name + ".config.json"), "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
    return path


def main():
    hybrid = {"settings": {"extractor_backend": "hybrid", "extractor_jev_hybrid": True,
                           "extractor_async": True, "router_backend": "rules"}}
    rules = {"extractor_backend": "rules", "extractor_jev_hybrid": False, "router_backend": "rules"}
    rows = [row(10000, 3000, 5000), row(8000, 2000, 3), row(12000, 4000, 200, router=300, planner=100)]
    warns = []
    with tempfile.TemporaryDirectory() as d:
        p_h = write(d, "hyb", rows, hybrid)
        p_r = write(d, "rul", rows, rules)
        p_n = write(d, "nocfg", rows, None)

        rep = L.analyze(p_h, 0, 0, warns.append)
        ok(rep["slots_ms_counted_as_jev"], "config lồng 'settings' phải đọc ra hybrid + Jev")
        ok(rep["turns_with_jev_on_path"] == 3, f"3 lượt có Jev, được {rep['turns_with_jev_on_path']}")
        # Total đã trừ: 10000-5000=5000, 8000-3=7997, 12000-600=11400
        ok(rep["total"]["adjusted"]["p50_ms"] == 7997, f"Total đã trừ p50 = 7997, được {rep['total']['adjusted']}")
        ok(rep["total_p95_delta_ms"] == 11400 - 12000, f"ΔTotal p95 = -600, được {rep['total_p95_delta_ms']}")
        ok(sorted(r["latency"]["total_ms"] for r in rows) == [8000, 10000, 12000], "dữ liệu mẫu")
        ok(rep["jev_by_leg"]["router"]["p50_ms"] == 300 and rep["jev_by_leg"]["planner"]["p50_ms"] == 100,
           "router/planner Jev phải được tính")
        # ttft: 3000-5000 → 0 (không âm), 2000-3 = 1997, 4000-600 = 3400
        ok(rep["ttft"]["adjusted"]["p50_ms"] == 1997, f"TTFT đã trừ p50 = 1997, được {rep['ttft']['adjusted']}")

        rep = L.analyze(p_h, 250, 0, warns.append)
        # lượt 1: 5000-250; lượt 2: 0; lượt 3: router 300-250=50, slots 200<250 → 0, planner 100<250 → 0
        ok(rep["removed_per_turn"]["p50_ms"] == 50, f"ref 250: trừ p50 = 50, được {rep['removed_per_turn']}")

        rep = L.analyze(p_r, 0, 0, warns.append)
        ok(not rep["slots_ms_counted_as_jev"], "extractor rules: không trừ slots_ms")
        ok(rep["jev_by_leg"].keys() == {"router", "planner"}, f"chỉ còn router/planner, được {rep['jev_by_leg'].keys()}")

        n0 = len(warns)
        rep = L.analyze(p_n, 0, 0, warns.append)
        ok(rep["slots_ms_counted_as_jev"] and len(warns) == n0 + 1, "thiếu config → coi là Jev và cảnh báo")

        rep = L.analyze(p_h, 0, 1, warns.append)
        ok(rep["n_turns"] == 2, "--skip-warmup 1 phải bỏ lượt đầu")

        ref, n = L.ref_ms_from_trace(p_h, 0, warns.append)
        ok((ref, n) == (250, 4), f"mốc ref bỏ chặng < 20 ms: p50 của [5000,200,300,100] = 250, được {(ref, n)}")

    import reference_eval
    xs = [123, 5, 999, 42, 7, 300, 18, 77, 640, 2, 11, 55, 1000, 250, 31, 89, 400, 3, 60, 700, 15]
    ok(L.p95(xs) == reference_eval.p95(xs), "p95 phải trùng eval/reference_eval.py")

    print("latency_minus_jev_check:", "OK" if not FAILS else f"{len(FAILS)} lỗi")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
