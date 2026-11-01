"""Conservative, inspectable rule certificates for the experimental cascade.

CERT is a conjunction of checks on live text. It is not a probability and does
not use labels or evaluation answers at runtime. An empty rule result abstains.
"""

import re

from harness.textnorm import find_money, fold

# CERT is a binary score: all checks must pass before rule labels bypass Jev.
# It is a deterministic certificate, not a calibrated probability.
RULE_CONFIDENCE_THRESHOLD = 1.0

UNSAFE = re.compile(r"\b(khong phai|dung|gia su|neu|vi du|bao la|noi la|hoi xem|ben khac|shopee|lazada|"
                    r"hom truoc|lan truoc|doi y|goi lai|dia chi|so dien thoai|dang dung)\b")
CONTEXT = re.compile(r"\b(cai do|mau do|hom truoc|lan truoc|nhu cu|van vay|cai ay|loai ay)\b")


def _result(rule_nonempty, checks):
    checks = {"R": bool(rule_nonempty), **checks}
    score = float(all(checks.values()))
    certified = score >= RULE_CONFIDENCE_THRESHOLD
    return {"score": round(score, 3), "threshold": RULE_CONFIDENCE_THRESHOLD,
            "certified": certified, "checks": checks,
            "reason": "certified" if certified else ",".join(k for k, v in checks.items() if not v)}


def customer(text, rules, context=None):
    """Certify only single, explicit value slots with no other candidate cue."""
    from harness.extractor import CUSTOMER_LLM_CUE_RX, customer_slots_rules

    f = fold(text)
    allowed = {"room_area_m2", "budget_vnd", "size", "color", "payment"}
    one = len(rules) == 1 and next(iter(rules), None) in allowed
    slot = next(iter(rules), None)
    money = find_money(text)
    area = re.findall(r"(\d{1,3})\s*(?:m2|m²|met vuong|mét vuông)", f)
    if slot == "room_area_m2":
        grounded = len(area) == 1 and int(area[0]) == rules[slot]
        parsed = grounded
        unique = not money and len(re.findall(r"\d+", text)) == 1
        cue = bool(re.search(r"m2|m²|met vuong", f))
    elif slot == "budget_vnd":
        grounded = len(money) == 1 and money[0][2] == rules[slot]
        parsed = grounded
        unique = len(money) == 1 and not area
        cue = bool(re.search(r"ngan sach|du dinh chi|toi da|muc gia", f))
    elif slot in ("size", "color", "payment"):
        grounded = bool(rules[slot]) and slot in customer_slots_rules(text, "2026-10-15")
        parsed = grounded
        unique = not money and not area and not re.search(r"\d", text) if slot != "size" else not money and not area
        cue = bool(re.search({"size": r"size|co giay|cỡ", "color": r"mau|màu",
                              "payment": r"cod|chuyen khoan|chuyển khoản|thanh toan|thanh toán"}[slot], f))
    else:
        grounded = parsed = unique = cue = False
    # A broad, independent candidate scanner must agree with the one parsed slot.
    suspicious = bool(CUSTOMER_LLM_CUE_RX.search(text)) and not cue
    no_extra = not suspicious and not re.search(r"\b(be|con nho|gia|giao|hen|ban khoan|hoi nguoi nha)\b", f)
    context_ok = not (context and (len(text.strip()) <= 32 or CONTEXT.search(f)))
    return _result(one, {"G": grounded, "P": parsed, "U": unique,
                         "N": not UNSAFE.search(f) and '"' not in text and "“" not in text,
                         "K": cue and no_extra, "C": context_ok})


def question(sentence, q_rules, known_values=None):
    """Certify an explicit single-slot question without claim or context risk."""
    from harness.extractor import SLOT_KW, agent_claims

    f = fold(sentence)
    signals = {slot for slot, rx in SLOT_KW if re.search(rx, f)}
    q = q_rules[0] if len(q_rules) == 1 else None
    slot = q.get("slot") if q else None
    grounded = bool(q and q.get("text") == sentence)
    generic = slot == "other" and not signals and bool(re.search(r"\b(co can|can them|ho tro gi them)\b", f))
    unique = bool(slot and (signals == {slot} or generic))
    parsed = bool(q and q.get("type") in ("open", "confirm"))
    return _result(q is not None, {"G": grounded, "P": parsed, "U": unique,
                                   "N": not UNSAFE.search(f) and '"' not in sentence and "“" not in sentence,
                                   "K": sentence.endswith("?") and not re.search(r"\d", sentence)
                                   and not agent_claims(sentence) and unique,
                                   "C": not CONTEXT.search(f)})
