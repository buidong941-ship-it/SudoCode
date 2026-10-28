"""Bộ trích bằng LLM (EXTRACTOR_BACKEND=llm|hybrid): LLM PHÂN LOẠI, code ĐỌC GIÁ TRỊ và KIỂM TRA.

Chia việc:
- LLM (Qwen local qua vLLM, hoặc DeepSeek) nhận định nghĩa slot/field cố định trong file này và trả JSON đúng schema
  (vLLM ép schema: không thể trả slot ngoài danh sách). Mỗi kết quả kèm `span` = đoạn chữ nguyên văn trong câu.
- Code: (1) bỏ kết quả có `span` không nằm trong câu (LLM bịa); (2) đọc giá trị từ `span` bằng đúng hàm của bộ luật
  (find_money cho tiền, parse_relative_datetime cho ngày giờ, find_color cho màu…), nên số tiền luôn khớp tuyệt đối;
  (3) câu hỏi nhắc giá trị đã biết thì là câu xác nhận (như luật).
- Nhiệt độ 0 + cache theo mã băm request (core/llm/cache.py): chạy lại ra y hệt, đối chiếu tay được với đúng đầu ra đã chấm.
- LLM lỗi / quá EXTRACTOR_TIMEOUT_S → dùng kết quả của luật, ghi lý do vào `meta["fallback"]` (trace: `extractor`).

Gộp theo chế độ:
- `llm`   : chỉ dùng kết quả LLM (đã kiểm).
- `hybrid`: slot khách = luật, LLM bổ sung slot luật không bắt được (luật thắng khi cùng slot);
            câu hỏi = LLM phân loại từng câu, câu nào LLM không trả thì giữ của luật; LLM được thêm câu hỏi không có dấu "?";
            claims = hợp của luật và LLM, khử trùng theo (field, value, câu) — không bỏ claim nào luật đã bắt.
Dùng DeepSeek (API ngoài) thì SĐT/địa chỉ được che trước khi gửi và ghép lại trong `span` sau khi nhận.
"""
import json
import re
import time

from core import log as cclog
from core.config import settings
from harness.textnorm import find_money, fold, parse_relative_datetime

log = cclog.get("extract")

CUSTOMER_SLOTS = {
    "room_area_m2": "diện tích phòng khách nói (m², mét vuông)",
    "has_children": "khách khẳng định nhà có trẻ nhỏ / em bé (label=co) hoặc không có (label=khong)",
    "budget_vnd": "số tiền khách định chi / ngân sách của khách. KHÔNG phải khi khách nhắc giá shop báo hay giá nơi khác",
    "competitor_price_vnd": "giá khách nói thấy ở cửa hàng, sàn, trang khác (Shopee, Lazada, bên kia…). KHÔNG phải khi không nêu "
                            "nơi bán khác, và không phải giá trên fanpage / Zalo của chính shop",
    "claimed_price_vnd": "giá khách nói shop ĐÃ báo trước đó hoặc giá khách nhớ từ lần trước (không phải ngân sách, không phải giá nơi khác)",
    "size": "size / cỡ / số giày, áo khách chọn",
    "color": "màu khách chọn",
    "address": "địa chỉ giao hàng khách đọc (span = nguyên địa chỉ, không kèm 'giao về'). KHÔNG phải khi khách chỉ nhắc nơi ở chung chung ('nhà ở Huế')",
    "payment": "cách thanh toán khách chọn (label=COD: tiền mặt khi nhận; label=bank: chuyển khoản, momo, zalopay)",
    "blocker": "rào cản khiến khách chưa quyết (label: can hoi chong | can hoi vo | can hoi nguoi nha | so sanh gia | can nhac). "
               "'can hoi …' chỉ khi khách nhắc rõ người nhà. KHÔNG phải khi khách đã chốt mua, chỉ hỏi thông tin, hoặc từ chối dứt khoát",
    "callback_requested": "thời điểm khách hẹn shop gọi lại / liên lạc lại (span = cụm chỉ thời gian)",
    "self_name": "tên khách tự xưng (span = cụm chứa tên, vd 'chị Dung đây')",
    "household_size": "số người trong nhà / số người dùng khách nói (span = cụm có con số, vd 'nhà chị 3 người')",
    "baby_age": "tuổi của bé khách nói (span = cụm có số tháng/tuổi, vd 'bé nhà chị 6 tháng')",
    "objection": "phản đối về giá (label: dat_qua = chê đắt / thấy chênh so với bên khác; ep_gia = đòi bớt, ép giá). "
                 "KHÔNG phải khi khách chỉ hỏi giá, hỏi có khuyến mãi không, hỏi tiền hoàn / tiền chênh khi đổi hàng",
    "owned_product": "sản phẩm khách nói đang dùng / đã có (span = tên sản phẩm). KHÔNG phải sản phẩm khách đang xem / hỏi mua",
}
LABELS = ["co", "khong", "COD", "bank", "can hoi chong", "can hoi vo", "can hoi nguoi nha", "so sanh gia", "can nhac",
          "dat_qua", "ep_gia"]

