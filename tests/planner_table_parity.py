#!/usr/bin/env python3
"""Bảng quyết định planner: kiểm schema, độ phủ dòng, và (khi có --ref-root) trùng trace với một bản code tham chiếu.

Lịch sử: D50 so bảng (PLANNER_TABLE=1, chỉ nhánh cũ) với _plan if-else cũ (PLANNER_TABLE=0) — trùng 100 %.
Bước 1b (06/11) bỏ _plan cũ, nên giờ phép so là: code HIỆN TẠI với code tham chiếu (bản trước khi dọn, --ref-root).

    python tests/planner_table_parity.py --sets test_set/public_sample                 # schema + độ phủ, không so
    python tests/planner_table_parity.py --ref-root /tmp/ref --out-dir /tmp/tp         # so trace với bản tham chiếu

Hai biến thể so (offline: router rules, generator offline, extractor rules, transport direct; không khóa, không GPU):
  full — bảng đầy đủ (cả dòng D51) + PRODUCT_LEXICON=1 (cấu hình chốt).
  core — bảng như trước D51. Bản mới dùng PLANNER_SKIP_SINCE=D51; bản tham chiếu dùng file bảng đã lọc dòng "since"
         → đồng thời chứng minh PLANNER_SKIP_SINCE tương đương cách cũ (cho vòng 0 của mục 20b).
Không dùng holdout. In số lượt so, số lượt lệch (kèm trường lệch đầu tiên). Exit 1 nếu có lệch hoặc bảng sai.
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


def core_rules(out_dir):
    """Bảng CHỈ có nhánh cũ (bỏ mọi dòng có "since") — cách tắt D51 của bản tham chiếu."""
    doc = json.load(open(os.path.join(ROOT, "harness", "planner_rules.json"), encoding="utf-8"))
    doc["rows"] = [r for r in doc["rows"] if not r.get("since")]
    path = os.path.join(out_dir, "planner_rules_core.json")
    json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return path


def variant_env(variant, side, out_dir):
    env = {"LLM_CACHE": "off", "IMPROVE_DIR": "", "PLANNER_BACKEND": "rules", "PLANNER_TABLE": "1"}
    if variant == "full":
        env.update(PRODUCT_LEXICON="1", PLANNER_SKIP_SINCE="")
    elif side == "ref":
        env.update(PRODUCT_LEXICON="0", PLANNER_RULES=core_rules(out_dir))
    else:
        env.update(PRODUCT_LEXICON="0", PLANNER_SKIP_SINCE="D51")
    return env


def run(root, out_dir, tag, scen, config, variant, side, a):
    out = os.path.join(out_dir, f"{tag}-{config}-{variant}-{side}.jsonl")
    env = {k: v for k, v in os.environ.items() if k != "PLANNER_RULES"}
    env.update(variant_env(variant, side, out_dir), DATABASE_URL=f"sqlite:///{out_dir}/{tag}-{config}-{variant}-{side}.db")
    cmd = [sys.executable, os.path.join(root, "run_eval.py"), "--scenarios", os.path.join(ROOT, scen), "--config", config,
           "--out", out, "--router", "rules", "--generator", "offline", "--extractor", "rules", "--transport", "direct",
           "--run-id", "table-parity", "--workers", str(a.workers)]
    subprocess.run(cmd, check=True, env=env, cwd=root, stderr=subprocess.DEVNULL)
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
    # PLANNER_TABLE=0 phải bị từ chối (đường _plan cũ đã bỏ)
    r = subprocess.run([sys.executable, "-c", "import core.config"], cwd=ROOT, capture_output=True, text=True,
                       env={**os.environ, "PLANNER_TABLE": "0"})
    if r.returncode == 0:
        errs.append("PLANNER_TABLE=0 không bị báo lỗi")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="*", default=DEFAULT_SETS)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--ref-root", help="thư mục repo tham chiếu (bản trước khi dọn); bỏ trống = chỉ kiểm schema + độ phủ")
    ap.add_argument("--variants", nargs="*", default=["full", "core"])
    a = ap.parse_args()
    out_dir = a.out_dir or tempfile.mkdtemp(prefix="table_parity_")
    os.makedirs(out_dir, exist_ok=True)
    errs = check_schema()
    for e in errs:
        print("SCHEMA:", e)
    bad = n = 0
    used = {}                                  # dòng → số lượt khớp (biến thể full, bản hiện tại)
    by_set = {}
    for scen in a.sets:
        if not os.path.isdir(os.path.join(ROOT, scen)):
            print(f"[bỏ qua] không có bộ {scen}"); continue
        tag = scen.replace("/", "_")
        for config in ("full", "baseline_no_memory"):
            for variant in a.variants:
                new = run(ROOT, out_dir, tag, scen, config, variant, "new", a)
                if variant == "full":
                    for y in new:
                        for rid in (y.get("planner") or {}).get("table", []):
                            used[rid] = used.get(rid, 0) + 1
                            by_set.setdefault(rid, {}).setdefault(tag, 0)
                            by_set[rid][tag] += 1
                if not a.ref_root:
                    print(f"[{scen} {config} {variant}] {len(new)} lượt (không so)")
                    continue
                old = run(a.ref_root, out_dir, tag, scen, config, variant, "ref", a)
                if len(old) != len(new):
                    print(f"[{scen} {config} {variant}] số lượt khác: tham chiếu {len(old)} ≠ mới {len(new)}"); bad += 1; continue
                k = 0
                for x, y in zip(old, new):
                    n += 1
                    d = first_diff(strip(x), strip(y))
                    if d:
                        bad += 1; k += 1
                        if k <= 3:
                            print(f"  LỆCH {scen} {config} {variant} {x.get('scenario_id')} {x.get('call')} t{x.get('turn')}: {d[:300]}")
                print(f"[{scen} {config} {variant}] {len(old)} lượt, lệch {k}")
    rows = json.load(open(os.path.join(ROOT, "harness", "planner_rules.json"), encoding="utf-8"))["rows"]
    never = [r["id"] for r in rows if r["id"] not in used]
    print(f"Dòng bảng đã khớp ít nhất 1 lần (full): {len(rows) - len(never)}/{len(rows)}; chưa khớp: {', '.join(never) or '—'}")
    if a.ref_root:
        print(f"TỔNG: {n} lượt so, lệch {bad}, lỗi schema {len(errs)}")
    else:
        print(f"TỔNG: lỗi schema {len(errs)} (không so trace: thiếu --ref-root)")
    json.dump({"turns": n, "diffs": bad, "schema_errors": errs, "row_hits": used, "row_hits_by_set": by_set,
               "never_hit": never, "ref_root": a.ref_root},
              open(os.path.join(out_dir, "planner_table_parity.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    sys.exit(1 if bad or errs or (a.ref_root and n == 0) else 0)


if __name__ == "__main__":
    main()
