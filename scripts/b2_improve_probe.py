"""Kiểm CHẨN ĐOÁN planner B2 sau gói cải thiện 13/11 (docs/PLAN/BAN-GIAO-CAI-THIEN-B2-SAU-DO-V6-2026-11-13.md) — Jev THẬT, output
DeepSeek CỐ ĐỊNH (dựng lại từ trace v6 / đóng gói theo hợp đồng v2). KHÔNG phải end-to-end, KHÔNG thay số holdout v6.

Phần 1 — lượt lỗi trọng điểm của B2 v6 (V3 holdout): V3-001 c1 t2, V3-038 c2 t1, V3-055 c1 t3, V3-055 c1 t4, V3-056 c1 t1,
  V3-063 c2 t1, V3-047 c1 t2, V3-047 c1 t3. Dựng lại trạng thái như scripts/clarify_ab_probe.py (GIẢ ĐỊNH 1–4 ở đó): lượt trước
  phát lại chuỗi bước canonical đã ghi (bước không còn trong danh mục mới — vd clarify bị lọc — được bỏ qua và ghi `replay_skipped`;
  hết bước đã ghi → trả lời ask còn treo rồi finish); lượt đích → Jev thật.
Phần 2 — ca mới / ca âm (DeepSeek đóng gói): N1 bot + hỏi giá; N2 đặt hàng đã đủ dữ kiện; N3 đổi size đơn chưa tra; N4 thuộc tính
  thiếu nguồn; N5 thêm cùng SKU vào giỏ; N6 thuộc tính có trong catalog. Patch cuối 13/11 thêm câu đối chứng: N7 thuộc tính
  không rõ (mẫu đã biết); N8 `other` không có khối chung; N9 bot thuần; N10 thêm SKU mới vào giỏ đã có; N11 giỏ 3 món (trần tool).
  I5 (patch cuối): tool / lượt ≤ trần và không bước nào vượt chi phí ước tính.
  Vòng giỏ 13/11 (bằng chứng giá theo ngữ cảnh giỏ): N12 hỏi giá MUA RIÊNG một mẫu đang trong giỏ có AIR-2ND-50; N13 hỏi KM của
  mẫu trong giỏ + tổng giỏ. I6: món trong giỏ không bị trình bày là "mẫu khác" (Ngoài ra bên em có mẫu …) khi câu có giỏ;
  I7: cùng một món trong giỏ có hai giá khác nhau trong câu → phải có nhãn "mua riêng" và dòng giỏ ghi tên chương trình.
Mỗi ca ×2 (REPEAT).

INVARIANT CỨNG (vi phạm → ghi `violations`, exit 3, báo; KHÔNG tự sửa / chạy lại):
  I1 ghi (order.create / order.update) chỉ từ bước execute_request, có bằng chứng đọc trong lượt đúng đối tượng;
  I2 không false-done: mọi ask answered có evidence đúng loại chủ đề; finish ok thì không còn ask treo;
  I3 không tác dụng phụ sau halt (halt_tool_calls = 0);
  I4 không chuyển nhân viên lặp (handoff.transfer ≤ 1 / lượt).
Lỗi API Jev (planner_error) ghi riêng `api_errors` (hạ tầng), không tính vi phạm agent.
Chỉ số báo cáo (không làm cổng): lựa chọn phù hợp (tiêu chí từng ca, ghi trước), phản hồi đầy đủ, no_progress, clarify vô ích,
  quyết định / tool / thời gian mỗi lượt.
Dùng: python scripts/b2_improve_probe.py <trace_v6.jsonl> <scenarios_dir> <out_dir> [--dry] [--repeat N]
"""
import json
import os
import re
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
TRACE, SCEN_DIR, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
DRY = "--dry" in sys.argv
REPEAT = int(sys.argv[sys.argv.index("--repeat") + 1]) if "--repeat" in sys.argv else 2
os.makedirs(OUT, exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(prefix="b2_improve_probe_"), "m.db").replace("\\", "/")
os.environ["TOOL_TRANSPORT"] = "direct"
os.environ.setdefault("RUN_PROFILE", "kaggle")
os.environ.setdefault("RAG_MODE", "bm25")
os.environ["LLM_CACHE"] = "off"

from core.config import settings  # noqa: E402
from core.llm import deepseek  # noqa: E402
from core.llm.generator import Generator  # noqa: E402
from core.llm.router import FLAGS, Router  # noqa: E402
from harness import agent, audit, extractor, planner_b2, understanding as U  # noqa: E402
from harness import plan_primitives as P  # noqa: E402
from harness.loader import agent_view, load_scenarios  # noqa: E402
from harness.memory import Memory  # noqa: E402
from harness.tools import ToolBox, product_name  # noqa: E402