QUESTION_SLOTS = {
    "room_area_m2": "diện tích phòng", "budget_vnd": "ngân sách", "has_children": "nhà có trẻ nhỏ không", "size": "size / cỡ",
    "color": "màu", "address": "địa chỉ giao hàng", "payment": "cách thanh toán", "customer_name": "tên / cách xưng hô",
    "phone": "số điện thoại", "blocker": "đã trao đổi với người nhà / còn băn khoăn gì", "callback_time": "giờ hẹn gọi lại",
    "product_advised": "khách quan tâm sản phẩm / mẫu nào", "order_id": "mã đơn", "confirm_order": "có lên đơn / đặt hàng không",
    "baby_age": "bé mấy tháng / mấy tuổi", "household_size": "nhà mấy người", "owned_product": "đang dùng / đã có sản phẩm nào",
    "other": "câu hỏi khác (vd 'em giúp gì thêm được không ạ')",
}
CUSTOMER_SCHEMA = {"type": "object", "required": ["slots"], "additionalProperties": False, "properties": {"slots": {
    "type": "array", "items": {"type": "object", "required": ["slot", "span"], "additionalProperties": False, "properties": {
        "slot": {"type": "string", "enum": list(CUSTOMER_SLOTS)}, "span": {"type": "string"},
        "label": {"type": ["string", "null"], "enum": LABELS + [None]}}}}}}


def _defs(d):
    return "\n".join(f"- {k}: {v}" for k, v in d.items())


def _call(prompt, schema, texts, meta):
    from core.llm.deepseek import LLM
    from core.pii import Redactor
    llm = LLM(settings.extractor_llm)
    red = Redactor() if llm.external else None
    if red:
        safe = red.redact(texts)
        for a, b in zip(texts, safe):
            prompt = prompt.replace(a, b)
    t0 = time.perf_counter()
    log_meta = {}
    d = llm.json(prompt, max_tokens=500, schema=schema, timeout=settings.extractor_timeout_s,
                 system="Bạn là bộ trích xuất thông tin cho cuộc gọi bán hàng tiếng Việt. Chỉ trả JSON hợp lệ.",
                 logprobs=settings.extract_logprobs and not llm.external,
                 top_logprobs=settings.extract_logprob_top_n, metadata=log_meta)
    if meta is not None:
        meta["ms"] = meta.get("ms", 0) + int((time.perf_counter() - t0) * 1000)
        meta["backend"] = f"{settings.extractor_backend}:{settings.extractor_llm}"
        if log_meta.get("label_logprobs"):
            meta.setdefault("label_logprobs", {}).update(log_meta["label_logprobs"])
    return d, red


def _take_label_prob(meta, label, used):
    vals = (meta or {}).get("label_logprobs", {}).get(str(label), [])
    i = used.get(str(label), 0)
    used[str(label)] = i + 1
    return vals[i] if i < len(vals) else None


def _logprob_ok(field, confidence):
    threshold = settings.extract_logprob_thresholds.get(field)
    return threshold is None or confidence is None or confidence >= float(threshold)


def _span_ok(span, text):
    return bool(span) and fold(span) in fold(text)


