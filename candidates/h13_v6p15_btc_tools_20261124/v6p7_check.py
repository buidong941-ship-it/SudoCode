"""Kaggle only (cần Internet để nạp NER). v6p7 bước B: che địa chỉ bằng NER + regex dự phòng, cắt span địa chỉ theo mã che,
trích lại một lần khi output tự mâu thuẫn, brief đổi biến thể trên đơn nhiều món (H13-037). Model hiểu có kịch bản."""
import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
frame_path = ROOT / "tests/b2_round_f_check.py"
F = types.ModuleType("v6p7_frame")
F.__file__ = str(frame_path)
exec(compile(frame_path.read_text(encoding="utf-8").split("# ================================================================== H8")[0],
             str(frame_path), "exec"), F.__dict__)
from harness import jev_write_gate as G
from harness import understanding as U
from core import pii
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


# ------------------------------------------------------------------ B1: che địa chỉ bằng NER (cục bộ) + regex dự phòng
os.environ["PII_NER"] = "1"
loaded = pii.ner_preload()
print("ner status:", pii.ner_status(), flush=True)
check("B1: NER model loaded locally", loaded)
CASES = [
    ("Gửi về 28 Lê Duẩn, Buôn Ma Thuột, Đắk Lắk, nhận hàng chị trả tiền mặt.", "28 Lê Duẩn, Buôn Ma Thuột, Đắk Lắk"),
    ("Gửi về 15 Phạm Văn Thuận, Biên Hòa, Đồng Nai, COD nha em.", "15 Phạm Văn Thuận, Biên Hòa, Đồng Nai"),
    ("Em lên đơn giao về 58 Nguyễn Thị Thập, Quận 7, TP HCM giùm chị, à mà nó bảo hành bao lâu vậy em?",
     "58 Nguyễn Thị Thập, Quận 7, TP HCM"),
]
for text, gold in CASES:
    red = pii.Redactor()
    masked = red.redact({"text": text})["text"]
    vals = [v for k, v in red.value_of.items() if k.startswith("[ĐỊA_CHỈ")]
    print("  mask:", masked, "| values:", vals, flush=True)
    check(f"B1: clean address boundary [{gold[:20]}]", vals == [gold] and gold not in masked)
red = pii.Redactor()
m = red.redact({"text": "Gửi về 15 Phạm Văn Thuận, Biên Hòa, Đồng Nai, COD nha em, số 0912345678 nhé"})["text"]
check("B1: COD stays visible, phone still masked", "COD" in m and "0912345678" not in m and "[SĐT_1]" in m)
red = pii.Redactor()
t9 = "Gửi về 1 Cách Mạng Tháng 8, Quận 3, TP HCM, giao tới thì cô trả tiền."
m = red.redact({"text": t9})["text"]
print("  fallback mask:", m, flush=True)
check("B1: address missed by NER still masked by regex fallback (no leak)", "Cách Mạng Tháng 8" not in m and "Quận 3" not in m)
check("B1: restore returns original text", red.restore(m) == t9)
saved = dict(pii._NER)
pii._NER.update({"pipe": None, "tried": True, "error": "simulated"})
red = pii.Redactor()
m = red.redact({"text": CASES[0][0]})["text"]
check("B1: model unavailable → regex path unchanged", "Lê Duẩn" not in m and "[ĐỊA_CHỈ_1]" in m)
pii._NER.update(saved)

# ------------------------------------------------------------------ B1: span model trả = mã che + chữ thừa → chỉ lấy giá trị mã
text = CASES[0][0]
red = pii.Redactor()
red.redact({"text": text})
tok = next(k for k in red.value_of if k.startswith("[ĐỊA_CHỈ"))
meta = {"dropped": []}
o = U._accept_observation({"slot": "address", "span": tok + ", nhận hàng", "stance": "stated", "subject": "self"},
                          text, red, "2026-10-15", meta)
print("  trimmed observation:", o, meta["dropped"], flush=True)
check("B1: model span 'mask + extra words' → address = mask value only",
      o is not None and o["span"] == "28 Lê Duẩn, Buôn Ma Thuột, Đắk Lắk")
os.environ["PII_NER"] = "0"                          # các phần sau dùng khung kiểm cũ (regex) cho ổn định


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
    for prefix in ("commit_request:", "answer_ask:", "clarify:", "read_order", "read_quote:", "read_stock:", "check_window:",
                   "clarify", "finish"):
        found = next((x for x in steps if x.startswith(prefix)), None)
        if found:
            return {"step": found}
    return {"step": "finish"}


def session(name):
    return F.session("v6p7-" + name, decider=planner)


def turn(s, text, *resps):
    F.QUEUE[:] = list(resps)
    row = s.turn(text)
    s.drain_audits()
    return row


def req(kind, evidence, ref=None, **kw):
    return {"kind": kind, "evidence": evidence, "target_ref": ref, **kw}


def created(row):
    return [ln["sku"] for c in F.calls(row, "order.create") for ln in (c["args"].get("lines") or [{"sku": c["args"].get("sku")}])]