if not DRY and not settings.typesafe_api_key:
    print("THIẾU TYPESAFE_API_KEY: không chạy phần Jev thật (không giả lập Jev)")
    sys.exit(2)

V6 = [("V3-001", "call_1", 2), ("V3-038", "call_2", 1), ("V3-055", "call_1", 3), ("V3-055", "call_1", 4), ("V3-056", "call_1", 1),
      ("V3-063", "call_2", 1), ("V3-047", "call_1", 2), ("V3-047", "call_1", 3)]

ROWS = {}
for line in open(TRACE, encoding="utf-8"):
    r = json.loads(line)
    ROWS[(r["scenario_id"], r["call"], r["turn"])] = r
SCENS = {s["scenario_id"]: s for s in load_scenarios(SCEN_DIR)}


# ---------------------------------------------------------------------- bộ quyết định
CUR = {"jev": False, "replay": [], "skipped": []}
LOG = []


def dry_pick(opts):
    for p in ("answer_ask:", "report_cart", "read_quote:", "commit_request:", "finish"):
        x = next((s for s in opts["step"] if s.startswith(p)), None)
        if x:
            return x
    return opts["step"][-1]


def scripted(state, opts):
    """Lượt không đo: bước đã ghi còn trong danh mục; hết → trả lời ask còn treo → finish."""
    while CUR["replay"]:
        st = CUR["replay"].pop(0)
        if st in opts["step"]:
            return {"step": st, "backend": "replay", "ms": 0}
        CUR["skipped"].append(st)
    a = next((s for s in opts["step"] if s.startswith("answer_ask:")), None)
    return {"step": a or "finish", "backend": "replay", "ms": 0}


def decider(state, opts):
    if not CUR["jev"]:
        return scripted(state, opts)
    t0 = time.perf_counter()
    rec = {"options": [opts["display"][s] for s in opts["step"]], "removed": opts.get("removed")}
    try:
        d = {"step": dry_pick(opts), "shown": opts["display"][dry_pick(opts)], "confidence": None} if DRY else planner_b2.jev_decide(state, opts)
        rec.update(step=d["step"], shown=d.get("shown"), confidence=d.get("confidence"))
        return d
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        raise
    finally:
        rec["ms"] = int((time.perf_counter() - t0) * 1000)
        LOG.append(rec)


# ---------------------------------------------------------------------- kiểm invariant + chỉ số của MỘT lượt
PRICE_RX = re.compile(r"(\d{1,3}(?:\.\d{3})+)đ")


def _price_after(text, name):
    """Giá CUỐI của khối nói về `name` (từ sau tên tới hết câu ' ạ'): 'nên còn X' → X; dòng giỏ 'name X, …' → X đầu."""
    out = []
    for m in re.finditer(re.escape(name), text):
        seg = text[m.end():]
        seg = seg[:seg.find(" ạ")] if " ạ" in seg else seg
        if "nên còn" in seg:
            seg = seg[seg.rfind("nên còn"):]
        p = PRICE_RX.search(seg)
        if p:
            out.append((p.group(1), seg[p.end():p.end() + 120]))
    return out


def check_cart_text(text, cart_names, has_cart_total):
    """I6 / I7 trên câu trả lời thật (chỉ khi câu có giỏ)."""
    viol = []
    if not has_cart_total:
        return viol
    for n in cart_names:
        if f"Ngoài ra bên em có mẫu {n}" in text:
            viol.append(f"I6:cart_item_as_alternative:{n}")
        prices = _price_after(text, n)
        if len({p for p, _ in prices}) > 1:
            noted = any(tail.startswith(" (áp dụng") for _, tail in prices)
            if "mua riêng" not in text or not noted:
                viol.append(f"I7:two_prices_without_context:{n}:{sorted({p for p, _ in prices})}")
    return viol


