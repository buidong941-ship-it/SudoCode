"""Nghiệm thu CPU BƯỚC 2 (18/11, QUYET-DINH-KIEN-TRUC-SAU-UI5): clarify(field, target_ref, purpose) + điều kiện phát giá theo biến thể.
Kaggle CPU, KHÔNG API. DeepSeek = phản hồi đóng gói; Jev = bộ quyết định có kịch bản theo chính sách chung; tool = mock BTC thật;
đáp án (giá từng size) tính độc lập bằng eval/mock_tools trong test. Chỉ khi B2_TWO_TIER (candidate); cờ tắt = hành vi cũ (V8).

V1 trường còn thiếu (dạng GEN-T09-01): hỏi KM giày khi chưa nói size → không phát giá mẫu gốc, hỏi đúng size, lưu tác vụ chờ
    (hai thứ tự quyết định: answer_ask trước / read_quote trước) · V2 khách trả lời ngắn "43" → tiếp tục tác vụ, báo ĐÚNG giá size 43,
    không nêu màu tùy chọn, không nhớ biến thể đại diện · V3 trường đã biết (nói size ngay) → báo giá ngay, không hỏi · V4 thuộc tính
    không ảnh hưởng giá: màu không bao giờ được hỏi; mẫu không biến thể báo giá ngay · V5 đổi ý giữa chừng (hỏi mẫu khác) → bỏ tác vụ
    chờ, không phát giá giày · V6 giá trị không có ("size 50") → nói rõ phần thiếu + lựa chọn đang có, không báo giá · V7 không trả lời
    hai lần → bỏ tác vụ (không hỏi vòng lặp) · V8 cờ tắt = hành vi cũ (tái hiện lỗi gốc làm mốc) · V9 chỉ phụ thu theo size (áo khoác,
    không KM loại trừ) cũng hỏi size · M mutant tắt cổng → test phát hiện giá mẫu gốc bị phát.
Dùng: python tests/b2_variant_clarify_check.py   (chỉ chạy trên cây đã áp overlay bước 2)"""
import os
import re
import sys
import types
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_fpath = os.path.join(ROOT, "tests", "b2_round_f_check.py")
F = types.ModuleType("b2_round_f_frame")
F.__file__ = _fpath
exec(compile(open(_fpath, encoding="utf-8").read().split("# ================================================================== H8")[0], _fpath, "exec"),
     F.__dict__)

from eval import mock_tools as mt  # noqa: E402
from harness import planner_b2tt as TT, variant_gate as VG  # noqa: E402
from harness.tools import product_name  # noqa: E402

ok, resp, Script = F.ok, F.resp, F.Script
TT_ON = {"b2_two_tier": True, "b2tt_max_tool_calls": 18, "b2tt_max_decisions": 4}
RUN, JK, APX = "SKU-SN-RUN1", "SKU-JK-WND", "SKU-AP-X"
DAY = "2026-10-15"
MONEY = re.compile(r"\d{1,3}(?:\.\d{3})+")


def vnd(v):
    return f"{v:,}".replace(",", ".")


def size_prices(par):
    p, _ = mt._parent(par)
    out = {}
    for v in p["variants"]:
        out.setdefault(str(v["size"]), set()).add(mt.pricing_get_quote(v["variant_sku"], on=DAY)["final_price_vnd"])
    return out


SP = size_prices(RUN)
BASE = mt.pricing_get_quote(RUN, on=DAY)["final_price_vnd"]
COLORS = sorted({v["color"] for v in mt._parent(RUN)[0]["variants"]})


def policy(order):
    def f(state, opts):
        for pre in order:
            hit = next((x for x in opts["step"] if x.startswith(pre)), None)
            if hit:
                return hit
        return "finish"
    return f


ANSWER_FIRST = ("clarify_field:", "answer_ask:", "read_quote:")
READ_FIRST = ("read_quote:", "clarify_field:", "answer_ask:")


def mk(order=ANSWER_FIRST):
    return Script(*[policy(order)] * 80)


def promo_q(text_name):
    return resp(intent="price_promo", asks=["promo"], asks_question=True,
                consult={"sort": "none", "scope": "mentioned", "goal": "about_named", "category_span": None, "budget_span": None,
                         "area_span": None})