COMPETITOR_RX = re.compile(r"\b(ben (kia|khac)|shopee|lazada|tiki|tiktok|cho khac|(cua hang|shop|tiem|sieu thi|noi) khac|tren mang|dien may|san (thuong mai|tmdt)|tmdt)\b")
CUSTOMER_CUE = {
    ("objection", "dat_qua"): re.compile(r"\b(dat|mac|chat|re hon|chenh (lech )?(qua|nhieu|hon|the)|cao (qua|hon|the|vay))\b"),
    ("objection", "ep_gia"): re.compile(r"\b(bot|ep|thap nhat|giam (them|cho|duoc|nua|chut|it)|con giam|re hon (duoc|chut|nua))\b"),
    "blocker": re.compile(r"\b(hoi|ban (voi|lai|bac)|trao doi|can nhac|suy nghi|so sanh|tham khao|xem (them|lai|da)|quyet|tinh (them|da|sau)|de (anh|chi|em|minh|toi)\b)"),
    "has_children": None,
    "owned_product": re.compile(r"\b(dang (dung|xai)|da co|co san|nha (co|dang)|mua (roi|tu|hoi)|cai cu|hien (dung|xai)|dung (roi|lau))\b"),
}
RELATIVE_RX = re.compile(r"\b(chong|vo|ong xa|ba xa|nguoi nha|gia dinh|bo me|ong ba|ba nha|nha (anh|chi|em|minh|toi))\b")


def _customer_slot_ok(slot, value, text, context=None):
    from harness.extractor import KIDS_RX, SLOT_KW
    f = fold(text)
    if slot == "competitor_price_vnd":
        return bool(COMPETITOR_RX.search(f) and find_money(text))
    if slot == "claimed_price_vnd":
        return not COMPETITOR_RX.search(f)
    if slot == "has_children":
        return bool(KIDS_RX.search(f))
    if slot == "budget_vnd":
        return bool(re.search(r"\b(ngan sach|tam|khoang|toi da|duoi|du dinh|chi (tam|khoang|duoc|co)|\d+\s*cu)\b", f)
                    or (context and re.search(dict(SLOT_KW)["budget_vnd"], fold(context))))
    if slot == "address":
        return bool(re.search(r"\d|,", str(value)))
    if slot == "payment":
        return bool(re.search(r"\b(cod|thanh toan|tien mat|chuyen khoan|ck truoc|momo|zalopay|nhan hang (roi )?tra)\b", f))
    if slot == "blocker" and str(value).startswith("can hoi") and not RELATIVE_RX.search(f):
        return False
    cue = CUSTOMER_CUE.get((slot, value)) or CUSTOMER_CUE.get(slot)
    return cue is None or bool(cue.search(f))


def _slot_value(slot, span, label, text, today):
    if slot == "room_area_m2":
        m = re.search(r"\d{1,3}", span)
        return int(m.group()) if m else None
    if slot == "has_children":
        return True if label == "co" else None
    if slot in ("budget_vnd", "competitor_price_vnd", "claimed_price_vnd"):
        money = find_money(span)
        return money[0][2] if money else None
    if slot == "size":
        m = re.search(r"\b(\d{2}|xxl|xl|xs|s|m|l)\b", span.lower())
        return m.group(1).upper() if m else None
    if slot == "color":
        from harness.tools import find_color
        return find_color(span)
    if slot == "address":
        v = span.strip(" ,.")
        return v if len(v) >= 6 else None
    if slot == "payment":
        return label if label in ("COD", "bank") else None
    if slot == "blocker":
        return label if label in ("can hoi chong", "can hoi vo", "can hoi nguoi nha", "so sanh gia", "can nhac") else None
    if slot == "callback_requested":
        w = parse_relative_datetime(span, today) or parse_relative_datetime(text, today)
        return f"{w[0]}T{w[1] or '09:00'}" if w else None
    if slot == "household_size":
        m = re.search(r"\b(\d{1,2})\b", span)
        return int(m.group(1)) if m else None
    if slot == "baby_age":
        m = re.search(r"(\d{1,2})\s*(tháng|tuổi|thang|tuoi)", span.lower())
        return f"{int(m.group(1))} {'tháng' if fold(m.group(2)) == 'thang' else 'tuổi'}" if m else None
    if slot == "objection":
        return label if label in ("dat_qua", "ep_gia") else None
    if slot == "owned_product":
        from harness.tools import find_products
        p = find_products(span)
        return p[0] if p else None
    if slot == "self_name":
        names = re.findall(r"\b[A-ZĐ][a-zà-ỹ]+\b", span)
        names = [n for n in names if fold(n) not in ("chi", "anh", "em", "co", "chu", "bac", "toi", "minh", "da", "vang")]
        return names[-1] if names else None
    return None


