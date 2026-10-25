#!/usr/bin/env python3
"""Trace của harness (chạy với model thật) + kịch bản → transcript hai phía, mỗi cuộc gọi một file.

    python datagen/export_transcripts.py --pair datagen/out_nat/dev runs/w2/full_dev.jsonl \\
                                         --pair datagen/out_nat/test runs/w2/full_test.jsonl \\
                                         --pair test_set/public_sample runs/w2/full_sample.jsonl

Đầu ra (mặc định `dataset/`):
    transcripts/<scenario_id>__<call>.json   một cuộc gọi: metadata + turns [{idx, speaker: C|A, text}]
    index.json                               danh sách cuộc gọi + thống kê theo persona / kênh / miền / ngành

Lời khách lấy nguyên văn từ kịch bản (bản ASR lỗi / teencode nếu kịch bản có — đó là thứ hệ thống thật sự nhận);
lời nhân viên là `agent_text` trong trace. CCCD / số tài khoản khách đọc được che (`mask_pii`) trước khi ghi.
"""
import argparse
import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from harness.loader import agent_view  # noqa: E402
from harness.textnorm import mask_pii  # noqa: E402
from harness.tools import mt  # noqa: E402

MALE = {"anh", "chú", "ông", "bác"}


def load_trace(path):
    by = collections.defaultdict(list)
    for line in open(path, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            by[(r["scenario_id"], r["call"])].append(r)
    for rows in by.values():
        rows.sort(key=lambda r: r["turn"])
    return by


def category_of(sku):
    p, _ = mt._parent(sku) if sku else (None, None)
    return p["category"] if p else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pair", nargs=2, action="append", required=True, metavar=("SCENARIO_DIR", "TRACE_JSONL"))
    ap.add_argument("--out", default=os.path.join(ROOT, "dataset"))
    a = ap.parse_args()

    tdir = os.path.join(a.out, "transcripts")
    os.makedirs(tdir, exist_ok=True)
    crm = {c["phone"]: c for c in mt.CRM}
    index, skipped = [], []
    for sdir, tpath in a.pair:
        trace = load_trace(tpath)
        cfg_p = os.path.splitext(tpath)[0] + ".config.json"
        cfg = json.load(open(cfg_p, encoding="utf-8")) if os.path.exists(cfg_p) else {}
        for f in sorted(glob.glob(os.path.join(sdir, "*.json"))):
            sc = json.load(open(f, encoding="utf-8"))
            if "calls" not in sc:
                continue
            sid, meta = sc["scenario_id"], sc.get("_meta") or {}
            view = agent_view(sc)
            cust = crm.get(sc["customer_phone"], {})
            region = cust.get("region") or (mt._region_of(meta["address"]) if meta.get("address") else None)
            for c in view["calls"]:
                rows = trace.get((sid, c["call"]), [])
                spec = sc["calls"][c["call"]]
                if len(rows) != len(c["turns"]) or any(not (r.get("agent_text") or "").strip() for r in rows):
                    skipped.append(f"{sid} {c['call']}: trace {len(rows)} lượt / kịch bản {len(c['turns'])} lượt, hoặc lời nhân viên rỗng")
                    continue
                turns, tools = [], []
                for i, (ct, r) in enumerate(zip(c["turns"], rows)):
                    turns.append({"idx": 2 * i + 1, "speaker": "C", "text": mask_pii(ct)})
                    turns.append({"idx": 2 * i + 2, "speaker": "A", "text": r["agent_text"].strip()})
                    tools += [tc["name"] for tc in r.get("tool_calls", [])]
                facts = spec.get("facts_established") or {}
                sku = ((spec.get("success_if") or {}).get("args_match") or {}).get("sku") or facts.get("variant_sku") or facts.get("product_advised")
                if not sku:
                    for other in sc["calls"].values():
                        fo = other.get("facts_established") or {}
                        sku = sku or fo.get("variant_sku") or fo.get("product_advised")
                tid = f"{sid}__{c['call']}"
                rec = {"id": tid, "scenario_id": sid, "call": c["call"], "n_calls_in_scenario": len(view["calls"]),
                       "split": meta.get("split") or ("btc_sample" if sid.startswith("SAMPLE") else None),
                       "persona": sc["persona"], "hard_case": sc.get("hard_case"), "level": sc.get("level"),
                       "channel": c["channel"], "input_mode": c["input_mode"], "call_date": c["date"],
                       "customer": {"honorific": sc["honorific"], "gender": "m" if sc["honorific"].lower() in MALE else "f",
                                    "region": region, "customer_id": cust.get("customer_id") or meta.get("customer_id")},
                       "product_sku": sku, "category": category_of(sku), "expected_outcome": spec.get("expected_outcome"),
                       "tools_called": sorted(set(tools)), "n_turns": len(turns), "turns": turns,
                       "facts_established": facts,
                       "source": {"generator": cfg.get("generator"), "router": cfg.get("router"),
                                  "model": (cfg.get("settings") or {}).get("deepseek_model"), "run_id": cfg.get("run_id"),
                                  "customer_turns": "LLM viết lại từ câu mẫu" if any((meta.get("naturalized") or {}).get(c["call"], []))
                                  else "câu mẫu của template / BTC"}}
                json.dump(rec, open(os.path.join(tdir, tid + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                index.append({k: rec[k] for k in ("id", "scenario_id", "call", "split", "persona", "hard_case", "channel",
                                                  "input_mode", "call_date", "category", "n_turns")}
                             | {"region": region, "customer_phone_hash": hash_phone(sc["customer_phone"])})

    by_cust = collections.defaultdict(list)
    for r in index:
        by_cust[r["customer_phone_hash"]].append(r)
    stats = {"calls": len(index), "turns": sum(r["n_turns"] for r in index),
             "customers": len(by_cust),
             "multi_session_customers": sum(1 for v in by_cust.values() if len(v) >= 2),
             "customers_3plus_sessions": sum(1 for v in by_cust.values() if len(v) >= 3),
             "multi_channel_customers": sum(1 for v in by_cust.values() if len({x["channel"] for x in v}) >= 2
                                            and "hotline" in {x["channel"] for x in v}),
             "by_channel": collections.Counter(r["channel"] for r in index),
             "by_region": collections.Counter(str(r["region"]) for r in index),
             "by_category_top": collections.Counter((r["category"] or "-").split("/")[0] for r in index),
             "by_persona": collections.Counter(r["persona"] for r in index),
             "by_input_mode": collections.Counter(r["input_mode"] for r in index),
             "hard_case_calls": sum(1 for r in index if r["hard_case"]),
             "skipped": skipped}
    json.dump({"stats": stats, "calls": index}, open(os.path.join(a.out, "index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(index)} cuộc → {tdir}; bỏ {len(skipped)} cuộc")
    print(json.dumps({k: v for k, v in stats.items() if k != "skipped"}, ensure_ascii=False, indent=1))
    for s in skipped[:10]:
        print("  bỏ:", s)


def hash_phone(p):
    import hashlib
    return hashlib.sha1(p.encode()).hexdigest()[:10]


if __name__ == "__main__":
    main()
