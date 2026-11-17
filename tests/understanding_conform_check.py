"""Kiểm validation kiểu output understanding (14/11, GEN-T25 c2t2: TypeError unhashable dict làm mất cả lượt).

Không gọi API: thay understanding._call bằng hàm trả output dựng sẵn. Kiểm:
1. output hợp lệ đi qua _conform KHÔNG đổi (so từng trường) và understand() cho cùng kết quả như trước khi có _conform;
2. mỗi trường sai kiểu (object thay chuỗi, chuỗi thay mảng, ...) không ném lỗi, bị bỏ và ghi meta.dropped why=type_invalid;
3. understand_record cũng không ném lỗi khi observation sai kiểu."""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import understanding as U  # noqa: E402

R = {"passed": 0, "failed": 0}


def ok(name, got, want):
    good = got == want
    R["passed" if good else "failed"] += 1
    print(("OK   " if good else "FAIL ") + name + ("" if good else f": got={got!r} want={want!r}"))


VALID = {"intent": "price_promo", "flags": [], "observations": [], "requests": [], "withdrawn": [],
         "response_to_agent": {"act": "none", "evidence": ""}, "asks": [], "refs": {"previous_contact": True},
         "safety": [], "asks_question": True, "ambiguity": {"level": "none", "reason": ""}}
TEXT = "sao ben facebook bao re hon"


def run(out, text=TEXT, state_ctx=None):
    U._call = lambda prompt, schema, mt: (copy.deepcopy(out), 5, 1, None)
    return U.understand(text, "2026-10-16", [], "", None, state_ctx=state_ctx)


# 1. hợp lệ: _conform giữ nguyên
dropped = []
ok("output hợp lệ: _conform không đổi", U._conform(copy.deepcopy(VALID), U._schema(), "$", dropped), VALID)
ok("output hợp lệ: không ghi dropped", dropped, [])
u = run(VALID)
ok("output hợp lệ: intent giữ", u["route"]["intent"], "price_promo")
ok("output hợp lệ: refs giữ", u["refs"]["previous_contact"], True)
ok("output hợp lệ: không có type_invalid", [x for x in u["meta"]["dropped"] if x.get("why") == "type_invalid"], [])

# 2. từng trường sai kiểu → không ném lỗi, có ghi lại
BAD = {
    "intent là object": {"intent": {"name": "negotiate"}},
    "flags chứa object": {"flags": [{"flag": "competitor_price"}]},
    "asks chứa object": {"asks": [{"ask": "price"}]},
    "safety chứa object": {"safety": [{"x": 1}]},
    "refs là mảng": {"refs": ["previous_contact"]},
    "ambiguity là chuỗi": {"ambiguity": "none"},
    "response_to_agent.act là object": {"response_to_agent": {"act": {"a": 1}, "evidence": ""}},
    "observation.slot là object": {"observations": [{"slot": {"s": "payment"}, "span": "x", "stance": "stated"}]},
    "observation.stance là object": {"observations": [{"slot": "payment", "span": "facebook", "stance": {"s": 1}}]},
    "request.kind là object": {"requests": [{"kind": {"k": "place_order"}, "evidence": "facebook"}]},
    "request.target_ref là object": {"requests": [{"kind": "callback", "evidence": "facebook", "target_ref": {"r": "P1"}}]},
    "request.condition.type là object": {"requests": [{"kind": "callback", "evidence": "facebook",
                                                        "condition": {"type": {"t": 1}, "span": "x"}}]},
    "withdrawn.kind là object": {"withdrawn": [{"kind": {"k": 1}, "evidence": "facebook"}]},
    "observations là object": {"observations": {"slot": "payment"}},
    "asks_question là chuỗi": {"asks_question": "true"},
}
for name, patch in BAD.items():
    out = {**VALID, **patch}
    try:
        u = run(out, state_ctx={"candidates": [{"ref": "P1", "kind": "product", "name": "RunLite 1"}]})
        tv = [x for x in u["meta"]["dropped"] if x.get("why") == "type_invalid"]
        ok(f"sai kiểu, {name}: không lỗi + ghi type_invalid", bool(tv), True)
    except Exception as e:  # noqa: BLE001
        ok(f"sai kiểu, {name}: không lỗi", f"{type(e).__name__}: {e}", "không lỗi")

