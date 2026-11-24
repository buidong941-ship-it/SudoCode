"""E0 (Kaggle CPU) cho biến thể chủ sở hữu tiến trình (B3 đã xóa 24/11; V07, V09, V14 và nhánh b3 của V22 bỏ theo) (THIET-KE-B1-B2-JEV-B3-WORKFLOW-2026-11-12, mục 7).

Không gọi API thật: DeepSeek = phản hồi đóng gói theo hợp đồng v2 (như planner_target_matrix_check); Jev planner = bộ quyết định
CÓ KỊCH BẢN (hàm của state/options) để kiểm WIRING, guard, ngân sách, trace. Tool = mock BTC thật (direct), memory SQLite tạm.
Stub không chứng minh Jev / DeepSeek chọn đúng trên câu thật — phải đo ở E1/E3.

V01 switch: ba giá trị chạy được không sửa source; tổ hợp mâu thuẫn bị từ chối; bảng phân nhóm đủ
V02 B2: Jev đổi bước kế theo kết quả tool (hết hàng → hỏi rõ; còn hàng → ghi)
V03 B2: ghi khi thiếu bằng chứng → blocked, executor không tự đọc / tự ghi thay
V04 B2: lặp → no_progress; hết ngân sách quyết định; lỗi API; tuple sai; confidence thấp → không ghi
V05 B2: finish khi còn ask → bị chặn; ask được trả lời có nguồn; ask còn lại khi dừng được ghi
V06 B2: đơn trùng đã tạo → hỏi đặt thêm, không ghi
V07 B3: workflow tự đọc bằng chứng còn thiếu rồi ghi đúng đối tượng; hết hàng không ghi; câu hỏi thuần không ghi
V08 B3/B2 can thiệp: vô hiệu handler bảng place_order → B1 không ghi được, B2/B3 vẫn ghi (quyền quyết định đã chuyển)
V09 B3: nhiều yêu cầu cùng lượt → hỏi, không gộp; điều kiện kho chưa rõ → không ghi
V10 cách ly: namespace bộ nhớ theo run/biến thể không đọc chéo; run_id chứa biến thể
"""
import json
import os
import sys
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
tmp = tempfile.mkdtemp(prefix="planner_variants_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "v.db").replace("\\", "/")
os.environ["TOOL_TRANSPORT"] = "direct"
os.environ.setdefault("RUN_PROFILE", "local")
os.environ.setdefault("RAG_MODE", "bm25")
os.environ["LLM_CACHE"] = "off"

from core.config import settings, check_variant  # noqa: E402
from core.llm import deepseek  # noqa: E402
from core.llm.generator import Generator  # noqa: E402
from core.llm.router import Router  # noqa: E402
from harness import agent, audit, planner_table, planner_variants, request_state, understanding as U  # noqa: E402
from harness.memory import Memory  # noqa: E402
from harness import plan_primitives as P  # noqa: E402
from harness.tools import ToolBox  # noqa: E402

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
    d = QUEUE.pop(0) if QUEUE else resp()
    return d, 7, 1, None


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


def session(name, variant, decider=None, phone="0911222333"):
    mem = Memory(f"variants:{variant}:{name}")
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


def req(kind, ev, ref=None, cond=None):
    return {"kind": kind, "evidence": ev, "target_ref": ref, "condition": cond}


def loop(row):
    return (row.get("planner") or {}).get("loop") or {}


def first(opts, key, prefix):
    return next((x for x in opts[key] if str(x).startswith(prefix)), "none")


def evidence(state):
    return state.get("evidence_this_turn") or []


class Script:
    """Bộ quyết định có kịch bản: mỗi phần tử là tuple (action, request_ref, target_ref, reason) hoặc hàm (state, opts) → tuple.
    Hết kịch bản → finish. Ghi lại state đã nhận để kiểm input."""

    def __init__(self, *plan, conf=None, raise_at=None):
        self.plan, self.conf, self.raise_at, self.seen = list(plan), conf, raise_at, []

    def __call__(self, state, opts):
        self.seen.append(state)
        self.opts_seen = getattr(self, "opts_seen", []) + [opts]
        if self.raise_at is not None and len(self.seen) - 1 == self.raise_at:
            raise TimeoutError("jev down")
        step = self.plan.pop(0) if self.plan else ("finish", "none", "none", "nothing_to_do")
        if callable(step):
            step = step(state, opts)
        if isinstance(step, dict):                 # quyết định dạng bước nguyên tử (v4): {"step": "..."}
            return step
        a, r, t, why = step
        out = {"action": a, "request_ref": r, "target_ref": t, "reason_code": why, "backend": "script", "ms": 0}
        if self.conf is not None:
            out["confidence"] = {k: self.conf for k in ("action", "request_ref", "target_ref", "reason_code")}
        return out


A_OUT, B_OK = "SKU-XM-4P", "SKU-SS-AX40"        # 15/10: Xiaomi Smart 4 Pro hết hàng, Samsung AX40 còn hàng (catalog BTC)
PRICE_Q = resp(intent="price_promo", asks=["price"], asks_question=True)


def adaptive_buyer(state, opts):
    """Chính sách thử nghiệm: đọc giá → đọc kho → còn hàng thì ghi, hết hàng thì hỏi rõ. Quyết định theo BẰNG CHỨNG trong state."""
    ev = {e.get("sku_ref"): e for e in evidence(state)}
    p = first(opts, "target_ref", "P")
    r = first(opts, "request_ref", "R")
    if p not in ev:
        return ("read_quote", r, p, "need_price")
    if ev[p].get("in_stock") is False:
        return ("clarify", r, "none", "after_blocked")
    done = [x for x in state.get("steps_done") or [] if x.get("action") == "commit_request"]
    if r != "none" and not done:
        return ("commit_request", r, "none", "commit_ready")
    return ("finish", "none", "none", "nothing_to_do")


# ================================================================== V01: switch
with Ctx():
    for v in ("b1", "b2_jev"):
        ok("V01", f"factory builds {v}", planner_variants.make(v).name, v)
    rows = planner_table.load_rows()
    try:
        planner_variants.check_partition(rows); part = True
    except ValueError as e:
        part = str(e)
    ok("V01", "every core table row is classified common/order/sales/answer", part, True)

    def rejected(variant, **kw):
        with patch.multiple(settings, **kw):
            try:
                check_variant(variant, settings)
                return False
            except ValueError:
                return True
    ok("V01", "b2 without ARCH=target rejected", rejected("b2_jev", arch=""), True)
    ok("V01", "b2 + PLANNER_BACKEND fallback rejected", rejected("b2_jev", planner_backend="qwen"), True)
    ok("V01", "b2 with zero budget rejected", rejected("b2_jev", b2_max_decisions=0), True)
    ok("V01", "unknown variant rejected", rejected("b4", arch="target"), True)
    ok("V01", "b1 accepted without target", rejected("b1", arch=""), False)
    s = session("v01", "b1")
    row = say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    ok("V01", "b1 trace records variant, no loop", (row["planner"]["variant"], "loop" in row["planner"]), ("b1", False))

# ================================================================== V02: B2 đổi bước kế theo kết quả tool
with Ctx():
    d = Script(adaptive_buyer, adaptive_buyer, adaptive_buyer, adaptive_buyer)
    s = session("v02a", "b2_jev", d)
    say(s, "Xiaomi Smart 4 Pro còn không em?", resp(intent="product_inquiry", asks=["stock"], asks_question=True))
    d.plan = [adaptive_buyer] * 4
    row = say(s, "Lấy cái Xiaomi Smart 4 Pro cho anh", resp(intent="place_order", requests=[req("place_order", "Lấy cái Xiaomi Smart 4 Pro", "P1")]))
    acts = [x["action"] for x in loop(row).get("decisions", [])]
    ok("V02", "out of stock: Jev reads quote, then clarifies (no commit)", (acts[:2], created_skus(row)), (["read_quote", "clarify"], []))
    ok("V02", "Jev saw stock evidence before deciding", any(e.get("in_stock") is False for st in d.seen for e in evidence(st)), True)
    d2 = Script(*[adaptive_buyer] * 4)
    s = session("v02b", "b2_jev", d2)
    say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    d2.plan = [adaptive_buyer] * 4
    row = say(s, "Ok chốt Samsung AX40 cho anh", resp(intent="place_order", requests=[req("place_order", "chốt Samsung AX40", "P1")]))
    acts = [x["action"] for x in loop(row).get("decisions", [])]
    ok("V02", "in stock: read_quote → commit_request → order created", (acts[:2], created_skus(row)), (["read_quote", "commit_request"], [[B_OK]]))
    ok("V02", "trace per step: tools of each step recorded", [x["tools"] for x in loop(row)["steps"]][:2],
       [["pricing.get_quote", "inventory.check"], ["pricing.quote_order", "order.create"]])
    ok("V02", "reply announces created order", "order_created" in row["goals"], True)

# ================================================================== V03: thiếu bằng chứng → blocked, không tự đọc / ghi thay
with Ctx():
    d = Script(lambda st, o: ("commit_request", first(o, "request_ref", "R"), "none", "commit_ready"),
               ("finish", "none", "none", "nothing_to_do"))
    s = session("v03", "b2_jev", Script())
    say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    s.planner.decider = d
    row = say(s, "Chốt Samsung AX40", resp(intent="place_order", requests=[req("place_order", "Chốt Samsung AX40", "P1")]))
    st = loop(row)["steps"][0]
    ok("V03", "commit without evidence → blocked with missing reads", (st["status"], sorted(st.get("missing") or [])),
       ("blocked", ["read_quote:P1", "read_stock:P1"]))
    ok("V03", "executor did not call any tool on blocked commit", st["tools"], [])
    ok("V03", "no order written", created_skus(row), [])
    ok("V03", "request still open (not consumed)", [i["status"] for i in row["request_state"]["items"]], ["open"])

# ================================================================== V04: lặp / ngân sách / lỗi / tuple sai / confidence
with Ctx():
    rp = ("read_policy", "none", "none", "need_policy")
    s = session("v04a", "b2_jev", Script(rp, rp, rp))
    row = say(s, "Bên mình giao hàng mấy ngày?", resp(intent="policy_question", asks_question=True))
    ok("V04", "same action twice without new evidence → no_progress", loop(row).get("stop"), "no_progress")
with Ctx({"b2_max_decisions": 2}):
    s = session("v04b", "b2_jev", Script(("read_order", "none", "none", "need_order"), ("read_policy", "none", "none", "need_policy"),
                                          ("read_order", "none", "none", "need_order")))
    row = say(s, "Đơn của anh tới đâu rồi?", resp(intent="order_status", asks_question=True))
    ok("V04", "decision budget enforced", (loop(row).get("stop"), len(loop(row)["decisions"])), ("budget_exhausted:decisions", 2))
with Ctx():
    s = session("v04c", "b2_jev", Script())
    say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    s.planner.decider = Script(raise_at=0)
    row = say(s, "Chốt Samsung AX40", resp(intent="place_order", requests=[req("place_order", "Chốt Samsung AX40", "P1")]))
    ok("V04", "Jev API error → stop planner_error, no write, no fallback", (loop(row).get("stop"), created_skus(row)),
       ("planner_error:TimeoutError", []))
    s.planner.decider = Script(("commit_request", "none", "none", "commit_ready"))
    row = say(s, "Chốt Samsung AX40", resp(intent="place_order", requests=[req("place_order", "Chốt Samsung AX40", "P1")]))
    ok("V04", "inconsistent tuple (commit without request) rejected, no write",
       (str(loop(row).get("stop")).startswith("invalid_tuple"), created_skus(row)), (True, []))
with Ctx({"b2_min_conf": 0.5}):
    s = session("v04d", "b2_jev", Script())
    say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    s.planner.decider = Script(*[adaptive_buyer] * 4, conf=0.2)
    row = say(s, "Chốt Samsung AX40", resp(intent="place_order", requests=[req("place_order", "Chốt Samsung AX40", "P1")]))
    ok("V04", "low confidence → stop, no write", (loop(row).get("stop"), created_skus(row)), ("low_confidence", []))

# ================================================================== V05: ask phải được trả lời / ghi lý do
with Ctx():
    d = Script(("finish", "none", "none", "nothing_to_do"), lambda st, o: ("answer_ask", "none", first(o, "target_ref", "ask:"), "customer_asked"),
               ("finish", "none", "none", "nothing_to_do"))
    s = session("v05", "b2_jev", Script())
    say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    s.planner.decider = d
    row = say(s, "Có ship COD không em?", resp(intent="policy_question", asks=["cod"], asks_question=True))
    st = loop(row)["steps"]
    ok("V05", "finish with pending ask is blocked", (st[0]["action"], st[0]["status"], st[0].get("missing")), ("finish", "blocked", ["ask:cod"]))
    ok("V05", "ask answered with sourced block", ("cod" in loop(row)["answered"], bool({"cod_ok", "cod_limit"} & set(row["goals"]))), (True, True))
    s.planner.decider = Script(("read_policy", "none", "none", "need_policy"), ("read_policy", "none", "none", "need_policy"))
    row = say(s, "Bảo hành bao lâu em?", resp(intent="policy_question", asks=["warranty"], asks_question=True))
    ok("V05", "ask left at stop is recorded with reason", loop(row).get("unanswered"), {"warranty": "no_progress"})

# ================================================================== V06: đơn trùng đã tạo → hỏi đặt thêm
with Ctx():
    s = session("v06", "b2_jev", Script())
    say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    s.planner.decider = Script(*[adaptive_buyer] * 4)
    say(s, "Chốt Samsung AX40", resp(intent="place_order", requests=[req("place_order", "Chốt Samsung AX40", "P1")]))
    s.planner.decider = Script(lambda st, o: ("commit_request", first(o, "request_ref", "R"), "none", "commit_ready"),
                               lambda st, o: ("clarify", first(o, "request_ref", "R"), "none", "after_blocked"))
    row = say(s, "Ok chốt Samsung AX40 nhé", resp(intent="place_order", requests=[req("place_order", "chốt Samsung AX40", "P1")]))
    ok("V06", "same products as created order → ask additional, no second write",
       (created_skus(row), "ask_additional_order" in row["goals"]), ([], True))

# ================================================================== V08: can thiệp — quyền quyết định tiến trình đã chuyển
def broken(c, row):
    c.s.table_row_used = True             # dấu phụ (không qua goal_contract) để biết dòng bảng place_order đã chạy


for variant, want_order in (("b1", False), ("b2_jev", True)):
    with Ctx(), patch.dict(planner_table.HANDLERS, {"place_order": broken}):
        s = session(f"v08{variant}", variant, Script(*[adaptive_buyer] * 4) if variant == "b2_jev" else None)
        say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
        if variant == "b2_jev":
            s.planner.decider = Script(*[adaptive_buyer] * 4)
        row = say(s, "Ok chốt Samsung AX40 cho anh", resp(intent="place_order", requests=[req("place_order", "chốt Samsung AX40", "P1")]))
        ok("V08", f"{variant}: table place_order handler {'not ' if want_order else ''}the owner",
           (bool(created_skus(row)), bool(getattr(s, "table_row_used", False))), (want_order, not want_order))

# ================================================================== V10: cách ly
with Ctx():
    m2, m3 = Memory("iso-run-b2_jev:full:S1"), Memory("iso-run-b3_workflow:full:S1")
    m2.wipe(); m3.wipe()
    m2.upsert_customer("C-ISO", "A", "anh", "0900000001", [("phone", "0900000001")])
    m2.write_fact("C-ISO", "address", "canary-b2", "test", "s", "2026-10-15", confidence=1.0)
    ok("V10", "memory namespace of b3 does not see b2 canary", m3.current_facts("C-ISO", "2026-10-15"), {})
    src = open(os.path.join(ROOT, "run_eval.py"), encoding="utf-8").read()
    ok("V10", "run_id gets variant suffix on target runs", 'run_id = f"{run_id}-{a.planner_variant}"' in src, True)


# ================================================================== v2 (duyệt 12/11): thao tác đơn từng bước + lỗi holdout 1/2
SEED = "0965384535"                    # khách C032 CRM seed BTC: một đơn OD301177 (tạo 03/10)
ADDR = "12 Lê Lợi, Quận 1, TP HCM"


def mk_order(s, sku, phone="0911222333"):
    """Đơn có sẵn của khách (tạo thẳng bằng tool mock, ngoài lượt đo) — để kiểm thao tác đổi / trả trên đơn đó."""
    q = s.tools.call("pricing.get_quote", sku=sku, customer_phone=phone)
    r = s.tools.call("order.create", customer_phone=phone, sku=sku, qty=1, price_vnd=q["final_price_vnd"], payment="COD", address=ADDR)
    s.tools.take_log()
    return r["order_id"]


def last_commit(state):
    return next((x for x in reversed(state.get("steps_done") or []) if x.get("action") == "commit_request"), None)


def adaptive_op(state, opts):
    """Chính sách thử nghiệm cho thao tác đơn: tra đơn → kiểm hạn → (đổi: kho biến thể mới) → ghi; quá hạn → hỏi / báo.
    Quyết định theo BẰNG CHỨNG trong state (đơn đã tra, hạn đổi trả, phần thiếu do code báo)."""
    r = first(opts, "request_ref", "R")
    if state.get("orders_read_this_turn") is None:
        return ("read_order", r, "none", "need_order")
    lc = last_commit(state)
    wins = state.get("return_windows") or []
    if any(w.get("eligible") is False for w in wins):
        return ("clarify", r, "none", "after_blocked")
    if lc is None:
        return ("commit_request", r, "none", "commit_ready")
    if lc.get("status") != "blocked":
        return ("finish", "none", "none", "nothing_to_do")
    miss = (lc.get("missing") or [""])[0]
    if miss.startswith("check_window:"):
        tg = miss.split(":", 1)[1]
        return ("check_window", r, tg if tg in opts["target_ref"] else first(opts, "target_ref", "O"), "need_window")
    if miss.startswith("read_stock:"):
        return ("read_stock", r, miss.split(":", 1)[1], "need_stock")
    if [x for x in state.get("steps_done") if x.get("action") == "commit_request"][-1] is lc and \
            sum(1 for x in state.get("steps_done") if x.get("action") in ("check_window", "read_stock")) >= len(
                [x for x in state.get("steps_done") if x.get("action") == "commit_request"]):
        return ("commit_request", r, "none", "commit_ready")
    return ("clarify", r, "none", "after_blocked")


def adaptive_op2(state, opts):
    """Như adaptive_op nhưng ghi lại ngay sau mỗi lần đọc bổ sung (đọc → thử ghi → đọc phần thiếu → thử ghi…)."""
    steps = state.get("steps_done") or []
    if steps and steps[-1].get("action") in ("check_window", "read_stock") and steps[-1].get("status") == "ok":
        win = state.get("return_windows") or []
        if any(w.get("eligible") is False for w in win):
            return ("clarify", first(opts, "request_ref", "R"), "none", "after_blocked")
        return ("commit_request", first(opts, "request_ref", "R"), "none", "commit_ready")
    return adaptive_op(state, opts)


def ops(row, action=None):
    return [(t["args"]["order_id"], t["args"]["action"]) + ((t["args"].get("new_variant_sku"),) if action else ())
            for t in calls(row, "order.update")]


# V11: B2 đổi địa chỉ đơn phiên trước — ghi cần bằng chứng đơn đã tra trong lượt
with Ctx():
    s = session("v11", "b2_jev", Script(), phone=SEED)
    o1 = next(c["ref"] for c in s.reqs.context(s)["candidates"] if c.get("order_id") == "OD301177")
    s.planner.decider = Script(lambda st, o: ("commit_request", first(o, "request_ref", "R"), "none", "commit_ready"),
                               ("read_order", "none", "none", "need_order"),
                               lambda st, o: ("commit_request", first(o, "request_ref", "R"), "none", "commit_ready"))
    row = say(s, f"Em đổi địa chỉ giao đơn sang {ADDR} giúp chị",
              resp(intent="order_change", observations=[{"slot": "address", "span": ADDR, "stance": "stated"}],
                   requests=[req("change_order_address", "đổi địa chỉ giao đơn", o1)]))
    st = loop(row)["steps"]
    ok("V11", "B2 address change without order evidence → blocked read_order, no tool", (st[0]["status"], st[0].get("missing"), st[0]["tools"]),
       ("blocked", ["read_order"], []))
    ok("V11", "after read_order: exactly one update_address, commit itself calls only order.update",
       (ops(row), st[2]["tools"]), ([("OD301177", "update_address")], ["order.update"]))
    ok("V11", "address_updated told", "address_updated" in row["goals"], True)

# V12: B2 trả hàng — Jev đổi bước theo kết quả hạn đổi trả (còn hạn → ghi; quá hạn → hỏi/báo, không ghi)
for name, created, write in (("recent", "2026-10-12", True), ("old", "2026-08-01", False)):
    with Ctx():
        fake = [{"order_id": "OD777001", "sku": "SKU-JK-WND-S-BE", "price_vnd": 690000, "date": created, "status": "delivered"}]
        s = session(f"v12{name}", "b2_jev", Script())
        s.planner.decider = Script(*[adaptive_op2] * 6)
        with patch.object(agent.CallSession, "_customer_orders", lambda self: fake):
            row = say(s, "Chị muốn trả lại cái áo", resp(intent="order_change", requests=[req("return", "muốn trả lại cái áo")]))
        acts = [x["action"] for x in loop(row)["decisions"]]
        ok("V12", f"{name}: Jev reads order first and checks the window", (acts[0], "check_window" in acts), ("read_order", True))
        ok("V12", f"{name}: write only when window evidence says eligible", bool(calls(row, "order.update")), write)
        if bool(calls(row, "order.update")) != write:
            print("  DIAG decisions", json.dumps(loop(row).get("decisions"), ensure_ascii=False, default=str)[:1500])
            print("  DIAG steps", json.dumps(loop(row).get("steps"), ensure_ascii=False, default=str)[:2500])
            print("  DIAG stop", loop(row).get("stop"), "| last state keys", sorted((s.planner.decider.seen or [{}])[-1].keys()))
            print("  DIAG last state", json.dumps((s.planner.decider.seen or [{}])[-1], ensure_ascii=False, default=str)[:2500])
        if not write:
            ok("V12", f"{name}: after window evidence 'passed' Jev clarifies; window passed told",
               (acts[-1], "exchange_window_passed" in row["goals"]), ("clarify", True))

# V13: B2 đổi size — thiếu kho biến thể mới → blocked read_stock:V#, Jev đọc rồi mới ghi
with Ctx():
    s = session("v13", "b2_jev", Script())
    oid = mk_order(s, "SKU-JK-WND-S-BE")
    s.planner.decider = Script(*[adaptive_op2] * 6)
    row = say(s, "Đổi giúp chị sang size M nhé", resp(intent="order_change", observations=[{"slot": "size", "span": "size M", "stance": "chosen"}],
                                                       requests=[req("exchange", "Đổi giúp chị sang size M")]))
    st = loop(row)["steps"]
    blocked_stock = [x for x in st if x["action"] == "commit_request" and any(str(m).startswith("read_stock:V") for m in x.get("missing") or [])]
    ok("V13", "commit before new-variant stock evidence → blocked read_stock:V#, no tool", (len(blocked_stock), blocked_stock[0]["tools"] if blocked_stock else None),
       (1, []))
    ok("V13", "exchange written once with the size-M variant of the same colour", ops(row, True), [(oid, "exchange_size", "SKU-JK-WND-M-BE")])
    if not ops(row, True):
        print("  DIAG13 decisions", json.dumps(loop(row).get("decisions"), ensure_ascii=False, default=str)[:1500])
        print("  DIAG13 steps", json.dumps(loop(row).get("steps"), ensure_ascii=False, default=str)[:2500])
        print("  DIAG13 stop", loop(row).get("stop"))

# V15: can thiệp — vô hiệu executor đổi/trả/địa chỉ của B1 → B1 không làm được, B2/B3 vẫn làm (không có chuỗi B1 ẩn)
def dead_exec(self, *a, **k):
    self.b1_exec_used = True
    return ["contract_error"]


for variant, want in (("b1", False), ("b2_jev", True)):
    with Ctx(), patch.object(agent.CallSession, "_plan_order_change_target", dead_exec), \
            patch.object(agent.CallSession, "_plan_address_change_target", dead_exec):
        s = session(f"v15{variant}", variant, Script())
        oid = mk_order(s, "SKU-JK-WND-S-BE")
        if variant == "b2_jev":
            s.planner.decider = Script(*[adaptive_op2] * 6)
        row = say(s, "Đổi giúp chị sang size M nhé", resp(intent="order_change", observations=[{"slot": "size", "span": "size M", "stance": "chosen"}],
                                                           requests=[req("exchange", "Đổi giúp chị sang size M")]))
        ok("V15", f"{variant}: exchange {'done without' if want else 'depends on'} the B1 executor",
           (bool(calls(row, "order.update")), bool(getattr(s, "b1_exec_used", False))), (want, not want))

# V16 (holdout mục 1): hỏi tiền hoàn sau khi ĐỔI sang mẫu rẻ hơn → số tiền chênh của lần đổi, không phải giá cả đơn
for variant in ("b1", "b2_jev"):
    with Ctx():
        s = session(f"v16{variant}", variant, Script())
        oid = mk_order(s, "SKU-SS-AX40")
        if variant == "b2_jev":
            s.planner.decider = Script(*[adaptive_op2] * 6)
        row = say(s, "Chị đổi sang AirPure X nhé em", resp(intent="order_change", requests=[req("exchange", "Chị đổi sang AirPure X")]))
        upd = [t["result"] for t in calls(row, "order.update")]
        refund = (upd[0] or {}).get("refund_vnd") if upd else None
        ok("V16", f"{variant}: exchange to cheaper model written with a refund", bool(refund), True)
        if variant == "b2_jev":
            s.planner.decider = Script(lambda st, o: ("answer_ask", "none", first(o, "target_ref", "ask:"), "customer_asked"))
        row = say(s, "Vậy chị được hoàn lại bao nhiêu em?", resp(intent="order_status", asks=["refund_amount"], asks_question=True))
        money = f"{refund:,}".replace(",", ".") if refund else "?"
        ok("V16", f"{variant}: refund answer = exchange difference {money}, not full order price",
           (money in row["agent_text"], "6.490.000" in row["agent_text"]), (True, False))

# V17 (holdout mục 2): lựa chọn mới CHỨA sản phẩm đã có trong đơn vừa tạo → hỏi, không tạo đơn trùng
for variant in ("b1", "b2_jev"):
    with Ctx():
        s = session(f"v17{variant}", variant, Script())
        if variant == "b2_jev":
            s.planner.decider = Script(lambda st, o: ("answer_ask", "none", "ask:price", "customer_asked"))
        say(s, "AirPure Y giá sao em?", resp(intent="price_promo", asks=["price"], asks_question=True))
        if variant == "b2_jev":
            s.planner.decider = Script(*[adaptive_buyer] * 4)
        say(s, "Lấy AirPure X", resp(intent="place_order", requests=[req("place_order", "Lấy AirPure X", "P1")]))
        ok("V17", f"{variant}: first order (AirPure X) created", [o.get("skus") for o in s.orders_created], [["SKU-AP-X"]])
        if variant == "b2_jev":
            s.planner.decider = Script(lambda st, o: ("commit_request", first(o, "request_ref", "R"), "none", "commit_ready"),
                                       lambda st, o: ("clarify", first(o, "request_ref", "R"), "none", "after_blocked"))
        row = say(s, "Lên đơn cả hai luôn em", resp(intent="place_order", requests=[req("place_order", "Lên đơn cả hai", "ALL")]))
        ok("V17", f"{variant}: order containing an already-ordered product → no write, ask additional",
           (created_skus(row), "ask_additional_order" in row["goals"], "đã có" in row["agent_text"]), ([], True, True))

# V19 (duyệt 12/11): Jev nhận GIÁ TRỊ memory/known kèm nguồn/TTL, điều kiện kèm lời khách, facts liên quan — đã che PII;
# baseline (không đọc memory) không thấy giá trị phiên trước
for cfg, read in (("full", True), ("baseline_no_memory", False)):
    with Ctx():
        mem = Memory(f"variants:v19:{cfg}")
        mem.wipe()
        ToolBox.reset_world()
        mem.upsert_customer("N-0911222333", None, None, "0911222333", [("phone", "0911222333")])
        mem.write_fact("N-0911222333", "budget_vnd", 7000000, "s0:call_1", "s0:call_1", "2026-10-10", valid_from="2026-10-10")
        mem.write_fact("N-0911222333", "address", ADDR, "s0:call_1", "s0:call_1", "2026-10-10", valid_from="2026-10-10")
        mem.read_enabled = read
        d = Script(("finish", "none", "none", "nothing_to_do"), ("finish", "none", "none", "nothing_to_do"),
                   ("finish", "none", "none", "nothing_to_do"), ("finish", "none", "none", "nothing_to_do"))
        s = agent.CallSession(memory=mem, today="2026-10-15", call_name="call_2", session_id="v19:call_2", channel="hotline",
                              channel_identity=None, phone="0911222333", input_mode="text", router=Router("rules"),
                              generator=Generator("offline"), config=cfg, planner_variant="b2_jev", planner_decider=d)
        s.start()
        say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
        say(s, "Nếu dưới 7 triệu thì lấy Samsung AX40", resp(intent="place_order", requests=[
            req("place_order", "thì lấy Samsung AX40", "P1", {"type": "price_max", "span": "Nếu dưới 7 triệu"})]))
        st = d.seen[-1]
        blob = json.dumps(st, ensure_ascii=False)
        cust = st.get("customer") or {}
        if read:
            ok("V19", "full: memory value + source + session/TTL reach Jev",
               (cust.get("values", {}).get("budget_vnd"), cust.get("meta", {}).get("budget_vnd", {}).get("source"),
                bool(cust.get("meta", {}).get("budget_vnd", {}).get("expires_on"))), (7000000, "memory", True))
            ok("V19", "full: remembered address sent as token, never raw", (str(cust.get("values", {}).get("address", "")).startswith("[ĐỊA_CHỈ"),
                                                                             "Lê Lợi" in blob), (True, False))
        else:
            ok("V19", "baseline: no previous-session values reach Jev", ("budget_vnd" in cust.get("values", {}), "Lê Lợi" in blob), (False, False))
        rq = (st.get("open_requests") or [{}])[0]
        ok("V19", f"{cfg}: condition with customer words + agreed terms reach Jev",
           ((rq.get("condition") or {}).get("type"), "dưới 7 triệu" in str((rq.get("condition") or {}).get("customer_words")), "agreed_terms" in rq),
           ("price_max", True, True))
        ok("V19", f"{cfg}: phone never in Jev state", "0911222333" in blob, False)
        ok("V19", f"{cfg}: facts section present (prior quotes / stale warnings / created orders)",
           sorted((st.get("facts") or {}).keys()), ["agent_proposal_last_turn", "orders_created_this_call", "prior_quotes", "stale_warnings"])

# V20 (v4, duyệt 12/11 sau E1): MỘT Choice trên bước nguyên tử đã gắn đối tượng — không thể ghép hành động với đối tượng sai loại
from harness import planner_b2 as B2  # noqa: E402
import types  # noqa: E402

KIND_OF = {"read_quote": ("P",), "read_stock": ("P", "V"), "check_window": ("O",), "answer_ask": ("ask:",)}
with Ctx():
    s = session("v20", "b2_jev", Script())
    oid = mk_order(s, "SKU-JK-WND-S-BE")
    s.planner.decider = d20 = Script(*[adaptive_op2] * 6)
    say(s, "Đổi giúp chị sang size M nhé, giá áo này bao nhiêu em?", resp(intent="order_change", observations=SIZE_M if "SIZE_M" in dir() else
        [{"slot": "size", "span": "size M", "stance": "chosen"}], asks=["price"], asks_question=True,
        requests=[req("exchange", "Đổi giúp chị sang size M")]))
    bad = []
    for o in d20.opts_seen:
        for st in o["step"]:
            a_, rq_, tg_ = B2.parse_step(st)
            if a_ not in P.ACTIONS:
                bad.append(st)
            elif a_ in KIND_OF and not str(tg_).startswith(KIND_OF[a_]):
                bad.append(st)
            elif a_ == "commit_request" and not rq_:
                bad.append(st)
            if st not in o["desc"] or not o["desc"][st]:
                bad.append("nodesc:" + st)
    ok("V20", "every offered step is a well-formed (action, matching target) pair with a description", bad, [])
    ok("V20", "step round-trip: step_of(parse_step(x)) == x", [st for o in d20.opts_seen for st in o["step"]
                                                              if B2.step_of(*B2.parse_step(st)) != st], [])
with Ctx():
    s = session("v20b", "b2_jev", Script())
    say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    s.planner.decider = Script(lambda st, o: {"step": "read_quote:ask:price", "backend": "script"})
    row = say(s, "Chốt Samsung AX40", resp(intent="place_order", requests=[req("place_order", "Chốt Samsung AX40", "P1")]))
    ok("V20", "step outside the offered list is rejected, no write", (loop(row).get("stop"), created_skus(row)),
       ("invalid_tuple:step_not_allowed", []))
# sửa resolve đơn duy nhất: Jev chọn mã đơn của khách có ĐÚNG một đơn → unique; nhiều đơn → không unique (vẫn phải hỏi)
for orders, want in (([{"order_id": "OD1"}], True), ([{"order_id": "OD1"}, {"order_id": "OD2"}], False)):
    tt = types.SimpleNamespace(orders=orders)
    tt.order_of = lambda oid, tt=tt: next((x for x in tt.orders if x["order_id"] == oid), None)
    tt.order_ref = lambda ref, tt=tt: {"type": "order", "order_id": ref} if tt.order_of(ref) else None
    got = P._order_for(tt, {"target": None, "status": "open"}, "OD1")
    ok("V20", f"order ref chosen by planner, customer has {len(orders)} order(s) → unique={want}", (got[0]["order_id"], got[1]), ("OD1", want))

# V21 (duyệt 12/11, v5): mức sẵn sàng = DỮ KIỆN (4 loại + đủ để thử), không cấp quyền / không commit; hỏi lại đúng điều cần
# rõ (không câu chính sách chung); yêu cầu có điều kiện phải được phản hồi trước khi kết thúc, không thực hiện khi chưa thỏa
def rd_of(state, rid="R1"):
    return next(((x.get("readiness") or {}).get("state") for x in state.get("open_requests") or [] if x.get("id") == rid), None)


with Ctx():
    s = session("v21a", "b2_jev", Script())
    oid = mk_order(s, "SKU-JK-WND-S-BE")
    d = Script(("read_order", "R1", "none", "x"),
               lambda st, o: ("check_window", "R1", first(o, "target_ref", "O"), "x"),
               ("clarify", "R1", "none", "x"))
    s.planner.decider = d
    row = say(s, "Chị muốn đổi cái áo khoác", resp(intent="order_change", requests=[req("exchange", "muốn đổi cái áo khoác")]))
    ok("V21", "readiness before evidence = missing_evidence; after order + window read, no size = missing_info",
       (rd_of(d.seen[0]), rd_of(d.seen[-1])), ("missing_evidence", "missing_info"))
    ok("V21", "clarify asks exactly the new size (no generic policy answer), no write",
       ("ask_new_size" in row["goals"], "policy_answer" in row["goals"], calls(row, "order.update")), (True, False, []))

for name, created, want in (("recent", "2026-10-12", "ready_executor_rechecks"), ("old", "2026-08-01", "forbidden")):
    with Ctx():
        fake = [{"order_id": "OD777003", "sku": "SKU-JK-WND-S-BE", "price_vnd": 690000, "date": created, "status": "delivered"}]
        s = session(f"v21b{name}", "b2_jev", Script())
        # 13/11 (S8, thay đổi hành vi đã khai báo): clarify:R# chỉ có trong danh mục khi guard xác định có điều cần hỏi / báo
        d = Script(("read_order", "R1", "none", "x"), ("check_window", "R1", "OD777003", "x"),
                   lambda st, o: {"step": "clarify:R1"} if "clarify:R1" in o["step"] else ("finish", "none", "none", "x"),
                   ("finish", "none", "none", "x"))
        s.planner.decider = d
        with patch.object(agent.CallSession, "_customer_orders", lambda self: fake):
            row = say(s, "Chị muốn trả lại cái áo", resp(intent="order_change", requests=[req("return", "muốn trả lại cái áo")]))
        st = loop(row)["steps"]
        ok("V21", f"{name}: readiness after window evidence = {want}", rd_of(d.seen[2]), want)
        ok("V21", f"{name}: readiness alone never writes", calls(row, "order.update"), [])
        if name == "recent":
            ok("V21", "recent: ready → clarify:R1 not offered (removed with readiness reason), turn ends without generic policy",
               ("clarify:R1" in d.opts_seen[2]["step"], d.opts_seen[2]["removed"].get("clarify:R1"), "policy_answer" in row["goals"]),
               (False, "readiness:ready_executor_rechecks", False))
        else:
            ok("V21", "old: clarify states window passed (forbidden), not a generic policy answer",
               ("exchange_window_passed" in row["goals"], "policy_answer" in row["goals"]), (True, False))

with Ctx():
    s = session("v21c", "b2_jev", Script())
    say(s, "Xiaomi Smart 4 Pro còn không em?", resp(intent="product_inquiry", asks=["stock"], asks_question=True))
    d = Script(("read_quote", "R1", "P1", "x"), ("finish", "none", "none", "x"), ("clarify", "R1", "none", "x"))
    s.planner.decider = d
    row = say(s, "Khi nào có hàng thì lấy Xiaomi Smart 4 Pro", resp(intent="place_order",
              requests=[req("place_order", "thì lấy Xiaomi Smart 4 Pro", "P1", {"type": "stock", "span": "Khi nào có hàng"})]))
    st = loop(row)["steps"]
    fin = next(x for x in st if x["action"] == "finish")
    ok("V21", "conditional request not yet answered → finish blocked (respond_request)", (fin["status"], fin.get("missing")),
       ("blocked", ["respond_request:R1"]))
    ok("V21", "stock condition unmet: readiness condition_unmet, reply states condition, no write, request stays conditional",
       (rd_of(d.seen[1]), "condition_pending" in row["goals"], created_skus(row),
        [i["status"] for i in row["request_state"]["items"]][-1]), ("condition_unmet", True, [], "conditional"))

with Ctx():
    s = session("v21d", "b2_jev", Script())
    say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    d = Script(("read_quote", "R1", "P1", "x"), ("commit_request", "R1", "none", "x"), ("finish", "none", "none", "x"))
    s.planner.decider = d
    row = say(s, "Nếu dưới 3 triệu thì lấy Samsung AX40", resp(intent="place_order",
              requests=[req("place_order", "thì lấy Samsung AX40", "P1", {"type": "price_max", "span": "Nếu dưới 3 triệu"})]))
    ok("V21", "price_max condition: executor rechecks at write → condition_unmet told, no write, request stays conditional",
       (bool({"condition_unmet", "condition_pending"} & set(row["goals"])), created_skus(row),
        [i["status"] for i in row["request_state"]["items"]][-1]),
       (True, [], "conditional"))

# V22 (v6, duyệt 12/11): điều kiện tổng quát theo bằng chứng — giá dưới / bằng / vượt ngưỡng; dừng sớm chỉ phản hồi từ bằng
# chứng đã có (không tool, không ghi)
def vnd(x):
    return f"{x:,}".replace(",", ".") + "đ"


with Ctx():
    s0 = session("v22p", "b1")
    PRICE_AX40 = s0.tools.call("pricing.get_quote", sku=B_OK, customer_phone="0911222333")["final_price_vnd"]
COND_CASES = (("below", f"Nếu dưới {vnd(PRICE_AX40 + 1000000)} thì lấy Samsung AX40", True),
              ("equal", f"Nếu tối đa {vnd(PRICE_AX40)} thì lấy Samsung AX40", True),
              ("above", f"Nếu dưới {vnd(PRICE_AX40 - 1000000)} thì lấy Samsung AX40", False))
for name, text, write in COND_CASES:
    span = text.split(" thì")[0]
    rq = resp(intent="place_order", requests=[req("place_order", "thì lấy Samsung AX40", "P1", {"type": "price_max", "span": span})])
    with Ctx():
        s = session(f"v22b2{name}", "b2_jev", Script())
        say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
        plan_ = [("read_quote", "R1", "P1", "x")] + ([("commit_request", "R1", "none", "x")] if write else [("clarify", "R1", "none", "x")]) \
            + [("finish", "none", "none", "x")]
        s.planner.decider = d = Script(*plan_)
        row = say(s, text, rq)
        ok("V22", f"b2 {name}: readiness before price = missing_evidence, after = {'ready' if write else 'condition_unmet'}",
           (rd_of(d.seen[0]), rd_of(d.seen[1])), ("missing_evidence", "ready_executor_rechecks" if write else "condition_unmet"))
        ok("V22", f"b2 {name}: write only when condition met ({write})", bool(created_skus(row)), write)
        if not write:
            ok("V22", "b2 above: reply states current total over customer's limit; request stays conditional",
               ("condition_unmet" in row["goals"], [i["status"] for i in row["request_state"]["items"]][-1]), (True, "conditional"))

with Ctx():
    s = session("v22halt", "b2_jev", Script())
    say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    text = COND_CASES[2][1]
    s.planner.decider = Script(("read_quote", "R1", "P1", "x"), ("read_policy", "none", "none", "x"), ("read_policy", "none", "none", "x"))
    row = say(s, text, resp(intent="place_order", requests=[req("place_order", "thì lấy Samsung AX40", "P1",
                                                              {"type": "price_max", "span": text.split(" thì")[0]})]))
    lp = loop(row)
    ok("V22", "early stop (no_progress) still answers the condition from evidence, with zero tool calls and no write",
       (lp.get("stop"), "condition_unmet" in row["goals"], lp.get("halt_tool_calls"), created_skus(row)),
       ("no_progress", True, 0, []))

# V18 (holdout mục 7): định nghĩa field audit theo nghĩa có mặt trong prompt (wiring; hành vi Qwen kiểm ở scripts/audit_claims_probe.py)
ok("V18", "audit price_vnd excludes promo thresholds / exchange refunds; is_human only identity sentences",
   ("NGƯỠNG" in audit.CLAIM_FIELDS["price_vnd"], "DANH TÍNH" in audit.CLAIM_FIELDS["is_human"], "KHÔNG có is_human" in audit.CLAIM_EXAMPLES_V2,
    "phí" in audit.CLAIM_EXAMPLES_V3 and "KHÔNG dùng cho" in audit.CLAIM_FIELDS["price_quoted_vnd"]),
   (True, True, True, True))

print(f"\n{PASS[0]} OK, {len(FAIL)} lỗi")
if FAIL:
    print("LỖI:", FAIL)
sys.exit(1 if FAIL else 0)
