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


def customer(text, rules, context=None, asked=None):
    """Certify only single, explicit value slots with no other candidate cue."""
    from core.config import settings
    if settings.extractor_cert_version >= 2:
        return customer_v2(text, rules, context, asked)
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


def empty(text, rules, context=None):
    """Certify that a customer turn carries no slot: no rule value and no cue at all.

    The cue scanner is deliberately broader than the rules (any digit, money,
    delivery, payment, deferral word...), checked on both accented and folded
    text. Short replies with context and back-references abstain because they
    may confirm a value said earlier.
    """
    from core.config import settings
    if settings.extractor_cert_version >= 2:
        return empty_v2(text, rules, context)
    from harness.extractor import CUSTOMER_CUE_FOLD_RX, CUSTOMER_LLM_CUE_RX

    f = fold(text)
    short_with_context = bool(context) and len(text.strip()) <= 32
    # Câu còn dấu: dùng regex có dấu (fold() làm "cỡ" khớp "có", "nhà" khớp "nha").
    # Câu mất dấu (ASR/teencode): dùng bản fold, rộng hơn nên dễ abstain hơn.
    accentless = f == re.sub(r"\s+", " ", (text or "").lower()).strip()
    cue = (CUSTOMER_CUE_FOLD_RX if accentless else CUSTOMER_LLM_CUE_RX).search(f if accentless else text)
    from harness import lexicon
    cue = cue or lexicon.cue_hit(f)          # cue lexicon đã duyệt (A-L) cũng chặn chứng nhận rỗng
    return _result(not rules, {"Q": not cue,
                               "C": not short_with_context and not CONTEXT.search(f)})


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


# =====================================================================================================================
# CERT v2 (docs/DE-XUAT-CERT-V2-2026-11-02.md; D18 CERT-1, D19 CERT-2, D20 CERT-3 — duyệt 02/11/2026).
# Bật bằng EXTRACTOR_CERT_VERSION=2 (mặc định 1 = hành vi cũ ở trên, tới khi D21 đạt điều kiện mục 4 của đề xuất).
# Vẫn nhị phân, kiểm được bằng mắt; không chắc thì bỏ phiếu trắng (Jev/Qwen).
# =====================================================================================================================
from harness.textnorm import strip_accents  # noqa: E402

# phủ định: bản có dấu (câu có dấu) và bản fold (câu mất dấu — bỏ "dung"/"cha" vì fold làm đúng/dùng/đựng, chả/chà va chạm)
NEG_ACC = re.compile(r"^(không|chưa|chẳng|chả|đừng|hông|hong|ko|k|kg|khỏi)$", re.I)
NEG_FOLD = re.compile(r"^(khong|chua|chang|hong|ko|k|kg|khoi)$")
# "không" cuối câu hỏi là trợ từ nghi vấn, không phải phủ định
Q_TAIL = re.compile(r"(không|khong|ko|k|hông|hong|chưa|chua)\s*(em|ạ|a|anh|chị|chi|vậy|vay|nhỉ|nhi|nhé|nhe|hả|ha|à)?\s*\??\s*$",
                    re.I)
QUES_RX = re.compile(r"\?\s*$|\b(được không|duoc khong|phải không|phai khong|đúng không|dung khong|hả|à)\s*\??\s*$|"
                     r"\b(có|co)\b.{1,30}\b(không|khong)\s*\??\s*$", re.I)
PREF_SLOTS = {"color", "size", "payment", "has_children"}            # khách hỏi → chưa chốt → bỏ phiếu trắng
UNSAFE_ACC = re.compile(r"\b(không phải|đúng là|giả sử|nếu|ví dụ|bảo là|nói là|hỏi xem|bên khác|shopee|lazada|hôm trước|"
                        r"lần trước|đổi ý|gọi lại|số điện thoại|đang dùng)\b", re.I)
UNSAFE_FOLD = re.compile(r"\b(khong phai|gia su|neu|vi du|bao la|noi la|hoi xem|ben khac|shopee|lazada|hom truoc|lan truoc|"
                         r"doi y|goi lai|so dien thoai|dang dung)\b")
CONTEXT_ACC = re.compile(r"\b(cái đó|màu đó|hôm trước|lần trước|như cũ|vẫn vậy|cái ấy|loại ấy|vẫn như)\b", re.I)
PAY_CHOICE = re.compile(r"\b(ship cod|cod (nhe|nha|nhe em|giup|gium|luon|di|a)|(chon|lay|tra|thanh toan|gui) (bang |qua |kieu )?"
                        r"(cod|chuyen khoan|momo|zalopay|tien mat|the)|thanh toan khi nhan|tra (tien )?(mat|khi nhan)|"
                        r"nhan hang (roi )?(moi )?(tra|thanh toan)|chuyen khoan (truoc|luon|nhe|nha|cho)|(da|vua|moi) (chuyen khoan|ck))\b")
