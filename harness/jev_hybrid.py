"""Jev label classification with locally grounded values.

Jev chooses which labels apply. Local rules supply concrete values; Qwen is
reserved for labels that Jev identifies but the rules cannot ground.
"""

from core.config import settings
from core.pii import Redactor
from harness.question_classifiers.jev_slots import _client


def labels(text, definitions, role, meta=None, context=None):
    """Return a set of present labels, or None on any invalid/failed request."""
    meta = meta if meta is not None else {}
    if settings.jev_simulated:
        from harness.jev_adapter import labels as simulated_labels
        return simulated_labels(text, definitions, role, meta, context)
    try:
        from typesafe_sdk import Choice

        safe = Redactor().redact({"sentence": text, "context": context or ""})
        questions = {name: Choice(
            instructions=(f"Does the current {role} sentence explicitly contain: {description}? "
                          "Use the conversation context only to resolve references or meaning. "
                          "Return yes only when the current sentence provides or asserts this information; "
                          "do not copy a value mentioned only in earlier context. "
                          # D10 (02/11): quy tắc chung của định nghĩa slot (harness/llm_extract.CUSTOMER_RULES), bản tiếng Anh
                          "A value stated inside a question or request still counts (e.g. 'ship to 5 Tran Phu, how many days?' "
                          "states an address); asking the shop about the value without stating it does not count; a short "
                          "confirmation such as 'yes, same address' is not a new value; if the speaker corrects themselves, use "
                          "the last value. "
                          "Privacy codes such as [ĐỊA_CHỈ_1] or [SĐT_1] stand for a real address / phone number that was "
                          "masked: a sentence containing [ĐỊA_CHỈ_n] DOES state an address (also inside a delivery question)."),
            criteria={"yes": "Explicitly present", "no": "Not explicitly present"})
            for name, description in definitions.items()}
        meta["jev_label_requests"] = meta.get("jev_label_requests", 0) + 1
        result = _client().system_one(state={"role": role, "sentence": safe["sentence"],
                                            "conversation_context": safe["context"]},
                                      questions=questions, model=settings.jev_model)
        choices = {name: result.choices[name].choice for name in definitions}
        if any(choice not in ("yes", "no") for choice in choices.values()):
            raise ValueError("invalid_jev_label")
        meta.pop("jev_label_error", None)
        return {name for name, choice in choices.items() if choice == "yes"}
    except Exception as exc:
        meta["jev_label_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        return None


def customer(text, rules, meta=None, context=None):
    from harness.llm_extract import CUSTOMER_SLOTS

    found = labels(text, CUSTOMER_SLOTS, "customer", meta, context)
    if found is None:
        return None
    grounded = set(rules)
    if "claimed_prices" in grounded:
        grounded.remove("claimed_prices")
        grounded.add("claimed_price_vnd")
    if meta is not None:
        meta["jev_customer_labels"] = sorted(found)
    # Jev owns label selection. Keep only values grounded by local extraction.
    # If Jev selects a label without a value, let the span-checked Qwen path
    # recover it; an empty label set is a valid classification.
    value_key = {"claimed_price_vnd": "claimed_prices"}
    missing = found - grounded
    if missing:
        if meta is not None:
            meta["jev_un_grounded_customer_labels"] = sorted(missing)
        return None
    selected = {value_key.get(label, label) for label in found}
    # A6 (BTCL-047): Jev bỏ một slot đơn hàng mà luật đã cắt được span thì sai
    # một lần làm hỏng order.create. Chính sách chọn bằng JEV_DROP_POLICY.
    dropped = sorted(PROTECTED & set(rules) - selected)
    if dropped:
        if meta is not None:
            meta["jev_dropped_rule_slots"] = dropped
        if settings.jev_drop_policy == "qwen":
            return None
        if settings.jev_drop_policy == "rules":
            selected |= set(dropped)
    return {key: value for key, value in rules.items() if key in selected}


PROTECTED = {"address", "payment"}


def claims(sentence, rule_claims, meta=None):
    from harness.llm_extract import FACTS, NUMBER_ROLES
    from harness.textnorm import find_money

    roles = {**NUMBER_ROLES, **FACTS}
    definitions = {name: item[-1] for name, item in roles.items()}
    found = labels(sentence, definitions, "agent", meta)
    if found is None:
        return None
    # Jev names are semantic roles; local claims carry field/value pairs.
    field_by_role = {name: item[0] for name, item in roles.items()}
    fields = {field_by_role[name] for name in found}
    grounded = {claim["field"] for claim in rule_claims}
    if meta is not None:
        meta.setdefault("jev_claim_labels", []).append(sorted(found))
    money_fields = {"price_vnd", "list_price_vnd", "price_quoted_vnd"}
    ambiguous_money = bool(fields & money_fields) and len(find_money(sentence)) != 1
    if None in fields or "is_human" in fields or ambiguous_money or not fields <= grounded:
        return None
    # Jev selects which grounded claims are retained; an empty set is valid.
    return [claim for claim in rule_claims if claim["field"] in fields]
