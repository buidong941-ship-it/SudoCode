"""Kaggle only. v6p4 (số lượng có cấu trúc): CallSession/tool BTC thật, model có kịch bản — không đo chất lượng LLM.
Số lượng do model trả dạng số nguyên + căn cứ nguyên văn; code chỉ kiểm căn cứ / khoảng / gắn dòng (không sửa regex)."""
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
frame_path = ROOT / "tests/b2_round_f_check.py"
F = types.ModuleType("v6p4_frame")
F.__file__ = str(frame_path)
exec(compile(frame_path.read_text(encoding="utf-8").split("# ================================================================== H8")[0],
             str(frame_path), "exec"), F.__dict__)
from harness import jev_write_gate as G
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
    return F.session("v6p4-" + name, decider=planner)


def say(s, text, requests=(), **kw):
    return F.say(s, text, F.resp(intent="place_order" if requests else "greeting_or_other", requests=list(requests), **kw))


def req(kind, evidence, ref=None, **kw):
    return {"kind": kind, "evidence": evidence, "target_ref": ref, **kw}


def qty_lines(row):
    out = {}
    for call in F.calls(row, "order.create"):
        a = call["args"]
        for ln in a.get("lines") or [{"sku": a.get("sku"), "qty": a.get("qty", 1)}]:
            out[ln["sku"]] = out.get(ln["sku"], 0) + (ln.get("qty") or 1)
    return out


def historical(name):
    s = session(name)
    s.brief = {**(s.brief or {}), "products_advised": [{"sku": "SKU-FAN-DC1"}, {"sku": "SKU-FAN-SEN"}]}
    s.focus = "SKU-FAN-DC1"
    return s


def criteria(s, text, item_kw=None, **kw):
    with patch.object(settings, "b2_two_tier", True), patch("harness.planner_b2tt.run", return_value=("delegate", {})):
        return say(s, text, [req("place_order", "lấy cái rẻ hơn", target_basis="criteria", **(item_kw or {}))],
                   consult={"sort": "cheapest", "scope": "discussed"}, **kw)


