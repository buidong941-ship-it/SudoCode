"""Kaggle only. v6p5 (lần 1: tiếp tục đơn vừa tạo + giỏ nháp có điều kiện + câu bàn giao): CallSession/tool BTC thật, model có
kịch bản — không đo chất lượng LLM."""
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
frame_path = ROOT / "tests/b2_round_f_check.py"
F = types.ModuleType("v6p5_frame")
F.__file__ = str(frame_path)
exec(compile(frame_path.read_text(encoding="utf-8").split("# ================================================================== H8")[0],
             str(frame_path), "exec"), F.__dict__)
from harness import jev_write_gate as G

passed, failed = 0, []


def check(name, value):
    global passed
    if value:
        passed += 1
        print("PASS", name, flush=True)
    else:
        failed.append(name)
        print("FAIL", name, flush=True)


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
    for prefix in ("commit_request:", "answer_ask:", "clarify:", "read_quote:", "clarify", "finish"):
        found = next((x for x in steps if x.startswith(prefix)), None)
        if found:
            return {"step": found}
    return {"step": "finish"}


def session(name):
    return F.session("v6p5-" + name, decider=planner)


def say(s, text, requests=(), **kw):
    return F.say(s, text, F.resp(intent="place_order" if requests else "greeting_or_other", requests=list(requests), **kw))


def req(kind, evidence, ref=None, **kw):
    return {"kind": kind, "evidence": evidence, "target_ref": ref, **kw}


def refs(s):
    s.reqs.context(s)
    return {tuple(v["skus"])[0]: k for k, v in s.reqs.refmap.items() if k.startswith("P") and v.get("type") == "product"}


ADDR = "12 Lê Lợi, Quận 1, TP HCM"
extra = {"jev_write_gate": True, "b2_two_tier": False, "b2_max_decisions": 20, "b2_max_tool_calls": 25}
with F.Ctx(extra), patch.object(G, "assess", assess):
    # 1. Phần 1: đơn vừa tạo chưa có địa chỉ; khách đọc địa chỉ kèm nhắc lại món đã đặt → bổ sung địa chỉ, không mở yêu cầu mới
    s = session("continuation")
    row = say(s, "Lấy AirPure Mini cho chị", [req("place_order", "Lấy AirPure Mini", "P1", target_basis="named")])
    check("setup: order created", len(s.orders_created) == 1)
    s.orders_created[0]["address"] = None              # dựng trạng thái: đơn vừa tạo còn thiếu địa chỉ
    s.turn_mentioned = ["SKU-AP-MINI"]
    r = refs(s)
    row = say(s, f"Gửi AirPure Mini về {ADDR} nha", [req("place_order", "Gửi AirPure Mini", r["SKU-AP-MINI"], target_basis="context")],
              observations=[{"slot": "address", "span": ADDR, "stance": "stated", "subject": "self"}])
    print("continuation reply:", row["agent_text"], "| goals", row.get("goals"), flush=True)
    upd = [c for c in F.calls(row, "order.update") if c["args"].get("action") == "update_address"]
    check("continuation: address added to the created order", len(upd) == 1 and upd[0]["args"]["order_id"] == s.orders_created[0]["order_id"])
    check("continuation: no new order and no new purchase request", not F.calls(row, "order.create")
          and not any(x["status"] in ("held", "open", "needs_target") for x in s.reqs.items))
    check("continuation: no product question", not {"ask_which_product", "ask_product"} & set(row.get("goals") or []))

    # 2. "đặt thêm" (new_request) KHÔNG bị coi là tiếp tục đơn
    s = session("explicit-additional")
    say(s, "Lấy AirPure Mini cho chị", [req("place_order", "Lấy AirPure Mini", "P1", target_basis="named")])
    s.turn_mentioned = ["SKU-AP-MINI"]
    r = refs(s)
    say(s, "Đặt thêm một đơn AirPure Mini nữa", [req("place_order", "Đặt thêm một đơn AirPure Mini", r["SKU-AP-MINI"],
        target_basis="named", new_request=True)])
    check("explicit new request is not swallowed as continuation", getattr(s, "order_continuation", None) is None)

    # 3. Phần 2: giỏ nháp, đổi sang biến thể hết hàng + "hết thì thôi" → báo hết hàng, bỏ khỏi giỏ, không đơn, không "nói lại"
    s = session("draft-unavailable")
    row = say(s, "Thêm Warmly size S màu đen vào giỏ nháp, chưa đặt", [req("add_to_cart", "Thêm Warmly size S màu đen", "P1",
        size_span="size S", color_span="màu đen", target_basis="named")])
    print("draft reply:", row["agent_text"], "| goals", row.get("goals"), flush=True)
    check("draft: confirmed as draft, not 'please repeat'", "draft_saved" in (row.get("goals") or []) and "nói lại" not in row["agent_text"]
          and not F.calls(row, "order.create"))
    row = say(s, "Đổi sang màu be, màu be mà hết thì thôi không lấy nữa", [req("edit_cart", "Đổi sang màu be", "P1", operation="update",
        color_span="màu be", request_id="R1", on_unavailable={"action": "cancel", "evidence": "màu be mà hết thì thôi không lấy nữa"})])
    text = row["agent_text"]
    print("draft unavailable reply:", text, "| goals", row.get("goals"), "| trace", (s.reqs.items[0] if s.reqs.items else {}).get("condition_trace"), flush=True)
    check("draft unavailable: stock of the requested variant read", any(c["args"].get("sku") == "SKU-JK-DWN-S-BE" for c in F.calls(row, "inventory.check")))
    check("draft unavailable: says out of stock and removed", "hết hàng" in text and "draft_withdrawn" in (row.get("goals") or []))
    check("draft unavailable: request withdrawn, variant not in cart, no order",
          s.reqs.items[0]["status"] == "withdrawn" and "SKU-JK-DWN-S-BE" not in s.cart and not F.calls(row, "order.create"))
    check("draft unavailable: condition trace recorded", any(x.get("branch") == "customer_cancel_if_unavailable"
                                                              for x in s.reqs.items[0].get("condition_trace") or []))

    # 4. giỏ nháp còn hàng + có nhánh hủy → lưu nháp, ghi trace còn hàng
    s = session("draft-in-stock")
    row = say(s, "Thêm Warmly size S màu đen vào giỏ nháp, hết thì thôi", [req("add_to_cart", "Thêm Warmly size S màu đen", "P1",
        size_span="size S", color_span="màu đen", target_basis="named", on_unavailable={"action": "cancel", "evidence": "hết thì thôi"})])
    check("draft in stock: saved, no order", "draft_saved" in (row.get("goals") or []) and not F.calls(row, "order.create")
          and s.reqs.items[0]["status"] == "held")

    # 5. Phần 4: câu bàn giao hủy đơn nói rõ chuyển nhân viên
    s = session("cancel-wording")
    say(s, "Lấy AirPure Mini cho chị", [req("place_order", "Lấy AirPure Mini", "P1", target_basis="named")])
    row = say(s, "Chị muốn hủy đơn vừa đặt", [req("cancel", "hủy đơn vừa đặt", "O1")])
    print("cancel reply:", row["agent_text"], flush=True)
    check("cancel handoff wording names the staff transfer", "chuyển nhân viên" in row["agent_text"] and "chuyên viên" not in row["agent_text"])

print("v6p5 checks:", passed, "PASS", flush=True)
assert not failed, failed
