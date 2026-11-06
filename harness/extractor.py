"""Extractor: trích có cấu trúc từ lời KHÁCH (slot → bộ nhớ) và từ lời AGENT (questions[], claims[], facts_used → trace).

Ba chế độ (`EXTRACTOR_BACKEND` / `run_eval.py --extractor`):
- `rules`  (mặc định): luật/regex trong file này — rẻ, tái lập được, mô tả được trong báo cáo.
- `llm`    : LLM (Qwen local hoặc DeepSeek) phân loại slot/câu hỏi/claim theo định nghĩa cố định; code đọc giá trị (số tiền,
             ngày, size, màu) và kiểm đoạn trích có thật trong câu (harness/llm_extract.py). LLM lỗi → dùng luật.
- `hybrid` : luật + LLM: LLM bổ sung chỗ luật bỏ sót, claim là hợp của hai bên (không bỏ claim nào luật đã bắt).
BTC chấm tay extractor — không được "ăn gian": không chế độ nào được bỏ claim/câu hỏi chỉ để làm đẹp RQR/HR.
Quy ước claims: chỉ ghi dữ kiện agent KHẲNG ĐỊNH và đối chiếu được (giá, KM, tồn kho, ngày giao, bảo hành, đổi trả, là người hay AI).
`facts_used` (CCR) luôn là code: so giá trị đã nhớ với lời agent / tham số tool.
"""
import logging
import re

from core.config import settings
from harness.textnorm import PHONE_RX, find_money, fold, parse_relative_datetime

log = logging.getLogger("extractor")

KIDS_RX = re.compile(r"(?<!mau )\b(be|con nho|em be|tre nho|tre con|chau nho)\b")
# "co" (fold) trùng cả "cô" lẫn "có" ("em có gọi lại không") → với "cô" phải có "sẽ"
CUSTOMER_CALLS_RX = re.compile(r"\b((anh|chi|minh|toi|tui|chu|bac)\s+(se\s+|de\s+|lai\s+)?|co\s+se\s+)"
                               r"(goi lai|goi cho|lien lac( lai)?|bao lai|nhan lai)\b")

BLOCKERS = [(r"(hoi|ban voi) (chong|ong xa|anh nha|bo no)", "can hoi chong"), (r"(hoi|ban voi) (vo|ba xa|chi nha|me no)", "can hoi vo"),
            (r"hoi (con|nguoi nha|gia dinh|bo me|me)", "can hoi nguoi nha"), (r"(so sanh|so gia|tham khao) (gia|them)", "so sanh gia"),
            (r"(can nhac|suy nghi|xem them|tim hieu them|de (cuoi tuan )?(anh|chi|em) quyet)", "can nhac")]
# A5 (01/11): thêm "ship/gửi/chuyển (hàng) đến/về/tới…" (BTCL-047) và dừng trước "không" cuối câu hỏi (BTCL-046).
# Giá trị vẫn phải bắt đầu bằng số/ngõ/hẻm nên "gửi về cho mẹ", "giao đến khi nào" không thành địa chỉ.
ADDRESS_RX = re.compile(r"(?:(?:giao|ship|gửi|chuyển)(?: hàng)? (?:về|tới|đến|ra|vô|vào)|giao cho \w+ (?:về|tới|ở)|địa chỉ(?: mới| giao)?(?: là|:)?|(?:giờ|hiện|nhà) (?:chị|anh|em|cô|chú)? ?ở|chuyển nhà (?:ra|vào|về|tới))\s+"
                        r"((?:số |ngõ |hẻm |\d)[^.!?]*?)(?=,?\s+(?:(?:nhé|nha|nhá|ạ|rồi)(?=\s*(?:[.!?,]|$))|(?:em|giúp|luôn|trong tuần|thanh toán|thì|mất|bao lâu|khi nào|được không|đúng không|không|hả|vậy)\b"
                        # D-7 (02/11): dừng trước "bên em…" và "anh trả tiền…" ("80 Ngô Quyền, Đà Nẵng, bên em có giao…")
                        r"|bên (?:em|mình|shop)\b|(?:anh|chị|cô|chú|mình|tôi|em) (?:trả|thanh toán|nhận|lấy)\b|trả tiền\b)|[.!?]|$)", re.I)