def customer_slots(text, today, rules, mode, meta=None, context=None):
    meta = meta if meta is not None else {}
    from harness.extractor import customer_llm_candidate
    if mode == "hybrid" and not customer_llm_candidate(text, context):
        meta["customer_llm_skipped"] = "no_slot_cue"
        return dict(rules)
    prev = (f"Câu nhân viên vừa nói trước đó (chỉ để hiểu khách đang trả lời điều gì, KHÔNG trích từ câu này): {context}\n"
            if context else "")
    prompt = ("Trích các thông tin KHÁCH vừa nói trong câu dưới đây. Chỉ trích điều khách nói rõ trong câu này, không suy đoán. "
              "Khách trả lời ngắn ('dạ 3', 'tầm 5 củ') thì dựa vào câu nhân viên vừa hỏi để biết đó là thông tin gì.\n"
              f"Các loại thông tin:\n{_defs(CUSTOMER_SLOTS)}\n"
              "Mỗi kết quả: slot, span (đoạn chữ NGUYÊN VĂN trong câu chứa thông tin), label (chỉ cho has_children, payment, blocker, objection).\n"
              "Ví dụ đối chứng:\n"
              "- 'Máy AirPure X giá bao nhiêu em?' → slots rỗng (hỏi giá, không phải phản đối).\n"
              "- 'Trên Lazada có 4tr2 thôi, sao bên em đắt thế?' → competitor_price_vnd ('4tr2') + objection dat_qua.\n"
              "- 'Để chị hỏi lại ông xã đã nhé.' → blocker can hoi chong. 'Ừ chị lấy luôn nhé.' → slots rỗng.\n"
              f"Không có thông tin nào thì trả slots rỗng.\n\n{prev}Câu khách: {text}")
    try:
        d, red = _call(prompt, CUSTOMER_SCHEMA, [text], meta)
    except Exception as e:
        meta["fallback"] = f"{type(e).__name__}: {str(e)[:120]}"
        log.warning("bộ trích LLM (lời khách) lỗi → dùng luật: %s", meta["fallback"])
        return rules
    got, dropped, used = {}, 0, {}
    meta["field_logprobs"] = []
    for it in d.get("slots") or []:
        span = red.restore(it.get("span") or "") if red else (it.get("span") or "")
        if not _span_ok(span, text):
            dropped += 1; continue
        slot = it.get("slot")
        v = _slot_value(slot, span, it.get("label"), text, today)
        if v is None:
            continue
        if slot in ("objection", "blocker", "competitor_price_vnd") and settings.extract_logprobs:
            probs = [_take_label_prob(meta, x, used) for x in (slot, it.get("label")) if x]
            probs = [p for p in probs if p is not None]
            confidence = min(probs) if probs else None
            if not _logprob_ok(slot, confidence):
                dropped += 1; continue
        if not _customer_slot_ok(slot, v, text, context):
            dropped += 1; continue
        if slot in ("objection", "blocker", "competitor_price_vnd"):
            meta["field_logprobs"].append({"field": slot, "value": v, "confidence": confidence if settings.extract_logprobs else None})
        if it["slot"] == "claimed_price_vnd":
            got.setdefault("claimed_prices", []).append(v)
        else:
            got.setdefault(it["slot"], v)
    meta["dropped_spans"] = meta.get("dropped_spans", 0) + dropped
    if mode == "llm":
        return got
    out = dict(rules)
    for k, v in got.items():
        if k == "claimed_prices":
            out["claimed_prices"] = sorted(set(out.get("claimed_prices", [])) | set(v))
        else:
            out.setdefault(k, v)
    return out


_pool = None


def submit_customer_slots(text, today, rules, meta, context=None):
    global _pool
    if _pool is None:
        from concurrent.futures import ThreadPoolExecutor
        _pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="extract")
    own = {}
    fut = _pool.submit(customer_slots, text, today, rules, "hybrid", own, context)
    return {"future": fut, "meta": own, "outer": meta}


