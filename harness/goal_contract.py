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
    if 'order_created' in goals and any(g in goals for g in ('order_failed', 'out_of_stock', 'ask_variant', 'ask_address', 'ask_payment')):
        errors.append('conflicting_order_result')
    return errors


def enforce(plan, tool_log):
    from core.llm.generator import question_slot
    errors = validate(plan['goals'], plan['facts'])
    evidence, created = [], []
    for call in tool_log:
        name = call.get('tool') or call.get('name')
        result = call.get('result') or call.get('response') or {}
        success = isinstance(result, dict) and not result.get('error')
        evidence.append({'tool': name, 'success': success})
        if name == 'order.create' and success and result.get('order_id'):
            created.append(result['order_id'])
    if 'order_created' in plan['goals'] and not set(str(get(plan['facts'], 'order.order_id') or '').split(', ')) <= set(created):
        errors.append('order_created_without_successful_tool')
    if 'order_partial' in plan['goals']:
        ids = {o.get('order_id') for o in plan['facts'].get('partial_orders', [])}
        if not ids or not ids <= set(created):
            errors.append('partial_order_without_successful_tool')
    plan['contract'] = {'errors': errors, 'provenance': evidence}
    if errors:
        plan['goals'], plan['facts'] = ['contract_error'], {}
    chosen = question_slot(plan['goals'], plan['facts'])
    deferred = [g for g in plan['goals'] if question_slot([g], plan['facts']) not in (None, chosen)]
    if deferred:
        plan['contract']['deferred_question_goals'] = deferred
        plan['goals'] = [g for g in plan['goals'] if g not in deferred]
    plan['question_slot'] = chosen
    return plan
