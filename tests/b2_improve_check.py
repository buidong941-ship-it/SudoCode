"""Kiểm XÁC ĐỊNH (Kaggle CPU, không API) cho gói cải thiện B2 sau đo v6 — docs/PLAN/BAN-GIAO-CAI-THIEN-B2-SAU-DO-V6-2026-11-13.md.

DeepSeek = phản hồi đóng gói theo hợp đồng v2; Jev planner = bộ quyết định CÓ KỊCH BẢN (kiểm wiring / guard / hợp đồng, KHÔNG
chứng minh Jev thật chọn đúng — phần đó ở scripts/b2_improve_probe.py). Tool = mock BTC thật, memory SQLite tạm.

G01 tên hiển thị ↔ canonical: ánh xạ 1-1 đảo được; trace giữ canonical + shown; Jev mô phỏng chọn tên hiển thị → bước canonical
G02 trace v6 (nếu có file): mọi bước đã ghi parse về hành động canonical, round-trip, có tên hiển thị
G03 dạng `ambiguity` của route.understanding là chuỗi; clarify chung chỉ có khi needs_clarification / hold (S8)
G04 thuộc tính: có khóa catalog → payload đúng SKU / khóa, render nguyên văn, answered + catalog, không đọc giá; thiếu nguồn →
    responded_no_source + câu chưa có thông tin; không nhận ra thuộc tính → noop, KHÔNG answered, finish bị chặn, dừng không tool;
    nhiều mẫu → hỏi mẫu nào (needs_customer)
G05 giỏ: add_to_cart → giỏ có delta trong state, report_cart báo tổng, 0 order.*; thêm cùng SKU → không đổi giỏ, không suy số lượng
G06 dòng chung sau khi B2 dừng: đối thủ → no_competitor_comment; hoãn → defer_ack; không greet / handoff; allowlist đúng; B3 rỗng;
    safety terminal vẫn trước owner
G07 order.create unresolved → _finish chuyển nhân viên đúng một lần; lượt sau không tạo lại, không chuyển lần hai
G08 bằng chứng dùng lại: trả lời giá (tool trong handler) đủ làm bằng chứng ghi đúng SKU, không đọc lại
G09 bot + câu hỏi sản phẩm: khối is_bot có trong state; ask `other` KHÔNG tự xong; câu hỏi giá vẫn phải trả lời
G10 noop / thiếu bằng chứng không bao giờ thành answered (mọi answered có evidence đúng loại chủ đề)
— patch cuối 13/11 —
G11 `other` không tự tra chính sách: khối chung → responded_common; không có → no_info; chỉ answered khi planner đã đọc tài liệu
G12 thuộc tính không rõ, mẫu đã biết → hỏi đúng nội dung (ask_which_attribute, gợi ý thông tin catalog), không lặp, không đọc giá
G13 thêm cùng SKU → phải phản hồi giỏ (finish bị chặn respond_cart), báo đã có trong giỏ, không khẳng định số lượng
G14 không đọc lặp (bước đọc đã có bằng chứng bị lọc; trả lời giá dùng lại view của lượt); trần tool cứng theo chi phí tối đa
— vòng giỏ 13/11 (bằng chứng giá theo ngữ cảnh giỏ và điều kiện KM) —
G16 N10: sau report_cart không còn read_quote món trong giỏ / report_cart lặp; dòng giỏ ghi AIR-2ND-50; không "Ngoài ra"; khối
    giá riêng của món trong giỏ bị bỏ khi khách không hỏi giá
G17 N12 giá mua riêng: trả 4.890.000đ từ get_quote, không lẫn giá trong giỏ; cùng câu có giỏ → nhãn "mua riêng"
G18 N13 KM trong giỏ + tổng: dòng giỏ 2.445.000đ kèm AIR-2ND-50, tổng 8.935.000đ; báo giỏ qua cart_total cũng chặn báo lại
— phụ kiện + một nguồn cập nhật giỏ (13/11, duyệt) —
G19 chuẩn hóa mã phụ kiện (màng lọc gắn tên máy → phụ kiện; không gắn → của máy duy nhất / mẫu đang bàn; quà tặng / mơ hồ → không đổi)
G20 V3-055 t4: ứng viên DeepSeek đã chuẩn hóa (P2 = màng lọc), giỏ không có máy AirPure Y, một nguồn target_ref
G21 không suy mua phụ kiện chỉ vì được nhắc: thiếu căn cứ trong câu yêu cầu → hỏi rõ (ask_accessory_intent), không thêm
Dùng: python tests/b2_improve_check.py [trace_v6.jsonl]
"""
import json
import os
import sys
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
tmp = tempfile.mkdtemp(prefix="b2_improve_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "v.db").replace("\\", "/")
os.environ["TOOL_TRANSPORT"] = "direct"
os.environ.setdefault("RUN_PROFILE", "local")
os.environ.setdefault("RAG_MODE", "bm25")
os.environ["LLM_CACHE"] = "off"

from core.config import settings  # noqa: E402
from core.llm import deepseek  # noqa: E402
from core.llm.generator import Generator  # noqa: E402
from core.llm.router import Router  # noqa: E402
from harness import agent, audit, planner_b2 as B2, planner_variants, understanding as U  # noqa: E402
from harness import plan_primitives as P  # noqa: E402
from harness.memory import Memory  # noqa: E402
from harness.tools import ToolBox, mt  # noqa: E402

FAIL, PASS = [], [0]


def ok(group, name, got, want=True):
    if got == want:
        PASS[0] += 1
        print(f"OK   [{group}] {name}", flush=True)
    else:
        FAIL.append((group, name))
        print(f"FAIL [{group}] {name}: got={got!r} want={want!r}", flush=True)


def resp(**kw):
    d = {"intent": "greeting_or_other", "flags": [], "observations": [], "requests": [], "withdrawn": [],
         "response_to_agent": {"act": "none"}, "asks": [], "refs": {}, "safety": [], "asks_question": False,
         "ambiguity": {"level": "none"}}
    d.update(kw)
    return d


QUEUE = []


def fake_call(prompt, schema, max_tokens):
    return (QUEUE.pop(0) if QUEUE else resp()), 7, 1, None


def fake_jev(sentence, known):
    return {"slot": "other", "type": "open", "text": sentence.strip()} if sentence.strip().endswith("?") else None


def fake_llm_json(self, prompt, **kw):
    return {"claims": []} if "claims" in json.dumps(kw.get("schema") or {}) else {"lead": "L0", "policy_refs": [], "attribute_refs": []}


BASE = dict(arch="target", understanding="", goal_contract=True, contract_v2=True, jev_simulated=True, requests_backend="",
            planner_selector="rules", planner_backend="rules", improve_dir="", order_qty=True,
            b2_max_decisions=6, b2_max_tool_calls=13, b2_deadline_s=30.0, b2_min_conf=0.0, b3_max_steps=8)


class Ctx:
    def __init__(self, extra=None):
        self.ps = [patch.object(settings, k, v) for k, v in {**BASE, **(extra or {})}.items()]
        self.ps += [patch.object(U, "_call", fake_call), patch.object(audit, "_jev_sentence", fake_jev),
                    patch.object(deepseek.LLM, "json", fake_llm_json)]

    def __enter__(self):
        for p in self.ps:
            p.start()
        return self

    def __exit__(self, *a):
        for p in reversed(self.ps):
            p.stop()


def session(name, variant="b2_jev", decider=None, phone="0911222333"):
    mem = Memory(f"b2improve:{variant}:{name}")
    mem.wipe()
    ToolBox.reset_world()
    s = agent.CallSession(memory=mem, today="2026-10-15", call_name="call_1", session_id=f"{name}:call_1", channel="hotline",
                          channel_identity=None, phone=phone, input_mode="text", router=Router("rules"),
                          generator=Generator("offline"), config="full", planner_variant=variant, planner_decider=decider)
    s.start()
    return s


def say(s, text, d):
    QUEUE[:] = [d]
    return s.turn(text)


def calls(row, name):
    return [t for t in row["tool_calls"] if t["name"] == name]


def created_skus(row):
    out = []
    for t in calls(row, "order.create"):
        a = t["args"]
        out.append(sorted(ln["sku"] for ln in a["lines"]) if a.get("lines") else [a["sku"]])
    return out


def writes(row):
    return [t["name"] for t in row["tool_calls"] if t["name"] in ("order.create", "order.update")]


def req(kind, ev, ref=None, cond=None):
    return {"kind": kind, "evidence": ev, "target_ref": ref, "condition": cond}


def loop(row):
    return (row.get("planner") or {}).get("loop") or {}


class Script:
    """Bộ quyết định có kịch bản: phần tử là chuỗi bước canonical, hoặc hàm (state, opts) → chuỗi bước. Hết → finish."""

    def __init__(self, *plan):
        self.plan, self.seen, self.opts_seen = list(plan), [], []

    def __call__(self, state, opts):
        self.seen.append(state)
        self.opts_seen.append(opts)
        step = self.plan.pop(0) if self.plan else "finish"
        if callable(step):
            step = step(state, opts)
        return {"step": step, "backend": "script", "ms": 0}


AX40, APX, APY, AF6 = "SKU-SS-AX40", "SKU-AP-X", "SKU-AP-Y", "SKU-AF-6L"
PRICE_Q = resp(intent="price_promo", asks=["price"], asks_question=True)
ATTR_Q = resp(intent="product_inquiry", asks=["attribute"], asks_question=True)


def all_answered_have_evidence(lp):
    """G10: mọi ask answered có ≥1 evidence thuộc loại TOPIC_EVIDENCE của chủ đề."""
    bad = []
    for topic, o in (lp.get("ask_outcome") or {}).items():
        if o["outcome"] == "answered" and not ({e["kind"] for e in o.get("evidence") or []} & P.TOPIC_EVIDENCE.get(topic, set())):
            bad.append(topic)
    for topic in lp.get("answered") or []:
        if (lp.get("ask_outcome") or {}).get(topic, {}).get("outcome") != "answered":
            bad.append("answered_without_outcome:" + topic)
    return bad


# ================================================================== G01: tên hiển thị ↔ canonical
with Ctx():
    d = Script("answer_ask:price", "finish")
    s = session("g01", decider=d)
    row = say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    bad = []
    for o in d.opts_seen:
        disp = o["display"]
        if len(set(disp.values())) != len(disp):
            bad.append("not_unique")
        for st in o["step"]:
            if B2.to_canonical(disp[st], o) != st:
                bad.append(st)
            if disp[st] == st:
                bad.append("same_as_canonical:" + st)
    ok("G01", "display ↔ canonical is 1-1 and invertible on every offered step", bad, [])
    decs = loop(row).get("decisions") or []
    ok("G01", "trace keeps canonical step + shown name", [(x.get("step"), x.get("shown")) for x in decs],
       [("answer_ask:price", "answer_customer_question:price"), ("finish", "finish_turn")])
    descs = d.opts_seen[0]["desc"]
    ok("G01", "every description states what it does + tools / no write",
       [k for k, v in descs.items() if not any(w in v for w in ("Tool", "tool", "Không ghi", "không ghi", "Không gọi tool"))], [])
    # Jev (mô phỏng) trả TÊN HIỂN THỊ → run() đổi về canonical trước validator
    from harness import jev_adapter

    def fake_infer(prompt, schema):
        return {"step": next((x for x in schema["properties"]["step"]["enum"] if x.startswith("answer_customer_question")), "finish_turn")}
    with patch.object(jev_adapter, "infer", fake_infer):
        s = session("g01b")                      # decider None → jev_decide (JEV_SIMULATED=1 trong BASE)
        row = say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    d0 = (loop(row).get("decisions") or [{}])[0]
    ok("G01", "simulated Jev picks a display name → executed as canonical answer_ask:price",
       (d0.get("step"), d0.get("shown"), d0.get("rejected")), ("answer_ask:price", "answer_customer_question:price", None))

# ================================================================== G02: trace v6 → canonical
V6_TRACE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "fixtures", "b2v6_full.jsonl")
if os.path.exists(V6_TRACE):
    steps, bad = set(), []
    for line in open(V6_TRACE, encoding="utf-8"):
        r = json.loads(line)
        for x in ((r.get("planner") or {}).get("loop") or {}).get("decisions") or []:
            if x.get("step"):
                steps.add(x["step"])
    for st in sorted(steps):
        a, rq, tg = B2.parse_step(st)
        if a not in P.ACTIONS or B2.step_of(a, rq, tg) != st:
            bad.append(st)
            continue
        disp = B2.display_of(st)
        if B2.to_canonical(disp, {"display": {st: disp}}) != st:
            bad.append("display:" + st)
    ok("G02", f"all {len(steps)} distinct v6 recorded steps parse to canonical actions, round-trip and map to display", bad, [])