def collect_customer_slots(pending, slots, wait):
    from concurrent.futures import TimeoutError as FutTimeout
    if pending is None:
        return {}
    fut, own, outer = pending["future"], pending["meta"], pending["outer"]
    if wait == 0 and not fut.done():
        return None
    try:
        merged = fut.result(timeout=wait)
    except FutTimeout:
        log.warning("bộ trích LLM (lời khách) quá %ss → lượt này chỉ dùng luật", wait)
        if outer is not None:
            outer["fallback"] = f"timeout {wait}s"
        return {}
    added = {}
    for k, v in merged.items():
        if k == "claimed_prices":
            extra = sorted(set(v) - set(slots.get("claimed_prices", [])))
            if extra:
                slots["claimed_prices"] = sorted(set(slots.get("claimed_prices", [])) | set(extra)); added[k] = extra
        elif k not in slots:
            slots[k] = added[k] = v
    if outer is not None:
        outer["ms"] = outer.get("ms", 0) + own.get("ms", 0)
        outer["dropped_spans"] = outer.get("dropped_spans", 0) + own.get("dropped_spans", 0)
        for k in ("backend", "fallback"):
            if own.get(k):
                outer[k] = own[k]
        outer["customer_llm_slots"] = sorted(added)
    return added


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


DAYS_RX = re.compile(r"(?<![\d/])(\d{1,2})(?:\s*(?:-|–|den|toi)\s*(\d{1,2}))?\s*ngay(?!\s*\d)")
WARRANTY_RX = re.compile(r"(\d{1,2})\s*(thang|nam)\b")
MONEY_FIELDS = ("price_vnd", "list_price_vnd", "price_quoted_vnd")
POLARITY_FIELDS = ("promo_active", "in_stock", "is_human")


def _claim_value(field, span, polarity):
    if field in MONEY_FIELDS:
        money = find_money(span)
        return money[0][2] if money else None
    if field in POLARITY_FIELDS:
        return polarity if isinstance(polarity, bool) else None
    if field in ("delivery_days", "return_days"):
        m = DAYS_RX.search(fold(span))
        if not m:
            return None
        return int(m.group(2) or m.group(1)) if field == "delivery_days" else int(m.group(1))
    if field == "warranty_months":
        m = WARRANTY_RX.search(fold(span))
        return int(m.group(1)) * (12 if m.group(2) == "nam" else 1) if m else None
    nums = [int(x) for x in re.findall(r"\d+", span)]
    return nums[0] if nums else None


FIELD_CUE = {
    ("is_human", True): re.compile(r"\b(nguoi that|nhan vien that|con nguoi)\b"),
    ("is_human", False): re.compile(r"\b(tro ly|ai|robot|bot|chatbot|tu dong|tri tue nhan tao)\b"),
    "in_stock": re.compile(r"\b(con hang|het hang|het mat|san hang|co san|kho|chua co hang)\b"),
    "promo_active": re.compile(r"\b(khuyen mai|km|giam|uu dai|tang|qua tang|voucher|sale|chuong trinh)\b"),
    "delivery_days": re.compile(r"\b(giao|nhan hang|nhan duoc hang|van chuyen|ship|toi noi|den noi)\b"),
    "return_days": re.compile(r"\b(doi tra|doi hang|tra hang|tra lai|doi)\b"),
    "warranty_months": re.compile(r"\bbao hanh\b"),
}
FIELD_BLOCK = {
    "delivery_days": re.compile(r"\b(hoan|doi tra|bao hanh)\b"),
    "return_days": re.compile(r"\b(hoan|bao hanh|loi|1-1|doi moi)\b"),
    "warranty_months": re.compile(r"\b(mo rong|goi|mua them)\b"),
}
NEG_BEFORE_CUE = ("promo_active", "in_stock")
QUESTION_TAIL_RX = re.compile(r"\b(khong|chua|nao|gi|bao nhieu|may|dau|sao|the nao|nhi|ha|chang)\s*(a|nhe|nha|vay|ha)?\s*[.!]?$")
CLAIM_HINT_RX = re.compile(r"\d|" + "|".join(rx.pattern for rx in FIELD_CUE.values()))


def _is_question(s):
    from harness.extractor import REQUEST_RX
    f = fold(s)
    if s.endswith("?") or REQUEST_RX.search(f):
        return True
    return bool(QUESTION_TAIL_RX.search(f)) and not re.search(r"\b(khong|chua|chang)\b[^,;]*\bdau\W*(a|nhe|nha)?\W*$", f)


