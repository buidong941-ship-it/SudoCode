"""Kaggle only. v6p12 (WRITE_PATH_GATE): (A) kiểu lời nói đổi / trả — DeepSeek mode + căn cứ, JEV kiểm chéo; ask_info không ghi;
(B) điều kiện promo_active / fee_free đánh giá từ dữ kiện tool + DT-03 + sổ đếm exchanges:<mã đơn>; (E) địa chỉ không mất:
profile_default bỏ qua lệch trạng thái đơn, địa chỉ của lượt trước, bổ sung địa chỉ đơn vừa tạo sau lượt xen, địa chỉ tham chiếu."""
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
frame_path = ROOT / "tests/b2_round_f_check.py"
F = types.ModuleType("v6p12_frame")
F.__file__ = str(frame_path)
exec(compile(frame_path.read_text(encoding="utf-8").split("# ================================================================== H8")[0],
             str(frame_path), "exec"), F.__dict__)
from core import pii
from core.config import settings
from core.llm import generator as GEN
from harness import agent
from harness import jev_write_gate as G
from harness import plan_primitives as P
from harness import request_state as RS
from harness import understanding as U
from harness.memory import Memory
from harness.tools import ToolBox

passed, failed = 0, []


def check(name, value):
    global passed
    if value:
        passed += 1
        print("PASS", name, flush=True)
    else:
        failed.append(name)
        print("FAIL", name, flush=True)


