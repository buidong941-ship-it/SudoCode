"""Kiểm scripts/hr_by_sku.py (C2): claim giá phụ kiện không bị tính sai ở main_sku / tool, nhưng vẫn sai ở official."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import hr_by_sku as H  # noqa: E402

FAILS = []


def ok(c, m):
    if not c:
        FAILS.append(m); print("FAIL:", m)


scen = {"S": {"scenario_id": "S", "customer_phone": "0900000001", "calls": {
    "call_1": {"call_date": "2026-10-15", "facts_established": {"product_advised": "SKU-AP-Y"},
               "ground_truth_facts": {"price_vnd": 5200000, "in_stock": True}},
    "call_2": {"days_later": 10, "ground_truth_facts": {"price_vnd": 5200000}}}}}


def row(call, turn, claims):
    return {"scenario_id": "S", "call": call, "turn": turn, "claims": claims}


trace = {("S", "call_1"): [row("call_1", 1, [{"field": "price_vnd", "value": 5200000, "sku": "SKU-AP-Y"},
                                             {"field": "price_vnd", "value": 690000, "sku": "SKU-AP-FLT-X"},
                                             {"field": "price_vnd", "value": 5500000, "sku": "SKU-AP-Y"},
                                             {"field": "promo_active", "value": True, "sku": "SKU-AP-Y"}])],
         ("S", "call_2"): [row("call_2", 1, [{"field": "promo_active", "value": True, "sku": "SKU-AP-Y"},
                                             {"field": "price_vnd", "value": 5200000, "sku": "SKU-AP-Y"}])]}
off = H.hallucination_rate(scen, trace)
ok(off["wrong"] == 2 and off["total_claims"] == 4, f"official phải tính 690k và 5,5tr là sai: {off}")
r = H.hr_sku(scen, trace)
m = r["main_sku"]
ok(m["wrong"] == 1 and m["total_claims"] == 3 and m["skipped_other_sku"] == 1, f"main_sku sai: {m}")
t = r["tool"]
# giá: 5,2tr đúng, 690k (giá thật của màng lọc) đúng, 5,5tr sai. promo_active: so với chính mock_tools của BTC.
price_wrong = [e for e in t["examples"] if e["field"] == "price_vnd"]
ok(len(price_wrong) == 1 and price_wrong[0]["claimed"] == 5500000, f"tool: chỉ 5,5tr là giá sai: {price_wrong}")
promo_wrong = {e["call"] for e in t["examples"] if e["field"] == "promo_active"}
want = {c for c, d in (("call_1", "2026-10-15"), ("call_2", "2026-10-25"))
        if True not in H.tool_truth("promo_active", "SKU-AP-Y", d, "0900000001")}
ok(promo_wrong == want, f"tool promo_active: {promo_wrong} != {want}")
ok(t["total_claims"] == 6, f"tool phải kiểm chứng đủ 6 claim: {t}")
ok(True in H.tool_truth("promo_active", "SKU-AP-Y", "2026-10-15", None), "GIFT-FILTER còn hiệu lực 15/10 (09-25..10-22)")
ok(H.call_dates(scen["S"]) == {"call_1": "2026-10-15", "call_2": "2026-10-25"}, "ngày gọi call_2 phải = call_1 + days_later")
print("TẤT CẢ OK" if not FAILS else f"{len(FAILS)} LỖI")
sys.exit(1 if FAILS else 0)