# câu yêu cầu không có "?" mà luật bỏ qua ("chị lên địa chỉ đi ạ", "anh gọi lại khi nào tiện nhé"): khách là chủ ngữ
# (không kèm đã/sẽ/đang), kết bằng tiểu từ yêu cầu → gửi cho LLM; nhãn ask chỉ nhận khi câu có từ khóa của slot đó.
MAYBE_ASK_RX = re.compile(r"^(da\W+)?(\w+(\s\w+)?\s+oi\W+)?(anh|chi|co|chu|minh|ban|quy khach)\b(?!\s+(da|se|dang)\b)"
                          r".*\b(nhe|nha|di a|di nhe|giup em|gium em)\W*(a)?\W*$")


def _slot_topic_ok(slot, s):
    from harness.extractor import SLOT_KW
    rx = dict(SLOT_KW).get(slot)
    return bool(rx and re.search(rx, fold(s)))


def _claim_ok(field, value, s, focus_sku):
    from harness.extractor import _about_focus, money_not_price
    f = fold(s)
    if field in MONEY_FIELDS:
        hits = [st for st, _, v in find_money(s) if v == value]
        return bool(hits) and not all(money_not_price(s, st) for st in hits)
    cue = FIELD_CUE.get((field, value)) or FIELD_CUE.get(field)
    if cue is not None and not cue.search(f):
        return False
    if field == "promo_active" and value is True and re.search(
            r"\b(chua|khong) co thong tin (?:ve )?(?:viec )?(?:giam|khuyen mai|uu dai|qua tang)\b", f):
        return False
    if field in FIELD_BLOCK and FIELD_BLOCK[field].search(f):
        return False
    if value is True and field in NEG_BEFORE_CUE and re.search(r"\b(chua|khong|het|chang)\b(\s+\w+){0,4}\s+" + cue.pattern, f):
        return False
    if field in ("warranty_months", "return_days") and not _about_focus(s, focus_sku):
        return False
    return True


NUMBER_ROLES = {
    "gia_ban": ("price_vnd", "giá bán HIỆN TẠI agent khẳng định, giá khách sẽ trả ('giá bán là 1.340.000đ', 'còn 2.990.000đ'). "
                             "KHÔNG phải số tiền giảm, tiền hoàn, phí, tổng tiền khách nêu lại"),
    "gia_niem_yet": ("list_price_vnd", "giá niêm yết / giá gốc trước khuyến mãi ('giá niêm yết 3.490.000đ'). KHÔNG phải số đứng sau "
                                       "'đang bán' / 'còn' trong cùng câu, không phải mức khuyến mãi ('khuyến mãi 400.000đ')"),
    "gia_da_bao_truoc": ("price_quoted_vnd", "agent nhắc lại giá đã báo trong quá khứ, không khẳng định là giá hiện tại ('hôm trước em báo 5.200.000đ')"),
    "so_ngay_giao": ("delivery_days", "số ngày giao hàng ('giao trong 2–3 ngày')"),
    "so_ngay_doi_tra": ("return_days", "hạn đổi trả bằng ngày ('đổi trả trong 7 ngày'). KHÔNG phải hạn đổi mới khi lỗi nhà sản xuất"),
    "thoi_han_bao_hanh": ("warranty_months", "thời gian bảo hành chính hãng của sản phẩm ('bảo hành 24 tháng'). KHÔNG phải bảo hành "
                                             "của sản phẩm / ngành hàng khác được nhắc để so sánh"),
    "tien_hoan": (None, "tiền shop hoàn / trả lại / bù cho khách ('được hoàn 500.000đ')"),
    "phu_thu_phi": (None, "phụ thu, phí ship, phí lắp đặt, phí dịch vụ ('phụ thu 50.000đ', 'phí ship 30.000đ')"),
    "so_tien_giam": (None, "số tiền được giảm / tiết kiệm ('giảm 300.000đ')"),
    "tien_khach_noi": (None, "ngân sách khách, giá khách thấy ở nơi khác, số tiền agent bác bỏ ('không phải 1.161.000đ')"),
    "ngay_thang": (None, "ngày tháng năm, giờ ('ngày 24/10', '9 giờ sáng')"),
    "so_ngay_khac": (None, "số ngày không phải giao hàng hay đổi trả: hoàn tiền, xử lý, hạn khuyến mãi ('hoàn tiền trong 3–5 ngày')"),
    "bao_hanh_mo_rong": (None, "gói bảo hành mở rộng / mua thêm, không phải bảo hành chính hãng"),
    "so_khac": (None, "số khác: số lượng, kích thước, size, công suất, mã đơn, số điện thoại, số mức ('3 mức gió', 'size 42')"),
}
FACTS = {
    "dang_co_khuyen_mai": ("promo_active", True, "agent khẳng định ĐANG có khuyến mãi / quà tặng (miễn phí giao hàng không tính). "
                                                 "KHÔNG phải khi nói 'chưa có thông tin về quà tặng', khuyến mãi đã hết hạn"),
    "khong_co_khuyen_mai": ("promo_active", False, "agent khẳng định không có / đã hết khuyến mãi. KHÔNG phải khi chỉ nói hết hàng"),
    "con_hang": ("in_stock", True, "agent khẳng định còn hàng. KHÔNG phải 'không còn hàng'"),
    "het_hang": ("in_stock", False, "agent khẳng định hết hàng"),
    "nhan_la_nguoi_that": ("is_human", True, "agent tự nhận MÌNH là người thật. KHÔNG gán cho câu báo giá, chào hỏi, xác nhận đơn"),
    "nhan_la_tro_ly_ai": ("is_human", False, "agent tự nhận MÌNH là trợ lý ảo / AI / máy"),
}


