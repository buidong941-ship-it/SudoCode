"""K09 (11/11): bảng rà TỪNG claim bị evaluator BTC chấm sai — câu cuối, SKU/target của claim, tool đúng thời điểm, truth.
Giữ nguyên số HR chính thức (eval/reference_eval.py); bảng này chỉ PHÂN LOẠI nguyên nhân, không thay metric BTC.

Phân loại mỗi claim sai:
  content_error         giá trị không có trong bất kỳ kết quả tool nào của cuộc gọi → agent nói sai / không nguồn
  correct_for_target    giá trị khớp tool cho ĐÚNG SKU claim gắn → lỗi giới hạn phép chấm theo field (gold là của SKU khác)
  extractor_attribution giá trị khớp tool của SKU KHÁC với SKU claim gắn (hoặc claim không gắn SKU) → lỗi attribution audit
  other_source          giá trị có trong tool nhưng không phải giá/KM (vd tổng tiền, tiền hoàn) → audit hiểu sai vai nghĩa

    python scripts/hr_review.py <scenarios_dir> <trace.jsonl> <out.json>
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "eval"))
import reference_eval as RE  # noqa: E402


def main():
    sdir, trace_path, out = sys.argv[1:4]
    scen = RE.load_scenarios(sdir)
    trace = RE.load_trace(trace_path)
    official = RE.hallucination_rate(scen, trace)
    rows_out = []
    for sid, s in scen.items():
        for call, spec in s["calls"].items():
            gt = spec.get("ground_truth_facts", {})
            rows = trace.get((sid, call), [])
            prices = {}          # sku → {final, list}
            other_numbers = set()
            for r in rows:
                for tc in r.get("tool_calls", []):
                    res = tc.get("result") or {}
                    if tc.get("name") == "pricing.get_quote" and isinstance(res, dict):
                        prices.setdefault((tc.get("args") or {}).get("sku"), set()).update(
                            {res.get("final_price_vnd"), res.get("list_price_vnd")})
                    elif isinstance(res, dict):
                        other_numbers |= {v for v in res.values() if isinstance(v, int)}
            for r in rows:
                for c in r.get("claims", []):
                    f = c["field"]
                    if f not in gt or c["value"] == gt[f]:
                        continue
                    v, sku = c["value"], c.get("sku")
                    own = prices.get(sku) or set()
                    anyp = set().union(*prices.values()) if prices else set()
                    if f.startswith("price") or f.startswith("list_price"):
                        kind = ("correct_for_target" if v in own else "extractor_attribution" if v in anyp
                                else "other_source" if v in other_numbers else "content_error")
                    else:
                        kind = "non_price_field"
                    rows_out.append({"scenario": sid, "call": call, "turn": r.get("turn"), "field": f, "claimed": v, "truth": gt[f],
                                     "claim_sku": sku, "tool_prices": {k: sorted(x for x in vs if x) for k, vs in prices.items()},
                                     "sentence": c.get("text"), "class": kind})
    summary = {}
    for x in rows_out:
        summary[x["class"]] = summary.get(x["class"], 0) + 1
    doc = {"official": {"hr": official["value"], "price_promo": official["price_promo_only"]}, "classes": summary, "claims": rows_out}
    json.dump(doc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({"official": doc["official"], "classes": summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
