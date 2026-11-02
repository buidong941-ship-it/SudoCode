"""C2: Hallucination Rate có xét SKU — số phụ của nhóm, đặt CẠNH số chính thức của eval/reference_eval.py (không sửa eval/).

Vì sao cần: `reference_eval.hallucination_rate` so MỌI claim cùng field với `ground_truth_facts` của call, không xét claim nói
về SKU nào. Agent báo giá phụ kiện / sản phẩm thứ hai (vd màng lọc 690.000đ) bị tính là sai vì GT là giá máy chính
(lần ③: 8/9 claim HR sai thuộc loại này). Script báo ba con số:

    official   y hệt reference_eval (để đối chiếu, phải khớp report.json)
    main_sku   chỉ chấm claim có sku = SKU chính của call (hoặc biến thể của nó); claim SKU khác → không kiểm chứng được
    tool       mọi claim có sku đối chiếu với eval/mock_tools.py (logic của BTC) đúng ngày gọi:
                 price_vnd       = final_price_vnd hoặc list_price_vnd của sku đó (agent hay nói "niêm yết X, còn Y")
                 list_price_vnd  = list_price_vnd
                 promo_active    = có KM áp dụng ngoài COD-0 / NAM-SHIP0 (gồm cả quà tặng)
                 in_stock        = inventory.check(sku, ngày gọi)
                 warranty_months = thuộc tính catalog
               field khác → không kiểm chứng được.

SKU chính của call = facts_established.product_chosen/product_advised của call đó, nếu không có thì của call gần nhất trước nó.

    python scripts/hr_by_sku.py --scenarios datagen/out_btc_like_final_v1/final/dev --trace runs/.../dev/full.jsonl [--json out.json]
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "eval"))
import mock_tools as mt  # noqa: E402
from reference_eval import hallucination_rate, load_scenarios, load_trace, pct  # noqa: E402

SKIP_PROMOS = {"COD-0", "NAM-SHIP0"}


def parent(sku):
    p, _ = mt._parent(sku) if sku else (None, None)
    return p["sku"] if p else sku


def call_dates(s):
    d0 = None
    out = {}
    for name, spec in s["calls"].items():
        if spec.get("call_date"):
            d = spec["call_date"]
        elif d0 and spec.get("days_later") is not None:
            d = (date.fromisoformat(d0) + timedelta(days=spec["days_later"])).isoformat()
        else:
            d = mt.REF if isinstance(mt.REF, str) else "2026-10-15"
        d0 = d0 or d
        out[name] = d
    return out


def main_skus(s):
    out, last = {}, None
    for name, spec in s["calls"].items():
        fe = spec.get("facts_established") or {}
        last = fe.get("product_chosen") or fe.get("product_advised") or last
        out[name] = last
    return out


def tool_truth(field, sku, on, phone):
    if field in ("price_vnd", "list_price_vnd", "promo_active"):
        q = mt.pricing_get_quote(sku, on=on, customer_phone=phone)
        if q.get("error"):
            return None
        if field == "price_vnd":
            return {q.get("final_price_vnd"), q.get("list_price_vnd")}
        if field == "list_price_vnd":
            return {q.get("list_price_vnd")}
        return {bool([a for a in q.get("applied_promos", []) if a.get("promo_code") not in SKIP_PROMOS])}
    if field == "in_stock":
        r = mt.inventory_check(sku, on=on)
        return None if r.get("error") else {r.get("in_stock")}
    if field == "warranty_months":
        p, _ = mt._parent(sku)
        w = (p or {}).get("attributes", {}).get("warranty_months")
        return None if w is None else {w}
    return None


def hr_sku(scenarios, trace):
    res = {"main_sku": {"wrong": 0, "total": 0, "wrong_p": 0, "total_p": 0, "examples": [], "skipped_other_sku": 0},
           "tool": {"wrong": 0, "total": 0, "wrong_p": 0, "total_p": 0, "examples": [], "unverifiable": 0}}
    for sid, s in scenarios.items():
        dates, mains = call_dates(s), main_skus(s)
        phone = s.get("customer_phone")
        for call, spec in s["calls"].items():
            gt = spec.get("ground_truth_facts") or {}
            main = parent(mains.get(call))
            for r in trace.get((sid, call), []):
                for c in r.get("claims", []):
                    f, sku = c["field"], c.get("sku")
                    is_p = f.startswith("price") or f.startswith("promo") or f.startswith("list_price")
                    # main_sku: như official nhưng bỏ claim nói về SKU khác
                    if f in gt:
                        if sku and main and parent(sku) != main:
                            res["main_sku"]["skipped_other_sku"] += 1
                        else:
                            m = res["main_sku"]
                            m["total"] += 1; m["total_p"] += int(is_p)
                            if c["value"] != gt[f]:
                                m["wrong"] += 1; m["wrong_p"] += int(is_p)
                                m["examples"].append({"scenario": sid, "call": call, "turn": r["turn"], "field": f, "sku": sku,
                                                      "claimed": c["value"], "truth": gt[f]})
                    # tool: đối chiếu mock_tools theo sku của claim
                    truth = tool_truth(f, sku, dates[call], phone) if sku else None
                    t = res["tool"]
                    if truth is None:
                        t["unverifiable"] += 1
                        continue
                    t["total"] += 1; t["total_p"] += int(is_p)
                    if c["value"] not in truth:
                        t["wrong"] += 1; t["wrong_p"] += int(is_p)
                        t["examples"].append({"scenario": sid, "call": call, "turn": r["turn"], "field": f, "sku": sku,
                                              "claimed": c["value"], "tool": sorted(truth, key=str)})
    out = {}
    for k, m in res.items():
        out[k] = {"value": pct(m["wrong"], m["total"]), "wrong": m["wrong"], "total_claims": m["total"],
                  "price_promo_only": {"value": pct(m["wrong_p"], m["total_p"]), "wrong": m["wrong_p"], "total": m["total_p"]},
                  "examples": m["examples"][:20]}
        out[k].update({x: m[x] for x in ("skipped_other_sku", "unverifiable") if x in m})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scenarios", required=True)
    ap.add_argument("--trace", required=True)
    ap.add_argument("--json", help="ghi kết quả ra file")
    a = ap.parse_args()
    sc, tr = load_scenarios(a.scenarios), load_trace(a.trace)
    out = {"official": hallucination_rate(sc, tr), **hr_sku(sc, tr)}
    for k in ("official", "main_sku", "tool"):
        v = out[k]
        extra = f"  (bỏ {v['skipped_other_sku']} claim SKU khác)" if "skipped_other_sku" in v else \
            f"  ({v['unverifiable']} claim không kiểm chứng được)" if "unverifiable" in v else ""
        print(f"{k:<9} HR {v['value']}% ({v['wrong']}/{v['total_claims']}) · giá & KM {v['price_promo_only']['value']}%"
              f" ({v['price_promo_only']['wrong']}/{v['price_promo_only']['total']}){extra}")
    for ex in out["tool"]["examples"][:10]:
        print("  tool sai:", json.dumps(ex, ensure_ascii=False))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