def phone_only_address(value):
    """1c (06/11): giá trị "địa chỉ" thực chất chỉ là SĐT ("số 0984726714", "số của vợ anh là 09…") → không phải địa chỉ (RT-06, RT-14)."""
    v = str(value or "")
    return bool(PHONE_RX.search(v)) and not re.search(r"\d|,", PHONE_RX.sub(" ", v))

CUSTOMER_LLM_CUE_RX = re.compile(
    r"\d|m2|m²|mét vuông|diện tích|phòng|bé|em bé|trẻ nhỏ|trẻ con|con nhỏ|ngân sách|tầm|khoảng|"
    r"giá|shopee|lazada|tiki|sàn|bên kia|bên khác|size|cỡ|màu|giao|địa chỉ|cod|thanh toán|"
    r"chuyển khoản|momo|zalopay|ông xã|bà xã|anh nhà|chị nhà|người nhà|cân nhắc|so sánh|"
    r"gọi lại|liên lạc|báo lại|tên là|chị là|anh là|cô là|chú là|\bnhà\b|tháng|tuổi|"
    r"đắt|mắc|giảm|bớt|đang dùng|đang xài|đã có|có sẵn|nhà có|"
    # trì hoãn / blocker không có từ khóa slot (A1 01/11: BTCL-006/056/057 bị bỏ sót)
    r"so thêm|phản hồi|quyết|chờ|đợi|suy nghĩ|tính sau|để sau|bàn lại|hỏi ý|hỏi lại|"
    r"ship|gửi|chuyển|nhận hàng|tên",
    re.I,
)
# Cùng bộ cue nhưng khớp trên chuỗi fold() để không lọt câu ASR mất dấu.
CUSTOMER_CUE_FOLD_RX = re.compile(fold(CUSTOMER_LLM_CUE_RX.pattern), re.I)


def customer_slots(text, today, meta=None, context=None, asked=None):
    rules = customer_slots_rules(text, today)
    if settings.extractor_backend == "rules":
        return rules
    if settings.extractor_backend == "hybrid" and settings.extractor_confidence_gate:
        from harness.rule_confidence import customer as certify_customer, empty as certify_empty

        cert = certify_customer(text, rules, context, asked)
        if meta is not None:
            meta["customer_confidence"] = cert
        if cert["certified"]:
            if meta is not None:
                meta["backend"] = "hybrid:certified_rules"
                meta["customer_qwen_skipped"] = True
            return rules
        empty = certify_empty(text, rules, context)
        if meta is not None:
            meta["customer_empty_confidence"] = empty
        if empty["certified"]:
            if meta is not None:
                meta["backend"] = "hybrid:certified_empty"
                meta["customer_qwen_skipped"] = True
            return {}
    if settings.extractor_backend == "hybrid" and settings.extractor_jev_hybrid:
        from harness.jev_hybrid import customer as jev_customer
        jev_slots = jev_customer(text, rules, meta, context)
        if jev_slots is not None:
            if meta is not None:
                meta["backend"] = "hybrid:jev_grounded_rules"
                meta["customer_qwen_skipped"] = True
            return _lock(jev_slots, rules, meta)
    from harness import llm_extract
    return _lock(llm_extract.customer_slots(text, today, rules, settings.extractor_backend, meta, context), rules, meta)


def _lock(result, rules, meta):
    """CERT v2 (3.5): slot đã được chứng nhận riêng thì giữ giá trị luật, Jev/Qwen không được ghi đè hay làm mất."""
    locked = ((meta or {}).get("customer_confidence") or {}).get("certified_slots") or []
    if not locked or result is None:
        return result
    out = dict(result)
    out.update({k: rules[k] for k in locked if k in rules})
    meta["cert_locked_slots"] = list(locked)
    return out


def customer_llm_candidate(text, context=None):
    """Cheap high-recall gate: skip customer LLM extraction for text with no slot cues."""
    if context and len(text.strip()) <= 32:
        return True
    from harness import lexicon
    return bool(CUSTOMER_LLM_CUE_RX.search(text)) or bool(lexicon.cue_hit(fold(text)))


