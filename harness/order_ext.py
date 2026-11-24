"""Tool riêng của nhóm (bước D, 23/11/2026): sửa dòng / hủy đơn đã tạo — KHÔNG sửa file BTC.

DIEU-CHINH-DE.md mục 3 cho phép thêm tool riêng khi vẫn giữ tool chuẩn. `eval/mock_tools.py` (BTC) lưu đơn theo TỪNG đơn vị hàng
(`_ORDERS[oid]["lines"] = [{"sku","price_vnd"}...]`), không có mã dòng, không có thao tác hủy; `order.update` chỉ tạo ticket. Hai tool
dưới đây đổi đúng trạng thái `_ORDERS` mà `order.create` / `order.status` dùng (nên `order.status` sau khi gọi KHÁC mock gốc — có
chủ ý) và tính lại giá / KM bằng `pricing_quote_order` của chính mock.

Bật bằng ORDER_EXT_TOOLS=1 (mặc định TẮT → hành vi như cũ). Mỗi hàm nhận `mt` (module mock của tiến trình gọi: ToolBox trực tiếp
hoặc MCP server) để hai đường cho cùng kết quả.

Ràng buộc (theo review 23/11): chỉ đơn trạng thái `created`; từ chối khi SKU đích khớp nhiều đơn vị (không có mã dòng); từ chối bỏ
dòng làm đơn rỗng (dùng order.cancel); đổi biến thể phải cùng sản phẩm cha và còn hàng; KM 1 lần/khách mà CHỈ đơn này dùng được trả
lại trước khi tính lại, KM mới được ghi nhận lại; giữ hạn mức COD; ghi lịch sử sửa trong đơn.
"""
import os

NAMES = ("order.update_line", "order.cancel")
EDITABLE = ("created",)


def enabled():
    return os.environ.get("ORDER_EXT_TOOLS", "0") == "1"


def _parent_of(mt, sku):
    p, _ = mt._parent(sku)
    return (p or {}).get("sku") or sku


def _others(mt, o):
    return [x for x in mt._ORDERS.values() if x is not o and x["customer_phone"] == o["customer_phone"] and x.get("status") != "cancelled"]


def _release_once(mt, o):
    """KM 1 lần/khách mà chỉ đơn này dùng → trả lại (để tính lại đúng); trả về tập đã trả để khôi phục khi lỗi."""
    used_elsewhere = {c for x in _others(mt, o) for c in x.get("promos") or []}
    freed = {(o["customer_phone"], c) for c in o.get("promos") or [] if c not in used_elsewhere} & mt._ONCE_USED
    mt._ONCE_USED.difference_update(freed)
    return freed


def _requote(mt, o, units, on):
    counts = {}
    for s in units:
        counts[s] = counts.get(s, 0) + 1
    same_day = [x for x in _others(mt, o) if x["created_on"] == o["created_on"]]
    return mt.pricing_quote_order([{"sku": s, "qty": n} for s, n in counts.items()], on, o["customer_phone"], o.get("address"),
                                  _second_item_used=any("AIR-2ND-50" in (x.get("promos") or []) for x in same_day))


def order_update_line(mt, order_id, sku, action, new_variant_sku=None, reason=None, on=None):
    on = on or mt.REF
    o = mt._ORDERS.get(order_id)
    if not o:
        return {"error": "order_not_found"}
    if o.get("status") not in EDITABLE:
        return {"error": "order_not_editable", "status": o.get("status")}
    units = [ln["sku"] for ln in o["lines"]]
    hit = [i for i, s in enumerate(units) if s == sku]
    if not hit:
        return {"error": "line_not_found", "sku": sku}
    if len(hit) > 1:
        return {"error": "ambiguous_line", "sku": sku, "units": len(hit)}          # không có mã dòng → không đoán đơn vị nào
    if action == "remove":
        new_units = [s for i, s in enumerate(units) if i != hit[0]]
        if not new_units:
            return {"error": "would_empty_order", "hint": "order.cancel"}
    elif action == "change_variant":
        if not new_variant_sku:
            return {"error": "missing_new_variant_sku"}
        if _parent_of(mt, new_variant_sku) != _parent_of(mt, sku) or new_variant_sku == sku:
            return {"error": "not_same_product_variant"}
        inv = mt.inventory_check(new_variant_sku, on)
        if not inv.get("in_stock"):
            return {"error": "new_variant_out_of_stock", **inv}
        new_units = [new_variant_sku if i == hit[0] else s for i, s in enumerate(units)]
    else:
        return {"error": "unknown_action"}
    freed = _release_once(mt, o)
    q = _requote(mt, o, new_units, on)
    if "error" in q:
        mt._ONCE_USED.update(freed)
        return q
    total = sum(u["final_price_vnd"] for u in q["units"])
    if o.get("payment") == "COD" and total > 10000000:
        mt._ONCE_USED.update(freed)
        return {"error": "cod_limit_exceeded", "limit_vnd": 10000000, "total_vnd": total}
    promos = sorted({a["promo_code"] for u in q["units"] for a in u["applied_promos"]} | {a["promo_code"] for a in q["order_promos"]})
    for code in promos:
        mt._ONCE_USED.add((o["customer_phone"], code))
    before = {"lines": [dict(x) for x in o["lines"]], "total_vnd": o["total_vnd"], "promos": list(o.get("promos") or [])}
    o["lines"] = [{"sku": u["sku"], "price_vnd": u["final_price_vnd"]} for u in q["units"]]
    o.update(sku=o["lines"][0]["sku"], qty=len(o["lines"]), price_vnd=o["lines"][0]["price_vnd"], total_vnd=total, promos=promos)
    o.setdefault("amendments", []).append({"on": on, "action": action, "sku": sku, "new_variant_sku": new_variant_sku,
                                           "reason": reason, "before": before})
    return {"order_id": order_id, "status": "updated", "action": action, "lines": [dict(x) for x in o["lines"]],
            "total_vnd": total, "promos": promos}


