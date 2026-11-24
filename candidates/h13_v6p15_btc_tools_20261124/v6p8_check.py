"""Kaggle only. v6p8: (1) schema bộ hiểu nhận null ở trường không bắt buộc; (2) tool riêng order.update_line / order.cancel
(ORDER_EXT_TOOLS=1) — kiểm trạng thái đơn SAU ghi qua order.status, ràng buộc từ chối, đường trực tiếp + MCP, và luồng agent."""
import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
frame_path = ROOT / "tests/b2_round_f_check.py"
F = types.ModuleType("v6p8_frame")
F.__file__ = str(frame_path)
exec(compile(frame_path.read_text(encoding="utf-8").split("# ================================================================== H8")[0],
             str(frame_path), "exec"), F.__dict__)
from harness import jev_write_gate as G
from harness.tools import ToolBox
from core.config import settings

passed, failed = 0, []


def check(name, value):
    global passed
    if value:
        passed += 1
        print("PASS", name, flush=True)
    else:
        failed.append(name)
        print("FAIL", name, flush=True)


PHONE = "0911222333"


def make_order(tb, skus):
    q = tb.call("pricing.quote_order", lines=[{"sku": s, "qty": 1} for s in skus], customer_phone=PHONE)
    lines = [{"sku": u["sku"], "qty": 1, "price_vnd": u["final_price_vnd"]} for u in q["units"]]
    return tb.call("order.create", customer_phone=PHONE, lines=lines, payment="COD", address="12 Lê Lợi, Quận 1, TP HCM")


def tool_suite(label):
    tb = ToolBox("2026-10-15")
    ToolBox.reset_world()
    o = make_order(tb, ["SKU-AP-MINI", "SKU-AF-6L"])
    oid = o.get("order_id")
    single = tb.call("pricing.quote_order", lines=[{"sku": "SKU-AP-MINI", "qty": 1}], customer_phone=PHONE)
    r = tb.call("order.update_line", order_id=oid, sku="SKU-AF-6L", action="remove", reason="khách bỏ")
    st = tb.call("order.status", order_id=oid)
    so = (st.get("orders") or [st])[0] if isinstance(st, dict) else {}
    print(f"  [{label}] remove:", r, "| status:", so.get("lines"), so.get("total_vnd"), flush=True)
    check(f"[{label}] remove one line → updated", r.get("status") == "updated")
    check(f"[{label}] order.status reflects removal (lines + total recomputed)",
          [x["sku"] for x in so.get("lines") or []] == ["SKU-AP-MINI"] and so.get("total_vnd") == single["total_vnd"])
    r = tb.call("order.update_line", order_id=oid, sku="SKU-AP-MINI", action="remove")
    check(f"[{label}] removing last line refused (use cancel)", r.get("error") == "would_empty_order")
    o2 = make_order(tb, ["SKU-AP-MINI", "SKU-AP-MINI", "SKU-AF-6L"])
    r = tb.call("order.update_line", order_id=o2["order_id"], sku="SKU-AP-MINI", action="remove")
    check(f"[{label}] SKU matching several units refused (no line id)", r.get("error") == "ambiguous_line")
    o3 = make_order(tb, ["SKU-AP-MINI", "SKU-JK-DWN-S-NAVY"])
    r = tb.call("order.update_line", order_id=o3["order_id"], sku="SKU-JK-DWN-S-NAVY", action="change_variant",
                new_variant_sku="SKU-JK-DWN-M-BE")
    st = tb.call("order.status", order_id=o3["order_id"])
    so = (st.get("orders") or [st])[0] if isinstance(st, dict) else {}
    print(f"  [{label}] change_variant:", r, "| status lines:", so.get("lines"), flush=True)
    check(f"[{label}] change variant of one line", r.get("status") == "updated"
          and sorted(x["sku"] for x in so.get("lines") or []) == ["SKU-AP-MINI", "SKU-JK-DWN-M-BE"])
    r = tb.call("order.update_line", order_id=o3["order_id"], sku="SKU-AP-MINI", action="change_variant", new_variant_sku="SKU-AF-6L")
    check(f"[{label}] change to another product refused", r.get("error") == "not_same_product_variant")
    r = tb.call("order.cancel", order_id=oid, reason="khách hủy")
    st = tb.call("order.status", order_id=oid)
    so = (st.get("orders") or [st])[0] if isinstance(st, dict) else {}
    check(f"[{label}] cancel → status cancelled in order.status", r.get("status") == "cancelled" and so.get("status") == "cancelled")
    r = tb.call("order.update_line", order_id=oid, sku="SKU-AP-MINI", action="remove")
    check(f"[{label}] cancelled order not editable", r.get("error") == "order_not_editable")


# ------------------------------------------------------------------ (2) tool: tắt cờ / bật cờ, trực tiếp + MCP
os.environ["ORDER_EXT_TOOLS"] = "0"
with patch.object(settings, "tool_transport", "direct"):
    tb = ToolBox("2026-10-15")
    ToolBox.reset_world()
    check("flag off → ext tool disabled (baseline behaviour)", tb.call("order.cancel", order_id="OD600001").get("error") == "tool_disabled")