def analyze_agent(text, known_values, meta=None, focus_sku=None):
    q_rules = agent_questions(text, known_values, use_classifier=settings.question_clf)
    c_rules = agent_claims(text, focus_sku=focus_sku)
    if settings.extractor_backend == "rules":
        return q_rules, c_rules
    if settings.extractor_backend == "hybrid" and (settings.extractor_confidence_gate or settings.extractor_jev_hybrid):
        return _analyze_agent_confidence(text, known_values, q_rules, c_rules, meta, focus_sku)
    if settings.agent_claim_backend == "rules":
        # Experiment: retain the customer hybrid extractor, but skip the
        # post-reply Qwen call for agent questions and claims entirely.
        questions, claims = q_rules, c_rules
        if meta is not None:
            meta["agent_qwen_skipped"] = True
    elif settings.agent_claim_backend == "current":
        from harness import llm_extract
        questions, claims = llm_extract.agent(text, known_values, q_rules, c_rules,
                                              settings.extractor_backend, meta, focus_sku=focus_sku)
    else:
        raise ValueError(f"Unknown AGENT_CLAIM_BACKEND: {settings.agent_claim_backend}")
    if settings.agent_question_backend == "jev_slots_experimental":
        from harness.question_classifiers.jev_slots import classify_agent_questions
        questions = classify_agent_questions(text, known_values, meta)
    return questions, claims


def _analyze_agent_confidence(text, known_values, q_rules, c_rules, meta, focus_sku):
    from harness import llm_extract
    from harness.rule_confidence import question as certify_question

    sentences = _sentences(text)
    by_sentence = {s: [q for q in q_rules if q["text"] == s] for s in sentences}
    certs = [certify_question(s, by_sentence[s], known_values)
             if settings.extractor_confidence_gate
             else {"certified": False, "checks": {}, "reason": "gate_disabled"} for s in sentences]
    certified = {s for s, cert in zip(sentences, certs) if cert["certified"]}
    if meta is not None:
        meta["agent_confidence"] = [{"sentence": i, **cert} for i, cert in enumerate(certs)]
        meta["rule_certified_sentences"] = len(certified)
        meta["claim_route"] = "current_hybrid"
    remaining = [s for s in sentences if s not in certified]
    if not remaining:
        if meta is not None:
            meta["agent_qwen_skipped"] = True
            meta["backend"] = "hybrid:certified_rules"
        return q_rules, c_rules
    uncertain_text = " ".join(remaining)
    uncertain_q = [q for q in q_rules if q["text"] not in certified]
    uncertain_c = [c for c in c_rules if c["text"] not in certified]
    jev_questions = settings.extractor_jev_hybrid or settings.agent_question_backend == "jev_slots_experimental"
    if settings.extractor_jev_hybrid and settings.agent_claim_backend == "current":
        from harness.jev_hybrid import claims as jev_claims
        qwen_sentences = []
        jev_label_meta = meta if meta is not None else {}
        jev_grounded_claims = []
        for s in remaining:
            sentence_claims = [c for c in uncertain_c if c["text"] == s]
            selected_claims = jev_claims(s, sentence_claims, jev_label_meta)
            jev_labels = jev_label_meta.get("jev_claim_labels", [])
            found_labels = jev_labels[-1] if jev_labels else []
            if selected_claims is None and (llm_extract.CLAIM_HINT_RX.search(fold(s))
                                             or found_labels or jev_label_meta.get("jev_label_error")):
                qwen_sentences.append(s)
            elif selected_claims is not None:
                jev_grounded_claims.extend(selected_claims)
        uncertain_c = jev_grounded_claims + [c for c in uncertain_c if c["text"] in qwen_sentences]
        if meta is not None:
            meta["claim_route"] = "jev_then_qwen_if_unresolved"
    else:
        qwen_sentences = ([s for s in remaining if llm_extract.CLAIM_HINT_RX.search(fold(s))]
                          if jev_questions else remaining)
    if settings.agent_claim_backend == "rules":
        questions, claims = uncertain_q, uncertain_c
        if meta is not None:
            meta["agent_qwen_skipped"] = True
    elif settings.agent_claim_backend == "current" and qwen_sentences:
        qwen_text = " ".join(qwen_sentences)
        qwen_q = [q for q in uncertain_q if q["text"] in qwen_sentences]
        qwen_c = [c for c in uncertain_c if c["text"] in qwen_sentences]
        questions, claims = llm_extract.agent(qwen_text, known_values, qwen_q, qwen_c,
                                               "hybrid", meta, focus_sku=focus_sku)
        known_claims = {(c["field"], str(c["value"]), c["text"]) for c in claims}
        claims += [c for c in uncertain_c if (c["field"], str(c["value"]), c["text"]) not in known_claims]
    elif settings.agent_claim_backend == "current":
        questions, claims = uncertain_q, uncertain_c
        if meta is not None:
            meta["agent_qwen_skipped"] = True
    else:
        raise ValueError(f"Unknown AGENT_CLAIM_BACKEND: {settings.agent_claim_backend}")
    if jev_questions:
        from harness.question_classifiers.jev_slots import classify_agent_questions

        jev_meta = meta if meta is not None else {}
        questions = classify_agent_questions(uncertain_text, known_values, jev_meta)
        if jev_meta.get("jev_slot_errors") and settings.agent_claim_backend == "current":
            fallback_q, fallback_c = llm_extract.agent(uncertain_text, known_values, uncertain_q, uncertain_c,
                                                        "hybrid", jev_meta, focus_sku=focus_sku)
            questions = fallback_q
            known_claims = {(c["field"], str(c["value"]), c["text"]) for c in claims}
            claims += [c for c in fallback_c if (c["field"], str(c["value"]), c["text"]) not in known_claims]
    by_text = {q["text"]: q for q in questions}
    by_text.update({q["text"]: q for q in q_rules if q["text"] in certified})
    return [by_text[s] for s in sentences if s in by_text], claims


