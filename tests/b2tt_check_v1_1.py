"""Nghiệm thu CPU candidate B2-TT (17/11) — v1.1, khóa ở runs/extra_1115/INTEG_ACCEPT.json. v1 (tests/b2tt_check.py) và verdict
TRƯỢT của nó giữ nguyên. v1.1 chỉ khác C11b: v1 vá eval.mock_tools nhưng ToolBox gọi harness.tools.mt (module nạp riêng) nên lỗi
giả lập không xảy ra; v1.1 tiêm vào đúng module, kiểm tiền đề lỗi đã xảy ra, và dùng mutant bỏ qua lỗi tool để chứng minh test bắt được.
Kaggle CPU, KHÔNG API.

DeepSeek = phản hồi đóng gói theo hợp đồng (có trường consult); Jev hai tầng = bộ quyết định CÓ KỊCH BẢN theo CHÍNH SÁCH chung
(ưu tiên survey → answer; không viết riêng cho từng ca). Tool = mock BTC thật (không sửa dữ liệu), memory SQLite tạm. Đáp án (mẫu /
giá / còn hàng) tính ĐỘC LẬP bằng eval/mock_tools trong test — không chép từ output candidate.
KHÔNG chứng minh Jev / DeepSeek thật chọn đúng (phần đó là canary API).

Nhóm: C1 chuỗi thực tế · C2 có/không KM · C3 hết hàng / ngừng bán · C4 đang bàn một mẫu rồi hỏi rẻ nhất · C5 thiếu / nhiều nhóm →
hỏi rõ · C6 ngân sách / diện tích · C7 có/không theo ngữ cảnh · C8 không hỏi lại · C9 giá giả định không ghi · C10 không đổi giỏ /
đơn / yêu cầu · C11 hết ngân sách tool / tool lỗi · C12 trace · C13 cờ tắt = hành vi bản chính (tái hiện lỗi gốc).
Dùng: python tests/b2tt_check_v1_1.py   (chỉ chạy trên cây đã áp overlay runs/freeze/20261117-integ-cand)"""
import os
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
from harness import agent, planner_b2tt as TT, understanding as U  # noqa: E402
from harness.memory import Memory  # noqa: E402
from harness.tools import ToolBox  # noqa: E402
from core.llm.generator import Generator  # noqa: E402
from core.llm.router import Router  # noqa: E402

ok, resp, Script, pick = F.ok, F.resp, F.Script, F.pick
TT_ON = {"b2_two_tier": True, "b2tt_max_tool_calls": 18, "b2tt_max_decisions": 4}
AIR, FAN, MB = "gia-dung/may-loc-khong-khi", "gia-dung/quat", "me-be"


def policy_inner(state, opts):
    """Chính sách chung của bộ quyết định giả tầng trong: survey nếu chưa đọc → answer → hỏi rõ nhóm → kết thúc."""
    for pre in ("survey:", "answer", "ask_customer_category", "finish_unresolved"):
        hit = next((k for k in opts if k.startswith(pre)), None)
        if hit:
            return {"pick": hit, "backend": "script", "ms": 0}


def ask_need_first(state, opts):
    return {"pick": "ask_customer_need" if "ask_customer_need" in opts else policy_inner(state, opts)["pick"], "backend": "script", "ms": 0}


def oracle(cat, day, kind="cheapest", query=None, max_price=None, min_area=None):
    """Đáp án độc lập: mẫu còn bán (không ngừng bán), còn hàng ngày `day`, giá bán sau KM theo pricing_get_quote."""
    items = mt.catalog_search(category=cat, query=query, max_price_vnd=max_price, min_room_area_m2=min_area)["items"]
    rows = []
    for it in items:
        if mt.inventory_check(it["sku"], on=day).get("in_stock"):
            rows.append((mt.pricing_get_quote(it["sku"], on=day)["final_price_vnd"], it["sku"], it["name"]))
    oos = [it["name"] for it in items if not mt.inventory_check(it["sku"], on=day).get("in_stock")]
    if not rows:
        return None, None, None, oos
    r = min(rows) if kind == "cheapest" else max(rows)
    return r[1], r[0], r[2], oos


