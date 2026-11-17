"""Kiểm XÁC ĐỊNH (không API) cho patch 15/11 (§8.17, duyệt): BTCL-066 thu hẹp (A1 / A2), ngữ cảnh GEN-T16 (B), F5 tối thiểu (C1–C3).

A1 bước gợi ý (answer_ask:recommend) không ra nội dung mà khách có mẫu của chính mình → đọc giá + kho ĐÚNG mẫu đó và hỏi khách muốn
   biết gì về mẫu; ask_outcome = needs_customer (báo giá tự động KHÔNG là đã trả lời tư vấn). Đủ nhánh của h_recommend: hỏi nhu
   cầu / gợi ý mẫu khác / gợi ý trùng mẫu đang bàn / không gợi ý được; không có mẫu; nhiều mẫu trong câu. Không vượt trần tool.
A2 vòng dừng (lỗi / tuple sai / deadline) mà câu hỏi còn treo, lượt không có nội dung → hỏi lại đúng loại (về mẫu của khách /
   xin nói lại); không gọi tool; ask vẫn ghi unanswered.
B  ngữ cảnh bộ hiểu có nội dung nhóm CART / ALL + các món của đề nghị đang chờ xác nhận.
C1 "ALL" không tự thành giỏ / đơn: thêm giỏ hoặc lệnh đặt nhắm ALL → không đổi giỏ, không order.create, xin xác nhận liệt kê đúng
   các món; khách đồng ý → đơn đúng các món đó.
C2 đề nghị đặt còn hiệu lực qua lượt hỏi COD / nói thanh toán / đọc địa chỉ; mất khi khách nêu mẫu khác / từ chối.
C3 câu đặt KHÔNG nêu mẫu khi đề nghị T đang chờ → đơn đúng T (dù model chọn ref màng lọc); câu nêu mẫu khác → không dùng T; câu chỉ
   ý định → F8 vẫn chặn (xin xác nhận đúng T, không ghi).
K  đối chứng: B1 không đổi ở C1 (ALL vẫn vào giỏ như cũ).

DeepSeek = phản hồi dựng sẵn theo hợp đồng v2; Jev = bộ quyết định có kịch bản; tool = mock BTC; memory SQLite tạm.
Dùng: python tests/b2_btcl066_f5_check.py"""
import os
import sys
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
tmp = tempfile.mkdtemp(prefix="b2_b066_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "v.db").replace("\\", "/")
os.environ["TOOL_TRANSPORT"] = "direct"
os.environ.setdefault("RUN_PROFILE", "local")
os.environ.setdefault("RAG_MODE", "bm25")
os.environ["LLM_CACHE"] = "off"

import types  # noqa: E402
_src = open(os.path.join(ROOT, "tests", "b2_round_f_check.py"), encoding="utf-8").read()
F = types.ModuleType("b2_round_f_frame")
F.__file__ = os.path.join(ROOT, "tests", "b2_round_f_check.py")
exec(compile(_src.split("# ================================================================== H8")[0], F.__file__, "exec"), F.__dict__)
from harness import agent  # noqa: E402
from harness import plan_primitives as P  # noqa: E402

FAIL, PASS = [], [0]


def ok(group, name, got, want=True):
    if got == want:
        PASS[0] += 1
        print(f"OK   [{group}] {name}", flush=True)
    else:
        FAIL.append((group, name))
        print(f"FAIL [{group}] {name}: got={got!r} want={want!r}", flush=True)


PRO, APX, APY, FLT = "SKU-AP-PRO", "SKU-AP-X", "SKU-AP-Y", "SKU-AP-FLT-P"
WRITES = ("order.create", "order.update", "handoff.transfer", "schedule.callback")
REC = F.resp(intent="product_inquiry", asks=["recommend"], asks_question=True)


def quoted(row):
    return [P._parent(t["args"]["sku"]) for t in row["tool_calls"] if t["name"] == "pricing.get_quote" and not t["args"].get("basket_skus")]


def writes(row):
    return [t["name"] for t in row["tool_calls"] if t["name"] in WRITES]


def outcome(row, topic):
    return (F.loop(row).get("ask_outcome") or {}).get(topic, {}).get("outcome")


def with_focus(name, decider, sku=APX):
    """Phiên có mẫu đang bàn của khách (lượt 1 khách nêu tên mẫu, không hỏi gì)."""
    s = F.session(name, decider=F.Script("finish"))
    F.say(s, f"Chị đang xem {agent.product_name(sku).replace('Máy lọc không khí ', '')}.", F.resp(intent="product_inquiry"))
    s.focus = sku
    s.planner.decider = decider          # lượt 1 chỉ finish; bộ quyết định của ca bắt đầu từ lượt cần kiểm
    return s


# ------------------------------------------------------------------ A1: bước gợi ý giữ đúng mẫu của khách
def rec_turn(name, rec_value, text="Em tư vấn giúp chị với.", focus=APX, d=None):
    with patch.object(agent.CallSession, "_recommend", lambda self, t: rec_value):
        dec = F.Script("answer_ask:recommend", "finish")
        s = with_focus(name, dec, focus) if focus else F.session(name, decider=dec)
        row = F.say(s, text, d or REC)
    return s, row


with F.Ctx():
    s, row = rec_turn("a1_none", None)
    ok("A1", "không gợi ý được + có mẫu của khách → đọc giá ĐÚNG mẫu đó (AirPure X), không mẫu khác", quoted(row), [APX])
    ok("A1", "có câu hỏi lại về mẫu (ask_which_attribute) + khối báo giá",
       ("ask_which_attribute" in row["goals"], "quote" in row["goals"]), (True, True))
    ok("A1", "ask recommend = needs_customer, KHÔNG answered", (outcome(row, "recommend"), "recommend" in F.loop(row).get("answered", [])),
       ("needs_customer", False))
    ok("A1", "câu trả lời nói đúng mẫu + hỏi muốn biết gì", ("AirPure X" in row["agent_text"], "muốn biết thông tin gì" in row["agent_text"]),
       (True, True))
    ok("A1", "không ghi, không vượt ước tính tool", (writes(row), [d.get("cost_overrun") for d in F.loop(row)["decisions"] if d.get("cost_overrun")]),
       ([], []))
    print("   →", row["agent_text"])

    s, row = rec_turn("a1_same", APX)
    ok("A1", "gợi ý trùng mẫu đang bàn → như trên: đọc giá mẫu đó + hỏi lại, needs_customer",
       (quoted(row), "ask_which_attribute" in row["goals"], outcome(row, "recommend")), ([APX], True, "needs_customer"))

    s, row = rec_turn("a1_other", PRO)
    ok("A1", "đối chứng: gợi ý mẫu khác → như cũ (recommend + giá mẫu gợi ý, answered), không ask_which_attribute",
       ("recommend" in row["goals"], PRO in quoted(row), outcome(row, "recommend"), "ask_which_attribute" in row["goals"]),
       (True, True, "answered", False))

    s, row = rec_turn("a1_need", "ASK_NEED")
    ok("A1", "đối chứng: hỏi nhu cầu → như cũ (ask_need, needs_customer), không đọc giá",
       ("ask_need" in row["goals"], quoted(row), outcome(row, "recommend")), (True, [], "needs_customer"))

    s, row = rec_turn("a1_nofocus", None, focus=None)
    ok("A1", "không có mẫu nào → như cũ (hỏi mẫu nào), không đọc giá",
       (quoted(row), "ask_which_attribute" in row["goals"], outcome(row, "recommend")), ([], False, "needs_customer"))

    s, row = rec_turn("a1_two", None, text="AirPure X với AirPure Y thì em tư vấn giúp chị.")
    ok("A1", "câu nêu HAI mẫu → hỏi mẫu nào (ask_product), không đọc giá mẫu nào",
       ("ask_product" in row["goals"], quoted(row), outcome(row, "recommend")), (True, [], "needs_customer"))

    # bộ quyết định chọn lại bước gợi ý sau khi đã needs_customer: ask không còn trong danh mục (không lặp, không no_progress)
    with patch.object(agent.CallSession, "_recommend", lambda self, t: None):
        dec = F.Script("answer_ask:recommend", F.pick("answer_ask:recommend", "finish"))
        s = with_focus("a1_repick", dec)
        row = F.say(s, "Em tư vấn giúp chị với.", REC)
    ok("A1", "sau needs_customer: bước gợi ý không còn trong danh mục → finish, stop=finish",
       (F.loop(row)["stop"], "answer_ask:recommend" in dec.opts_seen[-1]["step"]), ("finish", False))

    # trần tool: còn < 2 tool → bước gợi ý (đọc giá mẫu của khách) không được đưa vào danh mục
    with patch.object(agent.CallSession, "_recommend", lambda self, t: None):
        with F.Ctx({"b2_max_tool_calls": 1}):
            dec = F.Script(F.pick("answer_ask:recommend", "finish"))
            s = with_focus("a1_budget", dec)
            row = F.say(s, "Em tư vấn giúp chị với.", REC)
    ok("A1", "trần tool 1: bước gợi ý bị lọc (tool_budget), không gọi get_quote",
       (str((F.loop(row)["decisions"][0].get("removed") or {}).get("answer_ask:recommend", "")).startswith("tool_budget"), quoted(row)),
       (True, []))


# ------------------------------------------------------------------ A2: câu trả lời khi dừng
def boom(state, opts):
    raise RuntimeError("jev down")


PRICE = F.resp(intent="price_promo", asks=["price"], asks_question=True)
COD = F.resp(intent="policy_question", asks=["cod"], asks_question=True)
with F.Ctx():
    for name, dec, extra in (("a2_err", boom, {}), ("a2_invalid", F.Script("khong_co_buoc_nay"), {}),
                             ("a2_deadline", F.Script("finish"), {"b2_deadline_s": 1e-9})):
        with F.Ctx(extra):
            s = with_focus(name, dec)
            row = F.say(s, "Giá bao nhiêu em?", PRICE)
        lp = F.loop(row)
        ok("A2", f"{name}: hỏi giá, dừng cứng, có mẫu → hỏi lại về mẫu (ask_which_attribute), không tool trong lượt",
           ("ask_which_attribute" in row["goals"], row["tool_calls"], lp.get("halt_tool_calls")), (True, [], 0))
        ok("A2", f"{name}: ask giá vẫn ghi chưa trả lời (unanswered)", "price" in (lp.get("unanswered") or {}), True)
    print("   →", row["agent_text"])
    s = with_focus("a2_cod", boom)
    row = F.say(s, "Có ship COD không em?", COD)
    ok("A2", "hỏi COD (không phải câu hỏi sản phẩm), dừng cứng → xin nói lại (ask_repeat), không tool",
       ("ask_repeat" in row["goals"], "ask_which_attribute" in row["goals"], row["tool_calls"]), (True, False, []))
    s = F.session("a2_nofocus", decider=boom)
    row = F.say(s, "Giá bao nhiêu em?", PRICE)
    ok("A2", "không có mẫu → xin nói lại, vòng planner không gọi tool", ("ask_repeat" in row["goals"], F.loop(row).get("tool_calls"),
                                                                        F.loop(row).get("halt_tool_calls")), (True, 0, 0))
    s = with_focus("a2_hold", boom)
    row = F.say(s, "Giá bao nhiêu em?", F.resp(intent="price_promo", asks=["price"], asks_question=True,
                                                ambiguity={"level": "needs_clarification"}))
    ok("A2", "lượt mơ hồ: chỉ MỘT câu xin nói lại (không thêm câu A2)", (row["goals"].count("ask_repeat"), "ask_which_attribute" in row["goals"]),
       (1, False))


# ------------------------------------------------------------------ B: ngữ cảnh nhóm + đề nghị
with F.Ctx():
    s = F.session("b_ctx")
    s.cart, s.discussed = [FLT], [PRO, APX, FLT]
    s.reqs.proposal = {"goal": "confirm_order", "kind": "place_order", "target": {"type": "product", "skus": (PRO, APX)}}
    ctx = s.reqs.context(s)
    ok("B", "groups.CART = màng lọc Pro", ctx["groups"].get("CART"), [agent.product_name(FLT)])
    ok("B", "groups.ALL = Pro + X + màng lọc", ctx["groups"].get("ALL"), [agent.product_name(x) for x in (PRO, APX, FLT)])
    ok("B", "agent_proposal_items = các món của đề nghị", ctx["agent_proposal_items"], [agent.product_name(PRO), agent.product_name(APX)])
    s.reqs.proposal = None
    ok("B", "không có đề nghị → agent_proposal_items None", s.reqs.context(s)["agent_proposal_items"], None)


# ------------------------------------------------------------------ C1–C3: giỏ + xác nhận đúng đối tượng
def basket(name, decider=None):
    s = F.session(name, decider=F.Script("finish"))
    F.say(s, "Chị xem AirPure Pro với AirPure X.", F.resp(intent="product_inquiry"))
    s.discussed = [PRO, APX]
    s.planner.decider = decider or F.BUYER()
    return s


def proposal_skus(s):
    return sorted(P._parent(x) for x in ((s.reqs.proposal or {}).get("target") or {}).get("skus") or ())


PAY_BANK = [{"slot": "payment", "span": "chuyển khoản", "label": "bank", "stance": "chosen", "subject": "self"}]
ACCEPT = lambda ev: F.resp(intent="place_order", response_to_agent={"act": "accept", "evidence": ev}, observations=PAY_BANK)  # noqa: E731


def _need_then_commit(state, opts):
    """Bộ quyết định test cho lượt đặt: đọc đúng bằng chứng executor báo thiếu (missing read_quote / read_stock), không thì thực
    hiện yêu cầu; hết việc → finish."""
    for st in reversed(state["steps_done"]):
        for m in st.get("missing") or []:
            if str(m).startswith(("read_quote:", "read_stock:")) and m in opts["step"]:
                return m
    return next((x for x in opts["step"] if x.startswith("commit_request:")), "finish")


def fresh(s):
    """Bộ quyết định mới cho lượt kế (kịch bản của lượt trước không mang sang)."""
    s.planner.decider = F.Script(*[_need_then_commit] * 8)
with F.Ctx():
    s = basket("c1_cart")
    row = F.say(s, "Lấy đủ cả hai vào giỏ cho chị.", F.resp(intent="place_order", requests=[F.req("add_to_cart", "Lấy đủ cả hai", "ALL")]))
    ok("C1", "thêm giỏ nhắm ALL → giỏ KHÔNG đổi, không ghi", (list(s.cart), writes(row)), ([], []))
    ok("C1", "xin xác nhận liệt kê đúng 2 món", ("confirm_order" in row["goals"], proposal_skus(s)), (True, sorted([PRO, APX])))
    ok("C1", "câu xác nhận nêu cả hai mẫu", ("AirPure Pro" in row["agent_text"], "AirPure X" in row["agent_text"]), (True, True))
    print("   →", row["agent_text"])
    fresh(s)
    row = F.say(s, "Ok em, chị chuyển khoản nhé.", ACCEPT("Ok em"))
    # giá từng món trong giỏ (quote_order, KM máy thứ hai) khác giá mua riêng đã báo → revision_changed: xin xác nhận lại theo
    # tổng giỏ (hành vi có sẵn, không ghi); khách đồng ý lần nữa → đơn đúng 2 món
    ok("C1", "đồng ý lần 1: giá trong giỏ khác giá đã báo → không ghi, xin xác nhận lại đúng 2 món kèm tổng giỏ",
       (writes(row), "confirm_order" in row["goals"], "cart_total" in row["goals"], proposal_skus(s)), ([], True, True, sorted([PRO, APX])))
    print("   →", row["agent_text"])
    fresh(s)
    # V41 (15/11): câu "Ok em." không chứa "chuyển khoản" → phản hồi dựng sẵn không được kèm quan sát thanh toán đó (span không có
    # trong câu bị bộ hiểu loại; V41-1 fail-closed khi không định vị được phần thanh toán). Thanh toán đã biết từ lượt trước.
    row = F.say(s, "Ok em.", F.resp(intent="place_order", response_to_agent={"act": "accept", "evidence": "Ok em"}))
    ok("C1", "đồng ý lần 2 → đơn đúng 2 món (không thêm món nào)", sorted(F.created_parents(row)), sorted([PRO, APX]))

    s = basket("c1_cmd")
    row = F.say(s, "Chốt hết cho chị nhé.", F.ORDER("Chốt hết cho chị", ref="ALL"))
    ok("C1", "lệnh đặt rõ nhắm ALL → KHÔNG order.create, cổng all_unconfirmed, xin xác nhận đúng 2 món",
       (writes(row), (s.reqs.order_gate or {}).get("why"), proposal_skus(s)), ([], "all_unconfirmed", sorted([PRO, APX])))

    # C2 + C3: đề nghị [Pro, X] còn qua COD / thanh toán / địa chỉ; "chốt giúp chị" model chọn màng lọc → đơn đúng Pro + X
    # V41-2 (15/11): đề nghị phải KÈM giá từng máy đã báo (bộ quyết định đọc giá ở lượt "chốt hết") thì ca C3 bên dưới mới đúng là
    # "giá giỏ khác nội dung đã nói"; bản v40 không đọc giá → revision rỗng → không có gì để so (ca không kiểm được giá đổi).
    s = basket("c2_chain")
    F.say(s, "Chốt hết cho chị nhé.", F.ORDER("Chốt hết cho chị", ref="ALL"))
    s.planner.decider = F.Script(*[F.pick("answer_ask:", "commit_request:")] * 8)
    t0 = proposal_skus(s)
    r_cod = F.say(s, "Có ship COD không em?", COD)
    k1 = proposal_skus(s)
    r_pay = F.say(s, "Chị chuyển khoản nhé.", F.resp(intent="greeting_or_other", observations=PAY_BANK))
    k2 = proposal_skus(s)
    ADDR = "18 Phan Đình Giót, Thanh Trì, Hà Nội"
    r_addr = F.say(s, f"Giao về {ADDR} nhé.", F.resp(intent="greeting_or_other",
                                                      observations=[{"slot": "address", "span": ADDR, "stance": "stated", "subject": "self"}]))
    k3 = proposal_skus(s)
    ok("C2", "đề nghị [Pro, X] còn sau lượt hỏi COD / nói chuyển khoản / đọc địa chỉ", (t0, k1, k2, k3), (sorted([PRO, APX]),) * 4)
    ok("C2", "các lượt xen giữa không ghi, không mở yêu cầu đặt",
       (writes(r_cod) + writes(r_pay) + writes(r_addr), [r["kind"] for r in s.reqs.items if r["status"] in ("open", "conditional")]), ([], []))
    s.discussed = [PRO, APX, FLT]
    s.cart = [FLT]
    fresh(s)
    row = F.say(s, "Ok em chốt giúp chị nhé.", F.ORDER("chốt giúp chị", ref="P3"))
    # V41-2 (15/11, duyệt): C3 mang revision của đề nghị. Đề nghị [Pro, X] nêu giá TỪNG máy; giá trong giỏ (quote_order, KM máy thứ
    # hai AIR-2ND-50) khác nội dung đã nói → revision_changed → không ghi, xin xác nhận lại theo tổng giỏ (như đường đồng ý C1);
    # khách đồng ý → đơn đúng Pro + X (không màng lọc mà model chọn).
    ok("C3", "câu đặt không nêu mẫu, giá giỏ khác giá đã nói → không ghi, xin xác nhận lại đúng Pro + X kèm tổng giỏ",
       (writes(row), "confirm_order" in row["goals"], "cart_total" in row["goals"], proposal_skus(s)), ([], True, True, sorted([PRO, APX])))
    fresh(s)
    row = F.say(s, "Ok em.", F.resp(intent="greeting_or_other", response_to_agent={"act": "accept", "evidence": "Ok em"}))
    ok("C3", "đồng ý sau xác nhận lại → đơn ĐÚNG Pro + X (không màng lọc)", sorted(F.created_parents(row)), sorted([PRO, APX]))
    oc = F.calls(row, "order.create")
    ok("C3", "đơn ghi địa chỉ + thanh toán khách đã nói ở lượt xen giữa",
       ([c["args"].get("address") for c in oc], [c["args"].get("payment") not in (None, "COD") for c in oc]), ([ADDR], [True]))
    print("   →", row["agent_text"])

    s = basket("c2_other")
    F.say(s, "Chốt hết cho chị nhé.", F.ORDER("Chốt hết cho chị", ref="ALL"))
    F.say(s, "Thế còn AirPure Y thì sao em?", F.resp(intent="product_inquiry"))
    ok("C2", "khách nêu mẫu ngoài đề nghị → đề nghị cũ mất", s.reqs.proposal, None)
    s = basket("c2_decline")
    F.say(s, "Chốt hết cho chị nhé.", F.ORDER("Chốt hết cho chị", ref="ALL"))
    F.say(s, "Thôi để chị nghĩ thêm.", F.resp(intent="greeting_or_other", response_to_agent={"act": "decline", "evidence": "Thôi để chị nghĩ thêm"}))
    ok("C2", "khách từ chối → đề nghị mất", s.reqs.proposal, None)

    s = basket("c3_named")
    F.say(s, "Chốt hết cho chị nhé.", F.ORDER("Chốt hết cho chị", ref="ALL"))
    fresh(s)
    row = F.say(s, "Thôi chốt cho chị AirPure Y thôi.", F.ORDER("chốt cho chị AirPure Y", ref="P1"))
    ok("C3", "câu nêu mẫu khác → không dùng đề nghị cũ: đơn đúng AirPure Y", F.created_parents(row), [APY])

    s = basket("c3_intent")
    F.say(s, "Chốt hết cho chị nhé.", F.ORDER("Chốt hết cho chị", ref="ALL"))
    row = F.say(s, "Ừ chị cũng muốn lấy.", F.ORDER("chị cũng muốn lấy", ref="P1"))
    ok("C3", "câu chỉ ý định khi đề nghị T đang chờ → F8 chặn (intent_only), không ghi, xin xác nhận đúng T",
       (writes(row), (s.reqs.order_gate or {}).get("why"), proposal_skus(s)), ([], "intent_only", sorted([PRO, APX])))

    # V41-2 đối chứng: revision KHÔNG đổi (2 món không có KM gộp: giá giỏ = giá từng món đã nói) → C3 tạo đơn ngay, đúng 2 món
    RO9, FAN = "SKU-WF-RO9", "SKU-FAN-DC1"
    s = F.session("c3_same_rev", decider=F.Script("finish"))
    F.say(s, "Chị xem máy lọc nước RO Karofi 9 lõi với quạt Panasonic F-409.", F.resp(intent="product_inquiry"))
    s.discussed = [RO9, FAN]
    s.planner.decider = F.BUYER()
    F.say(s, "Chốt hết cho chị nhé.", F.ORDER("Chốt hết cho chị", ref="ALL"))
    pre = proposal_skus(s)
    fresh(s)
    row = F.say(s, "Ok em chốt giúp chị nhé.", F.ORDER("chốt giúp chị", ref=None))
    ok("C3", "đối chứng revision không đổi: đề nghị [RO9, quạt] → 'chốt giúp chị' tạo đơn ngay đúng 2 món",
       (pre, sorted(F.created_parents(row))), (sorted([RO9, FAN]), sorted([RO9, FAN])))

with F.Ctx({"planner_variant": "b1"}):
    s = F.session("k_b1", variant="b1")
    F.say(s, "Chị xem AirPure Pro với AirPure X.", F.resp(intent="product_inquiry"))
    s.discussed = [PRO, APX]
    F.say(s, "Lấy đủ cả hai vào giỏ cho chị.", F.resp(intent="place_order", requests=[F.req("add_to_cart", "Lấy đủ cả hai", "ALL")]))
    ok("K", "B1 không đổi: ALL vẫn vào giỏ", sorted(P._parent(x) for x in s.cart), sorted([PRO, APX]))

print(f"\n{PASS[0]} OK, {len(FAIL)} lỗi")
if FAIL:
    print("LỖI:", FAIL)
raise SystemExit(1 if FAIL else 0)