# ================================================================== đơn vị
with patch.object(settings, "write_path_gate", True):
    red = pii.Redactor()
    text = "Giờ chị muốn đổi qua size 41, mà lần này có còn miễn phí không?"
    meta = {"dropped": []}
    check("mode: verbatim span kept", U._mode_fields({"mode": "ask_info", "mode_span": "có còn miễn phí không"}, text, red, meta)
          == {"mode": "ask_info", "mode_span": "có còn miễn phí không"})
    check("mode: non-verbatim span → unclear", U._mode_fields({"mode": "direct", "mode_span": "đổi ngay giúp chị"}, text, red, meta)["mode"] == "unclear")
    check("mode: value outside list → unclear", U._mode_fields({"mode": "now"}, text, red, meta)["mode"] == "unclear")

    it = lambda mode, **kw: {"kind": "exchange", "mode": mode, **kw}
    dec = lambda mode: {"decision": "open_or_update_request", "mode": mode}
    check("op mode: direct/direct → write path", RS._op_mode_check({}, it("direct"), dec("direct")) is None)
    check("op mode: ask_info/ask_info → answer only", RS._op_mode_check({}, it("ask_info"), dec("ask_info")) == "ask_info")
    check("op mode: DeepSeek vs JEV mismatch → ask", RS._op_mode_check({}, it("direct"), dec("ask_info")) == "mode_mismatch")
    check("op mode: unclear → ask", RS._op_mode_check({}, it("unclear"), dec("unclear")) == "mode_unclear")
    check("op mode: conditional without condition → ask", RS._op_mode_check({}, it("conditional"), dec("conditional")) == "mode_condition_missing")
    check("op mode: conditional with condition → write path",
          RS._op_mode_check({}, it("conditional", condition={"type": "fee_free"}), dec("conditional")) is None)
    check("op mode: defer → deferred", RS._op_mode_check({}, it("defer"), dec("defer")) == "deferred")
    check("op mode: withdrawn → withdrawn",
          RS._op_mode_check({"withdrawn": [{"kind": "exchange"}]}, it("direct"), dec("direct")) == "withdrawn")

    # E1: profile_default đã khớp → không xét lệch lời kể trạng thái đơn
    with patch.object(settings, "jev_write_gate", True):
        a = {"address_scope": "profile_default", "order_state_claim": "none"}
        g = {"updates": [{"kind": "change_order_address", "decision": "open_or_update_request", "address_scope": "profile_default",
                          "order_state_claim": "delivered"}]}
        check("E1: profile_default agreed, claim mismatch ignored", RS._address_scope_check({}, a, g) == "profile_default")
        with patch.object(settings, "write_path_gate", False):
            check("E1 flag off: claim mismatch still asks", RS._address_scope_check({}, a, g) == "order_state_claim_mismatch")
        g["updates"][0]["address_scope"] = "existing_order"
        check("E1: scope mismatch still asks", RS._address_scope_check({}, a, g) == "address_scope_mismatch")

    # B: promo_active
    def fake_t(quotes=None, windows=None, facts=None, cid="C1"):
        mem = SimpleNamespace(current_facts=lambda c, today=None: dict(facts or {}))
        s = SimpleNamespace(turn_no=3, customer={"customer_id": cid} if cid else {}, mem=mem, today="2026-11-12",
                            reqs=SimpleNamespace(refmap={"P1": {"type": "product", "skus": ("SKU-AF-6L",)}}))
        return SimpleNamespace(s=s, quotes=quotes or {}, windows=windows or {}, stock={})
    po = lambda: {"id": "R1", "kind": "place_order", "condition": {"type": "promo_active", "span": "Có giảm thì chốt"}}
    r = po()
    ev = P.evaluate_condition(fake_t({"SKU-AF-6L": {"final_price_vnd": 3391500, "list_price_vnd": 3990000}}), r, {"resolved": ["SKU-AF-6L"]})
    check("promo: discounted quote → met + evidence on request", ev["state"] == "met"
          and r["condition_evidence"] == {"type": "promo_active", "turn": 3, "met": True})
    r = po()
    ev = P.evaluate_condition(fake_t({"SKU-AF-6L": {"final_price_vnd": 3990000, "list_price_vnd": 3990000}}), r, {"resolved": ["SKU-AF-6L"]})
    check("promo: no discount → unmet, reply goal, evidence not met", ev["state"] == "unmet" and ev["goals"] == ["condition_fact_unmet"]
          and r["condition_evidence"]["met"] is False)
    ev = P.evaluate_condition(fake_t({}), po(), {"resolved": ["SKU-AF-6L"]})
    check("promo: quote not read → missing_evidence read_quote", ev["state"] == "missing_evidence" and ev["detail"] == ["read_quote:P1"])

    # B: fee_free (DT-03 bản 2026-10, sổ đếm, chênh lệch giá)
    ex = lambda: {"id": "R1", "kind": "exchange", "condition": {"type": "fee_free", "span": "Nếu không tốn gì"}}
    ctx = {"oid": "OD600001", "new_sku": "SKU-JK-WND-L-DEN", "o": {"price_vnd": 690000}}
    win = {"OD600001": {"version": "2026-10", "eligible": True}}
    q_same = {"SKU-JK-WND-L-DEN": {"final_price_vnd": 690000}}
    fact0 = {"exchanges:OD600001": {"value": 0}}
    r = ex()
    ev = P.evaluate_condition(fake_t(q_same, win, fact0), r, ctx)
    check("fee: first exchange, same price → met", ev["state"] == "met" and r["condition_evidence"]["met"] is True)
    ev = P.evaluate_condition(fake_t(q_same, win, {"exchanges:OD600001": {"value": 1}}), ex(), ctx)
    check("fee: second exchange → unmet not_first_exchange", ev["state"] == "unmet" and ev["facts"]["condition"]["why"] == "not_first_exchange")
    ev = P.evaluate_condition(fake_t(q_same, win, {}), ex(), ctx)
    check("fee: no tracked count (CRM / lost) → pending unverified, not free", ev["state"] == "pending"
          and ev["facts"]["condition"]["why"] == "fee_unverified")
    ev = P.evaluate_condition(fake_t(q_same, win, {"exchanges:OD600001": {"value": "0"}}), ex(), ctx)
    check("fee: count of wrong type → unverified", ev["facts"]["condition"]["why"] == "fee_unverified")
    ev = P.evaluate_condition(fake_t(q_same, {"OD600001": {"version": "2026-06"}}, fact0), ex(), ctx)
    check("fee: old policy version → unmet policy_version", ev["state"] == "unmet" and ev["facts"]["condition"]["why"] == "policy_version")
    ev = P.evaluate_condition(fake_t({"SKU-JK-WND-L-DEN": {"final_price_vnd": 790000}}, win, fact0), ex(), ctx)
    check("fee: new variant dearer → unmet price_diff 100k", ev["state"] == "unmet" and ev["facts"]["condition"]["extra_vnd"] == 100000)
    ev = P.evaluate_condition(fake_t({}, win, fact0), ex(), ctx)
    check("fee: new variant price unread → unverified", ev["facts"]["condition"]["why"] == "fee_unverified")
    ev = P.evaluate_condition(fake_t(q_same, win, fact0, cid=None), ex(), ctx)
    check("fee: no customer id → unverified", ev["facts"]["condition"]["why"] == "fee_unverified")

    # câu trả lời
    for cond, must, never in (({"type": "promo_active", "product": "Nồi chiên Philips 6.2L", "price_vnd": 3990000}, "chưa có chương trình giảm giá", "đã lên đơn"),
                              ({"type": "fee_free", "why": "not_first_exchange", "order_id": "OD600001"}, "chưa đổi", "miễn phí"),
                              ({"type": "fee_free", "why": "price_diff", "order_id": "OD600001", "extra_vnd": 100000}, "100.000", "đã đổi"),
                              ({"type": "fee_free", "why": "fee_unverified", "order_id": "OD600001"}, "chưa xác minh", "đã đổi"),
                              ({"type": "fee_free", "why": "policy_version", "order_id": "OD600001"}, "bản cũ", "đã đổi")):
        txt = GEN.render_offline({"goals": ["condition_fact_unmet"], "facts": {"condition": cond}})
        print("  reply:", txt, flush=True)
        check(f"reply {cond.get('why') or cond['type']}: says reason, no done claim", must in txt and never not in txt)

