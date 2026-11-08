"""Ordered multi-action execution with code permissions and grounded arguments."""
from harness import planner_state, planner_decision

ORDER = ['request_handoff', 'cancel_order', 'give_delivery_info', 'add_to_cart', 'product_advice', 'policy_question', 'ask_price', 'change_order_address', 'exchange_order', 'return_order', 'order_status', 'place_order', 'cart_total', 'schedule_callback', 'defer_decision', 'greeting_closing', 'unclear']


def run(c):
    from harness import planner_table as T
    s, state = c.s, planner_state.snapshot(c.s)
    previous = next((h['text'] for h in reversed(s.history) if h.get('role') == 'agent'), None)
    trace = {'selected_actions': [], 'executed_actions': [], 'blocked': [], 'backend': 'unavailable', 'simulated': T.settings.jev_simulated, 'stage': state.stage}
    s.semantic_plan = trace
    if s.candidates:
        T.h_ask_identity(c, None)
        return
    try:
        decision = planner_decision.decide(c.text, previous, state)
        trace.update(decision)
        actions = list(decision['actions'])
        trace['selected_actions'] = list(actions)
        c.fl = decision['flags']
        c.route.update(flags=c.fl, backend=decision['backend'], simulated=decision['simulated'])
    except Exception as exc:
        trace['fallback'] = type(exc).__name__
        c.goals.append('ask_repeat')
        return
    if getattr(s, 'proxy_caller', False) and (c.y('wants_data_deleted') or any(a in actions for a in ('order_status', 'change_order_address', 'exchange_order', 'return_order')) or T.PREDS['proxy_info_ask'](c)):
        T.h_refuse_other_customer(c, None)
        return
    import re
    other_buyer = re.search(r'\b(so dien thoai|dia chi|don hang)\b.*\b(nguoi|khach)\s+((vua|da)\s+mua|khac|cu)\b', c.f)
    if c.y('asks_other_customer') or T.PREDS['other_pii'](c) or other_buyer:
        T.h_refuse_other_customer(c, None)
        return
    if c.y('asks_internal_cost') or ('refuse_internal' in (s.table_prev_goals or []) and T.PREDS['pressure_words'](c)):
        c.goals.append('refuse_internal')
        return
    if c.y('asks_if_bot'):
        c.goals.append('is_bot')
    if c.y('wants_data_deleted'):
        from harness.identity_permissions import may_forget
        if not may_forget(s):
            T.h_refuse_other_customer(c, None)
        else:
            T.h_forget_customer(c, None)
        return
    if c.y('medical_question'):
        T.h_handoff_scope(c, None)
        return
    if c.y('mentions_competitor'):
        c.goals.append('no_competitor_comment')
    if s.turn_no == 1 and s.brief and s.brief.get('is_returning') and c.prev_focus and not any(a in actions for a in ('place_order', 'change_order_address', 'return_order', 'exchange_order')):
        T.h_opening_returning(c, None)
    if 'request_handoff' in actions:
        actions = ['request_handoff']
    elif 'cancel_order' in actions:
        actions = ['cancel_order']
    if 'exchange_order' in actions and 'return_order' in actions:
        trace['blocked'].append({'actions': ['exchange_order', 'return_order'], 'reason': 'conflicting_order_changes'})
        actions = [a for a in actions if a not in ('exchange_order', 'return_order')]
        c.goals.append('ask_repeat')
    if 'place_order' in actions:
        actions = [a for a in actions if a not in ('add_to_cart', 'defer_decision', 'give_delivery_info')]
    if len(actions) > 1:
        actions = [a for a in actions if a not in ('greeting_closing', 'unclear')]
    if 'policy_question' in actions and c.asking:
        actions = [a for a in actions if a not in ('exchange_order', 'return_order')]
    for action in ORDER:
        if action not in actions:
            continue
        requires = planner_decision.ACTIONS[action].get('requires', [])
        missing = []
        if 'order' in requires and (not state.has_order or not (s.customer or {}).get('customer_id') or s.proxy_caller):
            missing.append('order')
        if 'product' in requires and not (c.mentioned or s.cart or s.focus):
            missing.append('product')
        if 'cart' in requires and not s.cart:
            missing.append('cart')
        if 'address' in requires and not c.slots.get('address'):
            missing.append('address')
        if missing and 'order' in missing and action in ('return_order', 'exchange_order') and c.asking:
            trace['blocked'].append({'action': action, 'missing': missing, 'fallback': 'policy_question'})
            T.h_policy_answer(c, None)
            trace['executed_actions'].append('policy_question')
            continue
        if missing:
            trace['blocked'].append({'action': action, 'missing': missing})
            c.goals.append('order_not_found' if 'order' in missing else 'ask_address' if 'address' in missing else 'ask_product')
            continue
        try:
            execute(action, c, T)
            trace['executed_actions'].append(action)
        except Exception as exc:
            trace.setdefault('errors', []).append({'action': action, 'error': type(exc).__name__})
            c.goals.append('contract_error')
            break
    if getattr(c, 'gift_q', False) and s.focus:
        if not c.facts.get('quote'):
            c.facts['quote'] = s._quote(s.focus)
        T.h_gift_status(c, None)
    if not c.goals:
        c.goals.append('ask_repeat')


