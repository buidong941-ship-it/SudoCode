"""Kaggle only: adversarial product selection and condition checks."""
from pathlib import Path
import sys
from types import SimpleNamespace as NS
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.config import settings
from harness.jev_write_gate import _product_evidence
from harness.request_state import RequestState
from harness import plan_primitives as P
from harness.understanding import _accept_requests
from core.pii import Redactor

st = RequestState()
st.refmap = {"P1": {"type": "product", "skus": ("SKU-AP-X",)},
             "P2": {"type": "product", "skus": ("SKU-AP-Y",)}}
s = NS(turn_no=2, turn_text="lấy mẫu rẻ hơn", call_tool_log=[
    {"name": "pricing.get_quote", "args": {"sku": "SKU-AP-X", "on": "2026-10-15"},
     "result": {"final_price_vnd": 100, "floor_price": 1}, "_turn": 1},
    {"name": "pricing.get_quote", "args": {"sku": "SKU-AP-Y"}, "result": {"error": "timeout"}, "_turn": 2}],
    discussed=["SKU-AP-X", "SKU-AP-Y"], turn_mentioned=[], focus="SKU-AP-X", cart=[],
    orders_created=[], brief={}, u_turn={}, table_prev_goals=[], b2tt_proposal=None, proxy_caller=False,
    _target_variant=lambda sku, text: sku, _order_overlap=lambda skus: (None, None))
s.reqs = st
ev = _product_evidence(s, st)
assert len(ev["products"]) == 1 and not ev["products"][0]["quote"]["checked_this_turn"]
assert "floor_price" not in str(ev)
assert st.context(s)["product_evidence"]["products"] == ev["products"]
sel = st.selection_criteria(s, {"consult": {"sort": "cheapest", "scope": "discussed"}})
assert sel["skus"] == s.discussed
r = {"id": "R1", "kind": "place_order", "status": "open", "turn": 2,
     "target": {"type": "product", "skus": ("SKU-AP-X",)}, "selection": sel}
t = NS(s=s, c=NS(text="giao về địa chỉ này", slots={}), active_requests=lambda: [r],
       stock={"SKU-AP-X": {"in_stock": True}, "SKU-AP-Y": {"in_stock": True}},
       quotes={"SKU-AP-X": {"final_price_vnd": 200}, "SKU-AP-Y": {"final_price_vnd": 100}})
with patch.object(settings, "jev_write_gate", True):
    obs, ctx = P._place_order_check(t, r, None)
    assert obs is None and ctx["resolved"] == ["SKU-AP-Y"], (obs, ctx)
    s.discussed.reverse()
    obs, ctx = P._place_order_check(t, r, None)
    assert ctx["resolved"] == ["SKU-AP-Y"]
    t.quotes["SKU-AP-X"]["final_price_vnd"] = 50
    assert P._place_order_check(t, r, None)[1]["resolved"] == ["SKU-AP-X"]
    t.quotes["SKU-AP-X"]["final_price_vnd"] = 100
    assert "cheaper_price_tie" in P._place_order_check(t, r, None)[0]["missing"]
    del t.quotes["SKU-AP-X"]
    assert P._place_order_check(t, r, None)[0]["missing"][0].startswith("read_quote:")
    st.items = [r]; st.turn = 2
    r["selection_evidence"] = {"turn": 2, "prices": {"SKU-AP-X": 200, "SKU-AP-Y": 100}}
    assert st.authorize("place_order", r["target"], req_id="R1")[1] == "selection_target_mismatch"

for phrase in ("có khóa trẻ em", "có khóa an toàn cho bé"):
    text = f"{phrase} thì lấy"
    raw = {"requests": [{"kind": "place_order", "evidence": "thì lấy", "target_ref": "P1",
                        "condition": {"type": "attribute", "span": phrase,
                                      "attribute": "child_safe_lock", "expected": True}}]}
    out = _accept_requests(raw, text, Redactor(), {"P1"}, {"dropped": []})
    assert out[0]["condition"]["attribute"] == "child_safe_lock"
    cond_req = {"kind": "place_order", "condition": out[0]["condition"]}
    task = NS(s=NS(turn_no=2))
    assert P.evaluate_condition(task, cond_req, {"resolved": ["SKU-AP-X"]})["state"] == "missing_evidence"
    cond_req["condition_evidence"] = {"source": "catalog.search", "turn": 2,
        "attribute": "child_safe_lock", "values": {"SKU-AP-X": False}}
    assert P.evaluate_condition(task, cond_req, {"resolved": ["SKU-AP-X"]})["state"] == "unmet"
    cond_req["condition_evidence"]["values"]["SKU-AP-X"] = True
    assert P.evaluate_condition(task, cond_req, {"resolved": ["SKU-AP-X"]})["state"] == "met"