PII_CODE = re.compile(r"\[(SĐT|ĐỊA_CHỈ|ĐỊA CHỈ)[^\]]*\]", re.I)
UNIT_RX = re.compile(r"m2|m²|mét vuông|met vuong", re.I)
STARTERS = {"anh", "chị", "em", "cô", "chú", "bác", "dạ", "vâng", "alo", "ok", "ừ", "ờ", "thôi", "vậy", "thế", "cho", "shop",
            "mình", "tôi", "con", "cháu", "bên", "nhà", "giá", "máy", "mẫu", "màu", "size", "phòng", "giao", "ship"}
# D20 (CERT-3, mục 3.8): thêm address / self_name / callback_requested / has_children sau khi có định nghĩa D10
CERT_V2_SLOTS = {"room_area_m2", "budget_vnd", "size", "color", "payment",
                 "address", "self_name", "callback_requested", "has_children"}
# D16/D27: bước nới chỉ bật bằng cờ đo CERT_V2_RELAX (mặc định rỗng = không đổi hành vi)
FIT_Q = re.compile(r"\b(co )?(vua|du|hop|duoc|on)\b.{0,12}\b(khong|ko|k|hong)\b|\bmua duoc (mau|loai|cai) nao\b")


def _relax(step):
    from core.config import settings
    return step in {x.strip() for x in (settings.cert_v2_relax or "").split(",") if x.strip()}


def _blocker_hit(f):
    """Entry value đã duyệt của lexicon khớp câu (D27 bước 1)."""
    from harness import lexicon
    for e in lexicon.entries(slot="blocker", kind="value"):
        m = e["rx"].search(f)
        if m:
            return e, m
    return None, None


def _accented(text):
    return fold(text) != re.sub(r"\s+", " ", (text or "").lower()).strip()


def _tokens(text):
    return [(m.group(), m.start(), m.end()) for m in re.finditer(r"[\wÀ-ỹ]+", text or "")]


def _anchor(text, slot, value):
    """Vị trí (start, end) của giá trị slot trong câu (để xét phủ định quanh nó). None nếu không định vị được.
    fold() giữ nguyên độ dài chuỗi nên vị trí trên bản fold dùng được cho bản gốc."""
    t, f = text or "", fold(text)
    m = None
    if slot == "room_area_m2":
        m = re.search(r"\b" + re.escape(str(value)) + r"\s*(m2|m²|mét vuông|mét|m)\b", t, re.I)
    elif slot == "budget_vnd":
        hit = [s for s in find_money(t) if s[2] == value]
        return (hit[0][0], hit[0][1]) if hit else None
    elif slot == "size":
        m = re.search(r"(size|cỡ|số)\s*" + re.escape(str(value)), t, re.I)
    elif slot == "color":
        from harness.tools import COLORS
        for w in sorted(COLORS.get(value, [str(value)]), key=len, reverse=True):
            m = re.search(r"\b" + re.escape(fold(w)) + r"\b", f)
            if m:
                break
    elif slot == "payment":
        m = re.search(r"\b(cod|thanh toan khi nhan|tien mat|nhan hang (roi )?(moi )?(tra|thanh toan)|chuyen khoan|ck|momo|"
                      r"zalopay|chuyen tien|banking)\b", f)
    elif slot == "address":
        i = f.find(fold(str(value))[:12])
        return (i, i + len(str(value))) if i >= 0 else None
    elif slot == "has_children":
        m = re.search(r"\b(be|con nho|em be|tre nho|tre con|chau nho)\b", f)
    elif slot in ("self_name", "callback_requested"):
        return (0, len(t))
    elif slot == "blocker" and _relax("blocker"):
        _, m = _blocker_hit(f)
    return m.span() if m else None


def negated(text, span, window=4):
    """NEG (3.1): có từ phủ định trong ±window từ quanh span. Không tính 'không/chưa' là trợ từ cuối câu hỏi,
    không tính 'k'/'kg' đứng sau chữ số (đơn vị: 500 k, 5 kg)."""
    if span is None:
        return False
    toks = _tokens(text)
    acc = _accented(text)
    tail = Q_TAIL.search(text or "")
    idx = [i for i, (_, s, e) in enumerate(toks) if e > span[0] and s < span[1]]
    if not idx:
        return False
    lo, hi = max(0, idx[0] - window), min(len(toks), idx[-1] + window + 1)
    for i in range(lo, hi):
        w, s, _ = toks[i]
        if tail and s >= tail.start():
            continue
        if w.lower() in ("k", "kg") and i > 0 and re.search(r"\d$", toks[i - 1][0]):
            continue
        if (NEG_ACC.match(w.lower()) if acc else NEG_FOLD.match(strip_accents(w.lower()))):
            return True
    return False