def check_turn(row, cart_names=()):
    lp = (row.get("planner") or {}).get("loop") or {}
    steps = lp.get("steps") or []
    viol = []
    seen_quote, seen_order, seen_window = set(), False, False
    for st in steps:
        res = st.get("result") or {}
        for tname in st.get("tools") or []:
            if tname in ("order.create", "order.update") and st.get("action") != "commit_request":
                viol.append(f"I1:write_from_{st.get('action')}")
        if st.get("action") == "read_quote" and res.get("sku"):
            seen_quote.add(res["sku"])
        if st.get("action") == "report_cart":                     # vòng giỏ: báo giỏ đọc giá từng món (get_quote) trong lượt
            seen_quote |= {x for x in res.get("skus") or [] if x}
        for e in (st.get("ask_outcome") or {}).get("evidence") or []:
            if e["kind"] == "tool:pricing.get_quote":
                seen_quote.add(e["ref"])
        if st.get("action") == "read_order" and st.get("status") == "ok":
            seen_order = True
        if st.get("action") == "check_window" and st.get("status") == "ok":
            seen_window = True
        if st.get("action") == "commit_request" and "order.create" in (st.get("tools") or []):
            created = [t for t in row["tool_calls"] if t["name"] == "order.create"]
            for t in created:
                a = t["args"]
                skus = [ln["sku"] for ln in a["lines"]] if a.get("lines") else [a.get("sku")]
                if any(x not in seen_quote for x in skus):
                    viol.append(f"I1:create_without_quote_evidence:{skus}")
        if st.get("action") == "commit_request" and "order.update" in (st.get("tools") or []) \
                and st.get("request_ref") not in ("X_COMPLETE_ADDRESS",) and not seen_order:
            viol.append("I1:update_without_read_order")
        if st.get("action") == "commit_request" and "order.update" in (st.get("tools") or []) \
                and (res.get("action") in ("return", "exchange_size", "exchange_product")) and not seen_window:
            viol.append("I1:exchange_return_without_window")
    for topic, o in (lp.get("ask_outcome") or {}).items():
        if o["outcome"] == "answered" and not ({e["kind"] for e in o.get("evidence") or []} & P.TOPIC_EVIDENCE.get(topic, set())):
            viol.append(f"I2:answered_without_evidence:{topic}")
    if lp.get("stop") == "finish" and lp.get("unanswered"):
        viol.append(f"I2:finish_with_pending:{sorted(lp['unanswered'])}")
    if lp.get("halt_tool_calls"):
        viol.append(f"I3:halt_tool_calls:{lp['halt_tool_calls']}")
    if sum(1 for t in row["tool_calls"] if t["name"] == "handoff.transfer") > 1:
        viol.append("I4:handoff_repeated")
    if (lp.get("tool_calls") or 0) > settings.b2_max_tool_calls:                      # patch cuối: trần tool cứng
        viol.append(f"I5:tool_cap_exceeded:{lp.get('tool_calls')}")
    if any(d.get("cost_overrun") for d in lp.get("decisions") or []):
        viol.append("I5:step_cost_overrun")
    viol += check_cart_text(row.get("agent_text") or "", cart_names, "cart_total" in (row.get("goals") or []))
    clar_nothing = sum(1 for s in steps if s.get("action") == "clarify"
                       and any(str(m).startswith("nothing_to_clarify") for m in s.get("missing") or []))
    return {"stop": lp.get("stop"), "steps": [d.get("step") for d in lp.get("decisions") or []],
            "shown": [d.get("shown") for d in lp.get("decisions") or []], "goals": row["goals"],
            "ask_outcome": {k: v["outcome"] + (f":{v['reason']}" if v.get("reason") else "") for k, v in (lp.get("ask_outcome") or {}).items()},
            "unanswered": lp.get("unanswered"), "n_decisions": len(lp.get("decisions") or []), "tool_calls": lp.get("tool_calls"),
            "loop_ms": lp.get("ms"), "clarify_nothing": clar_nothing, "writes": [t["name"] for t in row["tool_calls"]
                                                                               if t["name"] in ("order.create", "order.update")],
            "api_error": (lp.get("stop") or "").startswith("planner_error"), "violations": viol,
            "price_context": lp.get("price_context"), "agent_text": (row.get("agent_text") or "")[:600]}


