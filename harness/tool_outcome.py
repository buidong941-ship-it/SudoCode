"""Phân loại kết quả từng lời gọi tool (bàn giao FINAL 10/11, G1): confirmed_success / confirmed_failure / unresolved.

Thay phép chung "không có `error` là thành công": mỗi tool có dấu hiệu thành công riêng, lấy từ response của chính tool
(eval/mock_tools.py). Lỗi transport (`tool_exception`, không có response) của tool GHI là `unresolved`: không biết thao tác đã
có hiệu lực hay chưa — không coi là thất bại để tạo lại, cũng không coi là thành công để báo khách.
Một đơn cùng SKU/ngày tìm thấy sau đó KHÔNG chứng minh correlation với lời gọi lỗi, nên module này không đối soát.
"""

WRITE_TOOLS = ("order.create", "order.update", "schedule.callback", "handoff.transfer")
TRANSPORT_ERRORS = ("tool_exception", "timeout")


def _money(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0


def _str(v):
    return isinstance(v, str) and bool(v.strip())


# Dấu hiệu thành công theo response của từng tool. Tool không có trong bảng: đọc dữ liệu, không lỗi là có dữ liệu.
_SUCCESS = {
    "order.create": lambda a, r: _str(r.get("order_id")) and r.get("status") == "created" and _money(r.get("total_vnd")),
    "order.update": lambda a, r: r.get("order_id") == a.get("order_id") and r.get("status") in ("pickup_scheduled", "updated")
                                 and (a.get("action") is None or r.get("action") == a.get("action")),
    "schedule.callback": lambda a, r: _str(r.get("callback_id")) and _str(r.get("callback_at")),
    # handoff thành công = đã XẾP HÀNG cho nhân viên (status queued), không phải đã có người xử lý xong.
    "handoff.transfer": lambda a, r: _str(r.get("ticket_id")) and r.get("status") == "queued",
    "order.status": lambda a, r: isinstance(r.get("orders"), list),
    "pricing.get_quote": lambda a, r: _money(r.get("final_price_vnd")),
    # BTC 11/2026: báo giá TỪNG đơn vị của đơn nhiều dòng — đủ units/lines, tổng = cộng giá từng đơn vị
    "pricing.quote_order": lambda a, r: isinstance(r.get("units"), list) and bool(r["units"]) and isinstance(r.get("lines"), list)
                                        and all(_money(u.get("final_price_vnd")) and _str(u.get("sku")) for u in r["units"])
                                        and _money(r.get("total_vnd")) and r["total_vnd"] == sum(u["final_price_vnd"] for u in r["units"]),
    "inventory.check": lambda a, r: isinstance(r.get("in_stock"), bool),
    "crm.get_customer": lambda a, r: isinstance(r.get("found"), bool),
}


def _target(name, args, result):
    if name == "order.create":
        skus = [ln.get("sku") for ln in args.get("lines") or []] or [args.get("sku")]       # đơn nhiều dòng: một order_id, nhiều SKU
        return {"sku": skus[0], "skus": skus, "order_id": result.get("order_id") if isinstance(result, dict) else None}
    if name == "order.update":
        return {"order_id": args.get("order_id"), "action": args.get("action")}
    if name == "schedule.callback":
        return {"callback_at": args.get("callback_at")}
    return {}


def classify(call):
    """call: một dòng tool log {name|tool, args, result|response}. Trả {tool, write, status, target, reason}."""
    name = call.get("name") or call.get("tool")
    args = call.get("args") or {}
    result = call.get("result") if "result" in call else call.get("response")
    write = name in WRITE_TOOLS
    out = {"tool": name, "write": write, "target": _target(name, args, result)}
    if not isinstance(result, dict):
        return {**out, "status": "unresolved", "reason": "no_response"}
    err = result.get("error")
    if err in TRANSPORT_ERRORS:
        # tool đọc: chỉ là chưa có dữ liệu; tool ghi: không biết đã có hiệu lực hay chưa
        return {**out, "status": "unresolved", "reason": err}
    if err:
        return {**out, "status": "confirmed_failure", "reason": err}
    check = _SUCCESS.get(name)
    if check is not None and not check(args, result):
        return {**out, "status": "unresolved" if write else "confirmed_failure", "reason": "unexpected_response"}
    return {**out, "status": "confirmed_success", "reason": None}


def ok(call):
    return classify(call)["status"] == "confirmed_success"


def confirmed(tool_log, name):
    """Các lời gọi `name` thành công đã xác nhận, kèm response."""
    return [c for c in tool_log if (c.get("name") or c.get("tool")) == name and ok(c)]
