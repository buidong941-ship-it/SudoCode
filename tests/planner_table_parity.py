#!/usr/bin/env python3
"""D50: bảng quyết định (PLANNER_TABLE=1) phải cho CÙNG trace với _plan cũ (PLANNER_TABLE=0) khi bảng chỉ có nhánh cũ.

    python tests/planner_table_parity.py                          # các bộ dev mặc định, full + baseline, offline
    python tests/planner_table_parity.py --sets test_set/public_sample --workers 4

Chạy offline (router rules, generator offline, extractor rules, transport direct): không cần khóa, không cần GPU.
Không dùng holdout. Ngoài so trace còn kiểm schema bảng và luật an toàn của dòng approved.
In số lượt so sánh, số lượt lệch (kèm trường lệch đầu tiên). Exit 1 nếu có lệch hoặc bảng sai.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
from mcp_parity import first_diff, strip  # noqa: E402

DEFAULT_SETS = ["test_set/public_sample", "datagen/out_nat/dev", "datagen/out_btc_like_final_v1_1/final/dev",
                "datagen/out_btc_like_final_v2_1/final/dev", "datagen/out_btc_like_d7/final/dev", "datagen/out_v3/final/dev"]


def strip_table(row):
    r = strip(row)
    if isinstance(r.get("planner"), dict):
        r["planner"] = {k: v for k, v in r["planner"].items() if k != "table"}
    return r


def core_rules(out_dir):
    """Bản bảng CHỈ có nhánh cũ (bỏ dòng "since": "D51"…) — điều kiện của phép so trùng trace."""
    doc = json.load(open(os.path.join(ROOT, "harness", "planner_rules.json"), encoding="utf-8"))
    doc["rows"] = [r for r in doc["rows"] if not r.get("since")]
    path = os.path.join(out_dir, "planner_rules_core.json")
    json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return path


def run(out_dir, tag, scen, config, table, a):
    out = os.path.join(out_dir, f"{tag}-{config}-t{table}.jsonl")
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{out_dir}/{tag}-t{table}.db", "PLANNER_TABLE": str(table),
           "LLM_CACHE": "off", "IMPROVE_DIR": "", "PLANNER_BACKEND": "rules", "PRODUCT_LEXICON": "0",
           "PLANNER_RULES": core_rules(out_dir)}
    cmd = [sys.executable, os.path.join(ROOT, "run_eval.py"), "--scenarios", os.path.join(ROOT, scen), "--config", config,
           "--out", out, "--router", "rules", "--generator", "offline", "--extractor", "rules", "--transport", "direct",
           "--run-id", "table-parity", "--workers", str(a.workers)]
    subprocess.run(cmd, check=True, env=env, cwd=ROOT, stderr=subprocess.DEVNULL)
    return [json.loads(l) for l in open(out, encoding="utf-8")]


def check_schema():
    from harness import planner_table as pt
    errs = []
    doc = json.load(open(os.path.join(ROOT, "harness", "planner_rules.json"), encoding="utf-8"))
    e = pt.validate(doc)
    if e:
        errs += ["bảng: " + x for x in e]
    # dòng approved dùng handler ghi đơn phải bị từ chối; dòng approved an toàn thì qua
    bad = {"rows": [{"id": "X1", "priority": 500, "mode": "add", "origin": "approved", "when": {"intent": ["place_order"]},
                     "do": {"handler": "place_order"}}]}
    if not pt.validate(bad):
        errs.append("dòng approved dùng place_order không bị chặn")
    ok = {"rows": [{"id": "X2", "priority": 500, "mode": "add", "origin": "approved", "when": {"intent": ["price_promo"]},
                    "do": {"handler": "add_goal", "goals": ["quote"]}}]}
    if pt.validate(ok):
        errs.append("dòng approved an toàn bị chặn nhầm: " + "; ".join(pt.validate(ok)))
    if not pt.validate({"rows": [{"id": "X3", "priority": 1, "mode": "add", "when": {"preds": ["khong_ton_tai"]},
                                  "do": {"handler": "add_goal"}}]}):
        errs.append("predicate lạ không bị chặn")
    # mọi nhánh cũ phải có mặt (R00…R36)
    ids = {r["id"] for r in doc["rows"]}
    need = {f"R{i:02d}" for i in range(37)} - {"R24"} | {"R24a", "R24b"}
    if need - ids:
        errs.append("thiếu dòng: " + ", ".join(sorted(need - ids)))
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="*", default=DEFAULT_SETS)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args()
    out_dir = a.out_dir or tempfile.mkdtemp(prefix="table_parity_")
    os.makedirs(out_dir, exist_ok=True)
    errs = check_schema()
    for e in errs:
        print("SCHEMA:", e)
    bad = n = 0
    used = {}
    for scen in a.sets:
        if not os.path.isdir(os.path.join(ROOT, scen)):
            print(f"[bỏ qua] không có bộ {scen}"); continue
        tag = scen.replace("/", "_")
        for config in ("full", "baseline_no_memory"):
            old, new = run(out_dir, tag, scen, config, 0, a), run(out_dir, tag, scen, config, 1, a)
            if len(old) != len(new):
                print(f"[{scen} {config}] số lượt khác: cũ {len(old)} ≠ bảng {len(new)}"); bad += 1; continue
            k = 0
            for x, y in zip(old, new):
                n += 1
                for rid in (y.get("planner") or {}).get("table", []):
                    used[rid] = used.get(rid, 0) + 1
                d = first_diff(strip_table(x), strip_table(y))
                if d:
                    bad += 1; k += 1
                    if k <= 3:
                        print(f"  LỆCH {scen} {config} {x.get('scenario_id')} {x.get('call')} t{x.get('turn')}: {d[:300]}")
            print(f"[{scen} {config}] {len(old)} lượt, lệch {k}")
    rows = [r for r in json.load(open(os.path.join(ROOT, "harness", "planner_rules.json"), encoding="utf-8"))["rows"]
            if not r.get("since")]
    never = [r["id"] for r in rows if r["id"] not in used]
    print(f"Dòng bảng đã khớp ít nhất 1 lần: {len(rows) - len(never)}/{len(rows)}; chưa khớp: {', '.join(never) or '—'}")
    print(f"TỔNG: {n} lượt, lệch {bad}, lỗi schema {len(errs)}")
    json.dump({"turns": n, "diffs": bad, "schema_errors": errs, "row_hits": used, "never_hit": never},
              open(os.path.join(out_dir, "planner_table_parity.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    sys.exit(1 if bad or errs or n == 0 else 0)


if __name__ == "__main__":
    main()
