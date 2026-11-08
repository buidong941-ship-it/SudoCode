"""Partial commerce writes, optional facts and question aggregation; Kaggle only."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config import settings
from core.llm.generator import render_offline, payload
from harness import agent, coverage
from harness.goal_contract import enforce, validate

assert not validate(['quote'], {'quote': {'name': 'Máy', 'final_price_vnd': 0, 'in_stock': False, 'promo_names': []}})
assert validate(['order_created'], {'order': {'order_id': 'OD1', 'total_vnd': 0, 'estimated_delivery': 123}})
assert not validate(['order_created'], {'order': {'order_id': 'OD1', 'total_vnd': 0, 'estimated_delivery': None}})
plan = enforce({'goals': ['ask_address', 'ask_payment'], 'facts': {}}, [])
assert plan['goals'] == ['ask_payment'] and plan['question_slot'] == 'payment'
assert render_offline(plan).count('?') == 1
assert '"contract"' not in payload(plan)
with patch.object(settings, 'goal_contract', True):
    assert coverage.questions('Dạ được ạ.', 'payment', {})

s = agent.CallSession.__new__(agent.CallSession)
s.customer = {'phone': '0912222999'}; s.phone = '0912222999'
s.cart = ['SKU-AP-X', 'SKU-AF-4L']; s.focus = 'SKU-AP-X'; s.orders_created = []; s.history = []
s.known = {'address': '15 Đường A', 'payment': 'COD'}; s.expired = {}; s.old_addr_asked = False
s._resolve_variant = lambda sku, text: sku
s._quote = lambda sku, *args, **kwargs: {'sku': sku, 'final_price_vnd': 1000000, 'promo_codes': [], 'in_stock': True}
seen = []
def call(name, **args):
    assert name == 'order.create'
    sku = args['sku']; seen.append(sku)
    if sku == 'SKU-AF-4L' and seen.count(sku) == 1:
        return {'error': 'temporary_fixture_failure'}
    return {'order_id': 'OD1' if sku == 'SKU-AP-X' else 'OD2', 'total_vnd': 1000000}
s.tools = SimpleNamespace(call=call)
with patch.object(settings, 'planner_selector', 'jev'):
    facts = {}; goals = s._plan_order('lên đơn', facts)
    assert goals == ['order_partial'] and len(s.orders_created) == 1
    assert facts['partial_orders'][0]['order_id'] == 'OD1'
    proof = [{'name': 'order.create', 'result': {'order_id': 'OD1'}}]
    assert enforce({'goals': goals, 'facts': facts}, proof)['goals'] == ['order_partial']
    assert enforce({'goals': goals, 'facts': facts}, [])['goals'] == ['contract_error']
    assert s._plan_order('thử lại', {}) == ['order_created']
assert seen.count('SKU-AP-X') == 1 and seen.count('SKU-AF-4L') == 2
assert len(s.orders_created) == 2
before = len(seen)
s.orders_created = []; s.cart = ['SKU-AP-X']; s.known.pop('address', None)
s._quote = lambda sku, *a, **kw: {'sku': sku, 'final_price_vnd': 1000000, 'promo_codes': [], 'in_stock': False}
with patch.object(settings, 'planner_selector', 'jev'):
    assert s._plan_order('lên đơn', {}) == ['out_of_stock']
assert len(seen) == before
s.known['address'] = '15 Đường A'; s.known.pop('payment', None)
s._quote = lambda sku, *a, **kw: {'sku': sku, 'name': 'Fixture', 'final_price_vnd': 1000000, 'promo_codes': [], 'in_stock': True}
with patch.object(settings, 'planner_selector', 'jev'):
    assert s._plan_order('lên đơn', {}) == ['ask_payment']
assert len(seen) == before
s.known['payment'] = 'COD'
s._quote = lambda sku, *a, **kw: {'sku': sku, 'name': 'Fixture', 'final_price_vnd': 11000000, 'promo_codes': [], 'in_stock': True}
with patch.object(settings, 'planner_selector', 'jev'):
    assert s._plan_order('lên đơn', {}) == ['cod_limit']
assert len(seen) == before
print('partial-write retry, optional facts and one-question checks OK')
