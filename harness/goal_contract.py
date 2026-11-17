"""Shared registry, validation and runtime provenance for generator plans."""
import json
import math
from pathlib import Path
REGISTRY = json.loads(Path(__file__).with_name('generator_goals.json').read_text(encoding='utf-8'))


def get(facts, path):
    value = facts
    for key in path.split('.'):
        value = value.get(key) if isinstance(value, dict) else None
    return value


def valid_value(value, kind):
    if kind == 'money':
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
    if kind == 'string':
        return isinstance(value, str) and bool(value.strip())
    if kind == 'list':
        return isinstance(value, list) and bool(value)
    if kind == 'array':
        return isinstance(value, list)
    if kind == 'object':
        return isinstance(value, dict) and bool(value)
    if kind == 'bool':
        return isinstance(value, bool)
    if kind == 'integer':
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0
    if kind == 'orders':
        return isinstance(value, list) and bool(value) and all(isinstance(o, dict) and valid_value(o.get('order_id'), 'string') and valid_value(o.get('total_vnd'), 'money') for o in value)
    if kind == 'true':
        return value is True
    if kind == 'date':
        from datetime import date
        try:
            return isinstance(value, str) and date.fromisoformat(value) is not None
        except ValueError:
            return False
    return value is not None


def validate(goals, facts):
    errors = []
    if not isinstance(facts, dict):
        return ['facts_not_object']
    for goal in goals:
        if goal not in REGISTRY:
            errors.append(f'unknown_goal:{goal}')
            continue
        spec = REGISTRY[goal]
        for path, kind in spec['required_facts'].items():
            if not valid_value(get(facts, path), kind):
                errors.append(f'{goal}:invalid:{path}')
        optional = spec.get('optional_facts') or {}
        if isinstance(optional, dict):
            for path, kind in optional.items():
                value = get(facts, path)
                if value is not None and value != '' and not valid_value(value, kind):
                    errors.append(f'{goal}:invalid_optional:{path}')
    # Mâu thuẫn = hai KẾT QUẢ trái nhau của cùng lần tạo đơn. Xin địa chỉ/thanh toán/SĐT SAU khi tạo đơn là bước tiếp theo
    # hợp lệ (agent._plan_order trả ["order_created", "ask_address"]), không phải mâu thuẫn — Full 09/11: 28 lượt tạo đơn
    # thành công trên đường rules bị thay bằng contract_error vì quy tắc cũ (bất biến, không phụ thuộc CONTRACT_V2 từ 10/11).
    if 'order_created' in goals and any(g in goals for g in ('order_failed', 'out_of_stock', 'ask_variant', 'order_unresolved')):
        errors.append('conflicting_order_result')
    return errors


# Goal báo KẾT QUẢ thao tác ghi → tool phải có lời gọi thành công đã xác nhận (harness/tool_outcome.py) ngay trong lượt.
_RESULT_TOOL = {'callback_scheduled': 'schedule.callback', 'handoff': 'handoff.transfer', 'cancel_handoff': 'handoff.transfer'}


def _order_fact(ok_creates):
    rs = [c['result'] for c in ok_creates]
    eta = rs[0].get('estimated_delivery')
    out = {'order_id': ', '.join(r['order_id'] for r in rs), 'total_vnd': sum(r['total_vnd'] for r in rs)}
    if eta:
        out['estimated_delivery'] = eta
        out['estimated_delivery_ddmm'] = f'{eta[8:10]}/{eta[5:7]}'
    return out


