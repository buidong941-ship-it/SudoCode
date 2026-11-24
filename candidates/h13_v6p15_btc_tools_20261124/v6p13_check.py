"""Kaggle only. v6p13 vòng 2A: S1 evidence rỗng (NULLABLE_EVIDENCE), S4 tổng tiền thử (TRIAL_TOTAL), S2 tên khách gọi → mẫu /
hỏi chọn mẫu, hỏi chọn đơn khi lượt bị giữ (PICK_BY_NAME), S5 claim theo goal (CLAIM_SPAN), G7 xác nhận trước khi chuyển người
(DONE_NO_HANDOFF). Mỗi cờ: bật → hành vi mới, tắt → như v6p12."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core import pii
from core.config import settings
from core.llm import generator as GEN
from harness import agent
from harness import plan_primitives as P
from harness import planner_b2tt as TT
from harness import understanding as U
from harness.tools import mt

passed, failed = 0, []


def check(name, value):
    global passed
    if value:
        passed += 1
        print("PASS", name, flush=True)
    else:
        failed.append(name)
        print("FAIL", name, flush=True)


# ================================================================== S1: evidence null khi act = none
NULL_RESP = {"response_to_agent": {"act": "none", "evidence": None}}
for on in (True, False):
    with patch.object(settings, "nullable_evidence", on):
        dropped = []
        U._conform(dict(NULL_RESP), U._schema(), "$", dropped)
        hold = U._type_hold(dropped)
        check(f"S1 flag {'on' if on else 'off'}: null evidence {'kept' if on else 'holds turn'}",
              (hold == []) if on else (hold == ["$.response_to_agent.evidence"]))
with patch.object(settings, "nullable_evidence", True):
    dropped = []
    U._conform({"response_to_agent": {"act": "accept", "evidence": 5}}, U._schema(), "$", dropped)
    check("S1: wrong type (number) still dropped", U._type_hold(dropped) == ["$.response_to_agent.evidence"])

# ================================================================== S2: tên khách gọi → SKU
red = pii.Redactor()
refs = U._catalog_refs()
by_sku = {v: k for k, v in U._CATALOG_REFS_SKU.items()}
check("S2 catalog refs: discontinued excluded", "SKU-SN-RUN1-OLD" not in by_sku and "SKU-AF-6L" in by_sku)
T082 = "alo em ơi cái nồi chiên phi líp bên em bán bao nhiêu tiền vậy"
meta = {"dropped": []}
pick = lambda m, text=T082: U._accept_pick({"product_mention": m}, text, red, meta)
check("S2 pick: verbatim span + one ref → one sku",
      pick({"span": "nồi chiên phi líp", "kind": "model", "refs": [by_sku["SKU-AF-6L"]]}) ==
      {"kind": "model", "span": "nồi chiên phi líp", "skus": ["SKU-AF-6L"]})
check("S2 pick: span not in text → none", pick({"span": "nồi chiên Philips", "kind": "model", "refs": [by_sku["SKU-AF-6L"]]}) is None)
check("S2 pick: kind none → none", pick({"span": "nồi chiên phi líp", "kind": "none", "refs": [by_sku["SKU-AF-6L"]]}) is None)
check("S2 pick: unknown ref → none", pick({"span": "nồi chiên phi líp", "kind": "model", "refs": ["C999"]}) is None)
T083 = "à em anh hỏi giá giày chạy bộ ran lai chút"
two = pick({"span": "giày chạy bộ ran lai", "kind": "line", "refs": [by_sku["SKU-SN-RUN1"], by_sku["SKU-SN-RUN2"]]}, T083)
check("S2 pick: line → two skus", two and two["skus"] == ["SKU-SN-RUN1", "SKU-SN-RUN2"])
for on in (True, False):
    with patch.object(settings, "pick_by_name", on):
        check(f"S2 schema/prompt flag {'on' if on else 'off'}", ("product_mention" in U._schema()["properties"]) == on)


def b2tt_ctx(name_pick):
    s = SimpleNamespace(u_turn={"name_pick": name_pick} if name_pick else {}, focus=None, reqs=SimpleNamespace(refmap={}))
    crit = {"category": None, "category_span": None, "budget_max_vnd": None, "room_area_m2": None, "asks": ["price"],
            "goal": "none", "named": [], "anchor": [], "sort": "none", "scope": "category"}
    return SimpleNamespace(s=s), crit


for on in (True, False):
    with patch.object(settings, "pick_by_name", on):
        c, crit = b2tt_ctx({"skus": ["SKU-SN-RUN1", "SKU-SN-RUN2"]})
        out = TT.tasks(c, None, crit)
        check(f"S2 b2tt flag {'on' if on else 'off'}: many name matches → {'main flow only' if on else 'consult as before'}",
              (list(out) == ["delegate_main_flow"]) if on else ("consult_clarify_category" in out))


# hỏi chọn đơn khi lượt bị giữ
def order_t(hold="ambiguous_turn", kinds=("exchange",), n=2):
    orders = [{"order_id": f"OD60000{i}", "status": "created"} for i in range(1, n + 1)]
    s = SimpleNamespace(reqs=SimpleNamespace(hold=hold), u_turn={"request_items": [{"kind": k} for k in kinds]},
                        _order_products=lambda o: "Giày trekking HikePro", _customer_orders=lambda: orders)
    return SimpleNamespace(s=s, orders=None, c=SimpleNamespace(facts={}, goals=[]))


with patch.object(settings, "pick_by_name", True):
    t = order_t()
    w = P.ambiguous_order_hold(t)
    check("S2 order hold: two orders → ask which, action exchange",
          w and len(w["which_orders"]) == 2 and w["which_orders_action"] == "đổi hàng")
    check("S2 order hold: goal ask_which_order", P.ambiguous_hold_goals(order_t()) == ["ask_which_order"])
    check("S2 order hold: one order → none", P.ambiguous_order_hold(order_t(n=1)) is None)
    check("S2 order hold: not held → none", P.ambiguous_order_hold(order_t(hold=None)) is None)
    check("S2 order hold: no order op → none", P.ambiguous_order_hold(order_t(kinds=("place_order",))) is None)
with patch.object(settings, "pick_by_name", False):
    check("S2 order hold flag off: ask_repeat as before", P.ambiguous_hold_goals(order_t()) == ["ask_repeat"])
txt = GEN.render_offline({"goals": ["ask_which_order"], "facts": {"which_orders": [
    {"order_id": "OD600001", "product": "Giày trekking HikePro size 41"}, {"order_id": "OD600002", "product": "Giày sneaker Urban Classic"}],
    "which_orders_action": "đổi hàng"}})
print("  reply:", txt, flush=True)
check("S2 reply: lists both orders from tool data", "OD600001" in txt and "OD600002" in txt and "đơn nào" in txt)
txt = GEN.render_offline({"goals": ["ask_which_product"], "facts": {"which_products": ["Giày chạy bộ RunLite 1", "Giày chạy bộ RunLite 2 Pro"]}})
print("  reply:", txt, flush=True)
check("S2 reply: asks which product", "mẫu nào" in txt and "RunLite 2 Pro" in txt)


# ================================================================== S4: tổng tiền thử
def trial_t(mentioned=("SKU-SN-CAS-40-XAM",), qty_obs=(3, 2), cart=()):
    s = SimpleNamespace(cart=list(cart), focus=None, turn_no=3, qty_obs=qty_obs, _resolve_variant=lambda sku, text: sku,
                        _quote_order=lambda lines: mt.pricing_quote_order(lines, on="2026-11-02"),
                        _cart_facts=lambda oq: agent.CallSession._cart_facts(SimpleNamespace(known={}), oq))
    c = SimpleNamespace(mentioned=list(mentioned), text="giả sử anh lấy 2 đôi thì tổng hết nhiêu tiền", facts={}, goals=[])
    return SimpleNamespace(c=c, s=s)


t = trial_t()
P._trial_total(t)
cart = t.c.facts.get("cart") or {}
check("S4: two units quoted by tool, total from quote_order", t.c.goals == ["cart_total"] and cart.get("trial") and len(cart["items"]) == 2
      and cart["total_vnd"] == mt.pricing_quote_order([{"sku": "SKU-SN-CAS-40-XAM", "qty": 2}], on="2026-11-02")["total_vnd"])
print("  trial total:", cart.get("total_vnd"), flush=True)
t = trial_t(qty_obs=(2, 2))
P._trial_total(t)
check("S4: qty from an earlier turn → no trial total", t.c.goals == [])
t = trial_t(mentioned=("SKU-SN-CAS",))
P._trial_total(t)
check("S4: variant not chosen → no trial total", t.c.goals == [])
t = trial_t(mentioned=("SKU-SN-CAS-40-XAM", "SKU-AF-6L"))
P._trial_total(t)
check("S4: two different products → no trial total", t.c.goals == [])
txt = GEN.render_offline({"goals": ["cart_total"], "facts": {"cart": cart}})
print("  reply:", txt, flush=True)
check("S4 reply: says total", "tổng" in txt)


# ================================================================== S5: claim theo goal
POLICY = ["Mọi đơn COD trên 2.000.000đ phải được nhân viên gọi xác nhận trước khi giao (tránh hoàn hàng).\nKhác"]
claims = [{"field": "is_human", "value": True, "text": "Em đã lên đơn OD600001 cho anh/chị, tổng 2.796.500đ ạ."},
          {"field": "list_price_vnd", "value": 2000000,
           "text": "Theo chính sách bên em: Mọi đơn COD trên 2.000.000đ phải được nhân viên gọi xác nhận trước khi giao (tránh hoàn hàng)."},
          {"field": "price_vnd", "value": 2796500, "text": "Mẫu UF Sunhouse còn 2.796.500đ ạ."}]
row = {}
kept = agent._grounded_claims(claims, ["quote", "policy_answer"], POLICY, row)
check("S5: is_human without identity goal dropped; policy money not product price; real price kept",
      [c["field"] for c in kept] == ["price_vnd"] and len(row["claim_grounding"]) == 2)
kept = agent._grounded_claims([{"field": "is_human", "value": False, "text": "Dạ em là trợ lý AI của shop ạ."}], ["is_bot"], [], {})
check("S5: identity goal keeps is_human claim", len(kept) == 1)


# ================================================================== G7: đơn đã hủy → xác nhận trước, chuyển người khi khách đòi lại
def cancel_t():
    s = SimpleNamespace(ext_cancelled=["OD600001"], turn_no=2, handoff_task=None, open_questions=[], _record_view=lambda x: x,
                        _handoff=lambda text, kind: {"ticket_id": "T1"})
    c = SimpleNamespace(goals=[], facts={}, text="Em chuyển người hỗ trợ giúp chị xác nhận yêu cầu hủy đơn nhé.")
    return SimpleNamespace(c=c, s=s, extra_requests=lambda: ["X_CANCEL"])


with patch.object(P, "_single_cancellable_order", lambda t: None):
    with patch.object(settings, "done_no_handoff", True):
        t = cancel_t()
        r1 = P._commit_request(t, "X_CANCEL", None)
        check("G7 first ask: confirm, no handoff", r1["goals"] == ["cancel_done_confirm"] and "handoff" not in t.c.facts)
        t.c.goals, t.c.facts, t.s.turn_no = [], {}, 3
        r2 = P._commit_request(t, "X_CANCEL", None)
        check("G7 asks again: handoff", r2["goals"] == ["cancel_done_handoff"] and t.c.facts.get("handoff"))
    with patch.object(settings, "done_no_handoff", False):
        t = cancel_t()
        check("G7 flag off: handoff as before", P._commit_request(t, "X_CANCEL", None)["goals"] == ["cancel_done_handoff"])
txt = GEN.render_offline({"goals": ["cancel_done_confirm"], "facts": {"cancel_done_confirm": {"order_id": "OD600001"}}})
print("  reply:", txt, flush=True)
check("G7 reply: cancelled, offers staff only if needed", "OD600001" in txt and "hủy thành công" in txt and "đã chuyển" not in txt)

# ================================================================== câu condition_fact_unmet (đã sửa câu chữ)
for cond in ({"type": "promo_active", "product": "Nồi chiên Philips 6.2L", "price_vnd": 3990000},
             {"type": "fee_free", "why": "policy_version", "order_id": "OD600001"},
             {"type": "fee_free", "why": "not_first_exchange", "order_id": "OD600001"},
             {"type": "fee_free", "why": "price_diff", "order_id": "OD600001", "extra_vnd": 100000},
             {"type": "fee_free", "why": "fee_unverified", "order_id": "OD600001"}):
    txt = GEN.render_offline({"goals": ["condition_fact_unmet"], "facts": {"condition": cond}})
    print("  reply:", txt, flush=True)
    check(f"reply {cond.get('why') or cond['type']}: not done, next step offered", "chưa" in txt and "báo em" in txt or "chuyển nhân viên" in txt)

print("v6p13 checks:", passed, "PASS", flush=True)
assert not failed, failed