# ================================================================== tích hợp (phiên giả lập)
JEV = {"mode": "direct", "scope": "profile_default", "claim": "none"}
SEEN = {}


def decision(state, opts):
    SEEN["opts"] = sorted(opts)
    action = state["proposed_update"]["action"]
    out = {"decision": "reject_or_withdraw" if action == "withdraw" else "open_or_update_request",
           "request_id": opts["request_ids"][0], "target_ref": opts["target_refs"][0], "revision": opts["revision"]}
    if "mode" in opts:
        SEEN["mode_keys"] = sorted(state["proposed_update"])
        out["mode"] = JEV["mode"]
    if "address_scope" in opts:
        out.update(address_scope=JEV["scope"], order_state_claim=JEV["claim"])
    return out


real_assess = G.assess


def assess(*args, **kwargs):
    return real_assess(*args, **kwargs, decider=decision)


def planner(state, opts):
    steps = opts["step"]
    for req_ in state.get("open_requests") or []:
        for detail in req_.get("readiness", {}).get("detail") or []:
            if detail in steps:
                return {"step": detail}
    for prefix in ("commit_request:", "answer_ask:", "read_condition:", "clarify:", "read_order", "read_quote:", "read_stock:",
                   "check_window:", "clarify", "finish"):
        found = next((x for x in steps if x.startswith(prefix)), None)
        if found:
            return {"step": found}
    return {"step": "finish"}


SENTINEL = F.resp(intent="greeting_or_other")


def turn(s, text, *resps):
    F.QUEUE[:] = list(resps)
    row = s.turn(text)
    s.drain_audits()
    return row


def req(kind, evidence, ref=None, **kw):
    return {"kind": kind, "evidence": evidence, "target_ref": ref, **kw}


def addr_obs(span, **kw):
    return [{"slot": "address", "span": span, "stance": "stated", "subject": "self", **kw}]


def session_on(name, today, phone="0911222333"):
    mem = Memory(f"v6p12:{name}")
    mem.wipe()
    ToolBox.reset_world()
    s = agent.CallSession(memory=mem, today=today, call_name="call_1", session_id=f"{name}:call_1", channel="hotline",
                          channel_identity=None, phone=phone, input_mode="text", router=F.Router("rules"),
                          generator=F.Generator("offline"), config="full", planner_variant="b2_jev", planner_decider=planner)
    s.start()
    return s


def debug(label, row):
    rs = row.get("request_state") or {}
    ev = [(e.get("event"), e.get("why") or e.get("kind") or e.get("via")) for e in rs.get("events") or []][-8:]
    steps = [d.get("step") for d in ((row.get("planner") or {}).get("loop") or {}).get("decisions") or []]
    print(f"  [{label}] events {ev} | steps {steps}", flush=True)


