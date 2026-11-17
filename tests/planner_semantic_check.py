"""Kiểm tra hợp đồng planner mới bằng dữ liệu giả; chạy trong job Kaggle CPU."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import planner_policy, planner_selector, planner_state, planner_table


def main():
    actions = json.loads((Path(__file__).resolve().parents[1] / "harness/planner_actions.json").read_text(encoding="utf-8"))["actions"]
    assert actions["give_delivery_info"].get("implies_if") is None
    assert actions["place_order"]["requires"] == ["product"]
    assert planner_policy.exchange_window({"date": "2026-09-28", "received_on": "2026-10-10"}, "2026-10-20")["days"] == 14
    assert planner_policy.exchange_window({"date": "2026-10-02", "received_on": "2026-10-10"}, "2026-10-20")["eligible"] is False
    assert planner_policy.exchange_window({"date": "2026-09-28"}, "2026-10-20")["eligible"] is None

    calls = []
    tools = SimpleNamespace(call=lambda name, **kw: calls.append((name, kw)) or {"status": "updated"})
    order = {"order_id": "OD1", "address": "địa chỉ cũ"}
    s = SimpleNamespace(brief={"orders": [order]}, orders_created=[], cart=[], focus="SKU1", discussed=[],
                        history=[], semantic_plan=None, customer={"customer_id": "C1"}, proxy_caller=False,
                        known={"order_id": "OD1"}, tools=tools, _customer_orders=lambda: [order])
    state = planner_state.snapshot(s)
    assert state.has_order and state.stage == "after_sale"
    c = SimpleNamespace(s=s, text="Giao về địa chỉ mới", slots={"address": "địa chỉ mới"}, asking=False,
                        mentioned=[], alt=None, goals=[], facts={})
    with patch.object(planner_selector, "select", return_value=["change_order_address"]):
        assert planner_table._semantic_plan(c)
    assert calls == [("order.update", {"order_id": "OD1", "action": "update_address", "reason": "địa chỉ mới: địa chỉ mới"})]
    assert c.goals == ["address_updated"] and s.known["address"] == "địa chỉ mới"

    calls.clear(); s.proxy_caller = True; c.goals = []; c.facts = {}
    with patch.object(planner_selector, "select", return_value=["change_order_address"]):
        assert not planner_table._semantic_plan(c)
    assert not calls
    print("planner_semantic_check: OK")


if __name__ == "__main__":
    main()
