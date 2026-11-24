"""Kaggle only. v6p9: (1) điều kiện thuộc tính không đạt → câu từ kết quả đã xác minh (khóa + giá trị catalog), không chép span
lời khách (H13-056); (2) lời tiếp tục yêu cầu đang mở: size / màu / tên món không nguyên văn bị bỏ riêng trường, giữ trạng thái đã
lưu (H13-029); (3) đổi biến thể một dòng trên đơn nhiều món: chọn đúng một dòng + tra biến thể từ catalog (H13-037)."""
import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
frame_path = ROOT / "tests/b2_round_f_check.py"
F = types.ModuleType("v6p9_frame")
F.__file__ = str(frame_path)
exec(compile(frame_path.read_text(encoding="utf-8").split("# ================================================================== H8")[0],
             str(frame_path), "exec"), F.__dict__)
from harness import jev_write_gate as G
from harness import understanding as U
from core import pii
from core.llm import generator as GEN

passed, failed = 0, []


def check(name, value):
    global passed
    if value:
        passed += 1
        print("PASS", name, flush=True)
    else:
        failed.append(name)
        print("FAIL", name, flush=True)


# ------------------------------------------------------------------ (2) đơn vị: tiếp tục vs yêu cầu mới
def accept(req_id, new_request=None, text="Thanh toán COD em nhé"):
    it = {"kind": "place_order", "evidence": "Thanh toán COD", "target_ref": "P1", "request_id": req_id,
          "lines": [{"target_ref": "P1", "product_span": "Warmly", "size_span": "L", "color_span": "be"}]}
    if new_request is not None:
        it["new_request"] = new_request
    meta = {"dropped": []}
    out = U._accept_requests({"requests": [it]}, text, pii.Redactor(), {"P1"}, meta, {"R1"})
    return out[0], meta


o, m = accept("R1")
print("  continuation:", o.get("target_invalid"), o.get("lines"), m["dropped"], flush=True)
check("029 unit: continuation of open R1 → copied size/colour/name dropped, target kept valid",
      o["target_invalid"] is False and not o["lines"][0].get("size") and not o["lines"][0].get("color")
      and any(d.get("why") == "continuation_unverified_kept_state" for d in m["dropped"]))
o, _ = accept(None)
check("029 unit: new request with unverbatim size still invalid", o["target_invalid"] is True)
o, _ = accept("R9")
check("029 unit: request id not open → still invalid", o["target_invalid"] is True)
o, _ = accept("R1", new_request=True)
check("029 unit: marked new request → still invalid", o["target_invalid"] is True)

# ------------------------------------------------------------------ (1) đơn vị: câu báo điều kiện
txt = GEN.render_offline({"goals": ["condition_attribute_unmet"], "facts": {"condition": {
    "type": "attribute", "attribute": "child_safe_lock", "expected": True, "actual": False, "product": "Máy X"}}})
print("  unmet text:", txt, flush=True)
check("056 unit: label from catalog phrase, not customer span", "không có khóa an toàn trẻ em" in txt and "Máy X" in txt)
txt = GEN.render_offline({"goals": ["condition_attribute_unmet"], "facts": {"condition": {
    "type": "attribute", "attribute": "unknown_key_x", "expected": True, "actual": False, "product": "Máy X"}}})
check("056 unit: key without phrase → safe sentence, no technical key", "unknown_key_x" not in txt and "chưa lên đơn" in txt)


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


def created(row):
    return [ln["sku"] for c in F.calls(row, "order.create") for ln in (c["args"].get("lines") or [{"sku": c["args"].get("sku")}])]


def pref(s):
    s.reqs.context(s)
    return next(k for k, v in s.reqs.refmap.items() if k.startswith("P") and v.get("type") == "product")


