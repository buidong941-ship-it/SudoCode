"""Kaggle only. v6p3 (sửa món của đơn vừa tạo → chuyển nhân viên): CallSession/tool BTC thật, model có kịch bản."""
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
frame_path = ROOT / "tests/b2_round_f_check.py"
F = types.ModuleType("v6p3_frame")
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
    return F.session("v6p3-" + name, decider=planner)


def say(s, text, requests=(), **kw):
    return F.say(s, text, F.resp(intent="place_order" if requests else "greeting_or_other", requests=list(requests), **kw))


def req(kind, evidence, ref=None, **kw):
    return {"kind": kind, "evidence": evidence, "target_ref": ref, **kw}


def refs(s):
    s.reqs.context(s)
    return {tuple(v["skus"])[0]: k for k, v in s.reqs.refmap.items() if k.startswith("P") and v.get("type") == "product"}


def two_line_order(name):
    s = session(name)
    row = say(s, "Lấy AirPure Mini và Philips 6.2L cho chị", [req("place_order", "Lấy AirPure Mini và Philips 6.2L",
        lines=[{"target_ref": "P1"}, {"target_ref": "P2"}], target_basis="named")])
    return s, row


extra = {"jev_write_gate": True, "b2_two_tier": False, "b2_max_decisions": 20, "b2_max_tool_calls": 25}
with F.Ctx(extra), patch.object(G, "assess", assess):
    # 1. bỏ một món của đơn vừa tạo → chuyển nhân viên đúng đơn, không đơn mới, không xin nói lại
    s, row = two_line_order("amend-remove")
    check("setup: one two-line order", len(F.calls(row, "order.create")) == 1 and len(s.orders_created) == 1)
    oid = s.orders_created[0]["order_id"]
    s.turn_mentioned = ["SKU-AF-6L"]
    r = refs(s)
    row = say(s, "À khoan, bỏ Philips ra giùm chị nhé",
              [req("edit_cart", "bỏ Philips ra giùm chị", r["SKU-AF-6L"], operation="remove")])
    text = row["agent_text"]
    print("amend reply:", text, "| goals", row.get("goals"), "| amend", s.amend_created, flush=True)
    check("amend: exactly the removed line and the kept line",
          (s.amend_created or {}).get("products") == ["SKU-AF-6L"] and (s.amend_created or {}).get("keep") == ["SKU-AP-MINI"])
    check("amend: reply names removed and kept products correctly", text.find("Philips") < text.find("giữ") < text.find("AirPure Mini"))
    ho = F.calls(row, "handoff.transfer")
    check("amend: no new order", not F.calls(row, "order.create"))
    check("amend: one handoff ticket", len(ho) == 1)
    brief = (ho[0]["args"].get("brief") or {}) if ho else {}
    check("amend: brief names the order and the line change", oid in str(brief.get("next_action")) and "SKU-AF-6L" in str(brief.get("next_action")))
    check("amend: reply says transferred and order not changed", "amend_handoff" in (row.get("goals") or []) and "chưa thay đổi" in text)
    check("amend: no 'please repeat' reply", "nói lại" not in text)
    check("amend: no new held purchase request", not any(x["kind"] == "place_order" and x["status"] in ("held", "open", "needs_target")
                                                        for x in s.reqs.items))

    # 2. khách nhắc lại yêu cầu → không tạo ticket thứ hai
    r = refs(s)
    row = say(s, "Bỏ Philips giúp chị nhé em", [req("edit_cart", "Bỏ Philips", r["SKU-AF-6L"], operation="remove")])
    tickets = [t for t in F.calls(row, "handoff.transfer")]
    print("repeat reply:", row["agent_text"], flush=True)
    check("repeat amend: no second ticket", not tickets and not F.calls(row, "order.create"))

    # 3. sửa món KHÔNG thuộc đơn vừa tạo → không áp đường sửa đơn
    s, row = two_line_order("amend-other-product")
    s.turn_mentioned = ["SKU-FAN-SEN"]
    r = refs(s)
    row = say(s, "Bỏ Senko TS16 ra nha", [req("edit_cart", "Bỏ Senko TS16", r.get("SKU-FAN-SEN"), operation="remove")])
    check("other product: no amendment handoff", "amend_handoff" not in (row.get("goals") or []) and not F.calls(row, "order.create"))

    # 4. giỏ nháp chưa tạo đơn → giữ đường sửa giỏ của v6 (không chuyển nhân viên)
    s = session("draft-remove")
    say(s, "Thêm AirPure Mini và Philips 6.2L vào giỏ", [req("add_to_cart", "Thêm AirPure Mini và Philips 6.2L",
        lines=[{"target_ref": "P1"}, {"target_ref": "P2"}], target_basis="named")])
    r = refs(s)
    row = say(s, "Philips thì khỏi, lấy AirPure Mini thôi", [req("edit_cart", "Philips thì khỏi", r["SKU-AF-6L"], operation="remove", request_id="R1"),
        req("place_order", "lấy AirPure Mini thôi", r["SKU-AP-MINI"], target_basis="named", request_id="R1")])
    created = [ln["sku"] for c in F.calls(row, "order.create") for ln in (c["args"].get("lines") or [{"sku": c["args"].get("sku")}])]
    check("draft edit keeps v6 path (order of remaining item, no handoff)", created == ["SKU-AP-MINI"] and not F.calls(row, "handoff.transfer"))

print("v6p3 checks:", passed, "PASS", flush=True)
assert not failed, failed