def vnd(v):
    return f"{v:,}đ".replace(",", ".")


def session(name, day="2026-10-15", decider=None, phone="0911000111"):
    mem = Memory(f"b2tt:{name}")
    mem.wipe()
    ToolBox.reset_world()
    s = agent.CallSession(memory=mem, today=day, call_name="call_1", session_id=f"{name}:call_1", channel="hotline",
                          channel_identity=None, phone=phone, input_mode="text", router=Router("rules"),
                          generator=Generator("offline"), config="full", planner_variant="b2_jev",
                          planner_decider=decider or Script())
    s.start()
    return s


def consult(sort="cheapest", scope="category", cat=None, budget=None, area=None, asks=("price",)):
    return {"sort": sort, "scope": scope, "category_span": cat, "budget_span": budget, "area_span": area}


def q(text_cat, sort="cheapest", scope="category", budget=None, area=None, asks=("price",), **kw):
    return resp(intent="price_promo", asks=list(asks), asks_question=True,
                consult=consult(sort, scope, text_cat, budget, area), **kw)


def tt(row):
    return (F.loop(row) or {}).get("two_tier") or {}


def names(row, n):
    return [t for t in row["tool_calls"] if t["name"] == n]


WRITES = ("order.create", "order.update", "schedule.callback", "handoff.transfer")