def size_reply(span):
    return resp(intent="provide_info", observations=[{"slot": "size", "span": span, "stance": "stated", "subject": "self"}])


def vc(row):
    return (F.loop(row) or {}).get("variant_condition") or {}


def steps(row):
    return [d.get("step") for d in (F.loop(row) or {}).get("decisions") or []]


with F.Ctx(TT_ON):
    TT.DECIDERS.update(inner=None, outer=None)
    name = product_name(RUN)
    ok("V0", "tiền đề oracle: size 43 khác giá các size khác; mỗi size một giá", (len(SP["43"]) == 1 and SP["43"] != SP["42"]
                                                                                   and all(len(x) == 1 for x in SP.values())), True)
    for tag, order in (("answer_first", ANSWER_FIRST), ("read_first", READ_FIRST)):
        s = F.session(f"v1-{tag}", decider=mk(order))
        r = F.say(s, f"{name} đang có khuyến mãi gì không em?", promo_q(name))
        ok("V1", f"{tag}: không phát giá khi chưa biết size", MONEY.findall(r["agent_text"]), [])
        ok("V1", f"{tag}: hỏi đúng size (clarify_field:size@P#)", any(str(x).startswith("clarify_field:size@") for x in steps(r))
           and "ask_size_for_price" in r["goals"], True)
        ok("V1", f"{tag}: không bao giờ hỏi màu (không ảnh hưởng giá)", any(str(x).startswith("clarify_field:color") for x in steps(r)), False)
        pc = getattr(s, "pending_clarify", None) or {}
        ok("V1", f"{tag}: lưu tác vụ chờ (đối tượng, trường, lý do, câu hỏi)", (pc.get("target"), pc.get("field"), pc.get("purpose"),
                                                                              "promo" in (pc.get("asks") or [])),
           (RUN, "size", "price_depends_on_variant", True))
        ok("V1", f"{tag}: không báo giá vai advised vào bộ nhớ", (RUN, "advised") in {(q["sku"], q["role"]) for q in
                                                                                      s.mem.past_quotes(s.customer["customer_id"])}, False)
        # V2 khách trả lời ngắn
        r2 = F.say(s, "43", size_reply("43"))
        want = next(iter(SP["43"]))
        ok("V2", f"{tag}: tiếp tục tác vụ chờ", (vc(r2).get("resume") or {}).get("action"), "resumed")
        ok("V2", f"{tag}: báo ĐÚNG giá size 43 (oracle)", vnd(want) in r2["agent_text"] and vnd(BASE) not in r2["agent_text"], True)
        ok("V2", f"{tag}: không nêu màu tùy chọn của biến thể đại diện", any(f"màu {c_}" in r2["agent_text"] for c_ in COLORS), False)
        ok("V2", f"{tag}: không hỏi lại size", "ask_size_for_price" in r2["goals"], False)
        s.end()                                   # ghi bộ nhớ cuối cuộc (D54 nhớ variant_sku nếu khách đã chọn biến thể)
        ok("V2", f"{tag}: biến thể đại diện không bị nhớ như lựa chọn", s.known.get("variant_sku"), None)

    # V3 trường đã biết
    s = F.session("v3", decider=mk())
    r = F.say(s, f"{name} size 42 đang có khuyến mãi gì không em?", resp(intent="price_promo", asks=["promo"], asks_question=True,
              observations=[{"slot": "size", "span": "size 42", "stance": "stated", "subject": "self"}],
              consult={"sort": "none", "scope": "mentioned", "goal": "about_named"}))
    ok("V3", "nói size ngay → báo giá size 42, không hỏi", vnd(next(iter(SP["42"]))) in r["agent_text"] and "ask_size_for_price" not in r["goals"], True)

    # V4 mẫu không biến thể
    s = F.session("v4", decider=mk())
    r = F.say(s, f"{product_name(APX)} giá bao nhiêu em?", resp(intent="price_promo", asks=["price"], asks_question=True,
              consult={"sort": "none", "scope": "mentioned", "goal": "about_named"}))
    ok("V4", "mẫu không biến thể: báo giá ngay", vnd(mt.pricing_get_quote(APX, on=DAY)["final_price_vnd"]) in r["agent_text"]
       and not any(str(x).startswith("clarify_field") for x in steps(r)), True)
    ok("V4", "variant_gate: giày chỉ thiếu size (màu không ảnh hưởng)", VG.analyze(s, RUN, "")["fields"], ["size"])

    # V5 đổi ý giữa chừng
    s = F.session("v5", decider=mk())
    F.say(s, f"{name} đang có khuyến mãi gì không em?", promo_q(name))
    r = F.say(s, f"Thôi cho anh xem {product_name(APX)} giá bao nhiêu", resp(intent="price_promo", asks=["price"], asks_question=True,
              consult={"sort": "none", "scope": "mentioned", "goal": "about_named"}))
    ok("V5", "đổi mẫu → bỏ tác vụ chờ", ((vc(r).get("resume") or {}).get("action"), (vc(r).get("resume") or {}).get("why")),
       ("dropped", "target_changed"))
    ok("V5", "báo giá mẫu mới, không phát giá giày", vnd(mt.pricing_get_quote(APX, on=DAY)["final_price_vnd"]) in r["agent_text"]
       and vnd(BASE) not in r["agent_text"], True)

    # V6 giá trị không có
    s = F.session("v6", decider=mk())
    F.say(s, f"{name} đang có khuyến mãi gì không em?", promo_q(name))
    r = F.say(s, "size 50", size_reply("size 50"))
    ok("V6", "size không có → variant_unavailable, không báo giá", "variant_unavailable" in r["goals"] and not MONEY.findall(r["agent_text"]), True)
    ok("V6", "nêu các size đang có", all(x in r["agent_text"] for x in ("38", "43")), True)

    # V7 không trả lời hai lần → bỏ
    s = F.session("v7", decider=mk())
    F.say(s, f"{name} đang có khuyến mãi gì không em?", promo_q(name))
    a = F.say(s, "Ừ để anh xem đã", resp(intent="greeting_or_other"))
    b = F.say(s, "Ừm", resp(intent="greeting_or_other"))
    ok("V7", "lần 1 giữ, lần 2 bỏ tác vụ chờ", ((vc(a).get("resume") or {}).get("action"), (vc(b).get("resume") or {}).get("action")),
       ("kept", "dropped"))
    ok("V7", "không hỏi size lặp lại ở các lượt đó", "ask_size_for_price" in a["goals"] + b["goals"], False)

    # V9 chỉ phụ thu theo size
    s = F.session("v9", decider=mk())
    r = F.say(s, f"{product_name(JK)} giá bao nhiêu em?", resp(intent="price_promo", asks=["price"], asks_question=True,
              consult={"sort": "none", "scope": "mentioned", "goal": "about_named"}))
    ok("V9", "áo khoác (phụ thu size XL): hỏi size, không phát giá", "ask_size_for_price" in r["goals"] and not MONEY.findall(r["agent_text"]), True)

    # M mutant: tắt cổng (variant_gate coi mọi mẫu là đã rõ) → test phát hiện phát giá mẫu gốc
    with patch.object(VG, "analyze", lambda s_, sku, text: {"state": "resolved", "sku": sku}):
        s = F.session("mut", decider=mk(READ_FIRST))
        r = F.say(s, f"{name} đang có khuyến mãi gì không em?", promo_q(name))
    ok("M", "mutant tắt cổng: test PHÁT HIỆN giá mẫu gốc bị phát trước khi biết size", vnd(BASE) in r["agent_text"], True)

# V8 cờ tắt: hành vi cũ (mốc lỗi gốc GEN-T09-01: read_quote phát giá mẫu gốc)
with F.Ctx({"b2_two_tier": False}):
    s = F.session("v8", decider=mk(READ_FIRST))
    r = F.say(s, f"{product_name(RUN)} đang có khuyến mãi gì không em?", resp(intent="price_promo", asks=["promo"], asks_question=True))
    ok("V8", "cờ tắt: không có clarify_field / variant_condition", (any(str(x).startswith("clarify_field") for x in steps(r)),
                                                                     "variant_condition" in (F.loop(r) or {})), (False, False))
    ok("V8", "cờ tắt: tái hiện lỗi gốc (phát giá mẫu gốc)", vnd(BASE) in r["agent_text"], True)

print(f"\n{F.PASS[0]} OK, {len(F.FAIL)} FAIL")
for g, n in F.FAIL:
    print("FAIL", g, n)
sys.exit(1 if F.FAIL else 0)