def customer_slots_start(text, today, meta=None, context=None, asked=None):
    if settings.extractor_backend != "hybrid" or not settings.extractor_async:
        return customer_slots(text, today, meta, context), None
    from harness import llm_extract
    rules = customer_slots_rules(text, today)
    if settings.extractor_confidence_gate:
        from harness.rule_confidence import customer as certify_customer, empty as certify_empty

        cert = certify_customer(text, rules, context, asked)
        if meta is not None:
            meta["customer_confidence"] = cert
        if cert["certified"]:
            if meta is not None:
                meta["customer_qwen_skipped"] = True
                meta["backend"] = "hybrid:certified_rules"
            return dict(rules), None
        empty = certify_empty(text, rules, context)
        if meta is not None:
            meta["customer_empty_confidence"] = empty
        if empty["certified"]:
            if meta is not None:
                meta["customer_qwen_skipped"] = True
                meta["backend"] = "hybrid:certified_empty"
            return {}, None
    if settings.extractor_jev_hybrid:
        from harness.jev_hybrid import customer as jev_customer
        jev_slots = jev_customer(text, rules, meta, context)
        if jev_slots is not None:
            if meta is not None:
                meta["customer_qwen_skipped"] = True
                meta["backend"] = "hybrid:jev_grounded_rules"
            return _lock(dict(jev_slots), rules, meta), None
    if not customer_llm_candidate(text, context):
        if meta is not None:
            meta["customer_llm_skipped"] = "no_slot_cue"
        return dict(rules), None
    pending = llm_extract.submit_customer_slots(text, today, rules, meta, context)
    locked = ((meta or {}).get("customer_confidence") or {}).get("certified_slots") or []
    if locked and isinstance(pending, dict):
        pending["cert_locked"] = {k: rules[k] for k in locked if k in rules}
    return dict(rules), pending


def customer_slots_finish(pending, slots, wait):
    from harness import llm_extract
    out = llm_extract.collect_customer_slots(pending, slots, wait)
    locked = (pending or {}).get("cert_locked") if isinstance(pending, dict) else None
    if locked and isinstance(slots, dict):
        slots.update(locked)                 # CERT v2 (3.5): giữ giá trị luật của slot đã chứng nhận
    for d in (slots, out):                   # 1c (06/11): chốt cuối cho mọi nhánh (luật / Qwen / Jev): "địa chỉ" chỉ là SĐT → bỏ
        if isinstance(d, dict) and phone_only_address(d.get("address")):
            d.pop("address")
    return out


