"""Kaggle only. v6p1 (chọn theo tiêu chí): CallSession/tool BTC thật, quyết định model có kịch bản — không đo chất lượng LLM.

Bộ quyết định "lười" mô phỏng lỗi H13-045/046 của Jev thật: có bước thực hiện thì thực hiện, có finish thì kết thúc, chỉ đọc thêm
khi không còn lựa chọn nào khác. Trên v6, Jev kiểu này đọc một mẫu rồi kết thúc → không so được giá.
"""
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
frame_path = ROOT / "tests/b2_round_f_check.py"
F = types.ModuleType("v6p1_frame")
F.__file__ = str(frame_path)
exec(compile(frame_path.read_text(encoding="utf-8").split("# ================================================================== H8")[0],
             str(frame_path), "exec"), F.__dict__)
from harness import jev_write_gate as G
from harness import request_state as RSM
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


def decision(state, opts):
    action = state["proposed_update"]["action"]
    choice = "reject_or_withdraw" if action == "withdraw" else "open_or_update_request"
    return {"decision": choice, "request_id": opts["request_ids"][0],
            "target_ref": opts["target_refs"][0], "revision": opts["revision"]}


real_assess = G.assess


def assess(*args, **kwargs):
    return real_assess(*args, **kwargs, decider=decision)


offered = []
removed_seen = []
mode = {"lazy": True}


def lazy_planner(state, opts):
    steps = opts["step"]
    offered.append(list(steps))
    removed_seen.append(dict(opts.get("removed") or {}))
    if not mode["lazy"]:
        # bộ quyết định chuẩn của semantic_check (đọc phần readiness còn thiếu trước) — dùng cho ca hồi quy không có tiêu chí
        for req_ in state.get("open_requests") or []:
            for detail in req_.get("readiness", {}).get("detail") or []:
                if detail in steps:
                    return {"step": detail}
        order = ("commit_request:", "answer_ask:", "clarify:", "read_quote:", "clarify", "finish")
    else:
        order = ("commit_request:", "finish", "read_quote:", "clarify:", "clarify")
    for prefix in order:
        found = next((x for x in steps if x.startswith(prefix)), None)
        if found:
            return {"step": found}
    return {"step": steps[0]}


def session(name):
    return F.session("v6p1-" + name, decider=lazy_planner)


def say(s, text, requests=(), **kw):
    return F.say(s, text, F.resp(intent="place_order" if requests else "greeting_or_other", requests=list(requests), **kw))


def req(kind, evidence, ref=None, **kw):
    return {"kind": kind, "evidence": evidence, "target_ref": ref, **kw}


def skus(row):
    return [line["sku"] for call in F.calls(row, "order.create") for line in
            (call["args"].get("lines") or [{"sku": call["args"].get("sku")}])]


def criteria_turn(s, sort):
    with patch.object(settings, "b2_two_tier", True), patch("harness.planner_b2tt.run", return_value=("delegate", {})):
        return say(s, "Trong hai mẫu hôm trước lấy cái rẻ hơn" if sort == "cheapest" else "Trong hai mẫu hôm trước lấy cái xịn hơn",
                   [req("place_order", "lấy cái rẻ hơn" if sort == "cheapest" else "lấy cái xịn hơn", target_basis="criteria")],
                   consult={"sort": sort, "scope": "discussed"})


def historical(name):
    s = session(name)
    s.brief = {**(s.brief or {}), "products_advised": [{"sku": "SKU-FAN-DC1"}, {"sku": "SKU-FAN-SEN"}]}
    s.focus = "SKU-FAN-DC1"
    return s


extra = {"jev_write_gate": True, "b2_two_tier": False, "b2_max_decisions": 20, "b2_max_tool_calls": 25}
with F.Ctx(extra), patch.object(G, "assess", assess):
    # 1. lười + đủ ứng viên P#: vẫn phải đọc đủ hai giá rồi chọn mẫu rẻ
    s = historical("lazy-cheapest")
    offered.clear()
    row = criteria_turn(s, "cheapest")
    check("lazy planner still compares both prices and orders cheaper", skus(row) == ["SKU-FAN-SEN"])
    check("both compared SKUs quoted in turn", {c["args"].get("sku") for c in F.calls(row, "pricing.get_quote")} >= {"SKU-FAN-SEN", "SKU-FAN-DC1"})
    check("criteria request was not bound to focus before comparison",
          not any(e.get("event") == "bound" for e in s.reqs.events if e.get("id") == s.reqs.items[0]["id"]))

    # 2. tập so sánh có mẫu KHÔNG nằm trong ứng viên P# (tái hiện trace H13-045: Jev chỉ có read_quote:P1)
    with patch.object(RSM, "MAX_PRODUCT_CANDIDATES", 1):
        s = historical("lazy-cheapest-truncated")
        offered.clear()
        row = criteria_turn(s, "cheapest")
    sel = s.reqs.items[0].get("selection") if s.reqs.items else None
    print("truncated selection", sel, "refmap", s.reqs.refmap, flush=True)
    check("truncated: compared set still holds both SKUs", sel and set(sel["skus"]) == {"SKU-FAN-SEN", "SKU-FAN-DC1"})
    check("truncated: read step offered for SKU outside P# list",
          any(x == "read_quote:SKU-FAN-SEN" for steps in offered for x in steps) or "SKU-FAN-SEN" in {v["skus"][0] for v in s.reqs.refmap.values() if v.get("type") == "product"})
    check("truncated: order is the cheaper model", skus(row) == ["SKU-FAN-SEN"])

    # 3. tiêu chí ngược lại: mẫu đắt hơn
    s = historical("lazy-expensive")
    row = criteria_turn(s, "most_expensive")
    check("most_expensive picks higher tool price", skus(row) == ["SKU-FAN-DC1"])

    # 4. tập so sánh chỉ một mẫu → không ghi
    s = session("single-compared")
    s.brief = {**(s.brief or {}), "products_advised": [{"sku": "SKU-FAN-DC1"}]}
    s.focus = "SKU-FAN-DC1"
    s.discussed = ["SKU-FAN-DC1"]
    row = criteria_turn(s, "cheapest")
    check("single-candidate comparison does not write", not skus(row))

    # 5. hồi quy: đơn gọi tên trực tiếp không bị chặn finish / không đổi hành vi
    s = session("named-order")
    offered.clear()
    removed_seen.clear()
    mode["lazy"] = False
    row = say(s, "Lấy AirPure Mini cho chị", [req("place_order", "Lấy AirPure Mini", "P1", target_basis="named")])
    mode["lazy"] = True
    check("named order still created", skus(row) == ["SKU-AP-MINI"])
    check("no selection-based finish removal without selection",
          not any(r.get("finish") == "selection_evidence_pending" for r in removed_seen))

print("v6p1 checks:", passed, "PASS", flush=True)
assert not failed, failed
