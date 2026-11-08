"""Closed multi-action and safety flag contract shared by Jev and Qwen simulation."""
from dataclasses import asdict
from core.config import settings
from core.pii import Redactor
from harness.planner_selector import ACTIONS, _DOC


def decide(text, previous_agent, state):
    from core.llm.router import FLAGS, _rules
    FLAGS = {**FLAGS, 'asks_other_customer': ('Người gọi xin số điện thoại, địa chỉ, đơn hàng hoặc dữ liệu riêng của một người/khách khác, kể cả người vừa mua hàng.', 'Không xin dữ liệu khách khác.')}
    names = list(ACTIONS)
    safe = Redactor().redact({'customer': text, 'previous_agent': previous_agent, 'state': asdict(state)})
    if settings.planner_selector == 'jev' and not settings.jev_simulated:
        from typesafe_sdk import Choice
        from harness.question_classifiers.jev_slots import _client
        questions = {name: Choice(instructions=f'Khách thực sự yêu cầu: {ACTIONS[name]["description"]}? {_DOC["instruction"]}', criteria={'yes': 'Có', 'no': 'Không'}) for name in names}
        questions.update({f'flag_{name}': Choice(instructions=yes, criteria={'yes': yes, 'no': no}) for name, (yes, no) in FLAGS.items()})
        result = _client().system_one(state=safe, questions=questions, model=settings.jev_model)
        selected = [name for name in names if result.choices[name].choice == 'yes' and result.choices[name].confidence >= settings.planner_jev_min_conf]
        flags = {name: float(result.choices[f'flag_{name}'].confidence) if result.choices[f'flag_{name}'].choice == 'yes' else 0.0 for name in FLAGS}
        backend = 'jev'
    else:
        from harness.jev_adapter import infer
        schema = {'type': 'object', 'required': ['actions', 'flags'], 'additionalProperties': False,
                  'properties': {'actions': {'type': 'array', 'maxItems': 3, 'items': {'type': 'string', 'enum': names}},
                                 'flags': {'type': 'object', 'required': list(FLAGS), 'additionalProperties': False, 'properties': {name: {'type': 'boolean'} for name in FLAGS}}}}
        prompt = (f'{_DOC["instruction"]}\nPhân biệt phủ định, hỏi khả năng và đồng ý. Dùng hội thoại để hiểu xác nhận ngắn. '
                  f'Trả JSON actions và flags; không sinh tham số tool.\nActions: {ACTIONS}\nFlags: {FLAGS}\nRuntime data: {safe}')
        data = infer(prompt, schema)
        selected, flags = data['actions'], {name: float(data['flags'][name]) for name in FLAGS}
        backend = 'qwen_simulated_jev' if settings.jev_simulated else 'qwen'
    if len(selected) > 3:
        raise ValueError('too_many_actions')
    if any(name not in ACTIONS for name in selected):
        raise ValueError('unknown_action')
    rule_flags = _rules(text)['flags']
    for name in ('asks_if_bot', 'asks_internal_cost', 'wants_data_deleted'):
        flags[name] = max(flags.get(name, 0), rule_flags.get(name, 0))
    return {'actions': list(dict.fromkeys(selected)), 'flags': flags, 'backend': backend,
            'simulated': settings.jev_simulated, 'confidence': None if settings.jev_simulated else 'per_choice'}