def ordered(s, text="Lấy AirPure Mini cho chị"):
    turn(s, text, F.resp(intent="place_order", requests=[req("place_order", "Lấy AirPure Mini", "P1", target_basis="named")]), SENTINEL)
    return s.orders_created[0]["order_id"] if s.orders_created else None


def mem_key(row, key):
    return [w for w in row.get("memory_writes") or [] if w.get("key") == key]


def upd_addr(row):
    return [c for c in F.calls(row, "order.update") if c["args"].get("action") == "update_address"]


extra = {"jev_write_gate": True, "b2_two_tier": False, "b2_max_decisions": 20, "b2_max_tool_calls": 25, "address_scope_gate": True,
         "write_path_gate": True}
with F.Ctx(extra), patch.object(G, "assess", assess):
    U._STATIC = None
    # B promo_active: 11/11 có KM 15% → lên đơn; 15/10 không có → báo lý do, không lên đơn
    PROMO = "Philips 6.2L hôm nay bán giá nhiêu? Có giảm thì chốt cho anh luôn."
    promo_resp = lambda: F.resp(intent="place_order", asks=["price"], requests=[req("place_order", "chốt cho anh luôn", "P1",
                               target_basis="named", condition={"type": "promo_active", "span": "Có giảm thì chốt"},
                               lines=[{"target_ref": "P1", "product_span": "Philips 6.2L"}])])
    s = session_on("promo-on", "2026-11-11")
    row = turn(s, PROMO, promo_resp(), SENTINEL)
    made = F.calls(row, "order.create")
    print("  promo 11/11:", row["agent_text"], "| goals", row.get("goals"), flush=True)
    debug("promo-on", row)
    check("promo active (11/11): order.create at discounted price", made and all(
        (ln.get("price_vnd") or 0) < 3990000 for ln in (made[0]["args"].get("lines") or [made[0]["args"]])))
    s = session_on("promo-off", "2026-10-15")
    row = turn(s, PROMO, promo_resp(), SENTINEL)
    print("  promo 15/10:", row["agent_text"], "| goals", row.get("goals"), flush=True)
    debug("promo-off", row)
    check("promo inactive (15/10): no order.create, reason reply", not F.calls(row, "order.create")
          and "condition_fact_unmet" in (row.get("goals") or []) and "chưa có chương trình giảm giá" in row["agent_text"])

    # A đổi hàng: ask_info → không mở yêu cầu, không order.update; direct → mở yêu cầu
    for mode, label in (("ask_info", "ask_info"), ("direct", "direct")):
        JEV["mode"] = mode
        s = session_on("mode-" + label, "2026-10-15")
        ordered(s)
        row = turn(s, "Đổi qua size 41 thì có mất phí không em?", F.resp(intent="exchange", asks=["return_policy"], requests=[
                   req("exchange", "Đổi qua size 41", "O1", mode=mode, mode_span="có mất phí không" if mode == "ask_info" else "Đổi qua size 41")]),
                   SENTINEL)
        ex_items = [r for r in s.reqs.items if r["kind"] == "exchange"]
        events = [e.get("event") for e in (row.get("request_state") or {}).get("events") or []]
        print(f"  mode {label}:", row["agent_text"], "| events", events, flush=True)
        if mode == "ask_info":
            check("A ask_info: no exchange request opened, no order.update", not ex_items and not F.calls(row, "order.update")
                  and "op_ask_info" in events)
        else:
            check("A direct: exchange request opened", bool(ex_items))
    check("A: JEV asked mode and did not see DeepSeek mode", "mode" in SEEN.get("opts", [])
          and not any(k.startswith("mode") for k in SEEN.get("mode_keys", [])))
    JEV["mode"] = "direct"
    s = session_on("mode-mismatch", "2026-10-15")
    ordered(s)
    JEV["mode"] = "ask_info"
    row = turn(s, "Đổi qua size 41 giúp chị", F.resp(intent="exchange", requests=[req("exchange", "Đổi qua size 41", "O1", mode="direct",
               mode_span="Đổi qua size 41 giúp chị")]), SENTINEL)
    check("A mismatch: no exchange request, asks again", not [r for r in s.reqs.items if r["kind"] == "exchange"]
          and "ask_repeat" in (row.get("goals") or []) and not F.calls(row, "order.update"))

    # sổ đếm exchanges: order.create → 0; đổi thành công → +1; đơn không có fact → không tạo
    s = session_on("ledger", "2026-10-15")
    oid = ordered(s)
    cid = s.customer["customer_id"]
    facts = s.mem.current_facts(cid, s.today)
    check("ledger: created order starts at 0", (facts.get(f"exchanges:{oid}") or {}).get("value") == 0)
    s.call_tool_log.append({"name": "order.update", "args": {"order_id": oid, "action": "exchange_size", "new_variant_sku": "X"},
                            "result": {"order_id": oid, "action": "exchange_size", "fee_vnd": 0, "status": "pickup_scheduled"},
                            "_turn": s.turn_no})
    s.call_tool_log.append({"name": "order.update", "args": {"order_id": "OD999999", "action": "exchange_size"},
                            "result": {"order_id": "OD999999", "status": "pickup_scheduled"}, "_turn": s.turn_no})
    s.call_tool_log.append({"name": "order.update", "args": {"order_id": oid, "action": "exchange_size"},
                            "result": {"error": "new_variant_out_of_stock"}, "_turn": s.turn_no})
    s._remember_exchanges(cid, "test")
    facts = s.mem.current_facts(cid, s.today)
    check("ledger: confirmed exchange → 1, failed one not counted", (facts.get(f"exchanges:{oid}") or {}).get("value") == 1)
    check("ledger: untracked order not initialised", "exchanges:OD999999" not in facts)
    check("ledger: hidden from known / brief", not any(k.startswith("exchanges:") for k in s.known)
          and not any(k.startswith("exchanges:") for k in agent._mem_layers(facts)))

    # E2 (H13-038): đơn 2 món → sửa dòng → lượt đọc địa chỉ + tiền mặt → bổ sung địa chỉ cho đúng đơn
    os.environ["ORDER_EXT_TOOLS"] = "1"
    JEV["mode"] = "direct"
    s = session_on("e2-amend", "2026-10-12")
    row = turn(s, "Chị lấy Urban Classic size 39 màu đen với một Máy lọc nước UF Sunhouse", F.resp(intent="place_order", requests=[
               req("place_order", "Chị lấy Urban Classic size 39 màu đen", lines=[
                   {"target_ref": "P1", "product_span": "Urban Classic", "size_span": "size 39", "color_span": "màu đen"},
                   {"target_ref": "P2", "product_span": "Máy lọc nước UF Sunhouse"}], target_basis="named")]), SENTINEL)
    oid = s.orders_created[0]["order_id"] if s.orders_created else None
    row = turn(s, "À mà đôi giày em lấy size 40 giùm chị, máy lọc để nguyên", F.resp(intent="exchange", requests=[req("exchange",
               "đôi giày em lấy size 40", "O1", mode="direct", mode_span="đôi giày em lấy size 40",
               lines=[{"target_ref": "O1", "product_span": "đôi giày", "size_span": "size 40"}])]), SENTINEL)
    print("  e2 amend:", row["agent_text"], "| tools", [c["name"] for c in row["tool_calls"]], flush=True)
    A115 = "115 Phan Đình Phùng, Quy Nhơn, Bình Định"
    row = turn(s, f"Gửi về {A115}, nhận hàng chị trả tiền mặt.", F.resp(intent="place_order", observations=addr_obs(A115) + [
               {"slot": "payment", "span": "trả tiền mặt", "stance": "chosen", "subject": "self", "label": "COD"}],
               refs={"existing_order": True}), SENTINEL)
    debug("e2-address", row)
    up = upd_addr(row)
    print("  e2 address:", row["agent_text"], "| update", [u["args"] for u in up], flush=True)
    check("E2: address completes the order created this call after an amend turn",
          oid and len(up) == 1 and up[0]["args"].get("order_id") == oid and A115 in up[0]["args"].get("reason", ""))
    os.environ["ORDER_EXT_TOOLS"] = "0"

    # E3 (H13-058): lượt 1 địa chỉ + phạm vi chưa rõ → hỏi; lượt 2 "mấy đơn sau gửi về chỗ này" → ghi hồ sơ địa chỉ lượt 1
    NEW = "203 Nguyễn Văn Linh, Hải Châu, Đà Nẵng"
    s = session_on("e3-prev", "2026-10-10")
    JEV.update(scope="unclear", claim="none")
    row = turn(s, f"Anh chuyển nhà rồi, địa chỉ mới là {NEW}.", F.resp(intent="order_change", requests=[req("change_order_address",
               f"địa chỉ mới là {NEW}", None, address_scope="unclear", address_scope_span=None, order_state_claim="none",
               order_state_span=None)], observations=addr_obs(NEW)), SENTINEL)
    check("E3 setup: unclear scope → nothing written", not mem_key(row, "address") and not upd_addr(row))
    JEV.update(scope="profile_default", claim="none")
    row = turn(s, "Em sửa lại giùm anh, mấy đơn sau gửi về chỗ này nghe.", F.resp(intent="order_change", requests=[req(
               "change_order_address", "mấy đơn sau gửi về chỗ này", None, address_scope="profile_default",
               address_scope_span="mấy đơn sau gửi về chỗ này", order_state_claim="none", order_state_span=None)]), SENTINEL)
    print("  e3:", row["agent_text"], "| mem", mem_key(row, "address"), flush=True)
    check("E3: profile address taken from previous turn, recorded", any(w.get("value") == NEW for w in mem_key(row, "address"))
          and "address_saved_profile" in (row.get("goals") or []) and not upd_addr(row))
    s = session_on("e3-stale", "2026-10-10")
    JEV.update(scope="unclear")
    turn(s, f"Anh chuyển nhà rồi, địa chỉ mới là {NEW}.", F.resp(intent="order_change", requests=[req("change_order_address",
         f"địa chỉ mới là {NEW}", None, address_scope="unclear", order_state_claim="none")], observations=addr_obs(NEW)), SENTINEL)
    turn(s, "À mà shop có bán quạt không?", F.resp(intent="product_question", asks=["other"]), SENTINEL)
    JEV.update(scope="profile_default")
    row = turn(s, "mấy đơn sau gửi về chỗ này nghe", F.resp(intent="order_change", requests=[req("change_order_address",
               "mấy đơn sau gửi về chỗ này", None, address_scope="profile_default", address_scope_span="mấy đơn sau gửi về chỗ này",
               order_state_claim="none")]), SENTINEL)
    check("E3: address two turns back is not reused (asks)", not mem_key(row, "address") and "ask_address" in (row.get("goals") or []))

    # E4 (H13-059 c3): địa chỉ tham chiếu không vào slot
    s = session_on("e4-ref", "2026-10-15")
    row = turn(s, "Gửi về địa chỉ mới cô báo lần trước nha", F.resp(intent="greeting_or_other",
               observations=addr_obs("địa chỉ mới cô báo lần trước", value_kind="reference")), SENTINEL)
    check("E4: reference phrase not stored as address", not mem_key(row, "address")
          and (s.u_turn or {}).get("refs", {}).get("previous_address") is True)