SENTINEL = F.resp(intent="greeting_or_other")
extra = {"jev_write_gate": True, "b2_two_tier": False, "b2_max_decisions": 20, "b2_max_tool_calls": 25, "understanding_retry": True}
with F.Ctx(extra), patch.object(G, "assess", assess):
    two = [{"target_ref": "P1", "product_span": "AirPure Mini"}, {"target_ref": "P2", "product_span": "Philips 6.2L"}]
    text = "Lên đơn AirPure Mini với Philips 6.2L cho chị"
    amb = F.resp(intent="place_order", requests=[req("place_order", "Lên đơn AirPure Mini với Philips 6.2L", lines=two,
                 target_basis="named")], ambiguity={"level": "needs_clarification"})
    clean = F.resp(intent="place_order", requests=[req("place_order", "Lên đơn AirPure Mini với Philips 6.2L", lines=two,
                   target_basis="named")])
    # B2-1: mơ hồ dù hai dòng đều có tên → trích lại một lần → đơn hai món
    s = session("retry-amb")
    s.turn_mentioned = ["SKU-AP-MINI", "SKU-AF-6L"]
    row = turn(s, text, amb, clean, SENTINEL)
    um = (s.u_turn or {}).get("meta") or {}
    print("  retry meta:", um.get("retry"), "| created", created(row), flush=True)
    check("B2: contradictory ambiguity → exactly one retry", (um.get("retry") or {}).get("reasons") and len(F.QUEUE) == 1)
    check("B2: retried output used (order of both named items)", sorted(created(row)) == ["SKU-AF-6L", "SKU-AP-MINI"])
    # B2-2: trích lại vẫn mâu thuẫn → giữ hành vi cũ (không ghi)
    s = session("retry-still")
    row = turn(s, text, amb, amb, SENTINEL)
    check("B2: still contradictory after retry → no order, no third call", not F.calls(row, "order.create") and len(F.QUEUE) == 1)
    # B2-3: không mâu thuẫn → không gọi thêm
    s = session("no-retry")
    row = turn(s, text, clean, SENTINEL)
    check("B2: no trigger → no extra model call", len(F.QUEUE) == 1 and not ((s.u_turn or {}).get("meta") or {}).get("retry"))
    # B2-4: số lượng có căn cứ không nguyên văn → trích lại → null → mặc định 1
    q_bad = F.resp(intent="place_order", requests=[req("place_order", "Lấy AirPure Mini", lines=[{"target_ref": "P1",
                   "product_span": "AirPure Mini", "quantity": 3, "quantity_span": "ba cái"}], target_basis="named")])
    q_ok = F.resp(intent="place_order", requests=[req("place_order", "Lấy AirPure Mini", lines=[{"target_ref": "P1",
                  "product_span": "AirPure Mini"}], target_basis="named")])
    s = session("retry-qty")
    row = turn(s, "Lấy AirPure Mini cho chị", q_bad, q_ok, SENTINEL)
    print("  qty retry:", ((s.u_turn or {}).get("meta") or {}).get("retry"), created(row), flush=True)
    check("B2: unverbatim quantity → retry → order qty 1", created(row) == ["SKU-AP-MINI"]
          and all((c["args"].get("qty") or 1) == 1 for c in F.calls(row, "order.create")))
    # B2-5: tắt cờ → không trích lại (hành vi v6p6)
    with patch.object(settings, "understanding_retry", False):
        s = session("flag-off")
        row = turn(s, text, amb, clean, SENTINEL)
        check("B2: flag off → no retry", len(F.QUEUE) == 2 and not F.calls(row, "order.create"))

    # ------------------------------------------------------------------ B3: đổi biến thể một dòng trên đơn nhiều món
    s = session("multi-line-exchange")
    row = turn(s, "Lấy AirPure Mini và Warmly size S màu navy", F.resp(intent="place_order", requests=[req("place_order",
        "Lấy AirPure Mini và Warmly size S màu navy", lines=[{"target_ref": "P1", "product_span": "AirPure Mini"},
        {"target_ref": "P2", "product_span": "Warmly", "size_span": "size S", "color_span": "màu navy"}], target_basis="named")]),
        SENTINEL)
    print("  multi created:", created(row), flush=True)
    check("B3 setup: two-line order", len(created(row)) == 2)
    oid = s.orders_created[0]["order_id"] if s.orders_created else None
    row = turn(s, "Đổi cái áo sang size M màu be giúp chị", F.resp(intent="exchange", requests=[req("exchange",
        "Đổi cái áo sang size M màu be", "O1")], observations=[
        {"slot": "size", "span": "size M", "stance": "chosen", "subject": "self"},
        {"slot": "color", "span": "màu be", "stance": "chosen", "subject": "self"}]), SENTINEL)
    ho = F.calls(row, "handoff.transfer")
    na = str((ho[0]["args"].get("brief") or {}).get("next_action")) if ho else ""
    print("  exchange reply:", row["agent_text"], "| goals", row.get("goals"), "| brief:", na[:300], flush=True)
    check("B3: multi-line exchange handed off with order id in brief", ho and oid and oid in na)
    check("B3: reply says transferred, order not changed", "amend_handoff" in (row.get("goals") or []) and "chưa thay đổi" in row["agent_text"])

print("v6p7 checks:", passed, "PASS", flush=True)
assert not failed, failed