# 2b. đóng khi sai kiểu (14/11): bỏ trường KHÔNG được mở quyền ghi
CTX = {"candidates": [{"ref": "P1", "kind": "product", "name": "RunLite 1"}]}
PO = lambda **kw: {**VALID, "requests": [{"kind": "place_order", "evidence": "facebook", **kw}]}
u = run(PO(condition={"type": "stock", "span": {"s": 1}}), state_ctx=CTX)
ok("đóng: condition.span sai kiểu → điều kiện unknown (không thực thi)", (u["request_items"][0]["condition"] or {}).get("type"), "unknown")
u = run(PO(condition={"type": {"t": "stock"}, "span": "facebook"}), state_ctx=CTX)
ok("đóng: condition.type sai kiểu → điều kiện unknown, KHÔNG thành không điều kiện",
   (u["request_items"][0]["condition"] or {}).get("type"), "unknown")
u = run(PO(condition="khi có hàng"), state_ctx=CTX)
ok("đóng: condition là chuỗi → điều kiện unknown", (u["request_items"][0]["condition"] or {}).get("type"), "unknown")
u = run(PO(target_ref={"r": "P1"}), state_ctx=CTX)
ok("đóng: target_ref sai kiểu → target_invalid (cần hỏi đối tượng), không hạ thành 'chưa có target'",
   (u["request_items"][0]["target_ref"], u["request_items"][0]["target_invalid"]), (None, True))
ok("đóng: lỗi kiểu ở condition / target_ref KHÔNG giữ cả lượt", run(PO(target_ref={"r": 1}), state_ctx=CTX)["ambiguity"]["level"], "none")
for name, patch_ in {"request là chuỗi": {"requests": ["place_order"]},
                     "requests là object": {"requests": {"kind": "place_order"}},
                     "request.kind là object": {"requests": [{"kind": {"k": 1}, "evidence": "facebook"}]},
                     "request.evidence là object": {"requests": [{"kind": "place_order", "evidence": {"e": 1}}]},
                     "withdrawn chứa chuỗi": {"withdrawn": ["place_order"]},
                     "ambiguity.level là object": {"ambiguity": {"level": {"l": 1}}},
                     "response_to_agent.act là object": {"response_to_agent": {"act": {"a": 1}, "evidence": ""}}}.items():
    u = run({**VALID, **patch_}, state_ctx=CTX)
    ok(f"đóng: {name} → lượt mơ hồ (needs_clarification), có type_hold",
       (u["ambiguity"]["level"], bool(u["meta"].get("type_hold"))), ("needs_clarification", True))
u = run({**VALID, "flags": [{"x": 1}], "asks": [{"a": 1}], "observations": [{"slot": {"s": 1}, "span": "x", "stance": "stated"}]})
ok("không giữ lượt khi chỉ flags / asks / observation sai kiểu (không mở quyền ghi)", u["ambiguity"]["level"], "none")

# 3. understand_record
U._call = lambda prompt, schema, mt: ({"observations": [{"slot": {"s": 1}, "span": "x"}], "advised": "AirPure X"}, 5, 1, None)
try:
    slots, meta = U.understand_record("Khách hỏi AirPure X.", "2026-10-16")
    ok("understand_record sai kiểu: không lỗi + ghi type_invalid",
       (slots, any(x.get("why") == "type_invalid" for x in meta["dropped"])), ({}, True))
except Exception as e:  # noqa: BLE001
    ok("understand_record sai kiểu: không lỗi", f"{type(e).__name__}: {e}", "không lỗi")

print(R)
raise SystemExit(int(R["failed"] > 0))
