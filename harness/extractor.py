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
import re

from core.config import settings
from harness.textnorm import find_money, fold, parse_relative_datetime

KIDS_RX = re.compile(r"(?<!mau )\b(be|con nho|em be|tre nho|tre con|chau nho)\b")

BLOCKERS = [(r"(hoi|ban voi) (chong|ong xa|anh nha|bo no)", "can hoi chong"), (r"(hoi|ban voi) (vo|ba xa|chi nha|me no)", "can hoi vo"),
            (r"hoi (con|nguoi nha|gia dinh|bo me|me)", "can hoi nguoi nha"), (r"(so sanh|so gia|tham khao) (gia|them)", "so sanh gia"),
            (r"(can nhac|suy nghi|xem them|tim hieu them)", "can nhac")]
ADDRESS_RX = re.compile(r"(?:giao (?:về|tới|đến|cho \w+ (?:về|tới|ở))|địa chỉ(?: mới| giao)?(?: là|:)?|(?:giờ|hiện|nhà) (?:chị|anh|em|cô|chú)? ?ở|chuyển (?:nhà|về) (?:ra|vào|về|tới)?)\s+"
                        r"((?:số |ngõ |hẻm |\d)[^.!?]*?)(?=\s+(?:nhé|nha|nhá|ạ|em|giúp|luôn|trong tuần|thanh toán|thì|mất|bao lâu|khi nào|được không|đúng không|hả|vậy)\b|[.!?]|$)", re.I)


def customer_slots(text, today, meta=None, context=None):
    rules = customer_slots_rules(text, today)
    if settings.extractor_backend == "rules":
        return rules
    from harness import llm_extract
    return llm_extract.customer_slots(text, today, rules, settings.extractor_backend, meta, context)


def analyze_agent(text, known_values, meta=None, focus_sku=None):
    q_rules, c_rules = agent_questions(text, known_values), agent_claims(text, focus_sku=focus_sku)
    if settings.extractor_backend == "rules":
        return q_rules, c_rules
    from harness import llm_extract
    return llm_extract.agent(text, known_values, q_rules, c_rules, settings.extractor_backend, meta, focus_sku=focus_sku)


def customer_slots_start(text, today, meta=None, context=None):
    if settings.extractor_backend != "hybrid" or not settings.extractor_async:
        return customer_slots(text, today, meta, context), None
    from harness import llm_extract
    rules = customer_slots_rules(text, today)
    return dict(rules), llm_extract.submit_customer_slots(text, today, rules, meta, context)


def customer_slots_finish(pending, slots, wait):
    from harness import llm_extract
    return llm_extract.collect_customer_slots(pending, slots, wait)


def customer_slots_rules(text, today):
    t, f = text.lower(), fold(text)
    out = {}
    m = re.search(r"(\d{1,3})\s*(?:m2|m²|mét vuông|mét|m\b)", t)
    if m: out["room_area_m2"] = int(m.group(1))
    if KIDS_RX.search(f) and not re.search(r"khong co (be|con)", f):
        out["has_children"] = True
    for s, e, v in find_money(text):
        ctx = fold(text[max(0, s - 30):e + 15])
        if re.search(r"ben (kia|khac)|shopee|lazada|cho khac|tiki", ctx): out["competitor_price_vnd"] = v
        elif re.search(r"(bao|noi|bao gia|thay|giam xong|con)\b", ctx) and not re.search(r"ngan sach", ctx):
            out.setdefault("claimed_prices", []).append(v)
        elif re.search(r"ngan sach|tam|khoang|toi da|duoi|co (tam|khoang)", ctx): out["budget_vnd"] = v
    m = re.search(r"(?:size|cỡ|số)\s*(\d{2}|xs|s|m|l|xl|xxl)\b", t)
    if m: out["size"] = m.group(1).upper()
    from harness.tools import find_color
    color = find_color(text, prefix="mau ")
    if color: out["color"] = color
    m = ADDRESS_RX.search(text)
    if m and not re.search(r"địa chỉ cũ|như cũ", t):
        out["address"] = m.group(1).strip(" ,")
    if re.search(r"\bcod\b|thanh toan khi nhan|tien mat|nhan hang (roi )?tra", f): out["payment"] = "COD"
    elif re.search(r"chuyen khoan|ck truoc|qua ngan hang|momo|zalopay", f): out["payment"] = "bank"
    for rx, label in BLOCKERS:
        if re.search(rx, f):
            out["blocker"] = label; break
    w = parse_relative_datetime(text, today)
    if w and re.search(r"goi lai|lien lac|bao lai|goi cho", f):
        out["callback_requested"] = f"{w[0]}T{w[1] or '09:00'}"
    m = re.search(r"(?:chị|anh|cô|chú|em|tôi|mình) (?:là|tên là|tên) ([A-ZĐ][a-zà-ỹ]+)", text) \
        or re.search(r"\b(?:chị|anh|cô|chú|bác|em) ([A-ZĐ][a-zà-ỹ]+) (?:đây|nè|này)\b", text)
    if m: out["self_name"] = m.group(1)
    m = re.search(r"\b(?:nha|gia dinh|nha (?:chi|anh|em|minh|co|chu))\b[^.?!]{0,20}?\b(\d{1,2}) (?:nguoi|thanh vien)\b", f)
    if m: out["household_size"] = int(m.group(1))
    m = re.search(r"\b(?:be|con|chau)\b[^.?!]{0,20}?\b(\d{1,2}) (thang|tuoi)\b", f)
    if m: out["baby_age"] = f"{int(m.group(1))} {'tháng' if m.group(2) == 'thang' else 'tuổi'}"
    if re.search(r"\b(dat (hon|qua|the|vay)|mac (hon|qua)|chenh (the|qua|vay|hon)|gia cao|chat qua)\b", f):
        out["objection"] = "dat_qua"
    elif re.search(r"\b(bot (cho|di|gia|chut)|giam (them|gia) (cho|di|duoc)|ep gia|gia thap nhat)\b", f):
        out["objection"] = "ep_gia"
    m = re.search(r"\b(dang dung|dang xai|da co|co san|nha co)\b([^.?!]{0,40})", f)
    if m:
        from harness.tools import find_products
        owned = find_products(text[m.start():m.end() + 10])
        if owned: out["owned_product"] = owned[0]
    return out


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
    ("blocker", r"(bang khoan|trao doi|anh nha|chi nha|ong xa|ba xa|nguoi nha|da hoi|y kien)"),
    ("callback_time", r"(goi lai .*(luc|khi) nao|may gio|gio nao|hen .* (luc|ngay))"),
    ("product_advised", r"(san pham nao|mau nao|quan tam (den )?(gi|san pham)|tim (mau|san pham)|loai nao)"),
    ("order_id", r"ma don"),
    ("confirm_order", r"(len don|chot don|dat hang)"),
]
REQUEST_RX = re.compile(r"\b(cho em xin|xin (anh|chi|co|chu|minh|ban) (cho em )?(biet|ten|so|dia chi)|(anh|chi|co|chu|minh|ban) cho em biet"
                        r"|(anh|chi|co|chu|minh|ban) (doc|nhan|gui) (giup|cho) em)\b")
