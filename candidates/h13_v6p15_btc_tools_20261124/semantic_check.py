"""Kaggle only: actual CallSession/tools with scripted model outputs, not an LLM quality score."""
import copy
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
frame_path = ROOT / "tests/b2_round_f_check.py"
F = types.ModuleType("semantic_frame")
F.__file__ = str(frame_path)
exec(compile(frame_path.read_text(encoding="utf-8").split("# ================================================================== H8")[0],
             str(frame_path), "exec"), F.__dict__)
from harness import jev_write_gate as G, request_updates as R, plan_primitives as P
from harness.request_state import RequestState
from harness.tools import ToolBox
from core.config import settings

passed = 0
failed = []


def check(name, value):
    global passed
    if value:
        passed += 1
        print("PASS", name, flush=True)
    else:
        failed.append(name)
        print("FAIL", name, flush=True)


hold_next = False


def decision(state, opts):
    global hold_next
    action = state["proposed_update"]["action"]
    choice = "reject_or_withdraw" if action == "withdraw" else "open_or_update_request"
    if hold_next:
        choice, hold_next = "hold_and_clarify", False
    return {"decision": choice, "request_id": opts["request_ids"][0],
            "target_ref": opts["target_refs"][0], "revision": opts["revision"]}


real_assess = G.assess


def assess(*args, **kwargs):
    return real_assess(*args, **kwargs, decider=decision)


def planner(state, opts):
    steps = opts["step"]
    for prefix in ("read_condition:",):
        found = next((x for x in steps if x.startswith(prefix)), None)
        if found:
            return {"step": found}
    for req in state.get("open_requests") or []:
        for detail in req.get("readiness", {}).get("detail") or []:
            if detail in steps:
                return {"step": detail}
    for prefix in ("commit_request:", "answer_ask:", "clarify:", "read_quote:", "clarify", "finish"):
        found = next((x for x in steps if x.startswith(prefix)), None)
        if found:
            return {"step": found}
    return {"step": "finish"}


def session(name):
    return F.session("semantic-" + name, decider=planner)


def say(s, text, requests=(), **kw):
    return F.say(s, text, F.resp(intent="place_order" if requests else "greeting_or_other", requests=list(requests), **kw))


def req(kind, evidence, ref=None, **kw):
    return {"kind": kind, "evidence": evidence, "target_ref": ref, **kw}


def written(row):
    return F.calls(row, "order.create")


def skus(row):
    return [line["sku"] for call in written(row) for line in
            (call["args"].get("lines") or [{"sku": call["args"].get("sku")}])]