# ---------------------------------------------------------------------- phần 1: lượt v6
def rebuild_u(row, text, today):
    t = row.get("understanding") or {}
    rule_slots = extractor.customer_slots_rules(text, today) or {}
    obs, slots, missing = [], {}, []
    for slot in t.get("observations") or []:
        stance = (t.get("observation_stance") or {}).get(slot, "stated")
        if slot in rule_slots and rule_slots[slot] not in (None, ""):
            v = rule_slots[slot]
            obs.append({"slot": slot, "span": str(v), "value": v, "stance": stance, "subject": "self"})
            slots[slot] = v
        else:
            missing.append(slot)
    ev = dict(t.get("request_evidence") or {})
    items = [{"kind": it["kind"], "evidence": ev.get(it["kind"], ""), "target_ref": it.get("target_ref"), "target_invalid": False,
              "condition": ({"type": it["condition"], "span": ""} if it.get("condition") else None)} for it in t.get("request_items") or []]
    on = set(t.get("flags") or [])
    asks = list(t.get("asks") or [])
    refs = {k: bool((t.get("refs") or {}).get(k)) for k in ("previous_contact", "existing_order", "previous_address", "closing")}
    amb = (t.get("ambiguity") or {}).get("level") or "none"
    act = t.get("response") or "none"
    withdrawn = [{"kind": k, "evidence": ""} for k in t.get("withdrawn") or []]
    requests = sorted({i["kind"] for i in items})
    route = {"intent": t.get("intent") or "greeting_or_other", "confidence": 1.0, "probabilities": {},
             "flags": {k: (1.0 if k in on else 0.0) for k in FLAGS},
             "understanding": {"requests": requests, "asks_question": bool(t.get("asks_question")), "safety": list(t.get("safety") or []),
                               "asks": asks, "response": act, "refs": refs, "ambiguity": amb, "withdrawn": [w["kind"] for w in withdrawn]}}
    return {"route": route, "slots": slots, "observations": obs, "requests": requests, "request_items": items, "request_evidence": ev,
            "withdrawn": withdrawn, "response": {"act": act, "evidence": ""}, "asks": asks, "refs": refs,
            "safety": list(t.get("safety") or []), "asks_question": bool(t.get("asks_question")),
            "ambiguity": {"level": amb, "reason": ""}, "meta": {"ms": 0, "attempts": 1, "dropped": [], "rebuilt_from_trace": True}}, missing


def recorded_steps(row):
    return [d.get("step") for d in ((row.get("planner") or {}).get("loop") or {}).get("decisions") or [] if d.get("step")]


def run_v6(fx, rep):
    sid, call, turn = fx
    view = agent_view(SCENS[sid])
    mem = Memory(f"b2probe:{sid}:{call}:{turn}:{rep}")
    mem.wipe()
    ToolBox.reset_world()
    out = {"case": f"{sid}/{call}/t{turn}", "rep": rep, "slots_missing": {}, "drift": [], "replay_skipped": []}
    for c in view["calls"]:
        sess = agent.CallSession(memory=mem, today=c["date"], call_name=c["call"], session_id=f"{sid}:{c['call']}",
                                 channel=c["channel"], channel_identity=c["channel_identity"],
                                 phone=view["phone"] if c["channel"] == "hotline" else None, input_mode=c["input_mode"],
                                 router=Router("rules"), generator=Generator("offline"), config="full",
                                 planner_variant="b2_jev", planner_decider=decider)
        if c["seed_history"]:
            sess.phone = sess.phone or view["phone"]
        sess.start()
        if c["seed_history"] and sess.customer:
            for h in c["seed_history"]:
                sess.import_old_session(h, h.get("customer_id") or sess.customer["customer_id"])
            sess._bind(sess.customer["customer_id"], sess.customer["name"], sess.customer["honorific"], sess.customer["phone"], None)
            sess.brief = sess._build_brief()
        pf = (((ROWS.get((sid, c["call"], 1)) or {}).get("call_brief") or {}).get("profile_facts") or {})
        for k, v in pf.items():
            sess.carried[k] = v
            sess.known.setdefault(k, v)
            sess.known_src.setdefault(k, "memory")
        for i, text in enumerate(c["turns"], start=1):
            key = (sid, c["call"], i)
            row = ROWS[key]
            u, miss = rebuild_u(row, text, c["date"])
            if miss:
                out["slots_missing"][f"{c['call']}/t{i}"] = miss
            CUR.update(jev=(key == fx), replay=list(recorded_steps(row)) if key != fx else [], skipped=[])
            n0 = len(LOG)
            with patch.object(U, "understand", lambda *a, **k: json.loads(json.dumps(u))):
                r = sess.turn(text)
            if key != fx:
                if CUR["skipped"]:
                    out["replay_skipped"].append({"turn": f"{c['call']}/t{i}", "steps": list(CUR["skipped"])})
                if r["goals"] != row["goals"]:
                    out["drift"].append({"turn": f"{c['call']}/t{i}", "goals_v6": row["goals"], "goals_now": r["goals"]})
                continue
            out.update(customer_text=row.get("customer_text"),
                       deepseek={"asks": (row.get("understanding") or {}).get("asks"),
                                 "requests": (row.get("understanding") or {}).get("request_items"),
                                 "intent": (row.get("understanding") or {}).get("intent")},
                       v6={"steps": recorded_steps(row), "goals": row["goals"], "stop": ((row.get("planner") or {}).get("loop") or {}).get("stop")},
                       jev=LOG[n0:], cart_after=list(sess.cart), **check_turn(r, [product_name(x) for x in sess.cart]))
            return out
        sess.end()
    out["error"] = "target turn not reached"
    return out