CONFIRM_RX = re.compile(r"(dung khong|phai khong|dung a|van (lay|giu|la|o|dung)|\bnhi\b|chu a\b|nhu cu|hay (la )?(van|doi)|xac nhan|co phai)")


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def agent_questions(text, known_values):
    out = []
    for s in _sentences(text):
        f = fold(s)
        if not s.endswith("?") and not REQUEST_RX.search(f):
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
                if re.search(r"(hom truoc|lan truoc|hom \d|truoc day|da bao|da tu van|co tu van)", f) \
                        or re.search(r"^\W*d?\W*(la|chinh la)\s+(muc\s+)?gia\s+(khi|luc|cu|truoc|hom)", fold(s[en:en + 45])):
                    field = "price_quoted_vnd"
                claims.append({"field": field, "value": v, "text": s})
        if re.search(r"(het han|da ket thuc|khong con ap dung|het chuong trinh|het khuyen mai)", f):
            claims.append({"field": "promo_active", "value": False, "text": s})
        elif re.search(r"(chua co|khong co|chua ap dung|khong ap dung) (them )?(chuong trinh|khuyen mai|uu dai)", f) and not re.search(r"\bngoai\b", f):
            claims.append({"field": "promo_active", "value": False, "text": s})
        elif re.search(r"uu dai mien phi (giao|van chuyen|ship)", f) and not re.search(r"(khuyen mai|giam|tang kem|duoc tang)", f):
            pass
        elif re.search(r"(dang co|van con|dang ap dung|duoc tang|co khuyen mai|uu dai|tang kem|giam con)", f) and re.search(r"(khuyen mai|uu dai|tang|giam)", f) \
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
        if m and re.search(r"doi|tra", f) and not re.search(r"(loi|doi moi|bao hanh)", f):
            claims.append({"field": "return_days", "value": int(m.group(1) or m.group(2)), "text": s})
        if HUMAN_CLAIM_RX.search(f):
            claims.append({"field": "is_human", "value": True, "text": s})
        elif AI_CLAIM_RX.search(f):
            claims.append({"field": "is_human", "value": False, "text": s})
    return claims


def _about_focus(sentence, focus_sku):
    if not focus_sku:
        return True
    if re.search(r"\b(san pham|mat hang|nganh hang|loai|mau|hang) khac\b", fold(sentence)):
        return False
    from harness.tools import find_products, mt
    named = find_products(sentence)
    par = mt._parent(focus_sku)[0]
    return not named or bool(par and par["sku"] in named)


HUMAN_CLAIM_RX = re.compile(r"\b(em|minh|toi) (la|cung la|dung la) (nguoi that|nhan vien that|con nguoi|nguoi (chu|khong phai))\b")
AI_CLAIM_RX = re.compile(r"\b(em|minh|toi) (la|chi la) (tro ly (ao|ai)|ai|tri tue nhan tao|robot|chatbot|tong dai tu dong|may)\b"
                         r"|\bkhong phai (la )?nguoi that\b")


def facts_used(text, tool_args_list, carried):
    used, low = [], text.lower()
    f = fold(text)
    args_blob = " ".join(str(v).lower() for a in tool_args_list for v in a.values())
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
            hit = (mt._parent(val)[0] or {}).get("sku") in find_products(text) or str(val).lower() in args_blob
        elif isinstance(val, int):
            hit = any(v == val for _, _, v in find_money(text)) or bool(re.search(rf"\b{val}\s*(m2|m²|mét|m\b)", low)) or str(val) in args_blob
        else:
            sval = str(val).lower()
            if slot == "blocker":
                hit = bool(re.search(r"(anh nha|chi nha|ong xa|ba xa|nguoi nha|trao doi|hoi y kien|so sanh|can nhac)", f))
            elif slot == "product_advised":
                from harness.tools import product_name
                hit = sval in args_blob or fold(product_name(val)).split()[-1] in f.split() and fold(product_name(val)).split()[-2] in f
            else:
                hit = sval in low or sval in args_blob or fold(sval) in f
        if hit:
            used.append(slot)
    return used
