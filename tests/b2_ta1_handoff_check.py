"""Kiểm XÁC ĐỊNH (không API) cho hai sửa 14/11 (§8.14), theo đối tượng / trạng thái, không regex đoán ý:

T  TA1: lượt đầu khách quay lại nêu (parser catalog) một mẫu KHÁC mẫu đã tư vấn → câu chào vẫn nhắc đúng lịch sử (ngày + mẫu đã
   tư vấn) nhưng bỏ giá cũ của mẫu kia và câu hỏi rào cản; lượt đọc giá + kho của CHÍNH mẫu khách nêu bằng tool (opening_focus).
   Đối chứng: nêu đúng mẫu cũ / không nêu mẫu nào → như cũ; B1 không đổi.
H  Chuyển máy: cuộc gọi đã có ticket handoff được tool xác nhận (lý do y tế) → khách đòi gặp người phụ trách không tạo ticket thứ
   hai, câu trả lời báo lại ticket đang có. Đối chứng: chưa có ticket → chuyển một lần.

DeepSeek = phản hồi dựng sẵn theo hợp đồng v2; Jev = bộ quyết định có kịch bản; tool = mock BTC; memory SQLite tạm.
Dùng: python tests/b2_ta1_handoff_check.py"""
import os
import sys
import tempfile
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
tmp = tempfile.mkdtemp(prefix="b2_ta1_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "v.db").replace("\\", "/")
os.environ["TOOL_TRANSPORT"] = "direct"
os.environ.setdefault("RUN_PROFILE", "local")
os.environ.setdefault("RAG_MODE", "bm25")
os.environ["LLM_CACHE"] = "off"

# khung test dùng chung (Ctx, resp, say, Script, session...): chỉ nạp phần khung của b2_round_f_check, KHÔNG chạy các nhóm test của nó
import types  # noqa: E402
_src = open(os.path.join(ROOT, "tests", "b2_round_f_check.py"), encoding="utf-8").read()
F = types.ModuleType("b2_round_f_frame")
F.__file__ = os.path.join(ROOT, "tests", "b2_round_f_check.py")
exec(compile(_src.split("# ================================================================== H8")[0], F.__file__, "exec"), F.__dict__)
from core.llm.generator import Generator, render_offline  # noqa: E402
from core.llm.router import Router  # noqa: E402
from harness import agent, planner_table  # noqa: E402
from harness import plan_primitives as P  # noqa: E402
from harness.memory import Memory  # noqa: E402
from harness.tools import ToolBox  # noqa: E402

FAIL, PASS = [], [0]


def ok(group, name, got, want=True):
    if got == want:
        PASS[0] += 1
        print(f"OK   [{group}] {name}", flush=True)
    else:
        FAIL.append((group, name))
        print(f"FAIL [{group}] {name}: got={got!r} want={want!r}", flush=True)


PRO, APY, APX = "SKU-AP-PRO", "SKU-AP-Y", "SKU-AP-X"
PHONE, CID = "0911222333", "N-0911222333"


# ------------------------------------------------------------------ T1: h_opening_returning (đơn vị)
def opening(variant, mentioned, prev=PRO):
    with F.Ctx({"planner_variant": variant}):
        s = SimpleNamespace(brief={"last_session": {"date": "2026-10-12"}, "stale_warnings": []}, carried={},
                            known={"blocker": "can nhac", "price_quoted_vnd": 7690000}, u_turn={"asks": [], "request_items": []},
                            turn_mentioned=mentioned)
        c = SimpleNamespace(s=s, facts={}, goals=[], prev_focus=prev)
        planner_table.h_opening_returning(c, None)
        return c, render_offline({"goals": c.goals, "facts": c.facts, "honorific": "anh", "customer_name": ""})


c, txt = opening("b2_jev", [APY])
ok("T1", "nêu mẫu khác: vẫn nhắc ngày + mẫu đã tư vấn (lịch sử)", ("12/10" in txt, "AirPure Pro" in txt), (True, True))
ok("T1", "nêu mẫu khác: bỏ giá cũ của mẫu đã tư vấn + câu hỏi rào cản",
   (c.facts["brief"]["price_quoted_vnd"], "7.690.000" in txt, c.facts["brief"]["blocker"]), (None, False, None))
ok("T1", "nêu mẫu khác: opening_switch = mẫu khách nêu, ghi focus_switched", (c.opening_switch, c.facts["brief"].get("focus_switched")),
   (APY, {"from": PRO, "to": APY}))
c, txt = opening("b2_jev", [PRO])
ok("T1", "nêu đúng mẫu cũ: như cũ (có giá cũ, không switch)", (c.opening_switch, c.facts["brief"]["price_quoted_vnd"]), (None, 7690000))
c, txt = opening("b2_jev", [])
ok("T1", "không nêu mẫu: như cũ", (c.opening_switch, c.facts["brief"]["price_quoted_vnd"], c.facts["brief"]["blocker"]),
   (None, 7690000, "can nhac"))
c, txt = opening("b1", [APY])
ok("T1", "B1 không đổi", (c.opening_switch, c.facts["brief"]["price_quoted_vnd"]), (None, 7690000))


# ------------------------------------------------------------------ T2: cuộc gọi lại đầy đủ (agent + planner B2)
def returning(name, text, variant="b2_jev", decider=None):
    mem = Memory(f"b2ta1:{variant}:{name}")
    mem.wipe()
    ToolBox.reset_world()
    mem.upsert_customer(CID, None, None, PHONE, [("phone", PHONE)])
    mem.add_session(f"{name}:call_1", CID, "hotline", "2026-10-12", "khac",
                    "call_1 (12/10, hotline): Khách so sánh AirPure Y và AirPure Pro, đã tư vấn AirPure Pro giá 7.690.000đ.",
                    source="harness")
    for k, v in (("product_advised", PRO), ("price_quoted_vnd", 7690000)):
        mem.write_fact(CID, k, v, f"{name}:call_1", f"{name}:call_1", "2026-10-12", valid_from="2026-10-12")
    mem.add_quote(CID, f"{name}:call_1", PRO, "advised", 7990000, 7690000, None, None, "2026-10-12")
    d = decider or F.Script("finish")
    s = agent.CallSession(memory=mem, today="2026-10-15", call_name="call_2", session_id=f"{name}:call_2", channel="hotline",
                          channel_identity=None, phone=PHONE, input_mode="text", router=Router("rules"),
                          generator=Generator("offline"), config="full", planner_variant=variant, planner_decider=d)
    s.start()
    row = F.say(s, text, F.resp(intent="product_inquiry", refs={"previous_contact": True}))
    return s, row


def quoted(row):
    return [P._parent(t["args"]["sku"]) for t in row["tool_calls"] if t["name"] == "pricing.get_quote"]


with F.Ctx():
    s, row = returning("sw", "Sau khi xem lại, anh cũng nghiêng về cái AirPure Y đó.")
    lp = F.loop(row)
    ok("T2", "goal có opening_returning + quote", ("opening_returning" in row["goals"], "quote" in row["goals"]), (True, True))
    ok("T2", "lượt đọc giá đúng mẫu khách nêu (AirPure Y), qua opening_focus", (APY in quoted(row), (lp.get("opening_focus") or {}).get("sku")),
       (True, APY))
    ok("T2", "câu trả lời: nhắc mẫu đã tư vấn, nói giá mẫu Y, không nói giá cũ 7.690.000",
       ("AirPure Pro" in row["agent_text"], "AirPure Y" in row["agent_text"], "7.690.000" in row["agent_text"]), (True, True, False))
    ok("T2", "không ghi gì", [t["name"] for t in row["tool_calls"] if t["name"] in ("order.create", "handoff.transfer", "schedule.callback")], [])
    print("   →", row["agent_text"])

    s, row = returning("same", "Anh gọi lại về cái AirPure Pro hôm trước.")
    ok("T2", "nêu đúng mẫu cũ: không opening_focus, vẫn nhắc giá cũ", (F.loop(row).get("opening_focus"), "7.690.000" in row["agent_text"]),
       (None, True))
    s, row = returning("none", "Alo em, anh gọi lại đây.")
    ok("T2", "không nêu mẫu: không opening_focus, không đọc giá AirPure Y", (F.loop(row).get("opening_focus"), APY in quoted(row)), (None, False))

with F.Ctx({"planner_variant": "b1"}):
    s, row = returning("b1", "Sau khi xem lại, anh cũng nghiêng về cái AirPure Y đó.", variant="b1")
    ok("T2", "B1: không có opening_focus (không đổi)", (row.get("planner") or {}).get("loop", {}).get("opening_focus") if row.get("planner") else None, None)


# ------------------------------------------------------------------ H: chuyển máy một lần mỗi cuộc gọi
with F.Ctx():
    s = F.session("handoff2")
    r1 = F.say(s, "Chị đang uống kháng sinh thì vẫn hút sữa cho bé bú được không em?",
               F.resp(intent="out_of_scope", safety=["medical_question"], asks_question=True))
    r2 = F.say(s, "Em không rõ thì cho chị nói chuyện với người phụ trách nhé em.",
               F.resp(intent="out_of_scope", requests=[F.req("handoff", "cho chị nói chuyện với người phụ trách")]))
    n1, n2 = len(F.calls(r1, "handoff.transfer")), len(F.calls(r2, "handoff.transfer"))
    ok("H", "lượt y tế: chuyển máy 1 lần", n1, 1)
    ok("H", "khách đòi gặp người sau khi đã chuyển: không tạo ticket thứ hai", n2, 0)
    ok("H", "lượt 2 vẫn có goal handoff, câu trả lời không rỗng", ("handoff" in r2["goals"], bool(r2["agent_text"].strip())), (True, True))
    print("   →", r2["agent_text"])
    s = F.session("handoff1")
    r = F.say(s, "Cho chị nói chuyện với người phụ trách nhé em.",
              F.resp(intent="out_of_scope", requests=[F.req("handoff", "cho chị nói chuyện với người phụ trách")]))
    ok("H", "đối chứng: chưa có ticket → chuyển 1 lần", len(F.calls(r, "handoff.transfer")), 1)

# ------------------------------------------------------------------ T3: rào của TA1 (14/11)
c, _ = opening("b2_jev", [APY, APX])
ok("T3", "khách nêu HAI mẫu khác mẫu cũ → không chuyển, không tự báo giá mẫu nào", c.opening_switch, None)
c, _ = opening("b2_jev", [APY, PRO])
ok("T3", "khách nêu mẫu cũ + mẫu mới (phân vân) → không chuyển", c.opening_switch, None)


def boom(state, opts):
    raise RuntimeError("jev down")


def slow_finish(state, opts):
    import time as _t
    _t.sleep(0.05)
    return {"step": "finish", "backend": "script", "ms": 50}


for name, decider, extra, why in (("invalid", F.Script("khong_co_buoc_nay"), {}, "halting"),
                                  ("error", boom, {}, "halting"),
                                  ("deadline0", F.Script("finish"), {"b2_deadline_s": 1e-9}, "halting"),
                                  ("deadline_after", slow_finish, {"b2_deadline_s": 0.01}, "deadline")):
    with F.Ctx(extra):
        s, row = returning(f"g_{name}", "Sau khi xem lại, anh cũng nghiêng về cái AirPure Y đó.", decider=decider)
        of = F.loop(row).get("opening_focus") or {}
        ok("T3", f"{name}: dừng cứng / quá deadline → không gọi tool đọc giá mẫu Y (skipped={why})",
           (APY in quoted(row), of.get("skipped"), F.loop(row).get("stop")), (False, why, F.loop(row).get("stop")))
        print("      stop =", F.loop(row).get("stop"))

with F.Ctx():
    s, row = returning("g_quoted", "Sau khi xem lại, anh cũng nghiêng về cái AirPure Y đó.", decider=F.Script(F.pick("read_quote:"), "finish"))
    ok("T3", "planner đã đọc giá mẫu Y → opening_focus không đọc lại (quote_present), chỉ 1 get_quote Y",
       ((F.loop(row).get("opening_focus") or {}).get("skipped"), quoted(row).count(APY)), ("quote_present", 1))


# ------------------------------------------------------------------ C: _conform đóng → không mở quyền ghi (đầu-cuối)
with F.Ctx():
    s = F.session("c_ctrl", decider=F.BUYER())
    row = F.say(s, "Em lên đơn AirPure X cho anh nhé", F.ORDER("Em lên đơn AirPure X cho anh"))
    ok("C", "đối chứng: lệnh đặt rõ hợp lệ → có order.create", F.created_parents(row), [APX])
    s = F.session("c_cond", decider=F.BUYER())
    row = F.say(s, "Em lên đơn AirPure X cho anh nhé", F.ORDER("Em lên đơn AirPure X cho anh", cond={"type": {"t": "stock"}, "span": "x"}))
    ok("C", "condition.type sai kiểu → KHÔNG order.create, yêu cầu ở trạng thái có điều kiện",
       (F.calls(row, "order.create"), [r["status"] for r in s.reqs.items if r["kind"] == "place_order"]), ([], ["conditional"]))
    s = F.session("c_tgt", decider=F.BUYER())
    row = F.say(s, "Em lên đơn AirPure X cho anh nhé", F.ORDER("Em lên đơn AirPure X cho anh", ref={"r": "P1"}))
    ok("C", "target_ref sai kiểu → KHÔNG order.create, cần hỏi đối tượng",
       (F.calls(row, "order.create"), [r["status"] for r in s.reqs.items if r["kind"] == "place_order"]), ([], ["needs_target"]))
    s = F.session("c_hold", decider=F.BUYER())
    row = F.say(s, "Em lên đơn AirPure X cho anh nhé",
                F.resp(intent="place_order", requests=[F.req("place_order", "Em lên đơn AirPure X cho anh", "P1")],
                       ambiguity={"level": {"l": 1}}))
    ok("C", "ambiguity sai kiểu → lượt giữ (ambiguous_turn), KHÔNG order.create", (F.calls(row, "order.create"), s.reqs.hold),
       ([], "ambiguous_turn"))


# ------------------------------------------------------------------ Q: câu báo đã chuyển máy + đọc lại địa chỉ (14/11)
ok("Q", "chuyển máy lần 2: nói đã chuyển + đang chờ chuyên viên tiếp nhận, không nói như vừa chuyển",
   ("đã chuyển sang chuyên viên rồi" in r2["agent_text"], "đang chờ chuyên viên tiếp nhận" in r2["agent_text"],
    "xin phép chuyển" in r2["agent_text"]), (True, True, False))
txt = render_offline({"goals": ["handoff"], "facts": {"handoff": {"ticket_id": "HT0001", "status": "queued"}}, "honorific": "chị"})
ok("Q", "chuyển máy lần đầu: câu cũ", "xin phép chuyển" in txt, True)
ADDR = "18 Phan Đình Giót, Thanh Trì, Hà Nội"
txt = render_offline({"goals": ["order_created"], "honorific": "anh",
                      "facts": {"order": {"order_id": "OD1", "total_vnd": 4890000, "estimated_delivery": "2026-10-20", "address": ADDR}}})
ok("Q", "xác nhận đơn đọc lại đúng địa chỉ đã ghi", f"giao về {ADDR}" in txt, True)
txt = render_offline({"goals": ["order_created"], "honorific": "anh", "facts": {"order": {"order_id": "OD1", "total_vnd": 4890000}}})
ok("Q", "đơn chưa có địa chỉ: không thêm 'giao về'", "giao về" in txt, False)
with F.Ctx():
    s = F.session("q_addr", decider=F.BUYER())
    text = f"Em lên đơn AirPure X cho anh, giao về {ADDR} nhé"
    row = F.say(s, text, F.resp(intent="place_order", requests=[F.req("place_order", "Em lên đơn AirPure X cho anh", "P1")],
                                observations=[{"slot": "address", "span": ADDR, "stance": "stated", "subject": "self"}]))
    oc = F.calls(row, "order.create")
    ok("Q", "đầu-cuối: order.create đúng địa chỉ, câu xác nhận đọc lại đúng địa chỉ đó",
       ([c["args"].get("address") for c in oc], f"giao về {ADDR}" in row["agent_text"]), ([ADDR], True))
    print("   →", row["agent_text"])

print(f"\n{PASS[0]} OK, {len(FAIL)} lỗi")
if FAIL:
    print("LỖI:", FAIL)
raise SystemExit(1 if FAIL else 0)
