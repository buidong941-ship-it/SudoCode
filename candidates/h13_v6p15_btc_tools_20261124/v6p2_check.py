"""Kaggle only. v6p2 (tham chiếu mơ hồ): CallSession/tool BTC thật, quyết định model có kịch bản — không đo chất lượng LLM."""
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
frame_path = ROOT / "tests/b2_round_f_check.py"
F = types.ModuleType("v6p2_frame")
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


offered = []


def planner(state, opts):
    """Giống Jev trong trace H13-047: đọc giá mẫu đầu tiên nếu được mời, rồi hỏi lại / kết thúc."""
    steps = opts["step"]
    offered.append(list(steps))
    for prefix in ("read_quote:", "clarify", "finish"):
        found = next((x for x in steps if x.startswith(prefix)), None)
        if found:
            return {"step": found}
    return {"step": steps[0] if steps else "finish"}


def session(name):
    return F.session("v6p2-" + name, decider=planner)


def say(s, text, requests=(), **kw):
    return F.say(s, text, F.resp(intent="place_order" if requests else "greeting_or_other", requests=list(requests), **kw))


def req(kind, evidence, ref=None, **kw):
    return {"kind": kind, "evidence": evidence, "target_ref": ref, **kw}


def history(name, skus=("SKU-AF-XM", "SKU-AF-6L")):
    s = session(name)
    s.brief = {**(s.brief or {}), "is_returning": True, "products_advised": [{"sku": x} for x in skus]}
    s.focus = skus[-1]
    return s


extra = {"jev_write_gate": True, "b2_two_tier": False, "b2_max_decisions": 20, "b2_max_tool_calls": 25}
with F.Ctx(extra), patch.object(G, "assess", assess):
    # 1. mơ hồ giữa hai mẫu đã tư vấn → hỏi chọn đúng hai mẫu, không ghi, không báo giá mẫu đang bàn trước
    s = history("ambiguous-two")
    offered.clear()
    row = say(s, "Em ơi, chị lấy cái mà hôm trước em tư vấn đó nha", [req("place_order", "chị lấy cái mà hôm trước", target_basis="context")],
              refs={"previous_contact": True}, ambiguity={"level": "needs_clarification"})
    text = row["agent_text"]
    print("ambiguous reply:", text, "| goals", row.get("goals"), flush=True)
    check("ambiguous: no order written", not F.calls(row, "order.create"))
    check("ambiguous: asks which product", "ask_which_product" in (row.get("goals") or []) and "mẫu nào" in text)
    check("ambiguous: lists both real candidates", "Xiaomi" in text and "Philips" in text)
    check("ambiguous: does not claim missing chat history", "chưa thấy nội dung" not in text)
    check("ambiguous: focus price not read before the customer chooses", not F.calls(row, "pricing.get_quote"))

    # 2. khách hoãn sau câu hỏi chọn → không hỏi lặp, không ghi
    row = say(s, "Ơ thôi để chị xem lại tên nó rồi gọi lại em sau nhé",
              withdrawn=[{"kind": "place_order", "evidence": "thôi để chị xem lại"}], response_to_agent={"act": "defer", "evidence": "gọi lại em sau"})
    text = row["agent_text"]
    print("defer reply:", text, "| goals", row.get("goals"), "| hold", s.reqs.hold, flush=True)
    check("defer: no repeated product question", "ask_which_product" not in (row.get("goals") or []) and "mẫu nào" not in text)
    check("defer: no prior-contact question", "ask_prior_contact" not in (row.get("goals") or []))
    check("defer: nothing written", not F.calls(row, "order.create"))

    # 3. hồi quy: lịch sử chỉ một mẫu → giữ hành vi v6 (không đổi sang hỏi chọn)
    s = history("ambiguous-one", skus=("SKU-AF-6L",))
    s.discussed = []
    row = say(s, "Em ơi, chị lấy cái mà hôm trước em tư vấn đó nha", [req("place_order", "chị lấy cái mà hôm trước", target_basis="context")],
              refs={"previous_contact": True}, ambiguity={"level": "needs_clarification"})
    print("one-candidate reply:", row["agent_text"], "| goals", row.get("goals"), flush=True)
    check("single history product keeps v6 hold goal", "ask_which_product" not in (row.get("goals") or []) and not F.calls(row, "order.create"))

    # 4. hồi quy: mơ hồ nhưng không phải đặt mẫu (khách hỏi lại chuyện cũ) → không đổi sang hỏi chọn mẫu
    s = history("ambiguous-not-purchase")
    row = say(s, "Hôm trước em nói gì với chị ấy nhỉ", refs={"previous_contact": True}, ambiguity={"level": "needs_clarification"})
    print("non-purchase reply:", row["agent_text"], "| goals", row.get("goals"), flush=True)
    check("non-purchase ambiguity keeps v6 goal", "ask_which_product" not in (row.get("goals") or []))

    # 5. hồi quy: rút yêu cầu khi CÓ yêu cầu đang chờ vẫn rút đúng
    s = session("withdraw-existing")
    say(s, "Thêm AirPure Mini vào giỏ", [req("add_to_cart", "Thêm AirPure Mini", "P1", target_basis="named")])
    row = say(s, "Thôi chưa đặt nữa em", withdrawn=[{"kind": "place_order", "request_id": "R1", "evidence": "Thôi chưa đặt nữa"}])
    check("pending request still withdrawn exactly", s.reqs.items[0]["status"] == "withdrawn" and not F.calls(row, "order.create"))

print("v6p2 checks:", passed, "PASS", flush=True)
assert not failed, failed