def is_question(text):
    return bool(QUES_RX.search((text or "").strip()))


def _drop_spans(text, spans):
    out = text or ""
    for s, e in sorted(spans, reverse=True):
        out = out[:s] + " " * (e - s) + out[e:]
    return out


def _catalog_values():
    from harness.tools import COLORS, mt
    sizes = {str(v["size"]).upper() for p in mt.PRODUCTS for v in (p.get("variants") or []) if v.get("size") is not None}
    return set(COLORS), sizes


def _proper_nouns(text):
    """3.6: danh từ riêng viết hoa KHÔNG đứng đầu câu; bỏ tên sản phẩm / thương hiệu trong catalog và từ mở đầu quen thuộc."""
    from harness.tools import mt
    vocab = {w.lower() for p in mt.PRODUCTS for w in re.findall(r"[\wÀ-ỹ&]+", p["name"] + " " + p.get("brand", ""))}
    out = []
    for sent in re.split(r"(?<=[.!?])\s+|,\s*", text or ""):
        words = re.findall(r"[\wÀ-ỹ&]+", sent)
        for i, w in enumerate(words):
            if i == 0 or not w[:1].isupper() or (w.isupper() and len(w) <= 3):
                continue
            if w.lower() in vocab or w.lower() in STARTERS:
                continue
            out.append(w)
    return out


def _slot_cert(text, slot, value, context, asked):
    """Chứng chỉ riêng cho MỘT slot (3.5). → dict check (True = đạt). P đã bỏ vì trùng G (3.7)."""
    from harness.extractor import ADDRESS_RX
    acc = _accented(text)
    f = fold(text)
    span = _anchor(text, slot, value)
    colors, sizes = _catalog_values()
    # 3.2: bỏ token đơn vị (m2, m²) trước khi đếm số — "25m2" có MỘT số
    money = find_money(text)
    if slot == "room_area_m2":
        area = re.findall(r"(\d{1,3})\s*(?:m2|m²|met vuong|mét vuông)", f)
        g = len(area) == 1 and int(area[0]) == value
        plain = re.findall(r"\d+(?:[.,]\d+)*", UNIT_RX.sub(" ", _drop_spans(text, [(m[0], m[1]) for m in money])))
        u = len(plain) == 1                                   # số tiền thuộc slot khác (ngân sách) không tính
        cue = bool(UNIT_RX.search(text or ""))
    elif slot == "budget_vnd":
        g = len([m for m in money if m[2] == value]) == 1
        u = len(money) == 1
        cue = bool(re.search(r"ngan sach|du dinh chi|toi da|\btam\b|khoang|duoi|muc gia", f))
    elif slot == "size":
        g = str(value).upper() in sizes and span is not None                # 3.7: G độc lập = có trong catalog + có trong câu
        u = not money and not UNIT_RX.search(text or "")
        cue = bool(re.search(r"\b(size|co|so)\b", f))
    elif slot == "color":
        g = value in colors and span is not None
        u = not money
        cue = span is not None
    elif slot == "payment":
        # phải là khách CHỌN cách trả (D10), không phải nhắc "COD" khi nói về cài đặt / khách của họ (real_ref R044, R110)
        g = value in ("COD", "bank") and span is not None and bool(PAY_CHOICE.search(f))
        u = not money
        cue = span is not None
    elif slot == "address":
        m = ADDRESS_RX.search(text or "")
        g = bool(m) and m.group(1).strip(" ,") == value and bool(re.match(r"(số |ngõ |hẻm |kiệt |\d)", str(value), re.I))
        g = g and bool(re.search(r"\d+\s*[^\W\d_]", str(value)))           # có số nhà + tên đường
        u = not money
        cue = bool(m)
    elif slot == "self_name":
        v = re.escape(str(value))
        g = bool(re.search(r"(tên là|tên|là)\s+" + v + r"\b", text or "") or
                 re.search(r"\b(chị|anh|cô|chú|bác|em)\s+" + v + r"\s+(đây|nè|này)\b", text or ""))
        g = g and str(value)[:1].isupper()
        u = not money and len(_proper_nouns(text)) <= 1
        cue = g
    elif slot == "callback_requested":
        g = bool(re.search(r"goi lai|lien lac|bao lai|goi cho|nhan lai|nhan tin|hen", f)) and bool(value)
        u = not money
        cue = bool(re.search(r"\b(mai|mot|nay|toi|sang|chieu|thu (hai|ba|tu|nam|sau|bay|\d)|chu nhat|\d+\s*(h|gio))\b", f))
    elif slot == "has_children":
        g = value is True and span is not None and not re.search(r"\b(be ca|be nuoc|be boi|ho ca)\b", f)
        u = not money
        cue = span is not None
    elif slot == "blocker" and _relax("blocker"):
        # D27 bước 1: giá trị phải trùng giá trị của một entry value đã duyệt khớp câu; không số, không phủ định, không câu hỏi
        e, _ = _blocker_hit(f)
        g = e is not None and e["value"] == value
        u = not money and not re.search(r"\d", text or "")
        cue = g
    else:
        return {"S": False}
    unsafe = (UNSAFE_ACC.search(text) if acc else UNSAFE_FOLD.search(f))
    ctx_ref = (CONTEXT_ACC.search(text) if acc else CONTEXT.search(f))
    short = bool(context) and len((text or "").strip()) <= 32
    paired = asked == slot and cue            # 3.3: câu ngắn có ngữ cảnh chỉ đạt khi agent vừa hỏi ĐÚNG slot này
    ques_ok = not (slot in PREF_SLOTS and is_question(text))
    if slot == "blocker":
        ques_ok, paired = not is_question(text), bool(g)      # cụm lexicon tự đủ nghĩa, không cần ghép câu hỏi
    elif slot == "budget_vnd" and _relax("budget"):
        # D27 bước 3: đúng một số tiền + cue ngân sách, không có chữ "giá" (khách nhắc giá) → tự đủ nghĩa kể cả câu ngắn;
        # câu hỏi chỉ được khi hỏi "có vừa/đủ/hợp không"
        own = bool(g and u and cue) and not re.search(r"\bgia\b", f)
        paired = paired or own
        ques_ok = own and (not (is_question(text) or Q_TAIL.search(text or "")) or bool(FIT_Q.search(f)))
    return {"G": bool(g), "U": bool(u), "K": bool(cue),
            "NEG": not negated(text, span),
            "QUES": ques_ok,
            "N": not unsafe and '"' not in (text or "") and "“" not in (text or ""),
            "C": not ctx_ref and (not short or paired)}