else:
    print("SKIP [G02] không có trace v6 (truyền đường dẫn làm tham số 1)")

# ================================================================== G03: dạng ambiguity + clarify chung theo guard
SPY = []
_orig_options = B2.options


def spy_options(t):
    SPY.append(type((t.c.u or {}).get("ambiguity")).__name__)
    return _orig_options(t)


with Ctx(), patch.object(B2, "options", spy_options):
    d = Script("finish")
    s = session("g03a", decider=d)
    say(s, "Chị hỏi chút", resp(intent="greeting_or_other", asks_question=True, ambiguity={"level": "needs_clarification"}))
    d2 = Script("finish")
    s2 = session("g03b", decider=d2)
    say(s2, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    ok("G03", "route.understanding ambiguity is a string level (not dict)", sorted(set(SPY)), ["str"])
    ok("G03", "generic clarify offered when needs_clarification", "clarify" in d.opts_seen[0]["step"], True)
    ok("G03", "generic clarify removed otherwise (reason recorded)",
       ("clarify" in d2.opts_seen[0]["step"], d2.opts_seen[0]["removed"].get("clarify")), (False, "no_hold_no_ambiguity"))

# ================================================================== G04: thuộc tính
with Ctx():
    d = Script("answer_ask:attribute", "finish")
    s = session("g04a", decider=d)
    row = say(s, "Máy lọc không khí AirPure X dùng cho phòng bao nhiêu mét vuông em?", ATTR_Q)
    lp = loop(row)
    o = (lp.get("ask_outcome") or {}).get("attribute") or {}
    ans = next((x for x in lp.get("steps") or [] if x["action"] == "answer_ask"), {})
    ok("G04", "attribute with catalog key → answered, evidence catalog SKU-AP-X.room_area_m2",
       (o.get("outcome"), [e["ref"] for e in o.get("evidence") or []]), ("answered", [f"{APX}.room_area_m2"]))
    ok("G04", "rendered text states the catalog value verbatim (25 m²)", "phù hợp phòng khoảng 25 m²" in row["agent_text"], True)
    ok("G04", "attribute answer does not read price (no tool inside the answer step)", ans.get("tools"), [])
    ok("G04", "no greet / closing fallback appended", bool({"greet", "closing"} & set(row["goals"])), False)

    d = Script("answer_ask:attribute", "finish")
    s = session("g04b", decider=d)
    row = say(s, "Nồi chiên Philips 6.2L có chứng nhận FDA không em?", ATTR_Q)
    o = (loop(row).get("ask_outcome") or {}).get("attribute") or {}
    ok("G04", "certification term without catalog key → responded_no_source + no_info, no evidence",
       (o.get("outcome"), "no_info" in row["goals"], o.get("evidence")), ("responded_no_source", True, []))
    ok("G04", "reply says no exact information (no fabricated attribute)", "chưa có thông tin" in row["agent_text"], True)

    d = Script("answer_ask:attribute", "finish", "finish")
    s = session("g04c", decider=d)
    row = say(s, "Chị hỏi thăm cái nồi chiên Philips 6.2L với", ATTR_Q)
    lp = loop(row)
    o = (lp.get("ask_outcome") or {}).get("attribute") or {}
    ok("G12", "no attribute term, product known → needs_customer (ask_which_attribute), NOT answered, no loop",
       (o.get("outcome"), "ask_which_attribute" in row["goals"], "attribute" in (lp.get("answered") or []), lp.get("stop")),
       ("needs_customer", True, False, "finish"))
    ok("G12", "question asks what info about that product, suggesting only catalog info (bảo hành)",
       ("muốn biết thông tin gì về mẫu Nồi chiên không dầu Philips 6.2L" in row["agent_text"], "bảo hành" in row["agent_text"],
        "000đ" in row["agent_text"]), (True, True, False))
    ok("G12", "asking does not read price (no tool in the turn loop)", lp.get("tool_calls"), 0)

    d = Script("answer_ask:attribute", "finish")
    s = session("g04d", decider=d)
    row = say(s, "AirPure X với Samsung AX40 bảo hành bao lâu em?", ATTR_Q)
    o = (loop(row).get("ask_outcome") or {}).get("attribute") or {}
    ok("G04", "two products, attribute of which one unclear → needs_customer (ask_product), not last-mentioned",
       (o.get("outcome"), "ask_product" in row["goals"], "attribute_answer" in json.dumps(loop(row), ensure_ascii=False)),
       ("needs_customer", True, False))

# ================================================================== G05: giỏ
with Ctx():
    d = Script("answer_ask:price", "finish")
    s = session("g05", decider=d)
    say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    ok("G05", "report_cart not offered while cart is empty", "report_cart" in d.opts_seen[0]["step"], False)
    s.planner.decider = d = Script("report_cart", "finish")
    row = say(s, "Thêm Samsung AX40 vào giỏ giúp anh", resp(intent="place_order", requests=[req("add_to_cart", "Thêm Samsung AX40 vào giỏ", "P1")]))
    cart = d.seen[0].get("cart") or {}
    ok("G05", "state shows cart delta from preparation (added), quantity not tracked",
       (len(cart.get("added_this_turn") or []), cart.get("quantity_tracked")), (1, False))
    ok("G05", "report_cart → cart_total with quote_order; zero order.* writes", ("cart_total" in row["goals"], writes(row)), (True, []))
    ok("G05", "report_cart tools within SCOPE", [t for x in loop(row).get("steps") or [] if x["action"] == "report_cart"
                                                  for t in x["tools"] if t not in P.SCOPE["report_cart"]], [])
    s.planner.decider = d = Script("report_cart", lambda st, o: "report_cart" if "report_cart" in o["step"] else "finish", "finish")
    row = say(s, "Lấy thêm một cái Samsung AX40 nữa vào giỏ", resp(intent="place_order",
              requests=[req("add_to_cart", "Lấy thêm một cái Samsung AX40 nữa vào giỏ", "P1")]))
    ok("G05", "second report_cart with unchanged cart is not offered (cart_reported_unchanged); one report, turn ends by finish",
       (d.opts_seen[1]["removed"].get("report_cart"), loop(row).get("stop"),
        sum(1 for x in loop(row).get("steps") or [] if x["action"] == "report_cart")), ("cart_reported_unchanged", "finish", 1))
    ok("G13", "same SKU again: reply says it is already in the cart, no quantity claimed",
       ("cart_item_already" in row["goals"], "đã có trong giỏ" in row["agent_text"], "2 máy" in row["agent_text"]), (True, True, False))
    s.planner.decider = d = Script("finish", "report_cart", "finish")
    row = say(s, "Cho anh thêm cái Samsung AX40 nữa vào giỏ nhé", resp(intent="place_order",
              requests=[req("add_to_cart", "thêm cái Samsung AX40 nữa vào giỏ", "P1")]))
    st = loop(row).get("steps") or []
    ok("G13", "add_to_cart turn: finish blocked until the cart is answered (respond_cart), then ends normally",
       ((st[0].get("status"), st[0].get("missing")) if st else None, loop(row).get("stop")), (("blocked", ["respond_cart"]), "finish"))
    ok("G13", "cart reply: cart_item_already + cart_total, zero order.*", ({"cart_item_already", "cart_total"} <= set(row["goals"]), writes(row)),
       (True, []))
    cart = d.seen[0].get("cart") or {}
    ok("G05", "same SKU again: cart unchanged, shown as already in cart (no quantity inferred)",
       (cart.get("added_this_turn"), len(cart.get("requested_but_already_in_cart") or []), len(s.cart)), ([], 1, 1))
    ok("G05", "same SKU again: no order write", writes(row), [])

# ================================================================== G06: dòng chung sau khi B2 dừng
ok("G06", "B2 post-stop allowlist = R24a, R24b, R25, R35 (no E07 / R36)",
   sorted(planner_variants.B2Jev.post_stop_rows), ["R24a", "R24b", "R25", "R35"])
with Ctx():
    d = Script("answer_ask:price", "finish")
    s = session("g06a", decider=Script("answer_ask:price", "finish"))
    say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    s.planner.decider = Script("answer_ask:price", "finish")
    row = say(s, "Bên shop kia bán rẻ hơn, em bớt cho anh đi, giá AX40 bao nhiêu?",
              resp(intent="negotiate", flags=["mentions_competitor"], asks=["price"], asks_question=True))
    ok("G06", "competitor turn after B2 stop: no_competitor_comment added by R24a",
       ("no_competitor_comment" in row["goals"], "R24a" in row["planner"]["table"], "b2_jev:post_stop" in row["planner"]["table"]),
       (True, True, True))
    ok("G06", "no greet / closing / handoff after stop", bool({"greet", "closing", "handoff"} & set(row["goals"])), False)
    s.planner.decider = Script("answer_ask:price", "finish")
    row = say(s, "Để anh suy nghĩ thêm đã, mà AX40 giá bao nhiêu nhỉ?",
              resp(intent="callback", flags=["defers_decision"], asks=["price"], asks_question=True))
    ok("G06", "deferring turn after B2 stop: defer_ack by R35 (exactly once)",
       (row["goals"].count("defer_ack"), row["planner"]["table"].count("R35")), (1, 1))
    s.planner.decider = Script("answer_ask:price", "finish")
    row = say(s, "Xóa hết thông tin của anh đi em", resp(intent="meta", flags=["wants_data_deleted"], safety=["wants_data_deleted"],
              requests=[{"kind": "forget_me", "evidence": "Xóa hết thông tin của anh"}]))
    ok("G06", "safety / data-deletion terminal row still runs before the owner (no B2 loop)",
       ("b2_jev:jev" in row["planner"]["table"], bool(loop(row))), (False, False))


# ================================================================== G07: unresolved → handoff đúng một lần
def flaky_create(**kw):
    raise TimeoutError("transport timeout after write was sent")


with Ctx(), patch.dict(mt.TOOLS, {"order.create": flaky_create}):
    s = session("g07", decider=Script("answer_ask:price", "finish"))
    say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    s.planner.decider = Script("read_quote:P1", "commit_request:R1", "finish")
    row = say(s, "Chốt Samsung AX40 cho anh", resp(intent="place_order", requests=[req("place_order", "Chốt Samsung AX40", "P1")]))
    n1 = len(calls(row, "handoff.transfer"))
    ok("G07", "unresolved create → handoff in reply, at most one transfer", ("handoff" in row["goals"], n1 <= 1), (True, True))
    any_commit = lambda st, o: next((x for x in o["step"] if x.startswith("commit_request:R")), "finish")   # noqa: E731
    s.planner.decider = Script("read_quote:P1", any_commit, any_commit, "finish")
    row = say(s, "Lên lại đơn đi em", resp(intent="place_order", requests=[req("place_order", "Lên lại đơn", "P1")]))
    ok("G07", "next turn: no retry of create, no second transfer", (len(calls(row, "order.create")), len(calls(row, "handoff.transfer"))), (0, 0))

# ================================================================== G08: bằng chứng từ handler trả lời
with Ctx():
    s = session("g08", decider=Script("answer_ask:price", "finish"))
    say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    s.planner.decider = d = Script("answer_ask:price", "commit_request:R1", "finish")
    row = say(s, "AX40 giờ giá bao nhiêu, ổn thì lấy luôn cho anh", resp(intent="place_order", asks=["price"], asks_question=True,
              requests=[req("place_order", "lấy luôn cho anh", "P1")]))
    st = loop(row).get("steps") or []
    com = next((x for x in st if x["action"] == "commit_request"), {})
    ok("G08", "price answer's own tool results become evidence: commit not blocked for re-reads, writes once",
       (com.get("status"), com.get("missing"), created_skus(row)), ("ok", None, [[AX40]]))
    ok("G08", "Jev state after answering shows evidence for that SKU", any(e.get("final_price_vnd") for e in d.seen[1].get("evidence_this_turn") or []), True)

# ================================================================== G09: bot + câu hỏi sản phẩm
with Ctx():
    d = Script("finish", "answer_ask:price", "finish", "answer_ask:other", "finish")
    s = session("g09", decider=d)
    row = say(s, "Em là người hay máy vậy? Mà Samsung AX40 giá bao nhiêu?",
              resp(intent="price_promo", flags=["asks_if_bot"], asks=["other", "price"], asks_question=True))
    st = loop(row).get("steps") or []
    fins = [x for x in st if x["action"] == "finish"]
    ok("G09", "common is_bot block visible to planner before the loop", "is_bot" in (d.seen[0].get("responses_prepared_before_planner") or {}).get("goals", []), True)
    ok("G09", "first finish blocked on both asks", sorted((fins[0].get("missing") or [])) if fins else None, ["ask:other", "ask:price"])
    ok("G09", "after price answered, `other` is NOT auto-cleared by the bot block", (fins[1].get("missing") if len(fins) > 1 else None), ["ask:other"])
    ok("G09", "price question still answered from tool; is_bot kept", ("quote" in row["goals"], "is_bot" in row["goals"]), (True, True))
    ok("G09", "G10 invariant: answered asks all carry evidence of the topic's kind", all_answered_have_evidence(loop(row)), [])
    ok("G11", "`other` with the bot block: responded_common, no policy lookup added",
       ((loop(row).get("ask_outcome") or {}).get("other", {}).get("outcome"), "policy_answer" in row["goals"], "no_info" in row["goals"]),
       ("responded_common", False, False))

# ================================================================== G11: `other` không tự ánh xạ sang chính sách
with Ctx():
    s = session("g11a", decider=Script("answer_ask:other", "finish"))
    row = say(s, "Em là người hay máy vậy?", resp(intent="meta", flags=["asks_if_bot"], asks=["other"], asks_question=True))
    o = (loop(row).get("ask_outcome") or {}).get("other") or {}
    ok("G11", "pure bot question: is_bot only, other = responded_common (vetted is_bot), turn ends by finish",
       (o.get("outcome"), [e["ref"] for e in o.get("evidence") or []], "policy_answer" in row["goals"], loop(row).get("stop")),
       ("responded_common", ["is_bot"], False, "finish"))
    s = session("g11b", decider=Script("answer_ask:other", "finish"))
    row = say(s, "Shop có xuất hóa đơn đỏ không em?", resp(intent="greeting_or_other", asks=["other"], asks_question=True))
    o = (loop(row).get("ask_outcome") or {}).get("other") or {}
    ok("G11", "other without common block: no automatic policy search → responded_no_source (no_info), not answered",
       (o.get("outcome"), "policy_answer" in row["goals"], "no_info" in row["goals"]), ("responded_no_source", False, True))
    s = session("g11c", decider=Script("read_policy", "answer_ask:other", "finish"))
    row = say(s, "Shop có xuất hóa đơn đỏ không em?", resp(intent="greeting_or_other", asks=["other"], asks_question=True))
    o = (loop(row).get("ask_outcome") or {}).get("other") or {}
    ok("G11", "other after the planner explicitly read policy docs: answered only with policy evidence (else no_source)",
       (o.get("outcome") == "answered" and all(e["kind"] == "policy" for e in o.get("evidence") or []) and bool(o.get("evidence")))
       or o.get("outcome") == "responded_no_source", True)

# ================================================================== G14: đọc lặp + trần tool cứng
with Ctx():
    s = session("g14a", decider=Script("answer_ask:price", "finish"))
    say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    s.planner.decider = d = Script("read_quote:P1", "answer_ask:price", "finish")
    row = say(s, "AX40 giờ giá bao nhiêu em?", PRICE_Q)
    st = loop(row).get("steps") or []
    ans = next((x for x in st if x["action"] == "answer_ask"), {})
    o = (loop(row).get("ask_outcome") or {}).get("price") or {}
    ok("G14", "after read_quote:P1 the same read is no longer offered (evidence_present_this_turn)",
       ("read_quote:P1" in d.opts_seen[1]["step"], d.opts_seen[1]["removed"].get("read_quote:P1")), (False, "evidence_present_this_turn"))
    ok("G14", "price answer reuses this turn's quote view: no extra tool, answered with reused tool evidence",
       (ans.get("tools"), o.get("outcome"), any(e.get("reused_this_turn") for e in o.get("evidence") or []), loop(row).get("tool_calls")),
       ([], "answered", True, 2))
with Ctx({"b2_max_tool_calls": 2}):
    s = session("g14b", decider=Script("answer_ask:price", "finish"))
    row = say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    d0 = (loop(row).get("decisions") or [{}])[0]
    ok("G14", "hard tool cap: step whose max cost exceeds what is left is not offered (removed tool_budget), cap never exceeded",
       (str((d0.get("removed") or {}).get("answer_ask:price", "")).startswith("tool_budget:"), loop(row).get("tool_calls", 0) <= 2,
        "price" in (loop(row).get("unanswered") or {})), (True, True, True))
with Ctx():
    for name, text, d in (("g14c1", "Samsung AX40 giá bao nhiêu em?", PRICE_Q), ("g14c2", "Máy lọc không khí AirPure X dùng cho phòng bao nhiêu mét vuông em?", ATTR_Q)):
        s = session(name, decider=Script(lambda st, o: next((x for x in o["step"] if x.startswith("answer_ask:")), "finish"), "finish"))
        row = say(s, text, d)
        ok("G14", f"{name}: no step exceeded its estimated cost; turn within cap",
           ([x for x in loop(row).get("decisions") or [] if x.get("cost_overrun")], loop(row).get("tool_calls", 0) <= settings.b2_max_tool_calls), ([], True))

# ================================================================== G15: trần 13 (duyệt 13/11) đủ cho tư vấn danh mục lớn nhất
from core.config import Settings  # noqa: E402
with Ctx():
    A = P.T._A()
    cats = sorted({p["category"] for p in A.mt.PRODUCTS} | {cc for _, cc in A.CATEGORY_WORDS})
    worst = max(1 + sum(1 for p in A.mt.PRODUCTS if p["category"].startswith(c) and p["list_price_vnd"] >= 400000) + 2 + 2 for c in cats)
    ok("G15", "default cap is 13 and the worst recommend-with-focus cost (1 + n≥400k + 2 + 2) fits under it",
       (Settings().b2_max_tool_calls, worst <= Settings().b2_max_tool_calls), (13, True))

# ================================================================== G16–G18: bằng chứng giá theo ngữ cảnh giỏ (13/11 vòng giỏ)
AIR2 = "thứ 2 trong cùng đơn"                     # tên AIR-2ND-50 (catalog/promotions.json)


def cart_ax40_apx(name):
    s = session(name, decider=Script("answer_ask:price", "finish"))
    say(s, "Samsung AX40 với AirPure X giá sao em?", PRICE_Q)
    s.planner.decider = Script("report_cart", "finish")
    say(s, "Thêm Samsung AX40 vào giỏ giúp anh", resp(intent="place_order", requests=[req("add_to_cart", "Thêm Samsung AX40 vào giỏ")]))
    return s


def cart_prefs(s):
    return {k for k, v in s.reqs.refmap.items() if k.startswith("P") and v.get("type") == "product"
            and any(P._parent(x) in {P._parent(c) for c in s.cart} for x in v.get("skus") or ())}


ADD_APX = resp(intent="place_order", requests=[req("add_to_cart", "Thêm cả AirPure X vào giỏ")])
with Ctx():
    # G16a (N10): báo giỏ rồi Jev muốn đọc lại giá / báo lại → không còn trong danh mục; finish
    s = cart_ax40_apx("g16a")
    s.planner.decider = d = Script("report_cart", lambda st, o: next((x for x in o["step"] if x.startswith("read_quote:")
                                                                      and x[11:] in cart_prefs(s)), None)
                                   or ("report_cart" if "report_cart" in o["step"] else "finish"), "finish")
    row = say(s, "Thêm cả AirPure X vào giỏ nữa", ADD_APX)
    rm = d.opts_seen[1]["removed"]
    txt = row["agent_text"]
    ok("G16", "after report_cart: read_quote of cart items removed (evidence_present_this_turn), report_cart removed (unchanged)",
       (sorted(k for k, v in rm.items() if k.startswith("read_quote:") and v == "evidence_present_this_turn"),
        rm.get("report_cart")), (sorted(f"read_quote:{k}" for k in cart_prefs(s)), "cart_reported_unchanged"))
    ok("G16", "N10: one report_cart, finish, 2 items, total 8.935.000đ, no order write",
       (sum(1 for x in loop(row).get("steps") or [] if x["action"] == "report_cart"), loop(row).get("stop"), len(s.cart),
        "8.935.000đ" in txt, writes(row)), (1, "finish", 2, True, []))
    ok("G16", "N10 text: no 'Ngoài ra', AirPure X cart line names AIR-2ND-50, no unlabeled standalone 4.890.000đ",
       ("Ngoài ra" in txt, "2.445.000đ (áp dụng" in txt and AIR2 in txt, "4.890.000đ" in txt), (False, True, False))
    ok("G16", "trace records price_context (noted AirPure X)", "SKU-AP-X" in str((loop(row).get("price_context") or {}).get("noted")), True)
    # G16b: Jev đọc giá AirPure X TRƯỚC khi báo giỏ (khách không hỏi giá) → khối giá riêng bị bỏ, dòng giỏ thay
    s = cart_ax40_apx("g16b")
    s.planner.decider = d = Script(lambda st, o: next((x for x in o["step"] if x.startswith("read_quote:")
                                                       and "AirPure X" in o["desc"][x]), "report_cart"), "report_cart", "finish")
    row = say(s, "Thêm cả AirPure X vào giỏ nữa", ADD_APX)
    txt = row["agent_text"]
    ok("G16", "read standalone price before report_cart, no price ask → quote block dropped (dòng giỏ thay), no two prices",
       ("quote" in row["goals"], "4.890.000đ" in txt, "2.445.000đ" in txt,
        any(x.get("why") == "in_cart_no_price_ask" for x in (loop(row).get("price_context") or {}).get("dropped") or [])),
       (False, False, True, True))

with Ctx():
    # G17 (N12): giá mua riêng của mẫu đang trong giỏ
    s = cart_ax40_apx("g17a")
    s.planner.decider = Script("report_cart", "finish")
    say(s, "Thêm cả AirPure X vào giỏ nữa", ADD_APX)
    s.planner.decider = Script("answer_ask:price", "finish")
    row = say(s, "Nếu mua riêng AirPure X thì giá bao nhiêu em?", PRICE_Q)
    o = (loop(row).get("ask_outcome") or {}).get("price") or {}
    txt = row["agent_text"]
    ok("G17", "N12: standalone price 4.890.000đ answered from get_quote; 2.445.000đ absent; cart unchanged; no write",
       ("4.890.000đ" in txt, "2.445.000đ" in txt, o.get("outcome"), any(e["kind"] == "tool:pricing.get_quote" for e in o.get("evidence") or []),
        len(s.cart), writes(row)), (True, False, "answered", True, 2, []))
    s.planner.decider = Script("answer_ask:price", "report_cart", "finish")
    row = say(s, "Nếu mua riêng AirPure X thì giá bao nhiêu em?", PRICE_Q)
    txt = row["agent_text"]
    ok("G17", "standalone price + cart in same reply: quote labeled 'mua riêng', cart line names AIR-2ND-50",
       ("mua riêng giá 4.890.000đ" in txt, "2.445.000đ (áp dụng" in txt and AIR2 in txt), (True, True))

with Ctx():
    # G18 (N13): KM của mẫu trong giỏ + tổng giỏ
    s = cart_ax40_apx("g18a")
    s.planner.decider = Script("report_cart", "finish")
    say(s, "Thêm cả AirPure X vào giỏ nữa", ADD_APX)
    s.planner.decider = d = Script("answer_ask:promo", "answer_ask:cart_total", lambda st, o: "report_cart" if "report_cart" in o["step"] else "finish", "finish")
    row = say(s, "AirPure X trong giỏ được ưu đãi gì, tổng giỏ bao nhiêu em?", resp(intent="price_promo", asks=["promo", "cart_total"], asks_question=True))
    txt = row["agent_text"]
    ok("G18", "N13: cart line 2.445.000đ with AIR-2ND-50, total 8.935.000đ; standalone 4.890.000đ only labeled 'mua riêng'",
       ("2.445.000đ (áp dụng" in txt and AIR2 in txt, "8.935.000đ" in txt, "4.890.000đ" not in txt or "mua riêng" in txt), (True, True, True))
    ok("G18", "cart answered via answer_ask:cart_total → report_cart not offered again (unchanged), finish, no write",
       (d.opts_seen[2]["removed"].get("report_cart"), loop(row).get("stop"), writes(row)), ("cart_reported_unchanged", "finish", []))

# ================================================================== G19–G21: phụ kiện + một nguồn cập nhật giỏ (13/11, duyệt)
APY, FLT = "SKU-AP-Y", "SKU-AP-FLT-X"
PHI = next(p["sku"] for p in mt.PRODUCTS if "Philips 6.2L" in p["name"])
KAR = next(p["sku"] for p in mt.PRODUCTS if "Karofi 9" in p["name"])
with Ctx():
    norm = agent.normalize_accessories
    T4 = "Thêm Philips 6.2L nữa, với một bộ màng lọc thay thế cho AirPure Y luôn nhé."
    ok("G19", "'màng lọc thay thế cho AirPure Y' → phụ kiện của máy (máy không còn là đối tượng)",
       norm(T4, agent.find_products(T4))[0], [PHI, FLT])
    t = "Lấy AirPure Y với một bộ màng lọc nữa nhé"
    ok("G19", "'màng lọc' không gắn tên máy, một máy trong câu → thêm màng lọc của máy đó, máy giữ nguyên",
       norm(t, agent.find_products(t))[0], [APY, FLT])
    t = "Mua AirPure Y có được tặng màng lọc không em?"
    ok("G19", "câu nói quà tặng → không đổi", norm(t, agent.find_products(t))[0], agent.find_products(t))
    t = "AirPure X với AirPure Y thì màng lọc loại nào em?"
    ok("G19", "hai máy, 'màng lọc' không gắn máy nào → không đoán (ambiguous)",
       (norm(t, agent.find_products(t))[0], norm(t, agent.find_products(t))[1]["ambiguous"]), (agent.find_products(t), True))
    ok("G19", "'màng lọc' không nhắc máy, mẫu đang bàn AirPure Y → màng lọc của mẫu đang bàn",
       norm("Màng lọc giá bao nhiêu em?", [], APY)[0], [FLT])

    # G20 (V3-055 t4): ứng viên cho DeepSeek đã chuẩn hóa; ref P2 = màng lọc; giỏ không có máy AirPure Y; một nguồn
    s = session("g20", decider=Script("answer_ask:price", "finish"))
    say(s, "AirPure Y giá bao nhiêu em?", PRICE_Q)
    s.planner.decider = Script("report_cart", "finish")
    say(s, "Lấy thêm máy lọc nước RO Karofi 9 lõi", resp(intent="place_order", requests=[req("add_to_cart", "Lấy thêm máy lọc nước RO Karofi 9 lõi", "P1")]))
    s.planner.decider = d = Script("report_cart", "finish")
    row = say(s, T4, resp(intent="place_order", flags=["agrees_to_buy"],
                          requests=[req("add_to_cart", "Thêm Philips 6.2L nữa", "P1"),
                                    req("add_to_cart", "một bộ màng lọc thay thế cho AirPure Y", "P2")]))
    rm = {k: v["skus"] for k, v in s.reqs.refmap.items() if k in ("P1", "P2")}
    ok("G20", "ứng viên DeepSeek: P1 = Philips, P2 = màng lọc (đã chuẩn hóa trước khi dựng danh sách)",
       (rm.get("P1"), rm.get("P2")), ((PHI,), (FLT,)))
    ok("G20", "giỏ: Karofi + Philips + màng lọc, KHÔNG có máy AirPure Y; nguồn duy nhất target_ref; không ghi đơn",
       (sorted(s.cart), APY in s.cart, (loop(row).get("cart") or {}).get("source"), writes(row)),
       (sorted([KAR, PHI, FLT]), False, "target_ref", []))
    cart = d.seen[0].get("cart") or {}
    ok("G20", "Jev thấy giỏ vừa thêm đúng Philips + màng lọc (mỗi món một lần)",
       sorted(cart.get("added_this_turn") or []), sorted(["Nồi chiên không dầu Philips 6.2L", "Màng lọc thay thế AirPure X/Y"]))

    # G21: không suy mua phụ kiện chỉ vì được nhắc tên — thiếu căn cứ → hỏi rõ, không thêm
    s = session("g21a", decider=Script("report_cart", "finish"))
    t = "Thêm Philips 6.2L vào giỏ, mà màng lọc AirPure Y bao lâu thay một lần em?"
    row = say(s, t, resp(intent="place_order", requests=[req("add_to_cart", "Thêm Philips 6.2L vào giỏ")]))
    ok("G21", "yêu cầu thêm không nhắc màng lọc, câu có nhắc màng lọc → chỉ thêm Philips, hỏi rõ phụ kiện",
       (s.cart, "ask_accessory_intent" in row["goals"], "muốn thêm cả Màng lọc thay thế AirPure X/Y vào giỏ" in row["agent_text"]),
       ([PHI], True, True))
    s = session("g21b", decider=Script("report_cart", "finish"))
    t = "Thêm Philips 6.2L với màng lọc AirPure Y vào giỏ"
    row = say(s, t, resp(intent="place_order", requests=[req("add_to_cart", "Thêm Philips 6.2L với màng lọc AirPure Y vào giỏ", "P1")]))
    ok("G21", "bộ hiểu chỉ nhắm Philips, câu yêu cầu có màng lọc → không tự thêm màng lọc, hỏi rõ",
       (s.cart, "ask_accessory_intent" in row["goals"]), ([PHI], True))
    s = session("g21c", decider=Script("report_cart", "finish"))
    t = "Cho chị một bộ màng lọc thay thế cho AirPure Y vào giỏ"
    row = say(s, t, resp(intent="place_order", requests=[req("add_to_cart", "Cho chị một bộ màng lọc thay thế cho AirPure Y vào giỏ")]))
    ok("G21", "câu yêu cầu nói rõ màng lọc → thêm màng lọc (không thêm máy), không hỏi lại",
       (s.cart, "ask_accessory_intent" in row["goals"], writes(row)), ([FLT], False, []))

print(f"\n{PASS[0]} OK, {len(FAIL)} lỗi")
if FAIL:
    print("LỖI:", FAIL)
sys.exit(1 if FAIL else 0)
