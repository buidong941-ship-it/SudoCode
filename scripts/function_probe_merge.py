"""Probe 07/11: gộp các phần (shard) của function_probe.py và chấm lại với mốc luật thuần.

    python scripts/function_probe_merge.py --v2 A.json B.json --v1 C.json D.json --rules-pure rules_pure.json --out merged.json

In bảng: mỗi phần A/B/C/D × {luật+Jev (trace), luật thuần, Qwen v1, Qwen v2 thô, Qwen v2 + luật cứng}.
"""
import argparse, importlib.util, json, os
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
spec = importlib.util.spec_from_file_location("fp", os.path.join(ROOT, "scripts", "function_probe.py"))
fp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fp)
D = os.path.join(ROOT, "datagen", "function_probe")


def load_rows(files):
    rows = {}
    for f in files:
        for r in json.load(open(f, encoding="utf-8"))["rows"]:
            rows[r["id"]] = r
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v2", nargs="+", required=True)
    ap.add_argument("--v1", nargs="*", default=[])
    ap.add_argument("--rules-pure", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    funcs = json.load(open(os.path.join(D, "functions_v2.json"), encoding="utf-8"))["functions"]
    sc = {n for n, f in funcs.items() if f.get("state_change")}
    items = [json.loads(l) for l in open(os.path.join(D, "items.jsonl"), encoding="utf-8")]
    v2, v1 = load_rows(a.v2), load_rows(a.v1)
    pure = json.load(open(a.rules_pure, encoding="utf-8"))
    rows, missing = [], Counter()
    for it in items:
        r = {k: it.get(k) for k in ("id", "part", "group", "text", "gold", "accept", "primary")}
        if it.get("rules") is not None:
            r["rules_trace"] = it["rules"]
        p = pure.get(it["id"]) or {}
        if p.get("found") and p.get("setup_ok", True):
            r["rules_pure"] = p["functions"]
        if it["id"] in v2:
            r["qwen_v2_raw"], r["qwen_v2"] = v2[it["id"]].get("qwen_raw") or [], v2[it["id"]].get("qwen") or []
        else:
            missing["v2"] += 1
        if v1:
            if it["id"] in v1:
                r["qwen_v1"] = v1[it["id"]].get("qwen") or []
            else:
                missing["v1"] += 1
        for k in ("rules_trace", "rules_pure", "qwen_v1", "qwen_v2_raw", "qwen_v2"):
            if k in r:
                r[k + "_score"] = fp.score(r[k], it, sc, ordered=k.startswith("qwen"))
        rows.append(r)
    table = {}
    for k in ("rules_trace", "rules_pure", "qwen_v1", "qwen_v2_raw", "qwen_v2"):
        table[k] = fp.summarize(rows, k, sc)
    json.dump({"missing": missing, "table": table, "rows": rows}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("thiếu:", dict(missing))
    print(f"{'mốc':14} | " + " | ".join(f"{p}: action / exact (n)" for p in "ABCD"))
    for k, t in table.items():
        cells = [f"{t[p]['action']:5.1f} / {t[p]['exact']:5.1f} ({t[p]['n']})" if p in t else "—" for p in "ABCD"]
        print(f"{k:14} | " + " | ".join(cells))


if __name__ == "__main__":
    main()
