"""Kaggle only. v6p9b: (1) sửa dòng bằng tool thành công → yêu cầu đổi đóng; lượt địa chỉ sau đó không chuyển nhân viên, không nói
"đơn chưa thay đổi" (H13-037); (2) đơn đã hủy bằng tool, khách xin người xác nhận → không gọi hủy lần nữa, chuyển nhân viên, câu trả
lời nói đã hủy (H13-086)."""
import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
frame_path = ROOT / "tests/b2_round_f_check.py"
F = types.ModuleType("v6p9b_frame")
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
    for prefix in ("commit_request:", "answer_ask:", "read_condition:", "clarify:", "read_order", "read_quote:", "read_stock:",
                   "check_window:", "clarify", "finish"):
        found = next((x for x in steps if x.startswith(prefix)), None)
        if found:
            return {"step": found}
    return {"step": "finish"}


SENTINEL = F.resp(intent="greeting_or_other")


def turn(s, text, *resps):
    F.QUEUE[:] = list(resps)
    row = s.turn(text)
    s.drain_audits()
    return row


def say(s, text, requests=(), **kw):
    return F.say(s, text, F.resp(intent="place_order" if requests else "greeting_or_other", requests=list(requests), **kw))


def req(kind, evidence, ref=None, **kw):
    return {"kind": kind, "evidence": evidence, "target_ref": ref, **kw}


extra = {"jev_write_gate": True, "b2_two_tier": False, "b2_max_decisions": 20, "b2_max_tool_calls": 25}
os.environ["ORDER_EXT_TOOLS"] = "1"
with F.Ctx(extra), patch.object(G, "assess", assess):
    # ---- (1) 037: đổi biến thể xong → lượt địa chỉ hoàn tất đơn, không chuyển nhân viên
    s = F.session("v6p9b-amend-then-address", decider=planner)
    say(s, "Lấy AirPure Mini và Warmly size S màu navy", [req("place_order", "Lấy AirPure Mini và Warmly size S màu navy",
        lines=[{"target_ref": "P1", "product_span": "AirPure Mini"},
               {"target_ref": "P2", "product_span": "Warmly", "size_span": "size S", "color_span": "màu navy"}], target_basis="named")])
    row = turn(s, "Đổi cái áo sang size M màu be giùm chị", F.resp(intent="exchange", requests=[req("exchange",
               "Đổi cái áo sang size M màu be", "O1", lines=[{"target_ref": "O1", "product_span": "cái áo", "size_span": "size M",
                                                              "color_span": "màu be"}])]), SENTINEL)
    ex = [r for r in s.reqs.items if r["kind"] == "exchange"]
    print("  amend:", row.get("goals"), "| exchange req status:", [r["status"] for r in ex], flush=True)
    check("037: amend_done and exchange request settled", "amend_done" in (row.get("goals") or []) and ex and ex[-1]["status"] == "done")
    row = turn(s, "Gửi về 12 Lê Lợi, Quận 1, TP HCM, nhận hàng chị trả tiền", F.resp(intent="greeting_or_other", observations=[
        {"slot": "address", "span": "12 Lê Lợi, Quận 1, TP HCM", "stance": "stated", "subject": "self"}]), SENTINEL)
    print("  address turn:", row["agent_text"], "| goals", row.get("goals"), "| tools", [c["name"] for c in row["tool_calls"]], flush=True)
    check("037: address turn after amend → no handoff, no 'chưa thay đổi'", not F.calls(row, "handoff.transfer")
          and "chưa thay đổi" not in row["agent_text"] and "amend_handoff" not in (row.get("goals") or []))
    check("037: settled amend not re-run (no update_line / exchange write)", not F.calls(row, "order.update_line")
          and not [c for c in F.calls(row, "order.update") if c["args"].get("action") in ("exchange_product", "exchange_size")])

    # ---- (2) 086: hủy bằng tool, rồi khách xin người xác nhận
    s = F.session("v6p9b-cancel-then-person", decider=planner)
    say(s, "Lấy AirPure Mini cho chị", [req("place_order", "Lấy AirPure Mini", "P1", target_basis="named")])
    oid = s.orders_created[0]["order_id"] if s.orders_created else None
    s.brief = {**(s.brief or {}), "orders": [{"order_id": oid, "status": "created", "sku": "SKU-AP-MINI"}]}   # bản ghi cũ còn "created"
    row = say(s, "Chị muốn hủy đơn vừa đặt", [req("cancel", "hủy đơn vừa đặt", "O1")])
    check("086 setup: first cancel via order.cancel", len(F.calls(row, "order.cancel")) == 1)
    row = say(s, "Em chuyển người hỗ trợ giúp chị xác nhận yêu cầu hủy đơn nhé", [req("cancel", "xác nhận yêu cầu hủy đơn", "O1"),
              req("handoff", "Em chuyển người hỗ trợ giúp chị")])
    print("  person turn:", row["agent_text"], "| goals", row.get("goals"), "| tools", [c["name"] for c in row["tool_calls"]], flush=True)
    check("086: no second order.cancel", not F.calls(row, "order.cancel"))
    check("086: handed off to a person", bool(F.calls(row, "handoff.transfer")))
    ho = F.calls(row, "handoff.transfer")
    check("086: reply never says the order is not cancelled", "chưa hủy" not in row["agent_text"])
    na = str((ho[0]["args"].get("brief") or {}).get("next_action")) if ho else ""
    print("  brief next_action:", na[:240], flush=True)
    check("086: handoff brief says the order is already cancelled", "ĐÃ hủy" in na and str(oid) in na)
os.environ["ORDER_EXT_TOOLS"] = "0"

print("v6p9b checks:", passed, "PASS", flush=True)
assert not failed, failed
