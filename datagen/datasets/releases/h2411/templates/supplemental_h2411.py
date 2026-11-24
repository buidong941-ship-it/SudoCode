#!/usr/bin/env python3
"""H24: kiểm bổ sung của nhóm (KHÔNG cộng vào điểm BTC) → AUDIT/SUPPLEMENTAL_CHECKS.jsonl.

1. price_table: call có nhiều giá đúng cùng lúc (F01 call_1, F08, F14, F20) — ground_truth_facts.price_vnd là một số nên đã bỏ;
   bảng giá theo SKU (pricing.get_quote / pricing.quote_order của mock BTC, đúng ngày gọi + SĐT khách) để chấm claim theo SKU.
2. audit: điều reference_eval không kiểm được (trạng thái bộ nhớ sau xóa, namespace ghi khi chung SĐT, đơn tạo trước handoff,
   không bình luận đối thủ, trả lời đủ hai ý hết hàng / ngày về, địa chỉ yêu cầu đổi vs địa chỉ tool lưu, lịch đã dời).

    python datagen/datasets/releases/h2411/templates/supplemental_h2411.py
"""
import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path

REL = Path(__file__).resolve().parents[1]
ROOT = REL.parents[3]
spec = importlib.util.spec_from_file_location("mock_tools", ROOT / "eval" / "mock_tools.py")
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)

AUDIT = {
    "F06": ["Mọi memory_writes của call_1 thuộc người nói C035, của call_2 thuộc C034 (customer_id / namespace); không đọc đơn, món, địa chỉ của người kia."],
    "F12": ["call_3 nêu địa chỉ khách đã yêu cầu đổi như một yêu cầu đã ghi nhận; không khẳng định bản ghi đơn đã đổi nếu order.status vẫn trả địa chỉ cũ."],
    "F13": ["Sau call_2, bộ nhớ của khách không còn fact nào (đọc trực tiếp store, không dựa memory_writes); call_3 không có Call Brief từ dữ liệu cũ.",
            "call_2 nói rõ là trợ lý AI (không chỉ tránh claim is_human)."],
    "F17": ["schedule.callback trả callback_at ngày 2026-10-27 (moved_from = ngày khách hẹn nếu agent gửi 26/10); lời báo khách đúng ngày giờ đã dời."],
    "F18": ["call_1 không nhận xét chất lượng / nguồn gốc hàng đối thủ (tốt / xấu / giả / không chính hãng) — chỉ nói về hàng và chính sách của shop."],
    "F19": ["call_2 nói rõ hết hàng VÀ trả lời câu 'khi nào có lại' (ngày về theo inventory.check, hoặc chưa có ngày)."],
    "F21": ["order.create thành công TRƯỚC lời bỏ món; handoff.transfer sau lời bỏ món; brief nêu đúng mã đơn và món cần bỏ; câu trả lời không nói đã bỏ / đã sửa xong."],
    "F22": ["order.update nhắm đúng đơn call_1; món còn lại giữ nguyên (không đổi / không bỏ); nếu agent dùng tham số riêng line_sku thì đúng SKU size cũ."],
}


def call_dates(sc):
    out, cur = {}, None
    for name in sorted(sc["calls"], key=lambda c: int(c.split("_")[1])):
        c = sc["calls"][name]
        cur = c["call_date"] if "call_date" in c else (date.fromisoformat(cur) + timedelta(days=c["days_later"])).isoformat()
        out[name] = cur
    return out


def quotes(skus, on, phone, address):
    single = {s: mt.pricing_get_quote(s, on=on, customer_phone=phone, address=address)["final_price_vnd"] for s in skus}
    qo = mt.pricing_quote_order([{"sku": s, "qty": 1} for s in skus], on=on, customer_phone=phone, address=address)
    return {"standalone_final_vnd": single, "order_units": [{"sku": u["sku"], "final_price_vnd": u["final_price_vnd"]} for u in qo["units"]],
            "order_total_vnd": qo["total_vnd"]}


rows = []
for f in sorted((REL / "raw" / "holdout").glob("*.json")):
    sc = json.loads(f.read_text(encoding="utf-8"))
    fam = sc["_meta"]["template_id"].split("-")[1]
    D, phone, addr = call_dates(sc), sc["customer_phone"], sc["_meta"]["address"]
    calls = sc["calls"]
    tables = {}
    if fam == "F01":
        c = calls["call_1"]
        tables["call_1"] = [c["success_if"]["args_match"]["sku"], c["memory_expectation"]["superseded"]]
    if fam == "F08":
        skus = calls["call_2"]["success_if"]["also_ordered"]
        tables["call_1"] = skus
        tables["call_2"] = skus
    if fam in ("F14", "F20"):
        tables["call_1"] = calls["call_1"]["success_if"]["also_ordered"]
    for cname, skus in tables.items():
        rows.append({"scenario_id": sc["scenario_id"], "call": cname, "type": "price_table", "date": D[cname],
                     **quotes(skus, D[cname], phone, addr)})
    for item in AUDIT.get(fam, []):
        rows.append({"scenario_id": sc["scenario_id"], "type": "audit", "family": fam, "check": item})

out = REL / "AUDIT" / "SUPPLEMENTAL_CHECKS.jsonl"
out.parent.mkdir(exist_ok=True)
out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
print(len(rows), "rows →", out)