extra = {"jev_write_gate": True, "b2_two_tier": False, "b2_max_decisions": 20, "b2_max_tool_calls": 25}
with F.Ctx(extra), patch.object(G, "assess", assess):
    # 1. H13-086: "đặt một AirPure Mini" — số nguyên 1 + căn cứ "một" (không có đơn vị đếm) → tạo đơn 1 cái
    s = session("one-word")
    row = say(s, "Chị đặt một AirPure Mini giúp chị nha", [req("place_order", "đặt một AirPure Mini",
        lines=[{"target_ref": "P1", "product_span": "AirPure Mini", "quantity": 1, "quantity_span": "một"}], target_basis="named")])
    print("one-word reply:", row["agent_text"], flush=True)
    check("integer quantity with verbatim span creates the order", qty_lines(row) == {"SKU-AP-MINI": 1})

    # 2. số lượng nói nhưng không đổi được ra số (không có quantity, span ngoài định dạng) → giữ món, hỏi số lượng, không ghi
    s = session("unparsed")
    row = say(s, "Lấy vài cái AirPure Mini cho chị", [req("place_order", "Lấy vài cái AirPure Mini",
        lines=[{"target_ref": "P1", "product_span": "AirPure Mini", "quantity_span": "vài cái"}], target_basis="named")])
    print("unparsed reply:", row["agent_text"], "| goals", row.get("goals"), flush=True)
    r = s.reqs.items[0] if s.reqs.items else {}
    check("unparsed quantity: no order", not F.calls(row, "order.create"))
    check("unparsed quantity: product kept on the request", [ln.get("sku") for ln in r.get("lines") or []] == ["SKU-AP-MINI"]
          and r.get("missing") == "quantity")
    check("unparsed quantity: asks quantity, not which product", "ask_quantity" in (row.get("goals") or [])
          and "ask_which_product" not in (row.get("goals") or []) and "số lượng" in row["agent_text"])

    # 3. số nguyên không có căn cứ nguyên văn → không dùng
    s = session("unverified")
    row = say(s, "Lấy AirPure Mini cho chị", [req("place_order", "Lấy AirPure Mini",
        lines=[{"target_ref": "P1", "product_span": "AirPure Mini", "quantity": 5, "quantity_span": "năm cái"}], target_basis="named")])
    check("quantity without verbatim evidence: no order of 5", not F.calls(row, "order.create")
          and "ask_quantity" in (row.get("goals") or []))

    # 3b. H13-029/030 (v6p4b): model tự điền quantity nhưng khách không nói số lượng (không có căn cứ) → không chặn, mặc định 1
    s = session("quantity-no-span")
    row = say(s, "Lấy AirPure Mini, thanh toán COD em nhé", [req("place_order", "Lấy AirPure Mini",
        lines=[{"target_ref": "P1", "product_span": "AirPure Mini", "quantity": 1}], target_basis="named")])
    check("quantity without evidence is ignored, order created with default 1", qty_lines(row) == {"SKU-AP-MINI": 1}
          and "ask_quantity" not in (row.get("goals") or []))
    s = session("quantity-no-span-2")
    row = say(s, "Lấy AirPure Mini cho chị", [req("place_order", "Lấy AirPure Mini",
        lines=[{"target_ref": "P1", "product_span": "AirPure Mini", "quantity": 3}], target_basis="named")])
    check("unevidenced quantity 3 is not used", qty_lines(row) == {"SKU-AP-MINI": 1})

    # 4. H13-046: chọn theo tiêu chí + observation qty tự do "hai cái" (đếm hai mẫu) → đơn MỘT mẫu rẻ hơn
    s = historical("selection-free-qty")
    row = criteria(s, "Trong hai cái máy bữa trước lấy cái rẻ hơn", observations=[
        {"slot": "qty", "span": "hai cái", "stance": "chosen", "subject": "self"}])
    print("selection free qty:", qty_lines(row), flush=True)
    check("selection ignores free turn quantity", qty_lines(row) == {"SKU-FAN-SEN": 1})

    # 5. chọn theo tiêu chí có số lượng gắn vào chính yêu cầu → dùng số đó
    s = historical("selection-line-qty")
    row = criteria(s, "Trong hai mẫu bữa trước, lấy cái rẻ hơn, lấy cho chị 2 cái nha", item_kw={"quantity": 2, "quantity_span": "2 cái"})
    print("selection line qty:", qty_lines(row), "| reply", row["agent_text"], flush=True)
    import json as _j
    print("  debug items", _j.dumps([{k: x.get(k) for k in ("id", "status", "missing", "lines", "selection", "target")} for x in s.reqs.items],
                                    ensure_ascii=False, default=str), flush=True)
    print("  debug events", _j.dumps(s.reqs.events, ensure_ascii=False, default=str)[:1500], flush=True)
    print("  debug planner", _j.dumps(((row.get("planner") or {}).get("loop") or {}).get("steps"), ensure_ascii=False, default=str)[:1500], flush=True)
    print("  debug understanding", _j.dumps((row.get("understanding") or {}).get("dropped"), ensure_ascii=False, default=str), flush=True)
    check("selection uses quantity bound to the request", qty_lines(row) == {"SKU-FAN-SEN": 2})

    # 6. hồi quy: nhiều dòng, số nguyên từng dòng
    s = session("multi-line")
    row = say(s, "Lấy 2 cái AirPure Mini và 1 cái Senko TS16", [req("place_order", "Lấy 2 cái AirPure Mini và 1 cái Senko TS16",
        lines=[{"target_ref": "P1", "quantity": 2, "quantity_span": "2 cái"}, {"target_ref": "P2", "quantity": 1, "quantity_span": "1 cái"}],
        target_basis="named")])
    check("per-line integer quantities", qty_lines(row) == {"SKU-AP-MINI": 2, "SKU-FAN-SEN": 1})

print("v6p4 checks:", passed, "PASS", flush=True)
assert not failed, failed