extra = {"jev_write_gate": True, "b2_two_tier": False, "b2_max_decisions": 20, "b2_max_tool_calls": 25}
with F.Ctx(extra), patch.object(G, "assess", assess):
    s = session("two-lines")
    row = say(s, "Lấy AirPure Mini và Philips 6.2L cho chị", [req("place_order", "Lấy AirPure Mini và Philips 6.2L",
        lines=[{"target_ref": "P1"}, {"target_ref": "P2"}], target_basis="named")])
    check("one order contains both requested products", len(written(row)) == 1 and set(skus(row)) == {"SKU-AP-MINI", "SKU-AF-6L"})
    check("one request retains both lines", len(s.reqs.items) == 1 and len(s.reqs.items[0]["lines"]) == 2)

    for label, phrase in (("remove-no-giu", "Philips thì khỏi, lấy AirPure Mini thôi"),
                          ("remove-paraphrase", "Chị chỉ cần AirPure Mini, Philips không cần nữa")):
        s = session(label)
        row = say(s, "Thêm AirPure Mini và Philips 6.2L vào giỏ", [req("add_to_cart", "Thêm AirPure Mini và Philips 6.2L",
            lines=[{"target_ref": "P1"}, {"target_ref": "P2"}], target_basis="named")])
        check(label + " draft does not create an order", not written(row))
        ctx = s.reqs.context(s)
        refs = {tuple(value["skus"])[0]: ref for ref, value in s.reqs.refmap.items() if ref.startswith("P")}
        row = say(s, phrase, [req("edit_cart", phrase, refs["SKU-AF-6L"], operation="remove", request_id="R1"),
            req("place_order", phrase, refs["SKU-AP-MINI"], target_basis="named", request_id="R1")])
        check(label + " removes only one line", skus(row) == ["SKU-AP-MINI"] and len(s.reqs.items) == 1)

    s = session("quantity-per-line")
    row = say(s, "Lấy 2 cái AirPure Mini và 1 cái Senko TS16", [req("place_order", "Lấy 2 cái AirPure Mini và 1 cái Senko TS16",
        lines=[{"target_ref": "P1", "quantity_span": "2 cái"}, {"target_ref": "P2", "quantity_span": "1 cái"}], target_basis="named")])
    args = written(row)[0]["args"] if written(row) else {}
    counts = {}
    for line in args.get("lines", []):
        counts[line["sku"]] = counts.get(line["sku"], 0) + line["qty"]
    print("quantity payload", args, flush=True)
    check("quantities belong to each line", counts == {"SKU-AP-MINI": 2, "SKU-FAN-SEN": 1})

    s = session("draft-variant")
    row = say(s, "Thêm Warmly size S màu đen vào giỏ", [req("add_to_cart", "Thêm Warmly size S màu đen", "P1",
        size_span="size S", color_span="màu đen", target_basis="named")])
    check("draft variant saved without order", s.cart == ["SKU-JK-DWN-S-DEN"] and not written(row))
    row = say(s, "Đổi sang màu be, nếu còn hàng thì lấy Warmly", [req("edit_cart", "Đổi sang màu be", "P1", operation="update",
        color_span="màu be", request_id="R1"), req("place_order", "thì lấy Warmly", "P1", request_id="R1",
        target_basis="named", condition={"type": "stock", "span": "nếu còn hàng"})])
    check("draft edit retains size and changes color", s.reqs.items[0]["lines"][0]["sku"] == "SKU-JK-DWN-S-BE")
    check("out of stock requested variant never becomes old-color order", not written(row))
    check("draft edit does not call order update", not F.calls(row, "order.update"))

    s = session("draft-unavailable-withdraw")
    row = say(s, "Lấy Warmly size S màu be, hết hàng thì thôi chưa đặt", [req("place_order", "Lấy Warmly size S màu be", "P1",
        target_basis="named", size_span="size S", color_span="màu be",
        condition={"type": "stock", "span": "hết hàng"},
        on_unavailable={"action": "cancel", "evidence": "thì thôi chưa đặt"})])
    check("unavailable draft follows explicit withdrawal branch", not written(row) and s.reqs.items[0]["status"] == "withdrawn")
    check("draft withdrawal never becomes real-order cancellation", not F.calls(row, "handoff.transfer"))

    s = session("attribute-held")
    hold_next = True
    row = say(s, "AirPure Y có khóa trẻ em thì lấy cho chị", [req("place_order", "thì lấy cho chị", "P1", target_basis="named",
        condition={"type": "attribute", "attribute": "child_safe_lock", "expected": True, "span": "có khóa trẻ em"})])
    check("held cannot write", not written(row) and s.reqs.items[0]["status"] == "held")
    row = say(s, "Giao về 12 Lê Lợi, Quận 1, TP HCM, COD", observations=[
        {"slot": "address", "span": "12 Lê Lợi, Quận 1, TP HCM", "stance": "stated", "subject": "self"},
        {"slot": "payment", "span": "COD", "stance": "chosen", "subject": "self", "label": "COD"}])
    check("address continuation retains condition and same ID", len(s.reqs.items) == 1 and s.reqs.items[0]["condition"]["type"] == "attribute")
    check("held request resumes through actual attribute read", any(x["name"] == "catalog.search" for x in row["tool_calls"]) and skus(row) == ["SKU-AP-Y"])

    s = session("ambiguous-reference")
    s.brief = {**(s.brief or {}), "products_advised": [{"sku": "SKU-AF-XM"}, {"sku": "SKU-AF-6L"}]}
    s.focus = "SKU-AF-6L"
    row = say(s, "Chị lấy cái mà hôm trước em tư vấn đó nha", [req("place_order", "Chị lấy cái mà hôm trước", "P1", target_basis="context")],
              refs={"previous_contact": True})
    check("vague history cannot become focus consent", not written(row) and s.reqs.items[0]["status"] == "held")
    check("both historic candidates reach understanding", len([x for x in s.reqs.refmap if x.startswith("P")]) == 2)

    s = session("historical-cheapest")
    s.brief = {**(s.brief or {}), "products_advised": [{"sku": "SKU-FAN-DC1"}, {"sku": "SKU-FAN-SEN"}]}
    s.focus = "SKU-FAN-DC1"
    with patch.object(settings, "b2_two_tier", True), patch("harness.planner_b2tt.run", return_value=("delegate", {})):
        row = say(s, "Trong hai mẫu hôm trước lấy cái rẻ hơn", [req("place_order", "lấy cái rẻ hơn", target_basis="criteria")],
                  consult={"sort": "cheapest", "scope": "discussed"})
        selection = s.reqs.selection_criteria(s, {"consult": {"sort": "cheapest", "scope": "discussed"}})
    check("comparison recovers both historical SKUs", set(selection["skus"]) == {"SKU-FAN-DC1", "SKU-FAN-SEN"})
    check("cheapest is chosen by actual fresh tool prices", skus(row) == ["SKU-FAN-SEN"])

    s = session("stale-version")
    s.turn_mentioned = ["SKU-AP-MINI"]
    s.turn_text = "Lấy AirPure Mini cho chị"
    s.reqs.context(s)
    u = {"request_items": [req("place_order", s.turn_text, "P1", target_basis="named")], "response": {}, "slots": {}, "ambiguity": {}}
    u, norm = G.normalize(s, u, s.reqs)
    gate = real_assess(s, u, s.reqs, s.turn_no, decider=decision)
    s.reqs.proposal = {"kind": "place_order", "target": None, "goal": "confirm_order"}
    s.reqs.ingest(s, u, s.turn_no, gate=gate, normalization=norm)
    check("stale state cannot apply any transaction", s.reqs.hold == "jev_request_revision" and not s.reqs.items)

    s = session("staged-payload-tamper")
    s.turn_mentioned = ["SKU-AP-MINI"]
    s.turn_text = "Lấy AirPure Mini cho chị"
    s.reqs.context(s)
    u = {"request_items": [req("place_order", s.turn_text, "P1", target_basis="named")], "response": {}, "slots": {}, "ambiguity": {}}
    u, norm = G.normalize(s, u, s.reqs)
    gate = real_assess(s, u, s.reqs, s.turn_no, decider=decision)
    u["updates"][0]["lines"][0]["qty"] = 5
    s.reqs.ingest(s, u, s.turn_no, gate=gate, normalization=norm)
    check("staged quantity cannot change after decision", s.reqs.hold == "jev_request_revision" and not s.reqs.items)

    s = session("payload-tamper")
    s.turn_mentioned = ["SKU-AP-MINI"]
    s.turn_text = "Lấy AirPure Mini cho chị"
    s.reqs.context(s)
    u = {"request_items": [req("place_order", s.turn_text, "P1", target_basis="named")], "response": {}, "slots": {}, "ambiguity": {}}
    u, norm = G.normalize(s, u, s.reqs)
    gate = real_assess(s, u, s.reqs, s.turn_no, decider=decision)
    s.reqs.ingest(s, u, s.turn_no, gate=gate, normalization=norm)
    r = s.reqs.items[0]
    r["lines"][0]["qty"] = 3
    check("payload edit invalidates old write permission", s.reqs.authorize("place_order", r["target"], req_id=r["id"])[1] == "semantic_payload_changed")

    s = session("cancel-brief")
    s.handoff_task = {"action": "cancel", "order_id": "OD600001", "evidence": "hủy đơn này"}
    brief = s._handoff_brief("Hủy đơn này giúp chị", "khac")
    check("cancel brief follows cancellation goal", "hủy đơn" in brief["next_action"] and "chốt" not in brief["next_action"])

    for attr, expected, label in (("child_safe_lock", False, "opposite-attribute"),
                                   ("attribute_not_in_catalog", True, "unknown-attribute")):
        s = session(label)
        row = say(s, "AirPure Y có tính năng này thì lấy cho chị", [req("place_order", "thì lấy cho chị", "P1",
            target_basis="named", condition={"type": "attribute", "attribute": attr, "expected": expected,
                                              "span": "có tính năng này"})])
        check(label + " cannot create order", not written(row))

    s = session("withdraw-whole")
    say(s, "Thêm AirPure Mini vào giỏ", [req("add_to_cart", "Thêm AirPure Mini", "P1", target_basis="named")])
    row = say(s, "Thôi chưa đặt nữa em", withdrawn=[{"kind": "place_order", "request_id": "R1", "evidence": "Thôi chưa đặt nữa"}])
    check("explicit whole withdrawal closes exact request", s.reqs.items[0]["status"] == "withdrawn" and not written(row))
    row = say(s, "Giao về 12 Lê Lợi, Quận 1, TP HCM", observations=[
        {"slot": "address", "span": "12 Lê Lợi, Quận 1, TP HCM", "stance": "stated", "subject": "self"}])
    check("address cannot resurrect withdrawn purchase", not written(row) and s.reqs.items[0]["status"] == "withdrawn")

    s = session("accept-with-address")
    s.reqs.proposal = {"kind": "place_order", "goal": "confirm_order", "target": {"type": "product", "skus": ("SKU-AP-MINI",)},
                       "revision": {"units": [["SKU-AP-MINI", 2190000]], "qty": 1}}
    row = say(s, "Đồng ý, giao về 12 Lê Lợi, Quận 1, TP HCM", response_to_agent={"act": "accept", "evidence": "Đồng ý, giao về 12 Lê Lợi"},
              observations=[{"slot": "address", "span": "12 Lê Lợi, Quận 1, TP HCM", "stance": "stated", "subject": "self"}])
    if not written(row):
        print("consent debug", row.get("request_state"), row.get("understanding"), row.get("planner"), flush=True)
    check("consent with street number is not rejected as impure", skus(row) == ["SKU-AP-MINI"])

    s = session("exchange-existing-order")
    row = say(s, "Lấy Warmly size S màu navy cho chị", [req("place_order", "Lấy Warmly size S màu navy", "P1",
        size_span="size S", color_span="màu navy", target_basis="named")])
    check("existing-order setup creates correct variant", skus(row) == ["SKU-JK-DWN-S-NAVY"])
    row = say(s, "Đổi sang size M màu be giúp chị", [req("exchange", "Đổi sang size M màu be", "O1")], observations=[
        {"slot": "size", "span": "size M", "stance": "chosen", "subject": "self"},
        {"slot": "color", "span": "màu be", "stance": "chosen", "subject": "self"}])
    check("existing-order exchange updates instead of creating", not written(row) and any(
        call["args"].get("new_variant_sku") == "SKU-JK-DWN-M-BE" for call in F.calls(row, "order.update")))

    s = session("independent-actions")
    row = say(s, "Lấy AirPure Mini, mai 9 giờ gọi lại cho chị", [req("place_order", "Lấy AirPure Mini", "P1", target_basis="named"),
        req("callback", "mai 9 giờ gọi lại cho chị")], observations=[
        {"slot": "callback_requested", "span": "mai 9 giờ", "stance": "stated", "subject": "self"}])
    check("independent actions retain separate IDs", len(s.reqs.items) == 2 and {r["kind"] for r in s.reqs.items} == {"place_order", "callback"})
    check("independent purchase and callback both execute", len(written(row)) == 1 and len(F.calls(row, "schedule.callback")) == 1)

    s = session("separate-orders")
    row = say(s, "Lấy AirPure Mini một đơn riêng, Senko TS16 một đơn riêng", [
        req("place_order", "Lấy AirPure Mini một đơn riêng", "P1", target_basis="named", order_group="first", new_request=True),
        req("place_order", "Senko TS16 một đơn riêng", "P2", target_basis="named", order_group="second", new_request=True)])
    check("separate orders are not silently merged", len(written(row)) == 2 and len(s.reqs.items) == 2)

print("semantic checks:", passed, "PASS", flush=True)
assert not failed, failed
