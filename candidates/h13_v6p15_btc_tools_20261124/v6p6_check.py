"""Kaggle only. v6p6 (bước A: giữ đối tượng khi tiếp tục, ranh giới địa chỉ/thanh toán theo vị trí span, giỏ nháp luôn tra kho):
CallSession/tool BTC thật, model có kịch bản — không đo chất lượng LLM."""
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
frame_path = ROOT / "tests/b2_round_f_check.py"
F = types.ModuleType("v6p6_frame")
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


mode = {"commit": True}


def planner(state, opts):
    steps = opts["step"]
    if not mode["commit"]:
        steps = [x for x in steps if not x.startswith("commit_request:R")]
        for x in ("clarify", "finish"):
            found = next((y for y in steps if y.startswith(x)), None)
            if found:
                return {"step": found}
        return {"step": steps[0]}
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
    return F.session("v6p6-" + name, decider=planner)


def say(s, text, requests=(), **kw):
    return F.say(s, text, F.resp(intent="place_order" if requests else "greeting_or_other", requests=list(requests), **kw))


def req(kind, evidence, ref=None, **kw):
    return {"kind": kind, "evidence": evidence, "target_ref": ref, **kw}


def refs(s):
    s.reqs.context(s)
    return {tuple(v["skus"])[0]: k for k, v in s.reqs.refmap.items() if k.startswith("P") and v.get("type") == "product"}


def created(row):
    return [ln["sku"] for c in F.calls(row, "order.create") for ln in (c["args"].get("lines") or [{"sku": c["args"].get("sku")}])]