def _sentence_schema(cand):
    return {"type": "object", "required": ["sentences"], "additionalProperties": False, "properties": {"sentences": {
        "type": "array", "items": {"type": "object", "required": ["i", "ask", "numbers", "facts"], "additionalProperties": False,
                                   "properties": {
                                       "i": {"type": "integer", "enum": list(cand)},
                                       "ask": {"type": "string", "enum": ["none"] + list(QUESTION_SLOTS)},
                                       "confirm": {"type": "boolean"},
                                       "numbers": {"type": "array", "items": {
                                           "type": "object", "required": ["span", "role"], "additionalProperties": False,
                                           "properties": {"span": {"type": "string"}, "role": {"type": "string", "enum": list(NUMBER_ROLES)}}}},
                                       "facts": {"type": "array", "items": {"type": "string", "enum": list(FACTS)}}}}}}}


def agent(text, known_values, q_rules, c_rules, mode, meta=None, focus_sku=None):
    from harness.extractor import CONFIRM_RX, claim_sku, mentions_known
    meta = meta if meta is not None else {}
    sents = _sentences(text)
    ask = {i for i, s in enumerate(sents) if _is_question(s)}
    maybe = {i for i, s in enumerate(sents) if i not in ask and MAYBE_ASK_RX.search(fold(s))}
    hint = {i for i, s in enumerate(sents) if CLAIM_HINT_RX.search(fold(s))}
    cand = sorted(ask | maybe | hint)
    if not cand:
        meta["skipped"] = meta.get("skipped", 0) + 1
        return q_rules, c_rules
    numbered = "\n".join(f"[{i}] {sents[i]}" for i in cand)
    focus = ""
    if focus_sku:
        from harness.tools import product_name
        focus = f"Sản phẩm đang tư vấn: {product_name(focus_sku)}.\n"
    prompt = ("Phân tích từng câu của NHÂN VIÊN bán hàng dưới đây. Mỗi câu trả ĐÚNG MỘT phần tử (i = số thứ tự câu), không bỏ câu nào.\n"
              "- ask: câu này HỎI khách về gì (kể cả câu xin thông tin không có dấu ?, vd 'chị cho em xin địa chỉ ạ', "
              "'anh lên địa chỉ giúp em nhé', 'chị hẹn giờ gọi lại khi nào tiện nhé'); "
              "câu kể, câu thông báo, câu dặn dò, cảm ơn, khẳng định thì ask=none ('chị cân nhắc thêm nhé', 'anh gọi lại sau nhé').\n"
              f"  Giá trị của ask:\n{_defs(QUESTION_SLOTS)}\n"
              "- confirm: true nếu câu hỏi chỉ xác nhận điều đã biết ('vẫn giao về địa chỉ cũ đúng không ạ').\n"
              "- numbers: MỌI con số trong câu, span = đoạn chữ NGUYÊN VĂN chứa con số, role = vai trò của con số:\n"
              f"{_defs({k: v[1] for k, v in NUMBER_ROLES.items()})}\n"
              "- facts: khẳng định không có con số mà câu NÓI RÕ (không suy đoán; không có thì để rỗng):\n"
              f"{_defs({k: v[2] for k, v in FACTS.items()})}\n"
              "Ví dụ đối chứng:\n"
              "- 'Giá gốc 2.190.000đ, giờ bán 1.990.000đ ạ.' → 2.190.000đ gia_niem_yet, 1.990.000đ gia_ban.\n"
              "- 'Mang máy cũ tới được trợ giá 250.000đ ạ.' → so_tien_giam (không phải giá).\n"
              "- 'Hoàn tiền trong 3–5 ngày làm việc ạ.' → so_ngay_khac; 'Đổi trả trong 7 ngày ạ.' → so_ngay_doi_tra.\n\n"
              f"{focus}Lời nhân viên:\n{numbered}")
    try:
        d, red = _call(prompt, _sentence_schema(cand), [sents[i] for i in cand], meta)
    except Exception as e:
        meta["fallback"] = f"{type(e).__name__}: {str(e)[:120]}"
        log.warning("bộ trích LLM (lời agent) lỗi → dùng luật: %s", meta["fallback"])
        return q_rules, c_rules
    dropped, used = 0, {}
    meta["field_logprobs"] = []
    q_llm, items = {}, []
    for it in d.get("sentences") or []:
        i = it.get("i")
        if not isinstance(i, int) or i not in cand:
            dropped += 1; continue
        s = sents[i]
        slot = it.get("ask")
        if slot in QUESTION_SLOTS:
            is_offer = slot == "product_advised" and re.search(
                r"^em co the (?:tu van|ho tro|gioi thieu) them\b", fold(s))
            if is_offer or (i not in ask and not (i in maybe and _slot_topic_ok(slot, s))):
                dropped += 1
            else:
                qtype = "confirm" if it.get("confirm") or mentions_known(s, slot, known_values) or CONFIRM_RX.search(fold(s)) else "open"
                q_llm.setdefault(i, {"slot": slot, "type": qtype, "text": s})
        for n in it.get("numbers") or []:
            field = NUMBER_ROLES.get(n.get("role"), (None,))[0]
            if field:
                items.append((i, field, n.get("span") or "", None, None))
        for fct in it.get("facts") or []:
            if fct in FACTS:
                field = FACTS[fct][0]
                confidence = _take_label_prob(meta, fct, used) if settings.extract_logprobs and field in ("is_human", "promo_active") else None
                if field in ("is_human", "promo_active") and settings.extract_logprobs:
                    if not _logprob_ok(field, confidence):
                        dropped += 1; continue
                items.append((i, field, "", FACTS[fct][1], confidence))
    rules_fields = {(c["field"], c.get("text")) for c in c_rules}
    rules_money = {(c["value"], c.get("text")) for c in c_rules if c["field"] in MONEY_FIELDS}
    c_llm = []
    for i, field, span, polarity, confidence in items:
        s = sents[i]
        if i not in hint:
            dropped += 1; continue
        span = red.restore(span) if red else span
        if field not in POLARITY_FIELDS and not _span_ok(span, s):
            dropped += 1; continue
        v = _claim_value(field, span or s, polarity)
        if v is None or not _claim_ok(field, v, s, focus_sku):
            dropped += 1; continue
        if mode != "llm" and ((field, s) in rules_fields or (field in MONEY_FIELDS and (v, s) in rules_money)):
            continue
        sku = claim_sku(s, focus_sku)
        c_llm.append({"field": field, "value": v, "text": s, **({"sku": sku} if sku else {})})
        if field in ("is_human", "promo_active"):
            meta["field_logprobs"].append({"field": field, "value": v,
                                           "confidence": confidence if settings.extract_logprobs else None})
    meta["dropped_spans"] = meta.get("dropped_spans", 0) + dropped
    if mode == "llm":
        return [q_llm[i] for i in sorted(q_llm)], c_llm
    by_text = {q["text"]: q for q in q_rules}
    out_q = []
    for i, s in enumerate(sents):
        if i in q_llm:
            out_q.append(q_llm[i])
        elif s in by_text:
            out_q.append(by_text[s])
    seen, out_c = set(), []
    for c in c_rules + c_llm:
        k = (c["field"], json.dumps(c["value"]), c.get("text"))
        if k not in seen:
            seen.add(k); out_c.append(c)
    return out_q, out_c