def customer_slots_rules(text, today, lexicon_hits=None):
    from harness import lexicon
    text = lexicon.normalize(text)            # viết tắt / teencode đã duyệt (A-L); không có entry approved → giữ nguyên
    t, f = text.lower(), fold(text)
    out = {}
    m = re.search(r"(\d{1,3})\s*(?:m2|m²|mét vuông|mét|m\b)", t)
    if m: out["room_area_m2"] = int(m.group(1))
    if KIDS_RX.search(f) and not re.search(r"khong co (be|con)", f):
        out["has_children"] = True
    for s, e, v in find_money(text):
        ctx = fold(text[max(0, s - 80):e + 15])
        if re.search(r"ben (kia|khac)|shopee|lazada|cho khac|tiki|san thuong mai dien tu|tren san", ctx):
            out["competitor_price_vnd"] = v
        elif re.search(r"(bao|noi|bao gia|thay|giam xong|con)\b", ctx) and not re.search(r"ngan sach", ctx):
            out.setdefault("claimed_prices", []).append(v)
        elif re.search(r"ngan sach|tam|khoang|toi da|duoi|co (tam|khoang)", ctx): out["budget_vnd"] = v
    m = re.search(r"(?:size|cỡ|số)\s*(\d{2}|xs|s|m|l|xl|xxl)\b", t)
    if m: out["size"] = m.group(1).upper()
    from harness.tools import find_color
    color = find_color(text, prefix="mau ")
    if color: out["color"] = color
    m = ADDRESS_RX.search(text)
    if m and not re.search(r"địa chỉ cũ|như cũ", t) and not phone_only_address(m.group(1)):
        out["address"] = m.group(1).strip(" ,")
    if re.search(r"\bcod\b|thanh toan khi nhan|tien mat|nhan hang (roi )?tra", f): out["payment"] = "COD"
    elif re.search(r"chuyen khoan|ck truoc|qua ngan hang|momo|zalopay", f): out["payment"] = "bank"
    for rx, label in BLOCKERS:
        if re.search(rx, f):
            out["blocker"] = label; break
    w = parse_relative_datetime(text, today)
    # D32: KHÁCH tự gọi lại ("mai anh sẽ gọi lại em", "mai anh gọi lại được không") không phải hẹn shop gọi (định nghĩa D10)
    if w and (re.search(r"goi lai|lien lac|bao lai|goi cho", f) or lexicon.trigger("callback_requested", f)) \
            and not CUSTOMER_CALLS_RX.search(f):
        out["callback_requested"] = f"{w[0]}T{w[1] or '09:00'}"
    m = re.search(r"(?:chị|anh|cô|chú|em|tôi|mình) (?:là|tên là|tên) ([A-ZĐ][a-zà-ỹ]+)", text) \
        or re.search(r"\b(?:chị|anh|cô|chú|bác|em) ([A-ZĐ][a-zà-ỹ]+) (?:đây|nè|này)\b", text)
    if m: out["self_name"] = m.group(1)
    m = re.search(r"\b(?:nha|gia dinh|nha (?:chi|anh|em|minh|co|chu))\b[^.?!]{0,20}?\b(\d{1,2}) (?:nguoi|thanh vien)\b", f)
    if m: out["household_size"] = int(m.group(1))
    m = re.search(r"\b(?:be|con|chau)\b[^.?!]{0,20}?\b(\d{1,2}) (thang|tuoi)\b", f)
    if m: out["baby_age"] = f"{int(m.group(1))} {'tháng' if m.group(2) == 'thang' else 'tuổi'}"
    if re.search(r"\b(dat (hon|qua|the|vay)|mac (hon|qua)|chenh (the|qua|vay|hon)|gia cao|chat qua|re hon)\b", f):
        out["objection"] = "dat_qua"
    elif re.search(r"\b(bot (cho|di|gia|chut)|giam (them|gia) (cho|di|duoc)|giam duoc (khong|khong a)|ep gia|gia thap nhat)\b", f):
        out["objection"] = "ep_gia"
    m = re.search(r"\b(dang dung|dang xai|da co|co san|nha co)\b([^.?!]{0,40})", f)
    if m:
        from harness.tools import find_products
        owned = find_products(text[m.start():m.end() + 10])
        if owned: out["owned_product"] = owned[0]
    if settings.extractor_cert_version >= 2:
        # D18: khách phủ định thì không phải lựa chọn ("chị không lấy màu đen", "COD không được à") — bỏ ngay ở luật
        from harness.rule_confidence import _anchor, negated
        for k in ("color", "size", "payment"):
            if k in out and negated(text, _anchor(text, k, out[k])):
                out.pop(k)
    return lexicon.apply(text, out, hits=lexicon_hits)   # value / negative đã duyệt trong harness/lexicon/slots.json


