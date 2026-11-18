"""Probe 07/11: quy quyết định của planner LUẬT THUẦN (router luật, generator offline, extractor luật) ra tên hàm cho từng mục probe.

    python scripts/function_probe_rules.py --traces OUT/v3dev/full.jsonl OUT/holdout/full.jsonl OUT/fp/full.jsonl \
        --out OUT/rules_pure.json

Mỗi mục tra theo `rules_key` trong datagen/function_probe/items.jsonl (A/C: scenario/call/turn gốc; B/D: kịch bản dựng FP-<id>,
lượt cuối). Quy đổi goal + tool → hàm bằng `rules_functions()` của build_items.py (xấp xỉ, như mốc luật lần 1).
`setup_ok` = False khi mục cần "đã có đơn" mà kịch bản dựng không tạo được đơn ở call_1 (mục đó bị bỏ khỏi mốc luật thuần).
"""
import argparse, importlib.util, json, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
spec = importlib.util.spec_from_file_location("build_items", os.path.join(ROOT, "datagen", "function_probe", "build_items.py"))
bi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bi)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    seen = {}
    for t in a.traces:
        if os.path.exists(t):
            for x in bi.turns_from(t, lambda r: True):
                seen[x["id"]] = x
        else:
            print("không thấy trace", t)
    items = [json.loads(l) for l in open(os.path.join(ROOT, "datagen", "function_probe", "items.jsonl"), encoding="utf-8")]
    out, miss, bad = {}, 0, 0
    for it in items:
        x = seen.get(it.get("rules_key"))
        if not x:
            miss += 1
            out[it["id"]] = {"found": False}
            continue
        ok = not ((it.get("state") or {}).get("has_order") and it["part"] in ("B", "D") and not x["state"]["has_order"])
        bad += not ok
        out[it["id"]] = {"found": True, "functions": x["rules"], "goals": x["rules_goals"], "setup_ok": ok}
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(items)} mục: thiếu trace {miss}, kịch bản dựng không tạo được đơn {bad} → {a.out}")


if __name__ == "__main__":
    main()
