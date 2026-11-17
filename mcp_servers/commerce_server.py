#!/usr/bin/env python3
"""mcp-commerce: CRM + catalog + tồn kho + giá/KM + đơn hàng + hẹn gọi lại + chuyển máy, qua MCP (stdio).

Logic là `eval/mock_tools.py` của BTC (logic tham chiếu) — server chỉ đóng gói, không sửa kết quả.
Tên tool và tham số đúng `schemas/tools.schema.json`; kiểu dữ liệu lấy từ file đó nên server tự từ chối lời gọi
sai kiểu (MCP SDK kiểm inputSchema trước khi chạy tool).

Trạng thái runtime của mock (đơn mới, lịch gọi lại, ticket, KM 1 lần/khách) sống trong tiến trình server;
`world.reset` xóa nó khi harness chuyển sang kịch bản mới. Mỗi tiến trình harness có server riêng → không lẫn trạng thái.

    python mcp_servers/commerce_server.py      # thường do harness tự khởi động (TOOL_TRANSPORT=mcp)
"""
import importlib.util
import json
import os
import re

from common import ROOT, run_server, schema_from_signature

BTC_DIR = os.environ.get("BTC_DIR") or ROOT
_spec = importlib.util.spec_from_file_location("mock_tools", os.path.join(BTC_DIR, "eval", "mock_tools.py"))
mt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mt)


_SCALAR = {"string": {"type": "string"}, "int": {"type": "integer"}, "boolean": {"type": "boolean"},
           "date": {"type": "string", "format": "date"}, "datetime": {"type": "string"}}


def _json_type(spec):
    """Kiểu JSON từ mô tả trong tools.schema.json. Mảng có phần tử dạng `[{sku: string, qty: int}]` → items object có kiểu
    (BTC 11/2026: order.create lines, pricing.quote_order lines); mảng không mô tả phần tử (basket_skus) → mảng chuỗi SKU."""
    raw = str(spec)
    m = re.match(r"\s*([A-Za-z]+)", raw)
    base = m.group(1) if m else ""
    if base == "array":
        im = re.search(r"\[\{([^}]*)\}\]", raw)
        if im:
            props = {}
            for part in im.group(1).split(","):
                if ":" in part:
                    k, t = (x.strip() for x in part.split(":", 1))
                    props[k] = dict(_SCALAR.get(t.rstrip("?"), {}))
            return {"type": "array", "items": {"type": "object", "properties": props, "required": ["sku"]}}
        return {"type": "array", "items": {"type": "string"}}
    s = re.sub(r"\s*\(.*\)$", "", raw).strip().rstrip("?").strip()
    if "|" in s:
        return {"type": "string", "enum": s.split("|")}
    return _SCALAR.get(s, {"type": "object"} if s[:1].isupper() else {})


def _schema_path():
    p = os.path.join(BTC_DIR, "schemas", "tools.schema.json")      # cùng phiên bản BTC với mock (direct = MCP)
    return p if os.path.exists(p) else os.path.join(ROOT, "schemas", "tools.schema.json")


def _tools():
    spec = {t["name"]: t for t in json.load(open(_schema_path(), encoding="utf-8"))["tools"]}
    out = {}
    for name, fn in mt.TOOLS.items():
        s = spec.get(name, {})
        public = set((s.get("input") or {})) | {"on"}
        types_ = {k: _json_type(v) for k, v in (s.get("input") or {}).items()}
        types_.setdefault("on", {"type": "string", "format": "date"})
        desc = (s.get("description") or name) + (f" [{s['level']}]" if s.get("level") else "")
        sch = schema_from_signature(fn, types_)
        # chỉ xuất tham số công khai trong schema BTC; tham số nội bộ của mock (exclude, _second_item_used, _tie_prefer_first)
        # không thành quyền của agent
        if s.get("input"):
            sch["properties"] = {k: v for k, v in sch["properties"].items() if k in public}
            sch["required"] = [k for k in sch["required"] if k in public]
        out[name] = (fn, desc, sch)

    def reset():
        mt._ORDERS.clear(); mt._CALLBACKS.clear(); mt._TICKETS.clear(); mt._ONCE_USED.clear()
        return {"ok": True}
    out["world.reset"] = (reset, "Nội bộ harness: xóa đơn/lịch/ticket/KM đã dùng của lần chạy trước (không phải tool cho khách).",
                          {"type": "object", "properties": {}, "additionalProperties": False})
    return out


if __name__ == "__main__":
    run_server("mcp-commerce", _tools(),
               instructions="Tool nghiệp vụ bán hàng. Giá/KM/tồn kho luôn lấy từ đây, không tự suy ra. Mọi tool nhận `on` = ngày cuộc gọi.")