SLOT_KW = [
    ("room_area_m2", r"(m2|m²|met vuong|dien tich|phong .*(rong|bao nhieu))"),
    ("budget_vnd", r"(ngan sach|tam gia|du dinh chi|muc gia)"),
    ("baby_age", r"\b(be|con|chau)\b.*\b(may|bao nhieu) (thang|tuoi)|\b(be|chau) (duoc|nay) may\b"),
    ("household_size", r"\b(may|bao nhieu) (nguoi|thanh vien)\b"),
    ("owned_product", r"\b(dang dung|dang xai|da co) (may|loai|san pham|mau|cai)? ?(gi|nao)\b"),
    ("has_children", KIDS_RX.pattern),
    ("size", r"(size|co chan|co ao|mang so)"),
    ("color", r"\bmau (gi|nao|den|trang|xam|navy|be|do)|chon mau"),
    ("address", r"(dia chi|giao (ve|toi) dau|o dau a)"),
    ("payment", r"(thanh toan|cod|chuyen khoan)"),
    ("customer_name", r"(ten (gi|la gi)|xung ho|goi .* the nao)"),
    ("phone", r"(so dien thoai|sdt)"),
    ("blocker", r"(ban khoan|bang khoan|trao doi|anh nha|chi nha|ong xa|ba xa|nguoi nha|da hoi|y kien)"),
    ("callback_time", r"(goi lai .*(luc|khi) nao|may gio|gio nao|hen .* (luc|ngay))"),
    ("product_advised", r"(san pham nao|mau nao|quan tam (den )?(gi|san pham)|tim (mau|san pham)|loai nao)"),
    ("order_id", r"ma don"),
    ("confirm_order", r"(len don|chot don|dat hang)"),
]
REQUEST_RX = re.compile(r"\b(cho em xin|xin (anh|chi|co|chu|minh|ban) (cho em )?(biet|ten|so|dia chi)|(anh|chi|co|chu|minh|ban) cho em biet"
                        r"|(anh|chi|co|chu|minh|ban) (doc|nhan|gui) (giup|cho) em)\b"
                        r"|\b(anh|chi|co|chu|minh|ban|quy khach) (co the )?(len|gui|doc|nhan) (dia chi|so dien thoai)\b"
                        r"|\b(anh|chi|co|chu|minh|ban|quy khach) (goi lai|hen)\b[^.!?]*\b(khi nao|luc nao|may gio|gio nao)\b")
QUESTION_CUE_RX = re.compile(r"\b(khi nao|luc nao|may gio|gio nao|o dau|bao nhieu|loai nao|mau nao|size nao|mau gi|"
                             r"co phai|dung khong|phai khong|con .{0,24} ban khoan gi khong)\b")
CONFIRM_RX = re.compile(r"(dung khong|phai khong|dung a|van (lay|giu|la|o|dung)|\bnhi\b|chu a\b|nhu cu|hay (la )?(van|doi)|xac nhan|co phai)")


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


_question_classifier = None
_question_classifier_backend = None


def question_prob(s):
    global _question_classifier, _question_classifier_backend
    backend = settings.question_classifier_backend
    if _question_classifier is None or _question_classifier_backend != backend:
        _question_classifier = False
        _question_classifier_backend = backend
        try:
            from harness.question_classifiers import get_classifier
            _question_classifier = get_classifier(backend)
        except Exception as e:
            log.warning("không khởi tạo được question classifier %s (%s) → chỉ dùng luật", backend, type(e).__name__)
    if not _question_classifier:
        return None
    try:
        pred = _question_classifier.predict(s)
        if pred.error:
            log.warning("question classifier %s lỗi (%s) → chỉ dùng luật", backend, pred.error)
            return None
        log.debug("question classifier %s %.1fms p=%.3f tau=%.3f", backend, pred.latency_ms,
                  pred.probability, pred.threshold)
        return pred.probability, pred.threshold
    except Exception as e:
        log.warning("question classifier %s lỗi (%s) → chỉ dùng luật", backend, type(e).__name__)
        log.debug("question classifier traceback", exc_info=True)
        return None


def agent_questions(text, known_values, use_classifier=False):
    out = []
    for s in _sentences(text):
        f = fold(s)
        if not s.endswith("?") and not REQUEST_RX.search(f) and not QUESTION_CUE_RX.search(f):
            pt = question_prob(s) if use_classifier else None
            if not pt or pt[0] < pt[1]:
                continue
        slot = next((name for name, rx in SLOT_KW if re.search(rx, f)), None)
        if slot is None:
            from harness.tools import find_products
            slot = "product_advised" if find_products(s) else "other"
        qtype = "confirm" if mentions_known(s, slot, known_values) or CONFIRM_RX.search(f) else "open"
        out.append({"slot": slot, "type": qtype, "text": s})
    return out