print("v8_check: OK")

held_state = RequestState()
held_state.turn = 1
held_state.held_candidate = {"kind": "place_order", "target": {"type": "product", "skus": ("SKU-AP-X",)},
                              "condition": {"type": "attribute", "attribute": "child_safe_lock", "expected": True},
                              "selection": sel, "turn": 1, "evidence": "lấy mẫu rẻ hơn"}
held_state.retain_held({"request_id": "R1"})
held = held_state.held_candidate
assert held is held_state.items[0] and held["id"] == "R1" and not held_state.has_active("place_order")
assert held_state.authorize("place_order", held["target"], req_id="R1")[1] == "request_closed"
held_state.held_candidate = {**held, "turn": 2}
held_state.retain_held({"request_id": "R1"})
assert len(held_state.items) == 1 and held_state.held_candidate is held
assert held["selection"] == sel and held["condition"]["attribute"] == "child_safe_lock"
held_state._withdraw("place_order", 2, "explicit_withdrawal")
assert held["status"] == "withdrawn"
print("held lifecycle: OK")

from harness.identity_permissions import link_new_spoken_phone, may_bind_spoken_phone
from unittest.mock import Mock
mem = NS(lookup=Mock(return_value=[]), upsert_customer=Mock())
profile = NS(proxy_caller=False, candidates=[], customer={"customer_id": "N-FB1", "phone": None},
             mem=mem, tools=NS(call=Mock(return_value={"found": False})), phone=None, channel_identity="FB1")
result = link_new_spoken_phone(profile, "0912345678")
assert result["linked"] and profile.customer["phone"] == "0912345678"
mem.upsert_customer.assert_called_once_with("N-FB1", identities_=[("phone", "0912345678")])
assert may_bind_spoken_phone(profile, "0912345678")
for crm in ({"found": True}, {"error": "timeout"}, {}, {"found": False, "ambiguous": True}):
    profile.customer["phone"] = None
    profile.tools.call.return_value = crm
    assert not link_new_spoken_phone(profile, "0912345678")["linked"]
profile.tools.call.return_value = {"found": False}
mem.lookup.return_value = ["N-OTHER"]
assert link_new_spoken_phone(profile, "0912345678")["reason"] == "memory_phone_conflict"
mem.lookup.side_effect = RuntimeError("lookup failed")
assert not link_new_spoken_phone(profile, "0912345678")["linked"]
profile.proxy_caller = True
profile.tools.call.reset_mock()
assert not link_new_spoken_phone(profile, "0912345678")["linked"]
profile.tools.call.assert_not_called()
print("demo identity policy: OK")

obligation = NS(asks=lambda: ["price"], answered=["price"], deferred=[],
                ask_outcome={"price": {"outcome": "answered"}},
                consult_scope={"skus": ["SKU-AP-X", "SKU-AP-Y"]},
                quotes={"SKU-AP-X": {"final_price_vnd": 100}, "SKU-AP-Y": {"final_price_vnd": 200}},
                c=NS(facts={"quote": {"sku": "SKU-AP-X"}, "alternative": {"sku": "SKU-AP-Y"}}, goals=[]))
assert P.Turn.pending_asks(obligation) == ["price"]
obligation.c.goals = ["quote"]
assert P.Turn.pending_asks(obligation) == ["price"]
obligation.c.goals.append("alternative_quote")
assert P.Turn.pending_asks(obligation) == []
print("per-product answer obligation: OK")

withdraw_state = RequestState()
withdraw_state.items = [{"id": "R1", "kind": "place_order", "status": "open"},
                        {"id": "R2", "kind": "place_order", "status": "held"}]
with patch.object(settings, "jev_write_gate", True):
    assert not withdraw_state._withdraw("place_order", 3, "unspecified")
    assert all(r["status"] != "withdrawn" for r in withdraw_state.items)
    assert withdraw_state._withdraw("place_order", 3, "jev_reject_or_withdraw", req_id="R2")
    assert withdraw_state.items[0]["status"] == "open"
    assert withdraw_state.items[1]["status"] == "withdrawn" and withdraw_state.hold is None
print("scoped withdrawal: OK")
