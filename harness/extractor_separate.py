"""Independent claim and question routing; question certificates never certify claims."""
from core.config import settings


def analyze(text, known, q_rules, c_rules, meta, focus_sku):
    from harness import extractor, llm_extract
    from harness.rule_confidence import question as certify
    meta = meta if meta is not None else {}
    # llm_extract.agent keeps grounded rule claims and span-checks model additions.
    llm_q, claims = llm_extract.agent(text, known, q_rules, c_rules, 'hybrid', meta, focus_sku=focus_sku)
    meta['claim_route'] = 'rules_plus_' + settings.extractor_llm
    sentences = extractor._sentences(text)
    certified, remaining = set(), []
    certs = []
    for i, sentence in enumerate(sentences):
        rules = [q for q in q_rules if q['text'] == sentence]
        cert = certify(sentence, rules, known) if settings.extractor_confidence_gate else {'certified': False, 'checks': {}, 'reason': 'gate_disabled'}
        certs.append({'sentence': i, **cert})
        if cert['certified']:
            certified.add(sentence)
        else:
            remaining.append(sentence)
    meta['agent_confidence'] = certs
    meta['rule_certified_sentences'] = len(certified)
    questions = [q for q in q_rules if q['text'] in certified]
    if remaining:
        if settings.extractor_jev_hybrid or settings.agent_question_backend == 'jev_slots_experimental':
            from harness.question_classifiers.jev_slots import classify_agent_questions
            qmeta = {}
            selected = classify_agent_questions(' '.join(remaining), known, qmeta)
            meta.update(qmeta)
            if qmeta.get('jev_slot_errors'):
                selected = [q for q in llm_q if q['text'] in remaining]
                meta['question_fallback'] = 'span_checked_llm'
        else:
            selected = [q for q in llm_q if q['text'] in remaining]
        questions += selected
    by_text = {q['text']: q for q in questions}
    return [by_text[s] for s in sentences if s in by_text], claims