os.environ["ORDER_EXT_TOOLS"] = "1"
with patch.object(settings, "tool_transport", "direct"):
    tool_suite("direct")
try:
    with patch.object(settings, "tool_transport", "mcp"):
        tool_suite("mcp")
except Exception as e:                                          # noqa: BLE001
    check(f"[mcp] suite ran ({type(e).__name__}: {e})", False)


def decision(state, opts):
    action = state["proposed_update"]["action"]
    choice = "reject_or_withdraw" if action == "withdraw" else "open_or_update_request"
    return {"decision": choice, "request_id": opts["request_ids"][0],
            "target_ref": opts["target_refs"][0], "revision": opts["revision"]}


real_assess = G.assess


def assess(*args, **kwargs):
    return real_assess(*args, **kwargs, decider=decision)


def planner(state, opts):
    steps = opts["step"]
    for req_ in state.get("open_requests") or []:
        for detail in req_.get("readiness", {}).get("detail") or []:
            if detail in steps:
                return {"step": detail}
    for prefix in ("commit_request:", "answer_ask:", "clarify:", "read_order", "read_quote:", "clarify", "finish"):
        found = next((x for x in steps if x.startswith(prefix)), None)
        if found:
            return {"step": found}
    return {"step": "finish"}


def say(s, text, requests=(), **kw):
    return F.say(s, text, F.resp(intent="place_order" if requests else "greeting_or_other", requests=list(requests), **kw))


def req(kind, evidence, ref=None, **kw):
    return {"kind": kind, "evidence": evidence, "target_ref": ref, **kw}


def refs(s):
    s.reqs.context(s)
    return {tuple(v["skus"])[0]: k for k, v in s.reqs.refmap.items() if k.startswith("P") and v.get("type") == "product"}


extra = {"jev_write_gate": True, "b2_two_tier": False, "b2_max_decisions": 20, "b2_max_tool_calls": 25}
with F.Ctx(extra), patch.object(G, "assess", assess):
    # ---- (2) luồng agent: bỏ món đơn vừa tạo → order.update_line, không chuyển nhân viên
    s = F.session("v6p8-amend", decider=planner)
    say(s, "Lấy AirPure Mini và Philips 6.2L cho chị", [req("place_order", "Lấy AirPure Mini và Philips 6.2L",
        lines=[{"target_ref": "P1"}, {"target_ref": "P2"}], target_basis="named")])
    s.turn_mentioned = ["SKU-AF-6L"]
    r = refs(s)
    row = say(s, "À khoan, bỏ Philips ra giùm chị nhé", [req("edit_cart", "bỏ Philips ra giùm chị", r["SKU-AF-6L"], operation="remove")])
    print("  agent amend reply:", row["agent_text"], "| goals", row.get("goals"), flush=True)
    upd = F.calls(row, "order.update_line")
    check("agent: amend uses order.update_line on the removed item", len(upd) == 1 and upd[0]["args"].get("sku") == "SKU-AF-6L")
    check("agent: no handoff, reply confirms with new total", not F.calls(row, "handoff.transfer") and "amend_done" in (row.get("goals") or [])
          and "đã bỏ" in row["agent_text"])
    # ---- hủy đơn → order.cancel
    s = F.session("v6p8-cancel", decider=planner)
    say(s, "Lấy AirPure Mini cho chị", [req("place_order", "Lấy AirPure Mini", "P1", target_basis="named")])
    row = say(s, "Chị muốn hủy đơn vừa đặt", [req("cancel", "hủy đơn vừa đặt", "O1")])
    print("  agent cancel reply:", row["agent_text"], "| goals", row.get("goals"), flush=True)
    check("agent: cancel uses order.cancel, no handoff", len(F.calls(row, "order.cancel")) == 1 and not F.calls(row, "handoff.transfer")
          and "đã hủy" in row["agent_text"])

    # ---- (1) schema: trường không bắt buộc = null không còn bị coi là sai kiểu
    s = F.session("v6p8-null-fields", decider=planner)
    row = say(s, "Lấy AirPure Mini cho chị", [req("place_order", "Lấy AirPure Mini", "P1", target_basis="named", operation=None,
              lines=None, new_request=None, condition_changed=None)])
    um = (s.u_turn or {}).get("meta") or {}
    print("  null-fields dropped:", um.get("dropped"), "| type_hold", um.get("type_hold"), flush=True)
    check("schema: null optional fields → no type_invalid hold", not um.get("type_hold")
          and not any(d.get("why") == "type_invalid" for d in um.get("dropped") or []))
    check("schema: request still executes", bool(F.calls(row, "order.create")))

os.environ["ORDER_EXT_TOOLS"] = "0"
print("v6p8 checks:", passed, "PASS", flush=True)
assert not failed, failed