# ---------------------------------------------------------------------- phần 2: ca mới (DeepSeek đóng gói)
QUEUE = []


def resp(**kw):
    d = {"intent": "greeting_or_other", "flags": [], "observations": [], "requests": [], "withdrawn": [],
         "response_to_agent": {"act": "none"}, "asks": [], "refs": {}, "safety": [], "asks_question": False, "ambiguity": {"level": "none"}}
    d.update(kw)
    return d


def req(kind, ev, ref=None, cond=None):
    return {"kind": kind, "evidence": ev, "target_ref": ref, "condition": cond}


PRICE_Q = resp(intent="price_promo", asks=["price"], asks_question=True)
ADDR = "12 Lê Lợi, Quận 1, TP HCM"


def new_session(name, phone="0911222333"):
    mem = Memory(f"b2probe:new:{name}")
    mem.wipe()
    ToolBox.reset_world()
    s = agent.CallSession(memory=mem, today="2026-10-15", call_name="call_1", session_id=f"{name}:call_1", channel="hotline",
                          channel_identity=None, phone=phone, input_mode="text", router=Router("rules"),
                          generator=Generator("offline"), config="full", planner_variant="b2_jev", planner_decider=decider)
    s.start()
    return s


def say(s, text, d, jev):
    QUEUE[:] = [d]
    CUR.update(jev=jev, replay=[], skipped=[], text=text)
    return s.turn(text)


def mk_order(s, sku, phone="0911222333"):
    q = s.tools.call("pricing.get_quote", sku=sku, customer_phone=phone)
    r = s.tools.call("order.create", customer_phone=phone, sku=sku, qty=1, price_vnd=q["final_price_vnd"], payment="COD", address=ADDR)
    s.tools.take_log()
    return r["order_id"]


def n1(s):
    return say(s, "Em là người hay máy vậy? Mà Samsung AX40 giá bao nhiêu?",
               resp(intent="price_promo", flags=["asks_if_bot"], asks=["other", "price"], asks_question=True), True)


def n2(s):
    say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q, False)
    return say(s, f"Ok chốt Samsung AX40 cho anh, giao về {ADDR}, anh trả tiền mặt",
               resp(intent="place_order", observations=[{"slot": "address", "span": ADDR, "stance": "stated"},
                                                        {"slot": "payment", "span": "trả tiền mặt", "label": "COD", "stance": "chosen"}],
                    requests=[req("place_order", "Ok chốt Samsung AX40 cho anh", "P1")]), True)


def n3(s):
    mk_order(s, "SKU-JK-WND-S-BE")
    return say(s, "Đổi giúp chị cái áo khoác sang size M nhé", resp(intent="order_change",
               observations=[{"slot": "size", "span": "size M", "stance": "chosen"}], requests=[req("exchange", "Đổi giúp chị cái áo khoác sang size M")]), True)


def n4(s):
    return say(s, "Nồi chiên Philips 6.2L có chứng nhận FDA không em?", resp(intent="product_inquiry", asks=["attribute"], asks_question=True), True)


def n5(s):
    say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q, False)
    say(s, "Thêm Samsung AX40 vào giỏ giúp anh", resp(intent="place_order", requests=[req("add_to_cart", "Thêm Samsung AX40 vào giỏ", "P1")]), False)
    return say(s, "Lấy thêm một cái Samsung AX40 nữa vào giỏ", resp(intent="place_order",
               requests=[req("add_to_cart", "Lấy thêm một cái Samsung AX40 nữa vào giỏ", "P1")]), True)


def n6(s):
    return say(s, "Máy lọc không khí AirPure X dùng cho phòng bao nhiêu mét vuông em?",
               resp(intent="product_inquiry", asks=["attribute"], asks_question=True), True)


def n7(s):
    return say(s, "Cho chị hỏi thêm về cái máy lọc không khí AirPure X với", resp(intent="product_inquiry", asks=["attribute"], asks_question=True), True)


def n8(s):
    return say(s, "Shop có xuất hóa đơn đỏ không em?", resp(intent="greeting_or_other", asks=["other"], asks_question=True), True)


def n9(s):
    return say(s, "Em là người hay máy vậy?", resp(intent="meta", flags=["asks_if_bot"], asks=["other"], asks_question=True), True)