extra = {"jev_write_gate": True, "b2_two_tier": False, "b2_max_decisions": 20, "b2_max_tool_calls": 25}
with F.Ctx(extra), patch.object(G, "assess", assess):
    # ---- A1: H13-025 ba bước — giỏ hai món, bỏ một món giữ một món (chưa tạo đơn), lượt sau chỉ bổ sung thanh toán
    s = session("a1-three-steps")
    say(s, "Thêm AirPure Mini và Philips 6.2L vào giỏ", [req("add_to_cart", "Thêm AirPure Mini và Philips 6.2L",
        lines=[{"target_ref": "P1"}, {"target_ref": "P2"}], target_basis="named")])
    s.turn_mentioned = ["SKU-AP-MINI"]
    r = refs(s)
    mode["commit"] = False
    say(s, "Bỏ AirPure Mini ra nhé em", [req("edit_cart", "Bỏ AirPure Mini ra", r["SKU-AP-MINI"], operation="remove", request_id="R1")])
    mode["commit"] = True
    r1 = next(x for x in s.reqs.items if x["id"] == "R1")
    print("a1 after step 2:", r1.get("status"), r1.get("missing"), r1.get("target"), flush=True)
    s.turn_mentioned = []
    r = refs(s)
    row = say(s, "Nhận hàng anh trả tiền em nhé", [req("place_order", "Nhận hàng anh trả tiền", r.get("SKU-AF-6L"),
        target_basis="named", request_id="R1")])
    print("a1 step 3 reply:", row["agent_text"], "| goals", row.get("goals"), flush=True)
    check("A1: continuation keeps resolved target, order only the kept item", created(row) == ["SKU-AF-6L"])
    check("A1: no product question on payment-only turn", not {"ask_which_product", "ask_product"} & set(row.get("goals") or []))
    check("A1: step-2 target is the kept item", [x for x in r1.get("lines") or []] and all(x["sku"] == "SKU-AF-6L" for x in r1["lines"]))

    # ---- A1 âm: yêu cầu còn mơ hồ (chưa có đối tượng) → lượt bổ sung không tự chọn món
    s = session("a1-ambiguous")
    s.brief = {**(s.brief or {}), "products_advised": [{"sku": "SKU-AF-XM"}, {"sku": "SKU-AF-6L"}]}
    s.focus = "SKU-AF-6L"
    mode["commit"] = False
    say(s, "Chị lấy cái hôm trước em tư vấn nha", [req("place_order", "Chị lấy cái hôm trước", target_basis="context")])
    mode["commit"] = True
    r = refs(s)
    s.turn_mentioned = []
    row = say(s, "Nhận hàng chị trả tiền nhé", [req("place_order", "Nhận hàng chị trả tiền", r.get("SKU-AF-6L"),
        target_basis="named", request_id="R1")])
    print("a1 ambiguous reply:", row["agent_text"], "| goals", row.get("goals"), flush=True)
    check("A1: ambiguous request stays ambiguous, no order", not F.calls(row, "order.create"))

    # ---- A2: tiếp tục đơn vừa tạo, span thanh toán giao một phần với span địa chỉ → cắt tại điểm bắt đầu span thanh toán
    def order_without_address(name):
        s = session(name)
        say(s, "Lấy AirPure Mini cho chị", [req("place_order", "Lấy AirPure Mini", "P1", target_basis="named")])
        s.orders_created[0]["address"] = None
        s.turn_mentioned = ["SKU-AP-MINI"]
        return s, refs(s)

    text = "Gửi AirPure Mini về 12 Lê Lợi, Quận 1, TP HCM, nhận hàng chị trả tiền mặt."
    s, r = order_without_address("a2-partial")
    row = say(s, text, [req("place_order", "Gửi AirPure Mini", r["SKU-AP-MINI"], target_basis="context")], observations=[
        {"slot": "address", "span": "12 Lê Lợi, Quận 1, TP HCM, nhận hàng", "stance": "stated", "subject": "self"},
        {"slot": "payment", "span": "nhận hàng chị trả tiền mặt", "stance": "chosen", "subject": "self", "label": "COD"}])
    upd = [c["args"].get("reason") or "" for c in F.calls(row, "order.update") if c["args"].get("action") == "update_address"]
    print("a2 partial update:", upd, "| dropped", (s.u_turn.get("meta") or {}).get("dropped"), flush=True)
    check("A2: partial overlap trimmed, clean address written", len(upd) == 1 and "TP HCM" in upd[0] and "nhận hàng" not in upd[0])

    s, r = order_without_address("a2-disjoint")
    row = say(s, text, [req("place_order", "Gửi AirPure Mini", r["SKU-AP-MINI"], target_basis="context")], observations=[
        {"slot": "address", "span": "12 Lê Lợi, Quận 1, TP HCM, nhận hàng", "stance": "stated", "subject": "self"},
        {"slot": "payment", "span": "trả tiền mặt", "stance": "chosen", "subject": "self", "label": "COD"}])
    diag = [d for d in (s.u_turn.get("meta") or {}).get("dropped") or [] if d.get("why") == "span_relation:disjoint"]
    print("a2 disjoint diag:", diag, flush=True)
    check("A2: disjoint spans are logged with the payment span (known limitation, step B)", diag and diag[0].get("payment_span") == "trả tiền mặt")

    s, r = order_without_address("a2-unresolved")
    row = say(s, "Gửi AirPure Mini về 12 Lê Lợi, trả tiền mặt, Quận 1 nhé", [req("place_order", "Gửi AirPure Mini", r["SKU-AP-MINI"],
        target_basis="context")], observations=[
        {"slot": "address", "span": "12 Lê Lợi, trả tiền mặt, Quận 1", "stance": "stated", "subject": "self"},
        {"slot": "payment", "span": "trả tiền mặt", "stance": "chosen", "subject": "self", "label": "COD"}])
    print("a2 unresolved reply:", row["agent_text"], "| goals", row.get("goals"), flush=True)
    check("A2: unresolved boundary → no address write, asks address",
          not [c for c in F.calls(row, "order.update") if c["args"].get("action") == "update_address"] and "ask_address" in (row.get("goals") or []))

    # ---- A3: giỏ nháp đổi sang biến thể hết hàng, bộ hiểu BỎ SÓT lời dặn → vẫn tra kho, báo hết, hỏi, không khôi phục màu cũ
    s = session("a3-missed-branch")
    say(s, "Để Warmly size S màu đen trong giỏ nháp, chưa lên đơn", [req("add_to_cart", "Để Warmly size S màu đen", "P1",
        size_span="size S", color_span="màu đen", target_basis="named")])
    row = say(s, "Chị thích màu be hơn, size S", [req("edit_cart", "thích màu be hơn", "P1", operation="update",
        color_span="màu be", request_id="R1")])
    text = row["agent_text"]
    print("a3 reply:", text, "| goals", row.get("goals"), "| cart", s.cart, flush=True)
    check("A3: new draft variant stock read", any(c["args"].get("sku") == "SKU-JK-DWN-S-BE" for c in F.calls(row, "inventory.check")))
    check("A3: says out of stock and asks, no order", "hết hàng" in text and "ask_draft_alternative" in (row.get("goals") or [])
          and not F.calls(row, "order.create"))
    check("A3: old variant not restored to the draft", "SKU-JK-DWN-S-DEN" not in s.cart
          and [ln.get("sku") for ln in s.reqs.items[0].get("lines") or []] == ["SKU-JK-DWN-S-BE"])
    row = say(s, "Thôi để dịp khác vậy em", response_to_agent={"act": "defer", "evidence": "để dịp khác"})
    check("A3: defer keeps no order", not F.calls(row, "order.create"))

print("v6p6 checks:", passed, "PASS", flush=True)
assert not failed, failed