with F.Ctx(TT_ON):
    TT.DECIDERS.update(inner=policy_inner, outer=None)

    # ---------------- C1 chuỗi thực tế + C8 + C12
    s = session("c1")
    sku, price, name, _ = oracle(AIR, "2026-10-15")
    r1 = F.say(s, "Máy lọc không khí rẻ nhất là bao nhiêu?", q("Máy lọc không khí"))
    ok("C1", "không hỏi trẻ nhỏ / ngân sách", "ask_need" in r1["goals"], False)
    ok("C1", "có block product_pick", "product_pick" in r1["goals"], True)
    ok("C1", "nêu đúng mẫu rẻ nhất (oracle)", name in r1["agent_text"], True)
    ok("C1", "nêu đúng giá bán (oracle)", vnd(price) in r1["agent_text"], True)
    ok("C1", "nói 'thấp nhất' khi đã so đủ", "thấp nhất" in r1["agent_text"], True)
    ok("C1", "catalog.search đúng nhóm", [t["args"].get("category") for t in names(r1, "catalog.search")], [AIR])
    n_cat = len(mt.catalog_search(category=AIR)["items"])
    ok("C1", "kiểm kho đủ mọi mẫu của nhóm", len({t["args"]["sku"] for t in names(r1, "inventory.check")}) >= n_cat, True)
    ok("C1", "không tool ghi", [t["name"] for t in r1["tool_calls"] if t["name"] in WRITES], [])
    x = tt(r1)
    ok("C12", "trace: outcome answered_sourced", x.get("outcome"), "answered_sourced")
    ok("C12", "trace: tầng ngoài direct (một tác vụ)", (x.get("outer") or {}).get("mode"), "direct_single_task")
    ok("C12", "trace: tầng trong có options + pick", all(d.get("options") and d.get("pick") for d in x.get("inner") or []), True)
    ok("C12", "trace: đếm jev / tool / ms", all(k in x for k in ("jev_calls", "tool_calls", "ms", "criteria", "steps")), True)
    ok("C12", "trace: tool ≤ trần", x.get("tool_calls", 99) <= 18, True)
    ok("C3", "mẫu ngừng bán không được khảo sát", "SKU-AP-X-2024" in {t["args"].get("sku") for t in names(r1, "inventory.check")}, False)
    r1b = F.say(s, "Thế máy lọc không khí rẻ nhất ở đây là bao nhiêu?", q("máy lọc không khí"))
    ok("C8", "hỏi lại lần 2: vẫn trả lời, không hỏi trẻ nhỏ", ("ask_need" not in r1b["goals"]) and name in r1b["agent_text"], True)

    # ---------------- C7 có / không theo ngữ cảnh (chuỗi nhờ tư vấn → hỏi nhu cầu → "Không em")
    TT.DECIDERS["inner"] = ask_need_first
    s = session("c7")
    a1 = F.say(s, "Tư vấn giúp anh máy lọc không khí với.", q("máy lọc không khí", sort="none", asks=("recommend",)))
    ok("C7", "tác vụ recommend chưa biết nhu cầu: hỏi một nhu cầu", "ask_need" in a1["goals"], True)
    ok("C7", "câu hỏi nhu cầu là trẻ nhỏ", "bé nhỏ" in a1["agent_text"], True)
    TT.DECIDERS["inner"] = ask_need_first                    # cùng chính sách: ask_need chỉ còn khi chưa biết nhu cầu nào
    a2 = F.say(s, "Không em.", resp(intent="provide_info", observations=[
        {"slot": "has_children", "span": "Không", "label": "khong", "stance": "stated", "subject": "self"}]))
    ok("C7", "'Không em' sau câu hỏi trẻ nhỏ → has_children=False", s.known.get("has_children"), False)
    ok("C7", "không hỏi lại trẻ nhỏ", "bé nhỏ" in a2["agent_text"] or "ask_need" in a2["goals"], False)
    ok("C7", "tiếp tục tác vụ dang dở (reuse)", (tt(a2).get("outer") or {}).get("mode"), "reuse_pending")
    ok("C7", "tác vụ hoàn thành có nguồn", tt(a2).get("outcome"), "answered_sourced")
    a3 = F.say(s, "Thế máy lọc không khí rẻ nhất ở đây là bao nhiêu?", q("máy lọc không khí"))
    ok("C7", "sau đó hỏi rẻ nhất: trả lời, không hỏi trẻ nhỏ", name in a3["agent_text"] and "bé nhỏ" not in a3["agent_text"], True)
    TT.DECIDERS["inner"] = policy_inner
    # có em → True; "không" không có căn cứ → không ghi
    meta = {"dropped": []}
    from core.pii import Redactor
    o_yes = U._accept_observation({"slot": "has_children", "span": "Có", "label": "co", "stance": "stated"}, "Có em", Redactor(),
                                  "2026-10-15", meta, asked="has_children")
    ok("C7", "'Có em' → True", (o_yes or {}).get("value"), True)
    o_no_basis = U._accept_observation({"slot": "has_children", "span": "Không", "label": "khong", "stance": "stated"}, "Không em",
                                       Redactor(), "2026-10-15", meta, asked="confirm_order")
    ok("C7", "'Không' trả lời đề nghị khác: KHÔNG thành has_children", o_no_basis, None)
    o_neg = U._accept_observation({"slot": "has_children", "span": "nhà anh không có trẻ nhỏ", "label": "khong", "stance": "negated"},
                                  "nhà anh không có trẻ nhỏ", Redactor(), "2026-10-15", meta, asked=None)
    ok("C7", "phủ định có từ chỉ trẻ nhỏ → False", (o_neg or {}).get("value"), False)

    # ---------------- C2 có / không KM (giá bán sau KM theo oracle)
    for day in ("2026-10-15", "2026-11-11"):
        s = session(f"c2{day}", day=day)
        sku, price, name, _ = oracle(FAN, day)
        r = F.say(s, "Quạt nào rẻ nhất em?", q("Quạt"))
        ok("C2", f"{day}: mẫu + giá bán sau KM khớp oracle", name in r["agent_text"] and vnd(price) in r["agent_text"], True)

    # ---------------- C3 rẻ nhất hết hàng; đắt nhất hết hàng
    s = session("c3a", day="2026-10-25")
    sku, price, name, oos = oracle(MB, "2026-10-25", query="xe đẩy")
    r = F.say(s, "Xe đẩy loại rẻ nhất giá bao nhiêu?", q("Xe đẩy"))
    ok("C3", "xe đẩy: chọn mẫu còn hàng rẻ nhất (oracle)", name in r["agent_text"] and vnd(price) in r["agent_text"], True)
    ok("C3", "xe đẩy: nêu mẫu rẻ hơn đang hết hàng", all(n in r["agent_text"] for n in oos) and "hết hàng" in r["agent_text"], True)
    s = session("c3b", day="2026-10-18")
    sku, price, name, _ = oracle(AIR, "2026-10-18", kind="most_expensive")
    r = F.say(s, "Máy lọc không khí xịn nhất đắt nhất là con nào?", q("Máy lọc không khí", sort="most_expensive"))
    ok("C3", "đắt nhất khi mẫu đắt nhất hết hàng (oracle)", name in r["agent_text"] and "AirPure Pro" not in r["agent_text"], True)

    # ---------------- C4 đang bàn một mẫu rồi hỏi rẻ nhất trong nhóm
    s = session("c4", decider=Script(pick("answer_ask:"), "finish"))
    F.say(s, "Máy lọc không khí AirPure Y giá bao nhiêu?", resp(intent="price_promo", asks=["price"], asks_question=True,
                                                                consult=consult("none", "mentioned", None)))
    sku, price, name, _ = oracle(AIR, "2026-10-15")
    r = F.say(s, "Trong nhóm này cái nào rẻ nhất em?", q(None, scope="discussed"))
    ok("C4", "trả lời rẻ nhất trong nhóm đang bàn, không phải mẫu Y", name in r["agent_text"] and vnd(price) in r["agent_text"], True)

    # ---------------- C5 thiếu nhóm / nhiều nhóm → hỏi rõ, không tool
    s = session("c5a")
    r = F.say(s, "Cái nào rẻ nhất em?", q(None, scope="discussed"))
    ok("C5", "chưa rõ nhóm → hỏi rõ", "ask_product" in r["goals"], True)
    ok("C5", "chưa rõ nhóm → không gọi tool commerce", [t["name"] for t in r["tool_calls"] if t["name"].startswith(("catalog", "pricing", "inventory"))], [])
    s = session("c5b")
    r = F.say(s, "Máy lọc không khí hay máy lọc nước cái nào rẻ nhất?", q("Máy lọc không khí hay máy lọc nước"))
    ok("C5", "hai nhóm trong một span → hỏi rõ", "ask_product" in r["goals"], True)

    # ---------------- C6 ngân sách + diện tích
    s = session("c6")
    sku, price, name, _ = oracle(AIR, "2026-10-15", max_price=3000000, min_area=40)
    r = F.say(s, "Máy lọc không khí dưới 3 triệu cho phòng 40 mét loại rẻ nhất?", q("Máy lọc không khí", budget="dưới 3 triệu",
                                                                                      area="phòng 40 mét"))
    cs = names(r, "catalog.search")
    ok("C6", "catalog.search có ngân sách + diện tích", bool(cs) and cs[0]["args"].get("max_price_vnd") == 3000000
       and cs[0]["args"].get("min_room_area_m2") == 40, True)
    ok("C6", "đúng mẫu theo ràng buộc (oracle)", name in r["agent_text"] and vnd(price) in r["agent_text"], True)

    # ---------------- C9 / C10 giá giả định không ghi; không đổi giỏ / đơn / yêu cầu
    s = session("c9")
    before = (list(s.cart), len(s.reqs.items), len(s.orders_created))
    r = F.say(s, "Nếu anh lấy máy lọc không khí rẻ nhất thì hết bao nhiêu?", q("máy lọc không khí"))
    ok("C9", "giá giả định: không tool ghi", [t["name"] for t in r["tool_calls"] if t["name"] in WRITES], [])
    ok("C10", "không đổi giỏ / yêu cầu / đơn", (list(s.cart), len(s.reqs.items), len(s.orders_created)), before)
    # lượt có yêu cầu đặt → delegate (luồng B2 + cổng giữ nguyên)
    s = session("c10", decider=Script(pick("read_quote:", "commit_request:"), pick("commit_request:"), "finish"))
    F.say(s, "Máy lọc không khí AirPure Y giá bao nhiêu?", resp(intent="price_promo", asks=["price"], asks_question=True))
    r = F.say(s, "Lấy cho anh cái đó, rẻ nhất thì càng tốt", resp(intent="place_order", requests=[F.req("place_order", "Lấy cho anh cái đó", "P1")],
                                                              consult=consult("cheapest", "discussed", None)))
    ok("C10", "lượt có yêu cầu đặt → delegate về luồng B2", (tt(r).get("outer") or {}).get("mode"), "rule_delegate")

    # ---------------- C11 hết ngân sách tool; tool lỗi
    with patch.object(F.settings, "b2tt_max_tool_calls", 6):
        s = session("c11a")
        r = F.say(s, "Máy lọc không khí rẻ nhất là bao nhiêu?", q("Máy lọc không khí"))
        ok("C11", "hết trần tool: không khẳng định 'thấp nhất là' (chỉ nói giới hạn)", "chưa khẳng định" in r["agent_text"]
           or "chưa kiểm" in r["agent_text"], True)
        ok("C11", "hết trần tool: số tool ≤ trần", tt(r).get("tool_calls", 99) <= 6, True)
    from harness import tools as HT
    real = HT.mt.TOOLS["pricing.get_quote"]

    def broken(sku, **kw):
        if sku == "SKU-AP-MINI":
            raise RuntimeError("simulated tool failure")
        return real(sku, **kw)

    def c11b(name):
        s = session(name)
        r = F.say(s, "Máy lọc không khí rẻ nhất là bao nhiêu?", q("Máy lọc không khí"))
        fired = any(t["name"] == "pricing.get_quote" and t["args"].get("sku") == "SKU-AP-MINI"
                    and isinstance(t["result"], dict) and bool(t["result"].get("error")) for t in r["tool_calls"])
        claims = "mẫu có giá thấp nhất là" in r["agent_text"] and "chưa" not in r["agent_text"]
        return fired, claims, tt(r).get("outcome")

    real_rank = TT._rank

    def rank_ignores_errors(*a, **kw):
        out = real_rank(*a, **kw)
        out.update(complete=True, errors=[])
        return out
    with patch.dict(HT.mt.TOOLS, {"pricing.get_quote": broken}):
        fired, claims, outcome = c11b("c11b")
        ok("C11", "tool lỗi (tiền đề v1.1): lỗi giả lập thật sự xảy ra trên SKU-AP-MINI", fired, True)
        ok("C11", "tool lỗi: không gọi là 'thấp nhất' với dữ liệu thiếu", claims, False)
        ok("C11", "tool lỗi: outcome không phải answered_sourced", outcome == "answered_sourced", False)
        with patch.object(TT, "_rank", rank_ignores_errors):
            m_fired, m_claims, m_outcome = c11b("c11b-mut")
        ok("C11", "mutant bỏ qua lỗi tool (tiền đề): lỗi vẫn xảy ra", m_fired, True)
        ok("C11", "mutant bỏ qua lỗi tool: test PHÁT HIỆN câu 'thấp nhất'", m_claims, True)
        ok("C11", "mutant bỏ qua lỗi tool: test PHÁT HIỆN outcome answered_sourced", m_outcome == "answered_sourced", True)

TT.DECIDERS.update(inner=None, outer=None)

# ---------------- C13 cờ TẮT = hành vi bản chính (tái hiện lỗi gốc, làm mốc)
with F.Ctx({"b2_two_tier": False}):
    s = session("c13", decider=Script(pick("answer_ask:"), "finish"))
    r = F.say(s, "Máy lọc không khí rẻ nhất là bao nhiêu?", resp(intent="price_promo", asks=["price"], asks_question=True))
    ok("C13", "cờ tắt: không có trace two_tier", "two_tier" in (F.loop(r) or {}), False)
    ok("C13", "cờ tắt: tái hiện lỗi gốc (hỏi trẻ nhỏ)", "ask_need" in r["goals"], True)
    from harness.llm_extract import _slot_value
    ok("C13", "cờ tắt: has_children khong → None (như bản chính)", _slot_value("has_children", "không", "khong", "không", "2026-10-15"), None)

print(f"\n{F.PASS[0]} OK, {len(F.FAIL)} FAIL")
for g, n in F.FAIL:
    print("FAIL", g, n)
sys.exit(1 if F.FAIL else 0)