def customer_v2(text, rules, context=None, asked=None):
    """3.5: chứng nhận theo từng slot. Trả thêm `slots` {slot: {certified, checks}} và `certified_slots`.
    `certified` (cả lượt) = mọi slot đạt + không còn cue thừa ngoài vùng các slot đã nhận."""
    from harness.extractor import CUSTOMER_CUE_FOLD_RX, CUSTOMER_LLM_CUE_RX
    rules = {k: v for k, v in (rules or {}).items() if k != "claimed_prices"}
    per = {}
    for slot, value in rules.items():
        ch = (_slot_cert(text, slot, value, context, asked)
              if slot in CERT_V2_SLOTS or (slot == "blocker" and _relax("blocker")) else {"S": False})
        per[slot] = {"certified": all(ch.values()), "checks": ch}
    acc = _accented(text)
    spans = [s for s in (_anchor(text, k, v) for k, v in rules.items()) if s]
    rx, src = (CUSTOMER_LLM_CUE_RX, text) if acc else (CUSTOMER_CUE_FOLD_RX, fold(text))
    extra = [m.group() for m in rx.finditer(src or "")
             if not any(m.start() < e + 12 and m.end() > s - 12 for s, e in spans)]
    out = _result(bool(rules), {"S": bool(per) and all(p["certified"] for p in per.values()), "X": not extra})
    out.update(version=2, slots=per, certified_slots=sorted(k for k, p in per.items() if p["certified"]),
               extra_cues=extra[:5])
    return out


def empty_v2(text, rules, context=None):
    """Chứng nhận rỗng v2 = v1 (không luật, không cue, không tham chiếu ngược, khớp bản có dấu khi câu có dấu)
    + 3.6: không có danh từ riêng viết hoa (ngoài catalog) và không có mã PII đã che."""
    from harness.extractor import CUSTOMER_CUE_FOLD_RX, CUSTOMER_LLM_CUE_RX
    from harness import lexicon
    f = fold(text)
    acc = _accented(text)
    cue = (CUSTOMER_LLM_CUE_RX.search(text) if acc else CUSTOMER_CUE_FOLD_RX.search(f)) or lexicon.cue_hit(f)
    short_with_context = bool(context) and len((text or "").strip()) <= 32
    ctx_ref = CONTEXT_ACC.search(text) if acc else CONTEXT.search(f)
    out = _result(not rules, {"Q": not cue, "C": not short_with_context and not ctx_ref,
                              "PN": not _proper_nouns(text) and not PII_CODE.search(text or "")})
    out["version"] = 2
    return out