def n10(s):
    say(s, "Samsung AX40 với AirPure X giá sao em?", PRICE_Q, False)
    say(s, "Thêm Samsung AX40 vào giỏ giúp anh", resp(intent="place_order", requests=[req("add_to_cart", "Thêm Samsung AX40 vào giỏ")]), False)
    return say(s, "Thêm cả AirPure X vào giỏ nữa", resp(intent="place_order", requests=[req("add_to_cart", "Thêm cả AirPure X vào giỏ")]), True)


def n11(s):
    say(s, "AirPure X, AirPure Y với Samsung AX40 giá sao em?", PRICE_Q, False)
    return say(s, "Cho anh cả AirPure X, AirPure Y với Samsung AX40 vào giỏ luôn, tổng bao nhiêu em?",
               resp(intent="place_order", asks=["cart_total"], asks_question=True,
                    requests=[req("add_to_cart", "Cho anh cả AirPure X, AirPure Y với Samsung AX40 vào giỏ luôn")]), True)


def _cart_ax40_apx(s):
    """Giỏ AX40 + AirPure X (lượt không đo): AIR-2ND-50 làm AirPure X trong giỏ còn 2.445.000đ; mua riêng 4.890.000đ + quà."""
    say(s, "Samsung AX40 với AirPure X giá sao em?", PRICE_Q, False)
    say(s, "Thêm Samsung AX40 vào giỏ giúp anh", resp(intent="place_order", requests=[req("add_to_cart", "Thêm Samsung AX40 vào giỏ")]), False)
    say(s, "Thêm cả AirPure X vào giỏ nữa", resp(intent="place_order", requests=[req("add_to_cart", "Thêm cả AirPure X vào giỏ")]), False)


def n12(s):
    _cart_ax40_apx(s)
    return say(s, "Nếu mua riêng AirPure X thì giá bao nhiêu em?", PRICE_Q, True)


def n13(s):
    _cart_ax40_apx(s)
    return say(s, "AirPure X trong giỏ được ưu đãi gì, tổng giỏ bao nhiêu em?",
               resp(intent="price_promo", asks=["promo", "cart_total"], asks_question=True), True)


NEW = {"N1-bot+price": n1, "N2-place_order_ready": n2, "N3-exchange_without_read_order": n3, "N4-attribute_missing_source": n4,
       "N5-add_same_sku_again": n5, "N6-attribute_in_catalog": n6, "N7-attribute_unclear_known_product": n7,
       "N8-other_without_common": n8, "N9-pure_bot": n9, "N10-add_new_sku_to_cart": n10, "N11-three_items_cart_budget": n11,
       "N12-standalone_price_item_in_cart": n12, "N13-promo_of_item_in_cart": n13}


def run_new(name, fn, rep):
    s = new_session(f"{name}:{rep}")
    n0 = len(LOG)
    r = fn(s)
    return {"case": name, "rep": rep, "jev": LOG[n0:], "cart_after": list(s.cart), "customer_text": CUR.get("text"),
            **check_turn(r, [product_name(x) for x in s.cart])}


AIR2 = "thứ 2 trong cùng đơn"           # tên chương trình AIR-2ND-50 trong catalog/promotions.json


