"""Kaggle only. v6p15: order.update (tool BTC) + tham số riêng tùy chọn line_sku (LINE_SKU_UPDATE=1) thay order.update_line.
Không line_sku → đúng kết quả mock BTC; có line_sku → ticket đổi đúng dòng; lời gọi vẫn khớp args_match kiểu BTC; luồng agent."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["LINE_SKU_UPDATE"] = "1"
os.environ["ORDER_EXT_TOOLS"] = "0"
from core.config import settings
from eval import reference_eval as RE
from harness import plan_primitives as P
from harness.tools import ToolBox, mt

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
    return tb.call("order.create", customer_phone=PHONE, lines=lines, payment="COD", address="12 Lê Lợi, Quận 1, TP HCM"), lines


def tool_suite(tag):
    tb = ToolBox("2026-10-15")
    ToolBox.reset_world()
    o, _ = make_order(tb, ["SKU-SN-CAS-39-DEN", "SKU-WF-UF"])
    oid = o["order_id"]
    plain = tb.call("order.update", order_id=oid, action="exchange_size", new_variant_sku="SKU-SN-CAS-40-DEN")
    ToolBox.reset_world()
    o2, _ = make_order(tb, ["SKU-SN-CAS-39-DEN", "SKU-WF-UF"])
    ref = mt.order_update(o2["order_id"], "exchange_size", new_variant_sku="SKU-SN-CAS-40-DEN", on="2026-10-15") if tag == "direct" else plain
    check(f"[{tag}] no line_sku → same result as BTC mock", plain == ref and plain.get("status") == "pickup_scheduled")
    ToolBox.reset_world()
    o, lines = make_order(tb, ["SKU-WF-UF", "SKU-SN-CAS-39-DEN"])
    oid = o["order_id"]
    args = {"order_id": oid, "action": "exchange_size", "new_variant_sku": "SKU-SN-CAS-40-DEN", "line_sku": "SKU-SN-CAS-39-DEN"}
    r = tb.call("order.update", **args)
    shoe = next(ln for ln in lines if ln["sku"] == "SKU-SN-CAS-39-DEN")
    new_price = tb.call("pricing.get_quote", sku="SKU-SN-CAS-40-DEN", customer_phone=PHONE)["final_price_vnd"]
    check(f"[{tag}] line_sku: ticket for the chosen line (diff vs that line, not first unit)",
          r.get("status") == "pickup_scheduled" and r.get("line_sku") == "SKU-SN-CAS-39-DEN"
          and r.get("price_diff_vnd") == new_price - shoe["price_vnd"] and r.get("fee_vnd") == 0)
    st = tb.call("order.status", order_id=oid)["orders"][0]
    check(f"[{tag}] like the mock: ticket only, order lines unchanged", [ln["sku"] for ln in st["lines"]] == [ln["sku"] for ln in lines])
    check(f"[{tag}] BTC-style args_match still matches the call",
          RE.args_match({"action": "exchange_size", "new_variant_sku": "SKU-SN-CAS-40-DEN"}, args))
    check(f"[{tag}] unknown line → error, no ticket", tb.call("order.update", **{**args, "line_sku": "SKU-AP-MINI"}).get("error") == "line_not_found")
    check(f"[{tag}] line_sku on return → error", tb.call("order.update", **{**args, "action": "return"}).get("error") == "line_sku_only_for_exchange")
    check(f"[{tag}] update_line tool not available (ext tools off)",
          tb.call("order.update_line", order_id=oid, sku="SKU-WF-UF", action="remove").get("error") in ("tool_disabled", "tool_exception"))


with patch.object(settings, "tool_transport", "direct"):
    tool_suite("direct")
try:
    with patch.object(settings, "tool_transport", "mcp"):
        tool_suite("mcp")
except Exception as e:                                          # noqa: BLE001
    check(f"[mcp] suite ran ({type(e).__name__}: {e})", False)

# ------------------------------------------------------------------ luồng agent: đổi biến thể một dòng của đơn vừa tạo
with patch.object(settings, "tool_transport", "direct"):
    tb = ToolBox("2026-10-15")
    ToolBox.reset_world()
    o, lines = make_order(tb, ["SKU-SN-CAS-39-DEN", "SKU-WF-UF"])
    rec = {"order_id": o["order_id"], "sku": lines[0]["sku"], "skus": [ln["sku"] for ln in lines], "lines": [dict(x) for x in lines],
           "total_vnd": o["total_vnd"], "status": "created"}
    s = SimpleNamespace(tools=tb, orders_created=[rec])
    c = SimpleNamespace(text="À mà đôi giày em lấy size 40 giùm chị", facts={}, goals=[])
    t = SimpleNamespace(s=s, c=c)
    tb.log.clear()
    ok = P._try_ext_amend(t, o["order_id"], "change_variant", ["SKU-SN-CAS-39-DEN"], "SKU-SN-CAS-40-DEN")
    call = next((x for x in tb.log if x["name"] == "order.update"), {})
    check("agent: change variant → BTC order.update exchange_size with line_sku",
          ok and call.get("args", {}).get("action") == "exchange_size" and call["args"].get("line_sku") == "SKU-SN-CAS-39-DEN"
          and not any(x["name"] == "order.update_line" for x in tb.log))
    check("agent: reply facts show the order after the change",
          c.goals == ["amend_done"] and "SKU-SN-CAS-40-DEN" in rec["skus"] and c.facts["amend_done"]["total_vnd"] == rec["total_vnd"])
    tb.log.clear()
    check("agent: remove line → no tool (handoff path)", not P._try_ext_amend(t, o["order_id"], "remove", ["SKU-WF-UF"], None) and not tb.log)
    check("agent: cancel → no tool (handoff path)", not P._try_ext_cancel(t, o["order_id"]) and not tb.log)
    rec["lines"][0]["qty"] = 2
    check("agent: multi-unit line → no tool", not P._try_ext_amend(t, o["order_id"], "change_variant", [rec["lines"][0]["sku"]], "SKU-SN-CAS-41-DEN"))

print("v6p15 checks:", passed, "PASS", flush=True)
assert not failed, failed