def mentions_known(s, slot, known_values):
    has_known = slot in known_values and str(known_values[slot]).lower() in s.lower()
    if slot == "product_advised" and known_values.get(slot):
        from harness.tools import find_products, mt
        par = mt._parent(known_values[slot])[0]
        has_known = has_known or bool(par and par["sku"] in find_products(s))
    return has_known


NON_PRICE_RX = re.compile(r"(ngan sach|giam|\btru\b|tiet kiem|phi|ship|phu thu|chenh lech|hoan|ben kia|ben khac|tren|duoi|toi da|han muc)")


def money_not_price(s, st):
    ctx = fold(s[max(0, st - 40):st])
    if re.search(r"(khong phai|chu khong|khong con)( la| o)?( gia| muc)?\s*$", ctx):
        return True
    if re.search(r"(?<!gia )(?<!dang )(khuyen mai|uu dai|tro gia|voucher|thu cu doi moi|tang|tri gia)( (len|toi|den))?( la)?\s*$", ctx):
        return True
    return not re.search(r"\bcon\s*$", ctx) and bool(NON_PRICE_RX.search(ctx[-25:]))


def agent_claims(text, quote=None, focus_sku=None):
    claims = []
    for s in _sentences(text):
        n0 = len(claims)
        _sentence_claims(s, claims, focus_sku)
        sku = claim_sku(s, focus_sku) if len(claims) > n0 else None
        for c in claims[n0:] if sku else ():
            c["sku"] = sku
    return claims


def _sentence_claims(s, claims, focus_sku):
    f = fold(s)
    monies = find_money(s)
    for i, (st, en, v) in enumerate(monies):
        ctx = fold(s[max(0, st - 40, monies[i - 1][1] if i else 0):st])
        after = fold(s[en:en + 20])
        if money_not_price(s, st):
            continue
        final = bool(re.search(r"\bcon\s*$", ctx))
        if re.search(r"(gia|con|chi|tong|thanh tien|la|ban|niem yet)", ctx) or re.search(r"^\s*(a|thoi|nhe)", after):
            then_final = any(re.search(r"(giam|uu dai|ap ma|khuyen mai|tru|thu cu).*\bcon\s*$", fold(s[en:st2])) for st2, _, _ in monies[i + 1:])
            field = "list_price_vnd" if not final and (then_final or re.search(r"niem yet|gia goc", ctx)) else "price_vnd"
            if re.search(r"(hom truoc|lan truoc|hom \d|truoc day|da bao (muc )?gia|gia da bao la|da tu van|co tu van)", f) \
                    or re.search(r"^\W*d?\W*(la|chinh la)\s+(muc\s+)?gia\s+(khi|luc|cu|truoc|hom)", fold(s[en:en + 45])):
                field = "price_quoted_vnd"
            claims.append({"field": field, "value": v, "text": s})
    if re.search(r"\b(het han|da ket thuc|khong con ap dung|het chuong trinh|het khuyen mai)\b", f):
        claims.append({"field": "promo_active", "value": False, "text": s})
    elif re.search(r"(chua co|khong co|chua ap dung|khong ap dung) (them )?(chuong trinh|khuyen mai|uu dai)", f) and not re.search(r"\bngoai\b", f):
        claims.append({"field": "promo_active", "value": False, "text": s})
    elif re.search(r"uu dai mien phi (giao|van chuyen|ship)", f) and not re.search(r"(khuyen mai|giam|tang kem|duoc tang)", f):
        pass
    elif re.search(r"(dang co|van con|dang ap dung|duoc tang|co khuyen mai|uu dai|tang kem|giam con|dung ma|ap ma|bao gom)", f) and re.search(r"(khuyen mai|uu dai|tang|giam)", f) \
            and not re.search(r"\b(chua|khong|chang)\b(\s+\w+){0,4}\s+(khuyen mai|uu dai|qua tang|tang|giam)", f):
        claims.append({"field": "promo_active", "value": True, "text": s})
    if re.search(r"(tam het|het hang|het mat|chua co hang|(khong|chua) con hang)", f):
        claims.append({"field": "in_stock", "value": False, "text": s})
    elif re.search(r"(con hang|co san|san hang)", f):
        claims.append({"field": "in_stock", "value": True, "text": s})
    m = re.search(r"giao[^.?!]*?(\d+)(?:\s*(?:-|den|toi)\s*(\d+))?\s*ngay", f)
    if m:
        claims.append({"field": "delivery_days", "value": int(m.group(2) or m.group(1)), "text": s})
    m = re.search(r"bao hanh[^.?!]*?(\d+)\s*(thang|nam)", f)
    if m and not re.search(r"\bmo rong\b", f) and _about_focus(s, focus_sku):
        claims.append({"field": "warranty_months", "value": int(m.group(1)) * (12 if m.group(2) == "nam" else 1), "text": s})
    m = re.search(r"doi tra[^.?!]*?(\d+)\s*ngay|trong (?:vong )?(\d+) ngay", f)
    if m and re.search(r"doi|tra", f) and not re.search(r"(loi|doi moi|bao hanh)", f) and _about_focus(s, focus_sku):
        claims.append({"field": "return_days", "value": int(m.group(1) or m.group(2)), "text": s})
    if HUMAN_CLAIM_RX.search(f):
        claims.append({"field": "is_human", "value": True, "text": s})
    elif AI_CLAIM_RX.search(f):
        claims.append({"field": "is_human", "value": False, "text": s})