def _evidence_errors(goals, facts, tool_log):
    from harness import tool_outcome as T
    errors = []
    ok_creates = T.confirmed(tool_log, 'order.create')
    totals = {c['result']['order_id']: c['result']['total_vnd'] for c in ok_creates}
    if 'order_created' in goals:
        ids = [i for i in str(get(facts, 'order.order_id') or '').split(', ') if i]
        if not ids or not set(ids) <= set(totals):
            errors.append('order_created_without_successful_tool')
        elif get(facts, 'order.total_vnd') != sum(totals[i] for i in ids):
            errors.append('order_created_total_mismatch')     # số sẽ phát ngôn phải đúng response của chính các đơn đó
    if 'order_partial' in goals:
        parts = (facts or {}).get('partial_orders') or []
        if not parts or any(p.get('order_id') not in totals or p.get('total_vnd') != totals[p['order_id']] for p in parts):
            errors.append('partial_order_without_successful_tool')
    for goal, tool in _RESULT_TOOL.items():
        if goal not in goals or T.confirmed(tool_log, tool):
            continue
        called = any((c.get('name') or c.get('tool')) == tool for c in tool_log)
        # nhắc lại ticket chuyển máy đã được xác nhận ở lượt trước (agent._handoff, không gọi lại tool) thì hợp lệ
        restated = tool == 'handoff.transfer' and not called and get(facts, 'handoff.already_queued') is True \
            and valid_value(get(facts, 'handoff.ticket_id'), 'string')
        if not restated:
            errors.append(f'{goal}_without_successful_tool')
    if 'callback_scheduled' in goals:
        done = {c['result']['callback_at'] for c in T.confirmed(tool_log, 'schedule.callback')}
        if done and get(facts, 'callback.callback_at') not in done:
            errors.append('callback_scheduled_time_mismatch')
    if 'order_updated' in goals:
        oid = get(facts, 'update.order_id')
        calls = [c for c in tool_log if (c.get('name') or c.get('tool')) == 'order.update' and (c.get('args') or {}).get('order_id') == oid]
        # nhắc lại yêu cầu đổi/trả đã xác nhận ở lượt trước (agent.updates_done chỉ giữ kết quả thành công) thì không có lời gọi
        if calls and not any(T.ok(c) for c in calls):
            errors.append('order_updated_without_successful_tool')
    return errors


def _preserve(tool_log):
    """Khi plan lỗi: dựng lại goal/facts CHỈ từ kết quả ghi đã xác nhận trong lượt, để lỗi phản hồi không làm mất thông báo
    về thao tác đã thật sự xảy ra. Không gọi lại tool ghi."""
    from harness import tool_outcome as T
    goals, facts = [], {}
    creates = [c for c in tool_log if (c.get('name') or c.get('tool')) == 'order.create']
    ok_creates = [c for c in creates if T.ok(c)]
    if ok_creates:
        if len(ok_creates) < len([c for c in creates if T.classify(c)['reason'] != 'price_mismatch']):
            goals.append('order_partial')
            facts['partial_orders'] = [{'order_id': c['result']['order_id'], 'total_vnd': c['result']['total_vnd']} for c in ok_creates]
        else:
            goals.append('order_created')
            facts['order'] = _order_fact(ok_creates)
    ups = T.confirmed(tool_log, 'order.update')
    if ups and (ups[-1].get('args') or {}).get('action') in ('return', 'exchange_size', 'exchange_product'):
        r = ups[-1]['result']
        goals.append('order_updated')
        facts['update'] = {k: r[k] for k in ('order_id', 'refund_vnd', 'extra_payment_vnd', 'fee_vnd', 'refund_days', 'status') if k in r}
    cbs = T.confirmed(tool_log, 'schedule.callback')
    if cbs:
        goals.append('callback_scheduled')
        facts['callback'] = {'callback_at': cbs[-1]['result']['callback_at']}
    hos = T.confirmed(tool_log, 'handoff.transfer')
    if hos:
        goals.append('handoff')
        facts['handoff'] = {k: hos[-1]['result'][k] for k in ('ticket_id', 'status')}
    return goals, facts


def enforce(plan, tool_log):
    from core.llm.generator import question_slot
    from harness import tool_outcome as T
    errors = validate(plan['goals'], plan['facts'])
    errors += _evidence_errors(plan['goals'], plan['facts'], tool_log)
    evidence = [{k: v for k, v in T.classify(c).items() if v not in (None, {})} for c in tool_log]
    plan['contract'] = {'errors': errors, 'provenance': evidence}
    if errors:
        goals, facts = _preserve(tool_log)
        if goals and not validate(goals, facts) and not _evidence_errors(goals, facts, tool_log):
            plan['contract']['preserved_goals'] = goals
            plan['goals'], plan['facts'] = goals, facts
        else:
            plan['goals'], plan['facts'] = ['contract_error'], {}
    chosen = question_slot(plan['goals'], plan['facts'])
    deferred = [g for g in plan['goals'] if question_slot([g], plan['facts']) not in (None, chosen)]
    if deferred:
        plan['contract']['deferred_question_goals'] = deferred
        plan['goals'] = [g for g in plan['goals'] if g not in deferred]
    plan['question_slot'] = chosen
    return plan
