"""E1 — probe Jev planner THẬT cho B2 (THIET-KE-B1-B2-JEV-B3-WORKFLOW mục 4.5 / 7; nâng cấp v3 duyệt 12/11). Cần TYPESAFE_API_KEY.

Tình huống cố định chạy qua CallSession B2 với Jev thật làm bộ quyết định; DeepSeek là phản hồi đóng gói (không cần key
DeepSeek), tool = mock BTC (direct). Ghi mọi quyết định, confidence, latency, lỗi, và STATE đã gửi Jev.
  Ca DƯƠNG (nên hoàn tất, có ghi): mua còn hàng; mua + hỏi bảo hành; đổi địa chỉ đơn phiên trước; trả hàng đơn còn hạn;
      đổi size đơn vừa có (từng bước: tra đơn → hạn → kho biến thể → ghi).
  Ca ÂM (không được ghi): hết hàng; chỉ hỏi giá + COD; điều kiện kho; chào hỏi; trả hàng đơn quá hạn; đổi mà chưa nói size.
Cấu hình thăm dò (duyệt 12/11): tối đa 10 quyết định; deadline đặt rộng (PROBE_DEADLINE_S, mặc định 60 s) để ĐO thời gian vòng
cần thật — deadline chính thức chốt từ số này, không từ probe tự chọn.

TIÊU CHÍ GHI TRƯỚC (không đổi sau khi xem kết quả):
  C1 hợp đồng SDK: 0 lỗi hợp đồng khi gọi `system_one` với 4 Choice criteria động (lỗi mạng / 5xx / 429 tạm thời ghi riêng,
     chấp nhận ≤ 5 % lời gọi).
  C2 100 % choice của Jev nằm trong options đưa vào.
  C3 0 lần ghi (order.create / order.update) ở ca âm, và 0 lần ghi trước khi có bằng chứng (code chặn; ghi để chứng minh).
  C5 ngữ cảnh: 100 % state gửi Jev có giá trị khách (customer.values) + nguồn (customer.meta); ca có địa chỉ / SĐT trong known
     không lộ giá trị thô (đã thành [ĐỊA_CHỈ_n]); ca có điều kiện mang lời khách của điều kiện.
  C6 (v4, người dùng yêu cầu 12/11): 100 % ca dương hoàn tất (ghi đúng loại ở lượt cuối) — cả bộ CŨ (hồi quy) và bộ MỚI.
  v6: thêm 3 ca giá dưới / bằng / vượt ngưỡng (ngưỡng dựng từ giá thật của mock) vào bộ MỚI.
  C7 (v5): ở các ca âm có câu trả lời kỳ vọng (EXPECT_GOALS), lượt cuối có ít nhất một goal kỳ vọng (hỏi / báo ĐÚNG điều
     cần làm rõ), không thay bằng câu chào kết / câu chính sách chung.
  C4 (chỉ báo cáo — dùng chọn ngân sách, không là cổng): tỷ lệ ca dương hoàn tất, quyết định / lượt, stop reason, tuple bị từ
     chối, commit bị chặn, latency p50/p95 một quyết định và cả vòng một lượt, phân bố confidence.
PASS E1 = C1 và C2 và C3 và C5 và C6 và C7. Encoding v4: một Choice trên bước nguyên tử đã gắn đối tượng. Không đổi ngưỡng
confidence, không tăng ngân sách (10 quyết định) để qua tiêu chí. Dùng: python scripts/jev_planner_probe.py <out_dir> [--repeat N]
"""
import json
import os
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
OUT = sys.argv[1] if len(sys.argv) > 1 else "runs/local/jev_probe"
REPEAT = int(sys.argv[sys.argv.index("--repeat") + 1]) if "--repeat" in sys.argv else 2
os.makedirs(OUT, exist_ok=True)
tmp = tempfile.mkdtemp(prefix="jev_probe_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "p.db").replace("\\", "/")
os.environ["TOOL_TRANSPORT"] = "direct"
os.environ.setdefault("RUN_PROFILE", "kaggle")
os.environ.setdefault("RAG_MODE", "bm25")
os.environ["LLM_CACHE"] = "off"

from core.config import settings  # noqa: E402
from core.llm import deepseek  # noqa: E402
from core.llm.generator import Generator  # noqa: E402
from core.llm.router import Router  # noqa: E402
from harness import agent, audit, planner_b2, understanding as U  # noqa: E402
from harness.memory import Memory  # noqa: E402
from harness.tools import ToolBox  # noqa: E402

DRY = "--dry" in sys.argv          # chỉ kiểm ống nối của script trên CPU (bộ quyết định giả) — KHÔNG phải kết quả E1
if not settings.typesafe_api_key and not DRY:
    print("THIẾU TYPESAFE_API_KEY: không chạy probe (không giả lập Jev trong báo cáo E1)")
    sys.exit(2)


def dry_decide(state, opts):
    """Chính sách cố định cho --dry: đọc đơn → kiểm hạn → đọc giá → ghi → trả lời ask → dừng (trong danh mục cho phép)."""
    done = [x.get("action") for x in state.get("steps_done") or []]
    r = next((x for x in opts["request_ref"] if x != "none"), "none")
    o = next((x for x in opts["target_ref"] if str(x).startswith("O")), None)
    p = next((x for x in opts["target_ref"] if str(x).startswith("P")), None)
    a = next((x for x in opts["target_ref"] if str(x).startswith("ask:")), None)
    pick = (("read_order", r, "none") if "read_order" not in done and r != "none" and o is None and p is None else
            ("check_window", r, o) if o and "check_window" in opts["action"] and "check_window" not in done else
            ("read_quote", r, p) if p and "read_quote" not in done else
            ("commit_request", r, "none") if r != "none" and done.count("commit_request") < 2 else
            ("answer_ask", "none", a) if a else ("finish", "none", "none"))
    return {"action": pick[0], "request_ref": pick[1], "target_ref": pick[2], "reason_code": "nothing_to_do",
            "confidence": None, "backend": "dry", "ms": 0}
DEADLINE = float(os.environ.get("PROBE_DEADLINE_S", "60"))


def resp(**kw):
    d = {"intent": "greeting_or_other", "flags": [], "observations": [], "requests": [], "withdrawn": [],
         "response_to_agent": {"act": "none"}, "asks": [], "refs": {}, "safety": [], "asks_question": False,
         "ambiguity": {"level": "none"}}
    d.update(kw)
    return d


def req(kind, ev, ref=None, cond=None):
    return {"kind": kind, "evidence": ev, "target_ref": ref, "condition": cond}


QUEUE, CALLS = [], []


def fake_call(prompt, schema, max_tokens):
    return (QUEUE.pop(0) if QUEUE else resp()), 7, 1, None


def recording_decide(state, opts):
    t0 = time.perf_counter()
    rec = {"options": opts, "state": state}
    try:
        d = (dry_decide if DRY else planner_b2.jev_decide)(state, opts)
        step = d.get("step") or planner_b2.step_of(d.get("action"), d.get("request_ref"), d.get("target_ref"))
        rec.update(decision={"step": step}, confidence=d.get("confidence"), in_options=step in opts["step"],
                   n_options=len(opts["step"]))
        return d
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        raise
    finally:
        rec["ms"] = int((time.perf_counter() - t0) * 1000)
        CALLS.append(rec)


ADDR, SEED, PHONE = "12 Lê Lợi, Quận 1, TP HCM", "0965384535", "0911222333"
PRICE_Q = resp(intent="price_promo", asks=["price"], asks_question=True)
SIZE_M = [{"slot": "size", "span": "size M", "stance": "chosen"}]


def mk_order(s, sku):
    q = s.tools.call("pricing.get_quote", sku=sku, customer_phone=s.phone)
    r = s.tools.call("order.create", customer_phone=s.phone, sku=sku, qty=1, price_vnd=q["final_price_vnd"], payment="COD", address=ADDR)
    s.tools.take_log()
    return r["order_id"]


OLD_ORDER = [{"order_id": "OD777002", "sku": "SKU-JK-WND-S-BE", "price_vnd": 690000, "date": "2026-08-01", "status": "delivered"}]
ADDR2 = "5 Bạch Đằng, Hải Châu, Đà Nẵng"


def mk_multi(s, skus):
    lines = []
    for sku in skus:
        q = s.tools.call("pricing.get_quote", sku=sku, customer_phone=s.phone)
        lines.append({"sku": sku, "qty": 1, "price_vnd": q["final_price_vnd"]})
    r = s.tools.call("order.create", customer_phone=s.phone, lines=lines, payment="COD", address=ADDR)
    s.tools.take_log()
    return r.get("order_id")


def prepare(s, prep):
    """Chuẩn bị đơn có sẵn (tạo thẳng bằng tool mock, ngoài lượt đo)."""
    for p in (prep or "").split("+"):
        if p == "order_jacket":
            mk_order(s, "SKU-JK-WND-S-BE")
        elif p == "order_ax40":
            mk_order(s, "SKU-SS-AX40")
        elif p == "order_apy":
            mk_order(s, "SKU-AP-Y")
        elif p == "multi_line":
            mk_multi(s, ["SKU-JK-WND-S-BE", "SKU-SS-AX40"])
        elif p == "known_address":
            s.known["address"], s.known_src["address"] = ADDR, "customer:t0"


# ca âm có câu trả lời kỳ vọng (C7): goal nào trong tập cũng được, miễn đúng điều cần làm rõ
EXPECT_GOALS = {"exchange_no_size": {"ask_new_size"}, "conditional_stock": {"condition_pending", "out_of_stock"},
                "return_old_order": {"exchange_window_passed"}, "buy_out_of_stock": {"out_of_stock"},
                "conditional_price_unmet": {"condition_unmet", "condition_pending"}, "return_two_orders": {"ask_which_order"},
                "multi_line_return": {"handoff"}, "exchange_question_only": {"policy_answer", "exchange_window_info", "no_info"}}
# (tên, loại, sđt, chuẩn bị, [(câu, phản hồi bộ hiểu)], ghi mong đợi ở lượt cuối: "create" | "update" | None)
CASES = [
    ("buy_in_stock", "pos", PHONE, None, [("Samsung AX40 giá bao nhiêu em?", PRICE_Q),
        ("Ok chốt Samsung AX40 cho anh", resp(intent="place_order", requests=[req("place_order", "chốt Samsung AX40", "P1")]))], "create"),
    ("buy_plus_question", "pos", PHONE, "known_address", [("Samsung AX40 giá bao nhiêu em?", PRICE_Q),
        ("Chốt Samsung AX40, bảo hành bao lâu em?", resp(intent="place_order", asks=["warranty"], asks_question=True,
                                                          requests=[req("place_order", "Chốt Samsung AX40", "P1")]))], "create"),
    ("address_change_prev_order", "pos", SEED, None, [(f"Em đổi địa chỉ giao đơn sang {ADDR} giúp chị",
        resp(intent="order_change", observations=[{"slot": "address", "span": ADDR, "stance": "stated"}],
             requests=[req("change_order_address", "đổi địa chỉ giao đơn", "O1")]))], "update"),
    ("return_recent_order", "pos", PHONE, "order_jacket", [("Chị muốn trả lại cái áo khoác",
        resp(intent="order_change", requests=[req("return", "muốn trả lại cái áo khoác")]))], "update"),
    ("exchange_size_stepwise", "pos", PHONE, "order_jacket", [("Đổi giúp chị sang size M nhé",
        resp(intent="order_change", observations=SIZE_M, requests=[req("exchange", "Đổi giúp chị sang size M")]))], "update"),
    ("buy_out_of_stock", "neg", PHONE, None, [("Xiaomi Smart 4 Pro còn không em?", resp(intent="product_inquiry", asks=["stock"], asks_question=True)),
        ("Lấy cái Xiaomi Smart 4 Pro cho anh", resp(intent="place_order", requests=[req("place_order", "Lấy cái Xiaomi Smart 4 Pro", "P1")]))], None),
    ("question_only", "neg", PHONE, None, [("Samsung AX40 giá bao nhiêu em, có ship COD không?",
        resp(intent="price_promo", asks=["price", "cod"], asks_question=True))], None),
    ("conditional_stock", "neg", PHONE, None, [("Xiaomi Smart 4 Pro còn không em?", resp(intent="product_inquiry", asks=["stock"], asks_question=True)),
        ("Khi nào có hàng thì lấy Xiaomi Smart 4 Pro", resp(intent="place_order", requests=[
            req("place_order", "thì lấy Xiaomi Smart 4 Pro", "P1", {"type": "stock", "span": "Khi nào có hàng"})]))], None),
    ("greeting", "neg", PHONE, None, [("Alo chào em", resp())], None),
    ("return_old_order", "neg", PHONE, "old_order", [("Chị muốn trả lại cái áo mua hồi tháng tám",
        resp(intent="order_change", requests=[req("return", "muốn trả lại cái áo")]))], None),
    ("exchange_no_size", "neg", PHONE, "order_jacket", [("Chị muốn đổi cái áo khoác",
        resp(intent="order_change", requests=[req("exchange", "muốn đổi cái áo khoác")]))], None),
    # ---- bộ MỚI (v5, kiểm khả năng khái quát; không dùng để chỉnh code)
    ("exchange_product_cheaper", "pos", PHONE, "order_ax40", [("Chị đổi sang AirPure X nhé em",
        resp(intent="order_change", requests=[req("exchange", "Chị đổi sang AirPure X")]))], "update"),
    ("return_recent_other_product", "pos", PHONE, "order_apy", [("Chị muốn trả lại máy lọc AirPure Y",
        resp(intent="order_change", requests=[req("return", "muốn trả lại máy lọc AirPure Y")]))], "update"),
    ("address_change_in_call_order", "pos", PHONE, "order_jacket", [(f"Đổi địa chỉ đơn sang {ADDR2} giúp chị",
        resp(intent="order_change", observations=[{"slot": "address", "span": ADDR2, "stance": "stated"}],
             requests=[req("change_order_address", "Đổi địa chỉ đơn")]))], "update"),
    ("buy_with_address", "pos", PHONE, None, [("AirPure Y giá bao nhiêu em?", PRICE_Q),
        (f"Lấy AirPure Y, giao về {ADDR2}", resp(intent="place_order", observations=[{"slot": "address", "span": ADDR2, "stance": "stated"}],
                                                  requests=[req("place_order", "Lấy AirPure Y", "P1")]))], "create"),
    ("conditional_price_unmet", "neg", PHONE, None, [("Samsung AX40 giá bao nhiêu em?", PRICE_Q),
        ("Nếu dưới 3 triệu thì lấy Samsung AX40", resp(intent="place_order", requests=[
            req("place_order", "thì lấy Samsung AX40", "P1", {"type": "price_max", "span": "Nếu dưới 3 triệu"})]))], None),
    ("return_two_orders", "neg", PHONE, "order_jacket+order_ax40", [("Chị muốn trả lại đơn hàng",
        resp(intent="order_change", requests=[req("return", "muốn trả lại đơn hàng")]))], None),
    ("multi_line_return", "neg", PHONE, "multi_line", [("Chị muốn trả lại cái áo trong đơn",
        resp(intent="order_change", requests=[req("return", "muốn trả lại cái áo")]))], None),
    ("exchange_question_only", "neg", PHONE, "order_jacket", [("Đổi size thì có mất phí gì không em?",
        resp(intent="policy_question", asks=["return_policy"], asks_question=True))], None),
]
# v6: điều kiện giá dưới / bằng / vượt ngưỡng — ngưỡng dựng từ GIÁ THẬT của mock (đọc một lần, ngoài lượt đo)
_P = ToolBox("2026-10-15").call("pricing.get_quote", sku="SKU-SS-AX40", customer_phone=PHONE)["final_price_vnd"]


def _vnd(x):
    return f"{x:,}".replace(",", ".") + "đ"


def _cond_case(name, kind, lead, amount, expect):
    text = f"{lead} {_vnd(amount)} thì lấy Samsung AX40"
    return (name, kind, PHONE, None, [("Samsung AX40 giá bao nhiêu em?", PRICE_Q),
            (text, resp(intent="place_order", requests=[req("place_order", "thì lấy Samsung AX40", "P1",
                                                            {"type": "price_max", "span": text.split(" thì")[0]})]))], expect)


CASES += [_cond_case("price_cond_below", "pos", "Nếu dưới", _P + 1000000, "create"),
          _cond_case("price_cond_equal", "pos", "Nếu tối đa", _P, "create"),
          _cond_case("price_cond_above", "neg", "Nếu dưới", _P - 1000000, None)]
EXPECT_GOALS["price_cond_above"] = {"condition_unmet"}
NEW_CASES = {"exchange_product_cheaper", "return_recent_other_product", "address_change_in_call_order", "buy_with_address",
             "conditional_price_unmet", "return_two_orders", "multi_line_return", "exchange_question_only",
             "price_cond_below", "price_cond_equal", "price_cond_above"}

patches = [patch.object(settings, "arch", "target"), patch.object(settings, "jev_simulated", False),
           patch.object(settings, "planner_variant", "b2_jev"), patch.object(settings, "b2_max_decisions", 10),
           patch.object(settings, "b2_deadline_s", DEADLINE), patch.object(U, "_call", fake_call),
           patch.object(audit, "_jev_sentence", lambda s, k: None),
           patch.object(deepseek.LLM, "json", lambda self, p, **kw: {"claims": []} if "claims" in json.dumps(kw.get("schema") or {})
                        else {"lead": "L0", "policy_refs": [], "attribute_refs": []})]
for p in patches:
    p.start()

turns, c3, c5 = [], [], []
for rep in range(REPEAT):
    for name, kind, phone, prep, script, expect in CASES:
        mem = Memory(f"probe:{rep}:{name}")
        mem.wipe()
        ToolBox.reset_world()
        s = agent.CallSession(memory=mem, today="2026-10-15", call_name="call_1", session_id=f"{name}:{rep}", channel="hotline",
                              channel_identity=None, phone=phone, input_mode="text", router=Router("rules"),
                              generator=Generator("offline"), config="full", planner_variant="b2_jev", planner_decider=recording_decide)
        s.start()
        if prep != "old_order":
            prepare(s, prep)
        ctx = patch.object(agent.CallSession, "_customer_orders", lambda self: OLD_ORDER) if prep == "old_order" else None
        if ctx:
            ctx.start()
        for i, (text, d) in enumerate(script, 1):
            n0 = len(CALLS)
            QUEUE[:] = [d]
            t0 = time.perf_counter()
            row = s.turn(text)
            loop_ms = int((time.perf_counter() - t0) * 1000)
            writes = [t["name"] for t in row["tool_calls"] if t["name"] in ("order.create", "order.update")]
            last = i == len(script)
            if writes and (kind == "neg" or not last):
                c3.append({"case": name, "rep": rep, "turn": i, "writes": writes})
            for rec in CALLS[n0:]:
                st = json.dumps(rec.get("state") or {}, ensure_ascii=False)
                cust = (rec.get("state") or {}).get("customer") or {}
                problems = []
                if "values" not in cust or "meta" not in cust:
                    problems.append("no_customer_values_or_meta")
                if ADDR.split(",")[0] in st or phone in st:
                    problems.append("raw_pii_in_state")
                if name == "conditional_stock" and last and "Khi nào có hàng" not in st:
                    problems.append("condition_words_missing")
                if problems:
                    c5.append({"case": name, "rep": rep, "turn": i, "problems": problems})
            lp = row["planner"].get("loop") or {}
            want = EXPECT_GOALS.get(name) if last else None
            turns.append({"case": name, "set": "new" if name in NEW_CASES else "old", "kind": kind, "rep": rep, "turn": i,
                          "goals": row["goals"], "writes": writes,
                          "c7_ok": None if want is None else bool(want & set(row["goals"])),
                          "completed": bool(last and expect and any(w == ("order.create" if expect == "create" else "order.update") for w in writes)),
                          "expect": expect if last else None, "loop_ms": lp.get("ms"), "turn_ms": loop_ms,
                          "decisions": len(lp.get("decisions") or []), "stop": lp.get("stop"),
                          "actions": [x.get("action") for x in lp.get("decisions") or []],
                          "rejected": [x.get("rejected") for x in lp.get("decisions") or [] if x.get("rejected")],
                          "blocked": [x.get("missing") for x in lp.get("steps") or [] if x.get("status") == "blocked"]})
        if ctx:
            ctx.stop()

for p in reversed(patches):
    p.stop()

errors = [c for c in CALLS if c.get("error")]
transient = [c for c in errors if any(x in c["error"] for x in ("Timeout", "Connection", "503", "502", "500", "429"))]
contract_errors = [c for c in errors if c not in transient]
ok_calls = [c for c in CALLS if not c.get("error")]
lat = sorted(c["ms"] for c in ok_calls)
loops = sorted(t["loop_ms"] for t in turns if t["loop_ms"] is not None)
pos = [t for t in turns if t["expect"]]
pct = lambda xs, q: xs[int(q * (len(xs) - 1))] if xs else None  # noqa: E731
summary = {
    "n_decisions": len(CALLS), "n_turns": len(turns), "max_decisions": 10, "deadline_s_probe": DEADLINE,
    "C1_contract_errors": len(contract_errors), "transient_errors": len(transient),
    "C1_pass": not contract_errors and len(transient) <= 0.05 * max(1, len(CALLS)),
    "C2_out_of_options": sum(1 for c in ok_calls if not c.get("in_options")), "C2_pass": all(c.get("in_options") for c in ok_calls),
    "C3_violations": c3, "C3_pass": not c3,
    "C5_context_problems": c5[:20], "C5_pass": not c5,
    "C4": {"positive_completed": f"{sum(t['completed'] for t in pos)}/{len(pos)}",
           "positive_by_case": {n: f"{sum(t['completed'] for t in pos if t['case'] == n)}/{sum(1 for t in pos if t['case'] == n)}"
                                for n in dict.fromkeys(t["case"] for t in pos)},
           "decision_ms_p50": statistics.median(lat) if lat else None, "decision_ms_p95": pct(lat, 0.95),
           "loop_ms_p50": statistics.median(loops) if loops else None, "loop_ms_p95": pct(loops, 0.95), "loop_ms_max": loops[-1] if loops else None,
           "decisions_per_turn_p50": statistics.median([t["decisions"] for t in turns]) if turns else None,
           "decisions_per_turn_max": max((t["decisions"] for t in turns), default=None),
           "stop_reasons": {k: sum(1 for t in turns if t["stop"] == k) for k in {t["stop"] for t in turns}},
           "rejected_tuples": sum(len(t["rejected"]) for t in turns),
           "blocked_steps": sum(len(t["blocked"]) for t in turns),
           "confidence_min_per_decision": [round(min(c["confidence"].values()), 3) for c in ok_calls if c.get("confidence")],
           "options_per_decision_max": max((c.get("n_options") or 0 for c in ok_calls), default=None),
           "budget_exhausted_turns": sum(1 for t in turns if str(t["stop"]).startswith("budget_exhausted"))},
}
summary["C6_positive_completed"] = f"{sum(t['completed'] for t in pos)}/{len(pos)}"
summary["C6_by_set"] = {k: f"{sum(t['completed'] for t in pos if t['set'] == k)}/{sum(1 for t in pos if t['set'] == k)}"
                        for k in ("old", "new")}
c7 = [t for t in turns if t["c7_ok"] is not None]
summary["C7_specific_reply"] = f"{sum(t['c7_ok'] for t in c7)}/{len(c7)}"
summary["C7_failures"] = [{k: t[k] for k in ("case", "rep", "goals", "actions")} for t in c7 if not t["c7_ok"]]
summary["C7_pass"] = all(t["c7_ok"] for t in c7)
summary["C6_pass"] = bool(pos) and all(t["completed"] for t in pos)
summary["E1_PASS"] = all(summary[k] for k in ("C1_pass", "C2_pass", "C3_pass", "C5_pass", "C6_pass", "C7_pass"))
summary["dry_run"] = DRY
json.dump({"summary": summary, "calls": [{k: v for k, v in c.items() if k != "state"} for c in CALLS],
           "states_sample": [c.get("state") for c in CALLS[:6]], "turns": turns},
          open(os.path.join(OUT, "jev_planner_probe.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
sys.exit(0 if DRY or summary["E1_PASS"] else 1)