OTHER_PRODUCT_RX = re.compile(r"\b(san pham|mat hang|nganh hang|loai|hang) khac\b")


def claim_sku(sentence, focus_sku):
    from harness.tools import find_products, mt
    named = find_products(sentence)
    if named:
        par = mt._parent(focus_sku)[0] if focus_sku else None
        return focus_sku if par and par["sku"] in named else named[0]
    if OTHER_PRODUCT_RX.search(fold(sentence)) or re.search(r"\bmẫu khác\b", sentence.lower()):
        return None
    return focus_sku


def _about_focus(sentence, focus_sku):
    return not focus_sku or claim_sku(sentence, focus_sku) == focus_sku


HUMAN_CLAIM_RX = re.compile(r"\b(em|minh|toi) (la|cung la|dung la) (nguoi that|nhan vien that|con nguoi|nguoi (chu|khong phai))\b")
AI_CLAIM_RX = re.compile(r"\b(em|minh|toi) (la|chi la) (tro ly (ao|ai)|ai|tri tue nhan tao|robot|chatbot|tong dai tu dong|may)\b"
                         r"|\bkhong phai (la )?nguoi that\b")


def facts_used(text, tool_args_list, carried):
    used, low = [], text.lower()
    f = fold(text)
    arg_values, arg_numbers = set(), set()

    def collect_values(value):
        if isinstance(value, dict):
            for child in value.values():
                collect_values(child)
        elif isinstance(value, (list, tuple, set)):
            for child in value:
                collect_values(child)
        else:
            arg_values.add(str(value).lower())
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                arg_numbers.add(value)

    for args in tool_args_list:
        collect_values(args)

    def has_phrase(phrase):
        phrase = fold(str(phrase)).strip()
        return bool(phrase and re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", f))

    for slot, val in carried.items():
        if val in (None, "", [], {}):
            continue
        hit = False
        if isinstance(val, bool):
            hit = slot == "has_children" and bool(re.search(r"\b(be|tre nho|con nho|em be)\b", f))
        elif slot == "household_size":
            hit = bool(re.search(rf"\b{int(val)} (nguoi|thanh vien)\b", f))
        elif slot == "baby_age":
            hit = fold(str(val)) in f
        elif slot == "objection":
            hit = bool(re.search(r"(khuyen mai|uu dai|tang kem|qua tang|chinh hang|gia tot nhat|giam them)", f))
        elif slot == "owned_product":
            from harness.tools import find_products, mt
            hit = (mt._parent(val)[0] or {}).get("sku") in find_products(text) or str(val).lower() in arg_values
        elif isinstance(val, int):
            hit = any(v == val for _, _, v in find_money(text)) or bool(re.search(rf"\b{val}\s*(m2|m²|mét|m\b)", low)) or val in arg_numbers
        else:
            sval = str(val).lower()
            if slot == "blocker":
                hit = bool(re.search(r"(anh nha|chi nha|ong xa|ba xa|nguoi nha|trao doi|hoi y kien|so sanh|can nhac)", f))
            elif slot == "product_advised":
                from harness.tools import product_name
                words = fold(product_name(val)).split()
                hit = sval in arg_values or (len(words) >= 2 and has_phrase(" ".join(words[-2:])))
            else:
                hit = has_phrase(sval) or sval in arg_values
        if hit:
            used.append(slot)
    return used