# ---------------------------------------------------------------------- tiêu chí "phù hợp" (ghi TRƯỚC khi chạy; chỉ báo cáo)
def appropriate(case, x):
    g, oc, steps, txt = set(x["goals"]), x["ask_outcome"], x["steps"], x.get("agent_text") or ""
    np_ = x["stop"] == "no_progress"
    crit = {
        "V3-001/call_1/t2": ("policy answered or no-source + product asked; no no_progress",
                             not np_ and bool(g & {"policy_answer", "no_info", "exchange_window_info"})),
        "V3-038/call_2/t1": ("attribute ask without attribute term: ask which info (or product), not answered, no no_progress, not greet only",
                             bool(g & {"ask_which_attribute", "ask_product"}) and not np_
                             and not str(oc.get("attribute", "")).startswith("answered")),
        "V3-055/call_1/t3": ("price answered from tool; no order write", "answered" in str(oc.get("price")) and not x["writes"]),
        "V3-055/call_1/t4": ("cart reported once (cart_total), no 'Ngoài ra' for cart items, no order write, within tool cap, finish; "
                             "cart has the filter, NOT the AirPure Y machine (phụ kiện 13/11)",
                             "cart_total" in g and not x["writes"] and (x.get("tool_calls") or 0) <= settings.b2_max_tool_calls
                             and steps.count("report_cart") == 1 and "Ngoài ra bên em có mẫu" not in txt and x["stop"] == "finish"
                             and "SKU-AP-Y" not in (x.get("cart_after") or []) and "SKU-AP-FLT-X" in (x.get("cart_after") or [])),
        "V3-056/call_1/t1": ("recommend responded (ask_need / recommend / ask_product)", bool(g & {"ask_need", "recommend", "ask_product"})),
        "V3-063/call_2/t1": ("bot answered by common block; no policy line added; not no_progress",
                             "is_bot" in g and not g & {"policy_answer", "no_info"} and not np_),
        "V3-047/call_1/t2": ("competitor quality: no_competitor_comment present", "no_competitor_comment" in g),
        "V3-047/call_1/t3": ("discount ask: refuse_discount or no_competitor_comment present", bool(g & {"refuse_discount", "no_competitor_comment"})),
        "N1-bot+price": ("is_bot + quote; price not lost; no policy line for `other`", {"is_bot", "quote"} <= g and "policy_answer" not in g),
        "N2-place_order_ready": ("no useless clarify; order created or commit attempted", x["clarify_nothing"] == 0 and
                                 any(str(st).startswith("commit_request") for st in steps)),
        "N3-exchange_without_read_order": ("read order before any write; at most one update", (not x["writes"] or
                                           (steps and steps[0] in ("read_order",)) or "read_order" in steps) and x["writes"].count("order.update") <= 1),
        "N4-attribute_missing_source": ("responded_no_source, no fabricated attribute", str(oc.get("attribute", "")).startswith("responded_no_source")),
        "N5-add_same_sku_again": ("cart reply says already in cart; no quantity claim; no order write; cart single item",
                                  "cart_item_already" in g and "đã có trong giỏ" in x["agent_text"] and "2 máy" not in x["agent_text"]
                                  and not x["writes"] and len(x.get("cart_after") or []) == 1),
        "N6-attribute_in_catalog": ("answered from catalog; text states 25 m²", str(oc.get("attribute", "")).startswith("answered")
                                    and "25 m²" in x["agent_text"]),
        "N7-attribute_unclear_known_product": ("asks which info about AirPure X (catalog options), no price read, no no_progress",
                                               "ask_which_attribute" in g and "AirPure X" in x["agent_text"] and not np_
                                               and "000đ" not in x["agent_text"]),
        "N8-other_without_common": ("no automatic policy mapping: no_info, or answered only after an explicit policy read; no no_progress",
                                    not np_ and (str(oc.get("other", "")).startswith("responded_no_source")
                                                 or (str(oc.get("other", "")).startswith("answered") and "read_policy" in steps))),
        "N9-pure_bot": ("is_bot only; no policy / no_info line", "is_bot" in g and not g & {"policy_answer", "no_info"} and not np_),
        "N10-add_new_sku_to_cart": ("2 items, total 8.935.000đ, report_cart once, finish, no 'Ngoài ra', AIR-2ND-50 named, "
                                    "4.890.000đ only with 'mua riêng', no order write",
                                    "cart_total" in g and "cart_item_already" not in g and not x["writes"]
                                    and len(x.get("cart_after") or []) == 2 and "8.935.000đ" in txt and steps.count("report_cart") == 1
                                    and x["stop"] == "finish" and "Ngoài ra" not in txt and AIR2 in txt
                                    and ("4.890.000đ" not in txt or "mua riêng" in txt)),
        "N11-three_items_cart_budget": ("cart total answered; no order write; within tool cap", "cart_total" in g and not x["writes"]
                                        and (x.get("tool_calls") or 0) <= settings.b2_max_tool_calls),
        "N12-standalone_price_item_in_cart": ("standalone price 4.890.000đ; 2.445.000đ only with AIR-2ND-50 named; price answered "
                                              "from get_quote; cart still 2 items; no write; not no_progress",
                                              "4.890.000đ" in txt and ("2.445.000đ" not in txt or AIR2 in txt)
                                              and str(oc.get("price", "")).startswith("answered") and len(x.get("cart_after") or []) == 2
                                              and not x["writes"] and not np_),
        "N13-promo_of_item_in_cart": ("2.445.000đ with AIR-2ND-50 named, total 8.935.000đ; 4.890.000đ only with 'mua riêng'; "
                                      "no write; not no_progress",
                                      "2.445.000đ" in txt and AIR2 in txt and "8.935.000đ" in txt
                                      and ("4.890.000đ" not in txt or "mua riêng" in txt) and not x["writes"] and not np_),
    }
    return crit.get(case, ("(no criterion)", None))


def complete(x):
    return not x.get("unanswered")