extra = {"jev_write_gate": True, "b2_two_tier": False, "b2_max_decisions": 20, "b2_max_tool_calls": 25}
with F.Ctx(extra), patch.object(G, "assess", assess):
    # ---- (1) agent: span điều kiện bị model chọn lệch ("thì lên đơn luôn nha") → câu vẫn nêu đúng thuộc tính theo catalog
    s = F.session("v6p9-attr", decider=planner)
    row = say(s, "Xiaomi Smart 4 Lite có khóa trẻ em thì lên đơn luôn nha", [req("place_order", "lên đơn luôn nha", "P1",
              target_basis="named", condition={"type": "attribute", "attribute": "child_safe_lock", "expected": True,
                                               "span": "thì lên đơn luôn nha"})])
    print("  attr reply:", row["agent_text"], "| goals", row.get("goals"), flush=True)
    check("056: unmet attribute blocks the order", not created(row))
    check("056: reply states the catalog attribute, not the mis-picked span",
          "condition_attribute_unmet" in (row.get("goals") or []) and "khóa an toàn trẻ em" in row["agent_text"]
          and "thì lên đơn luôn nha" not in row["agent_text"])

    # ---- (2) agent: giỏ nháp L be, lượt chỉ nói COD, model chép size/màu/tên → giữ L be, không kẹt đối tượng
    s = F.session("v6p9-draft-cod", decider=planner)
    say(s, "Để Warmly size L màu xanh navy vào giỏ nháp trước nhé, chưa lên đơn", [req("add_to_cart", "vào giỏ nháp trước", "P1",
        target_basis="named", lines=[{"target_ref": "P1", "product_span": "Warmly", "size_span": "size L", "color_span": "màu xanh navy"}])])
    p = pref(s)
    say(s, "À khoan, lấy màu be thôi, size vẫn L", [req("edit_cart", "lấy màu be thôi", p, operation="update", request_id="R1",
        target_basis="context", lines=[{"target_ref": p, "size_span": "size vẫn L", "color_span": "màu be"}])])
    p = pref(s)
    row = say(s, "Thanh toán COD em nhé", [req("place_order", "Thanh toán COD em nhé", p, request_id="R1", target_basis="context",
              new_request=False, lines=[{"target_ref": p, "product_span": "Warmly", "size_span": "L", "color_span": "be"}])],
              observations=[{"slot": "payment", "span": "COD", "stance": "chosen", "subject": "self", "label": "COD"}])
    items = (s.u_turn or {}).get("request_items") or []
    lines = [ln.get("sku") for ln in (s.reqs.items[0].get("lines") or [])] if s.reqs.items else []
    print("  draft COD:", [(i.get("target_invalid"), i.get("lines")) for i in items], "| req lines", lines, "| created", created(row),
          "| reply", row["agent_text"], flush=True)
    check("029: continuation turn keeps target valid", items and items[0].get("target_invalid") is False)
    check("029: stored variant kept (L be), never navy", lines == ["SKU-JK-DWN-L-BE"]
          and all(x == "SKU-JK-DWN-L-BE" for x in created(row)))
    check("029: no target_unresolved hold", s.reqs.items[0].get("missing") != "target_unresolved")

    # ---- (3) agent: đổi size/màu "cái áo" trên đơn máy lọc + áo → order.update_line đúng dòng
    os.environ["ORDER_EXT_TOOLS"] = "1"
    s = F.session("v6p9-line-variant", decider=planner)
    row = say(s, "Lấy AirPure Mini và Warmly size S màu navy", [req("place_order", "Lấy AirPure Mini và Warmly size S màu navy",
              lines=[{"target_ref": "P1", "product_span": "AirPure Mini"},
                     {"target_ref": "P2", "product_span": "Warmly", "size_span": "size S", "color_span": "màu navy"}], target_basis="named")])
    check("037 setup: two-line order", len(created(row)) == 2)
    row = turn(s, "Đổi cái áo sang size M màu be giùm chị, size S bỏ đi", F.resp(intent="exchange", requests=[req("exchange",
               "Đổi cái áo sang size M màu be", "O1", lines=[{"target_ref": "O1", "product_span": "cái áo", "size_span": "size M",
                                                              "color_span": "màu be"}])]), SENTINEL)
    print("  line_change:", [i.get("line_change") for i in (s.u_turn or {}).get("request_items") or []], flush=True)
    upd = F.calls(row, "order.update_line")
    print("  line variant:", [u["args"] for u in upd], "| goals", row.get("goals"), "| reply", row["agent_text"], flush=True)
    check("037: update_line change_variant on the jacket line → M be",
          len(upd) == 1 and upd[0]["args"].get("sku") == "SKU-JK-DWN-S-NAVY" and upd[0]["args"].get("new_variant_sku") == "SKU-JK-DWN-M-BE")
    check("037: amend_done, no handoff", "amend_done" in (row.get("goals") or []) and not F.calls(row, "handoff.transfer"))
    st = s.tools.call("order.status", order_id=s.orders_created[0]["order_id"]) if s.orders_created else {}
    so = (st.get("orders") or [st])[0] if isinstance(st, dict) else {}
    check("037: order.status re-read shows new line set", sorted(x["sku"] for x in so.get("lines") or []) == ["SKU-AP-MINI", "SKU-JK-DWN-M-BE"])

    # ---- (3b) hai áo cùng đổi được sang size L → không đoán dòng, giữ chuyển nhân viên
    s = F.session("v6p9-two-jackets", decider=planner)
    row = say(s, "Lấy Warmly size S màu navy và Windbreak size M màu be", [req("place_order",
              "Lấy Warmly size S màu navy và Windbreak size M màu be", lines=[
                  {"target_ref": "P1", "product_span": "Warmly", "size_span": "size S", "color_span": "màu navy"},
                  {"target_ref": "P2", "product_span": "Windbreak", "size_span": "size M", "color_span": "màu be"}], target_basis="named")])
    print("  two jackets created:", created(row), flush=True)
    row = turn(s, "Đổi cái áo sang size L giùm chị", F.resp(intent="exchange", requests=[req("exchange", "Đổi cái áo sang size L",
               "O1", lines=[{"target_ref": "O1", "product_span": "cái áo", "size_span": "size L"}])]), SENTINEL)
    print("  two jackets reply:", row["agent_text"], "| goals", row.get("goals"), flush=True)
    check("037b: two candidate lines → no update_line (no guessing)", len(created(row)) == 0 and not F.calls(row, "order.update_line"))
    check("037b: falls back to handoff", bool(F.calls(row, "handoff.transfer")))
    os.environ["ORDER_EXT_TOOLS"] = "0"

print("v6p9 checks:", passed, "PASS", flush=True)
assert not failed, failed