def execute(action, c, T):
    s = c.s
    if action == 'request_handoff':
        T.h_handoff_scope(c, None)
    elif action == 'cancel_order':
        T.h_cancel_request(c, None)
    elif action == 'give_delivery_info':
        from harness.llm_extract import _is_question
        if not any(c.slots.get(k) for k in ('address', 'payment')) and (_is_question(c.text) or 'chi hoi' in c.f):
            T.h_policy_answer(c, None)
            return
        if s.buy_intent:
            c.goals.extend(s._plan_order(c.text, c.facts))
        else:
            c.goals.append('confirm_order' if s.focus else 'ask_product')
    elif action == 'add_to_cart':
        for sku in c.mentioned or ([c.alt] if c.alt else [s.focus]):
            if sku:
                s._cart_add(sku)
        c.facts['cart'] = s._cart_quote(c.text)
        c.goals.append('cart_total')
    elif action == 'product_advice':
        c.it = 'product_inquiry'
        T.h_recommend(c, None)
        if 'recommend' not in c.goals and s.focus:
            T.h_quote(c, None)
    elif action == 'policy_question':
        T.h_policy_answer(c, None)
    elif action == 'ask_price':
        if s.focus:
            T.h_quote(c, None)
        else:
            c.goals.append('ask_product')
    elif action == 'change_order_address':
        orders = s._customer_orders()
        wanted = s.known.get('order_id')
        order = next((o for o in reversed(orders) if o['order_id'] == wanted), orders[-1] if orders else None)
        if not order:
            c.goals.append('order_not_found')
            return
        address = c.slots['address']
        if order.get('address') != address:
            result = s.tools.call('order.update', order_id=order['order_id'], action='update_address', reason=f'địa chỉ mới: {address}')
            if result.get('error'):
                c.facts['order_error'] = result['error']
                c.goals.append('order_failed')
                return
        s.known['address'] = address
        c.facts['address_update'] = {'orders': [order['order_id']], 'address': address}
        c.goals.append('address_updated')
    elif action in ('exchange_order', 'return_order'):
        goals = s._plan_order_change(c.text, c.facts, action_override='return' if action == 'return_order' else 'exchange')
        c.goals.extend(['exchange_window_passed'] if goals == ['WINDOW_PASSED'] else goals)
    elif action == 'order_status':
        T.h_order_status(c, None)
    elif action == 'place_order':
        s.buy_intent = True
        for sku in c.mentioned or ([s.focus] if s.focus else []):
            s._cart_add(sku)
        c.goals.extend(s._plan_order(c.text, c.facts))
    elif action == 'cart_total':
        T.h_cart_total(c, None)
    elif action == 'schedule_callback':
        when = c.slots.get('callback_requested')
        if not when:
            parsed = T._A().extractor.parse_relative_datetime(c.text, s.today)
            when = f'{parsed[0]}T{parsed[1] or "09:00"}' if parsed else None
        if when:
            c.goals.extend(s._plan_callback(when, c.facts))
        else:
            c.goals.append('ask_repeat')
    elif action == 'defer_decision':
        s.buy_intent = False
        T.h_defer_ack(c, None)
    elif action == 'greeting_closing':
        c.goals.append('greet' if s.turn_no == 1 and not c.goals else 'closing')
    elif action == 'unclear':
        T.h_ask_repeat(c, None)