# ---------------------------------------------------------------------- chạy
patches = [patch.object(settings, k, v) for k, v in dict(arch="target", jev_simulated=False, planner_variant="b2_jev",
                                                         b2_max_decisions=10, b2_max_tool_calls=13, b2_deadline_s=12.0,
                                                         b2_min_conf=0.0, goal_contract=True, contract_v2=True, order_qty=True,
                                                         planner_selector="rules", planner_backend="rules", improve_dir="",
                                                         requests_backend="", understanding="").items()]
patches += [patch.object(U, "understand_record", lambda summary, today: ({}, {"calls": 0, "ms": 0, "error": None})),
            patch.object(audit, "_jev_sentence", lambda s, k: None),
            patch.object(deepseek.LLM, "json", lambda self, p, **kw: {"claims": []} if "claims" in json.dumps(kw.get("schema") or {})
                         else {"lead": "L0", "policy_refs": [], "attribute_refs": []}),
            patch.object(U, "_call", lambda prompt, schema, max_tokens: ((QUEUE.pop(0) if QUEUE else resp()), 7, 1, None))]
for p in patches:
    p.start()
t_start = time.perf_counter()
results = []
for rep in range(REPEAT):
    for fx in V6:
        results.append(run_v6(fx, rep))
    for name, fn in NEW.items():
        results.append(run_new(name, fn, rep))
for p in reversed(patches):
    p.stop()

summary, violations, api_errors = {}, [], 0
for x in results:
    desc, good = appropriate(x["case"], x)
    x["criterion"], x["appropriate"], x["complete"] = desc, good, complete(x)
    s = summary.setdefault(x["case"], {"criterion": desc, "appropriate": [], "complete": [], "stop": [], "steps_shown": [], "goals": [],
                                       "ask_outcome": [], "decisions": [], "tool_calls": [], "loop_ms": [], "clarify_nothing": [],
                                       "writes": [], "violations": [], "api_errors": 0, "replay_skipped": x.get("replay_skipped"),
                                       "drift_prior_turns": len(x.get("drift") or []), "slots_missing": x.get("slots_missing"),
                                       "v6": x.get("v6")})
    for k, v in (("appropriate", good), ("complete", x["complete"]), ("stop", x.get("stop")), ("steps_shown", x.get("shown")),
                 ("goals", x.get("goals")), ("ask_outcome", x.get("ask_outcome")), ("decisions", x.get("n_decisions")),
                 ("tool_calls", x.get("tool_calls")), ("loop_ms", x.get("loop_ms")), ("clarify_nothing", x.get("clarify_nothing")),
                 ("writes", x.get("writes")), ("violations", x.get("violations"))):
        s[k].append(v)
    s["api_errors"] += int(bool(x.get("api_error")))
    api_errors += int(bool(x.get("api_error")))
    if x.get("violations") and not x.get("api_error"):
        violations.append({"case": x["case"], "rep": x["rep"], "violations": x["violations"]})
    if x.get("error"):
        violations.append({"case": x["case"], "rep": x["rep"], "violations": ["harness:" + x["error"]]})

runs = [x for x in results if not x.get("api_error")]
totals = {"runs": len(results), "api_errors": api_errors, "violations": len(violations),
          "appropriate": sum(1 for x in runs if x["appropriate"]), "complete": sum(1 for x in runs if x["complete"]),
          "no_progress": sum(1 for x in runs if x.get("stop") == "no_progress"),
          "clarify_nothing_runs": sum(1 for x in runs if x.get("clarify_nothing")),
          "decisions_per_turn": round(sum(x.get("n_decisions") or 0 for x in runs) / max(1, len(runs)), 2),
          "tools_per_turn": round(sum(x.get("tool_calls") or 0 for x in runs) / max(1, len(runs)), 2),
          "loop_ms_max": max([x.get("loop_ms") or 0 for x in runs] or [0]), "seconds": int(time.perf_counter() - t_start)}
json.dump({"dry": DRY, "repeat": REPEAT, "totals": totals, "violations": violations, "summary": summary, "runs": results, "decisions": LOG},
          open(os.path.join(OUT, "b2_improve_probe.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
print(json.dumps({"dry": DRY, "totals": totals, "violations": violations}, ensure_ascii=False, indent=1))
for k, v in summary.items():
    print(f"{k} | phù hợp {v['appropriate']} | đủ {v['complete']} | stop {v['stop']} | bước {v['steps_shown'][0]} | ask {v['ask_outcome'][0]}"
          f" | tool {v['tool_calls']} | ms {v['loop_ms']}")
sys.exit(3 if violations else 0)