def order_cancel(mt, order_id, reason=None, on=None):
    on = on or mt.REF
    o = mt._ORDERS.get(order_id)
    if not o:
        return {"error": "order_not_found"}
    if o.get("status") not in EDITABLE:
        return {"error": "order_not_cancellable", "status": o.get("status")}
    _release_once(mt, o)
    o["status"] = "cancelled"
    o.setdefault("amendments", []).append({"on": on, "action": "cancel", "reason": reason})
    return {"order_id": order_id, "status": "cancelled"}


def line_sku_enabled():
    return os.environ.get("LINE_SKU_UPDATE", "0") == "1"


def order_update(mt, order_id, action, new_variant_sku=None, reason=None, on=None, line_sku=None):
    """v6p15 (24/11, duyệt): order.update của BTC + tham số RIÊNG tùy chọn `line_sku` (DIEU-CHINH-DE mục 3: được thêm tham số).
    Không có line_sku → gọi đúng mt.order_update (cùng kết quả mock, mục 10). Có line_sku → đổi size / sản phẩm cho ĐÚNG đơn vị đó
    của đơn nhiều dòng: cùng kiểm tra và cùng dạng ticket như mock (phí DT-03, chênh lệch), chỉ khác giá gốc lấy từ dòng được chọn
    (mock luôn lấy giá đơn vị đầu). Như mock: chỉ tạo ticket, không sửa đơn."""
    kw = {"on": on} if on else {}
    if not line_sku:
        return mt.order_update(order_id, action, new_variant_sku=new_variant_sku, reason=reason, **kw)
    on = on or mt.REF
    if action not in ("exchange_size", "exchange_product"):
        return {"error": "line_sku_only_for_exchange"}
    found = mt.order_status(order_id=order_id)["orders"]
    if not found:
        return {"error": "order_not_found"}
    o = found[0]
    hit = [ln for ln in o.get("lines") or [{"sku": o.get("sku"), "price_vnd": o.get("price_vnd")}] if ln.get("sku") == line_sku]
    if not hit:
        return {"error": "line_not_found"}
    if len({ln.get("price_vnd") for ln in hit}) > 1:
        return {"error": "line_ambiguous"}                 # cùng SKU nhưng khác giá (vd AIR-2ND-50): không đoán đơn vị
    if not new_variant_sku:
        return {"error": "missing_new_variant_sku"}
    inv = mt.inventory_check(new_variant_sku, on)
    if not inv.get("in_stock"):
        return {"error": "new_variant_out_of_stock", **inv}
    new_price = mt.pricing_get_quote(new_variant_sku, on, 1, o.get("customer_phone"))["final_price_vnd"]
    n_prev = sum(1 for t in mt._TICKETS if t["order_id"] == order_id and t["action"].startswith("exchange"))
    fee = 0 if n_prev == 0 else 60000                      # cùng quy tắc mock BTC (DT-03: lần 1 miễn phí, lần 2+: 30k/chiều ×2)
    diff = new_price - hit[0]["price_vnd"]
    t = {"order_id": order_id, "action": action, "new_variant_sku": new_variant_sku, "fee_vnd": fee, "price_diff_vnd": diff,
         "refund_vnd": -diff if diff < 0 else 0, "extra_payment_vnd": diff if diff > 0 else 0, "refund_days": "3-5 ngày làm việc",
         "status": "pickup_scheduled", "line_sku": line_sku}
    mt._TICKETS.append(t)
    return t


LINE_SKU_PROP = {"type": "string", "description": "Tham số riêng của nhóm (tùy chọn): SKU của dòng cần đổi trong đơn nhiều dòng."}

FUNCS = {"order.update_line": order_update_line, "order.cancel": order_cancel}
SCHEMAS = {
    "order.update_line": {"type": "object", "properties": {
        "order_id": {"type": "string"}, "sku": {"type": "string"}, "action": {"type": "string", "enum": ["remove", "change_variant"]},
        "new_variant_sku": {"type": "string"}, "reason": {"type": "string"}, "on": {"type": "string", "format": "date"}},
        "required": ["order_id", "sku", "action"]},
    "order.cancel": {"type": "object", "properties": {
        "order_id": {"type": "string"}, "reason": {"type": "string"}, "on": {"type": "string", "format": "date"}},
        "required": ["order_id"]},
}
DESCRIPTIONS = {
    "order.update_line": "Tool riêng của nhóm: bỏ / đổi biến thể ĐÚNG MỘT dòng của đơn chưa giao (status created); tính lại giá/KM.",
    "order.cancel": "Tool riêng của nhóm: hủy toàn bộ đơn chưa giao (status created).",
}
