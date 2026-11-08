"""Kaggle-only behavioral contracts. No BTC sample scenarios or live APIs."""
import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config import settings
from harness.goal_contract import validate, enforce, REGISTRY
from harness import planner_executor as E, planner_table as T, planner_state


def main():
    root = Path(__file__).resolve().parents[1]
    for base in ('core', 'harness', 'scripts', 'mcp_servers'):
        for path in (root / base).rglob('*.py'):
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    assert not validate(['order_created'], {'order': {'order_id': 'OD1', 'total_vnd': 0}})
    assert validate(['order_created'], {'order': {'order_id': '', 'total_vnd': -1}})
    assert validate(['unknown'], {})
    assert validate(['order_created', 'out_of_stock'], {'order': {'order_id': 'OD1', 'total_vnd': 1}})
    plan = {'goals': ['order_created'], 'facts': {'order': {'order_id': 'OD1', 'total_vnd': 1}}}
    assert enforce(dict(plan), [])['goals'] == ['contract_error']
    assert enforce(dict(plan), [{'name': 'order.create', 'result': {'order_id': 'OD1'}}])['goals'] == ['order_created']
    assert 'ask_address' in REGISTRY and REGISTRY['ask_payment']['question_slot'] == 'payment'
    class Session:
        def __init__(self):
            self.brief = {}; self.focus = 'SKU-AF-4L'; self.cart = []; self.discussed = []; self.orders_created = []
            self.customer = {'customer_id': 'N-0911111000', 'phone': '0911111000'}
            self.phone = '0911111000'; self.history = []; self.candidates = []; self.proxy_caller = False
            self.table_prev_goals = []; self.privacy_refused = False; self.turn_no = 2; self.buy_intent = False
            self.known = {}; self.outcome = None
            self._why = lambda *a: None
    def ctx(s):
        c = T.Ctx(s, 'Thêm món rồi tính tổng giúp chị.', {}, {'intent': 'meta', 'flags': {}})
        c.f = 'them mon roi tinh tong giup chi'; c.asking = False; c.mentioned = ['SKU-AF-4L']; c.alt = None; c.prev_focus = s.focus
        return c
    decision = {'actions': ['cart_total', 'add_to_cart', 'add_to_cart'], 'flags': {}, 'backend': 'mock', 'simulated': True}
    s = Session(); c = ctx(s); seen = []
    def perform(action, context, table):
        seen.append(action)
        if action == 'add_to_cart': context.s.cart.append('SKU-AF-4L')
        context.goals.append('cart_total')
    with patch.object(E.planner_decision, 'decide', return_value=decision), patch.object(E, 'execute', side_effect=perform):
        E.run(c)
    assert seen == ['add_to_cart', 'cart_total'], seen
    s = Session(); s.proxy_caller = True; c = ctx(s)
    decision['actions'] = ['order_status']; decision['flags'] = {}
    with patch.object(E.planner_decision, 'decide', return_value=decision), patch.object(E, 'execute') as ex:
        E.run(c); ex.assert_not_called()
    assert c.goals == ['refuse_other_customer']
    s = Session(); c = ctx(s); decision['actions'] = ['change_order_address']
    with patch.object(E.planner_decision, 'decide', return_value=decision), patch.object(E, 'execute') as ex:
        E.run(c); ex.assert_not_called()
    assert s.semantic_plan['blocked']
    s = Session(); c = ctx(s)
    with patch.object(E.planner_decision, 'decide', side_effect=RuntimeError('model unavailable')), patch.object(E, 'execute') as ex:
        E.run(c); ex.assert_not_called()
    assert c.goals == ['ask_repeat']
    from harness.jev_adapter import block_real_api, COUNTS
    with patch.object(settings, 'jev_simulated', True):
        block_real_api()
        import typesafe_sdk
        try:
            typesafe_sdk.TypeSafeClient(api_key='fixture')
            raise AssertionError('real API was not blocked')
        except RuntimeError:
            pass
    assert COUNTS['real_requests'] == 0 and COUNTS['blocked_real_requests'] == 1
    print('jev1108 behavioral checks OK; no sample or baseline evaluations; no real API calls')


if __name__ == '__main__':
    main()