# tắt cờ: prompt / schema / câu hỏi JEV như v6p11
captured = {}
real_fake = F.fake_call


def capture(prompt, schema, *a, **k):
    captured["prompt"], captured["schema"] = prompt, schema
    return real_fake(prompt, schema, *a, **k)


with F.Ctx({**extra, "write_path_gate": False}), patch.object(G, "assess", assess), patch.object(U, "_call", capture):
    U._STATIC = None
    SEEN.clear()
    s = session_on("off", "2026-10-15")
    ordered(s)
    turn(s, "Đổi qua size 41 giúp chị", F.resp(intent="exchange", requests=[req("exchange", "Đổi qua size 41", "O1")]), SENTINEL)
    props = captured["schema"]["properties"]["requests"]["items"]["properties"]
    cond_enum = props["condition"]["properties"]["type"]["enum"]
    check("flag off: schema has no mode, no fact conditions", "mode" not in props and "promo_active" not in cond_enum)
    check("flag off: prompt has no write-path block", U.WRITE_PATH_PROMPT.strip()[:40] not in captured["prompt"])
    check("flag off: JEV not asked mode", "mode" not in SEEN.get("opts", []))
    U._STATIC = None

print("v6p12 checks:", passed, "PASS", flush=True)
assert not failed, failed
