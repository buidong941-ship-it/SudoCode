"""Kaggle only. v6p7b: trích lại một lần khi trường quyết định sai kiểu JSON; trace ghi đường dẫn trường + thông tin trích lại."""
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
frame_path = ROOT / "tests/b2_round_f_check.py"
F = types.ModuleType("v6p7b_frame")
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


def turn(s, text, *resps):
    F.QUEUE[:] = list(resps)
    row = s.turn(text)
    s.drain_audits()
    return row


def req(kind, evidence, ref=None, **kw):
    return {"kind": kind, "evidence": evidence, "target_ref": ref, **kw}


SENT = F.resp(intent="greeting_or_other")
good = F.resp(intent="place_order", requests=[req("place_order", "Lấy AirPure Mini", "P1", target_basis="named")])
bad = F.resp(intent="place_order", requests=[req("place_order", "Lấy AirPure Mini", "P1", target_basis="named")], withdrawn="khong")
extra = {"jev_write_gate": True, "b2_two_tier": False, "b2_max_decisions": 20, "b2_max_tool_calls": 25, "understanding_retry": True}
with F.Ctx(extra), patch.object(G, "assess", assess):
    s = F.session("v6p7b-type-retry", decider=planner)
    row = turn(s, "Lấy AirPure Mini cho chị", bad, good, SENT)
    u = row.get("understanding") or {}
    print("  trace understanding:", {k: u.get(k) for k in ("dropped", "type_hold", "retry", "ambiguity")}, flush=True)
    check("type-invalid decision field → exactly one retry", u.get("retry") and len(F.QUEUE) == 1)
    check("retried output used → order created", bool(F.calls(row, "order.create")))
    check("trace keeps retry reasons with field path", "withdrawn" in " ".join(u["retry"]["reasons"]) if u.get("retry") else False)

    s = F.session("v6p7b-type-still", decider=planner)
    row = turn(s, "Lấy AirPure Mini cho chị", bad, bad, SENT)
    u = row.get("understanding") or {}
    print("  still:", {k: u.get(k) for k in ("dropped", "type_hold", "retry")}, flush=True)
    check("still invalid after retry → held, no order, no third call", not F.calls(row, "order.create") and len(F.QUEUE) == 1)
    check("trace exports the invalid field path", any(d.get("field") for d in u.get("dropped") or []) and u.get("type_hold"))

print("v6p7b checks:", passed, "PASS", flush=True)
assert not failed, failed
