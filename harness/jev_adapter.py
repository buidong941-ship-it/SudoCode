"""Qwen simulation; denies real TypeSafe clients instead of replaying gold."""
import threading
from core.config import settings
from core.llm.deepseek import LLM
from core.pii import Redactor

COUNTS = {'simulated_requests': 0, 'real_requests': 0, 'blocked_real_requests': 0}
_lock = threading.Lock()
_blocked = False


def block_real_api():
    global _blocked
    if not settings.jev_simulated or _blocked:
        return
    with _lock:
        if _blocked:
            return
        try:
            import typesafe_sdk
        except ImportError:
            return
        def denied(*args, **kwargs):
            COUNTS['blocked_real_requests'] += 1
            raise RuntimeError('Real Jev API denied in simulation')
        typesafe_sdk.TypeSafeClient = denied
        _blocked = True


def infer(prompt, schema):
    block_real_api()
    with _lock:
        COUNTS['simulated_requests'] += 1
    return LLM('qwen', role='extract').json(prompt, schema=schema, cache=False, max_tokens=500)


def labels(text, definitions, role, meta, context):
    safe = Redactor().redact({'sentence': text, 'context': context or ''})
    schema = {'type': 'object', 'required': ['labels'], 'additionalProperties': False,
              'properties': {'labels': {'type': 'array', 'items': {'type': 'string', 'enum': list(definitions)}}}}
    meta['simulated'] = True
    try:
        return set(infer(f'Classify explicitly stated labels in CURRENT {role} sentence only; do not copy previous values. Return JSON labels, empty array if none. Definitions: {definitions}. Data: {safe}', schema)['labels'])
    except Exception as exc:
        meta['jev_label_error'] = type(exc).__name__
        return None


def questions(text, known_values, meta=None):
    from harness.extractor import _sentences, agent_questions
    from harness.question_classifiers.jev_slots import SLOT_CRITERIA, TYPE_CRITERIA, SLOT_INSTRUCTIONS, TYPE_INSTRUCTIONS
    meta = meta if meta is not None else {}
    out, errors = [], []
    for sentence in _sentences(text):
        schema = {'type': 'object', 'required': ['slot', 'type'], 'additionalProperties': False,
                  'properties': {'slot': {'type': 'string', 'enum': list(SLOT_CRITERIA)}, 'type': {'type': 'string', 'enum': list(TYPE_CRITERIA)}}}
        try:
            safe = Redactor().redact({'sentence': sentence, 'known_values': known_values})
            result = infer(f'{SLOT_INSTRUCTIONS}\n{TYPE_INSTRUCTIONS}\nSlots: {SLOT_CRITERIA}\nData: {safe}\nReturn JSON slot,type.', schema)
            slot, kind = result['slot'], result['type']
            if slot not in SLOT_CRITERIA or kind not in TYPE_CRITERIA or ((slot == 'none') != (kind == 'none')):
                raise ValueError('slot_type_mismatch')
            if slot != 'none':
                out.append({'slot': slot, 'type': kind, 'text': sentence})
        except Exception as exc:
            errors.append(type(exc).__name__)
            out.extend(agent_questions(sentence, known_values, use_classifier=False))
    meta.update(simulated=True, question_backend='qwen_simulated_jev', jev_slot_requests=0, jev_slot_ms=0,
                simulated_slot_requests=len(_sentences(text)), jev_slot_errors=errors)
    return out
