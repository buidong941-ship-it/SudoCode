"""Một biểu diễn chung cho mức khẳng định của mệnh đề (CONTRACT_V2, 09/11).

Trước đây mỗi thành phần tự xử lý phủ định/câu hỏi theo cách riêng: guardrail bỏ qua CẢ CÂU khi thấy "không/chưa",
extractor lọc vài cụm "chưa có thông tin", luật slot khách xét ±4 từ, executor dùng `_is_question` cho cả lượt.
Hệ quả quan sát được: RT-01 ("hiện chưa có chính sách bảo hành 3 năm" bị ghi claim 36 tháng), JEVNEW-012
("chỉ hỏi có COD không, chưa chọn" bị ghi payment=COD), và lỗ hổng ngược ("Không lo ạ, máy bảo hành 3 năm" lọt
guardrail vì cả câu có chữ "không").

Module này trả MỘT nhãn cho vị trí của một giá trị trong câu, theo đúng mệnh đề chứa nó:

    affirmed     khẳng định ("máy bảo hành 12 tháng")
    negated      phủ định phạm vi chứa giá trị ("chưa có chính sách bảo hành 3 năm")
    unknown      nói chưa biết / chưa xác nhận ("em chưa có thông tin về bảo hành 3 năm")
    question     hỏi về giá trị ("bên em có COD không")
    conditional  giả định ("nếu chị chọn COD thì ...")
    reported     thuật lại lời người khác ("chị nói quản lý hứa bảo hành 3 năm")

Mỗi bên tiêu thụ tự chọn tập nhãn chấp nhận (khai báo ở cuối file) nhưng KHÔNG tự viết lại luật phủ định:
guardrail coi affirmed/conditional/reported là có thể bị nghe như cam kết; memory chỉ ghi affirmed/conditional;
lựa chọn của khách (thanh toán) chỉ nhận affirmed; action ghi dữ liệu chỉ chạy khi yêu cầu là affirmed.

Thuần luật, không gọi model. Vị trí tính trên chuỗi đã chuẩn hóa `canon()`; `fold(canon(x))` cùng độ dài với `canon(x)`.
"""
import re
import unicodedata

from harness.textnorm import find_money, strip_accents

AFFIRMED, NEGATED, UNKNOWN, QUESTION, CONDITIONAL, REPORTED = (
    "affirmed", "negated", "unknown", "question", "conditional", "reported")

# Tập nhãn được chấp nhận theo vai trò (một nơi khai báo)
COMMITMENT = frozenset({AFFIRMED, CONDITIONAL, REPORTED})   # guardrail: câu có thể bị khách hiểu là shop cam kết
ASSERTED = frozenset({AFFIRMED, CONDITIONAL})                # memory/claim: agent đã nói ra như dữ kiện
CHOICE = frozenset({AFFIRMED})                               # lựa chọn của khách (thanh toán): hỏi/giả định không phải chọn
MENTION = frozenset({AFFIRMED, QUESTION, CONDITIONAL, REPORTED})  # màu/size/địa chỉ khách nhắc: chỉ bỏ khi phủ định/chưa biết
REQUEST = frozenset({AFFIRMED})                              # action ghi dữ liệu: chỉ khi khách thực sự yêu cầu


def canon(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()


def pfold(text):
    """fold giữ nguyên độ dài so với canon(text) (đ→d, bỏ dấu, chữ thường)."""
    return strip_accents(canon(text).lower())


def _accented(t):
    return pfold(t) != t.lower()


# ---------------------------------------------------------------- tách mệnh đề
# Dấu câu, dấu phẩy không nằm trong số (1,5 triệu), liên từ đối lập. "chứ" cuối câu hỏi ("được chứ ạ?") không tách.
_SEP = re.compile(r"[!?;]+|\.+(?!\d)|(?<!\d)\.+|(?<!\d),|,(?!\d)|\s(?:nhưng|tuy nhiên|song)\s"
                  r"|\schứ\s(?!\s*(?:ạ|nhỉ|nhé|em|anh|chị)?\s*[?.!]?\s*$)|\smà\s+(?:là|chỉ)\s", re.I)


def clauses(text):
    """[(start, end, ends_with_question_mark)] trên canon(text)."""
    t = canon(text)
    out, start = [], 0
    for m in _SEP.finditer(t):
        if m.start() > start or "?" in m.group():
            out.append((start, m.start(), "?" in m.group()))
        start = m.end()
    if start < len(t):
        out.append((start, len(t), False))
    return out or [(0, len(t), False)]


def _clause_index(cls, pos):
    for i, (s, e, _) in enumerate(cls):
        if s <= pos < max(e, s + 1):
            return i
    for i, (s, e, _) in enumerate(cls):          # vị trí nằm trên dấu tách → mệnh đề đứng trước
        if pos < s:
            return max(0, i - 1)
    return len(cls) - 1


# ---------------------------------------------------------------- luật nhãn (trên bản fold)
UNKNOWN_RX = re.compile(r"\b(chua co thong tin|chua (the )?(xac nhan|xac minh|kiem tra duoc)|khong (the )?(xac nhan|biet)"
                        r"|chua ro|khong ro|chua nam duoc|chua thay (thong tin|chinh sach|ghi nhan))\b")
TOPIC_RX = re.compile(r"^\W*(da\W+)?(ve( viec)?|doi voi|chuyen|rieng)\b")
COND_RX = re.compile(r"\b(neu|gia su|gia nhu|truong hop|lo nhu|vi du|khi nao (chi|anh) (chon|lay|dat))\b")
# Thuật lại lời người khác: chủ thể không phải agent/shop + động từ nói/hứa. "em chỉ báo giá" không tính (chỉ ≠ chị).
REPORT_RX = re.compile(r"(?<!\bem )(?<!\bminh )(?<!\bshop )\b(anh|chi|bac|khach|quan ly|nhan vien|ben (kia|khac)|nguoi ta"
                       r"|ong xa)\b((?:\s+\w+){0,4}?)\s+(noi|bao(?! hanh)|hua|ke|nhac|cho biet|keu|cam ket)\b"
                       r"|\btheo (loi|nhu) (anh|chi|khach|quan ly|nhan vien)\b")
AGENT_SUBJ = re.compile(r"\b(em|minh|shop|ben em|cua hang)\b")
NEG_FOLD = re.compile(r"\b(khong|chua|chang|ko|khoi)\b")
NEG_ACC = re.compile(r"(?<!\w)(không|chưa|chẳng|chả|đừng|hông|ko|khỏi)(?!\w)")
# Cụm có chữ phủ định nhưng không phủ định giá trị đứng sau (giới hạn, trấn an, phần chưa cộng thêm)
NEG_EXEMPT = re.compile(r"\b(khong (chi|nhung|qua|hon|toi|den|duoi|lo|sao|can|mat( phi)?|tinh|phat sinh)|dung lo"
                        r"|chua (tinh|bao gom|gom|ke|co vat|giam|ap dung khuyen mai|ap ma)|sua chua)\b")
COPULA = re.compile(r"\b((?<!phai )(?<!khong )la|(?<!khong )(?<!chua )con|bang)\b|:")
# Câu hỏi: khung "có ... không" (phạm vi bắt đầu từ "có"), câu hỏi có từ để hỏi, động từ "hỏi"
_Q_CO_TAIL = r"(?=(?:\s+\S+){0,10}?\s+(%s)\W*(%s)?\W*$)"
Q_CO_FOLD = re.compile(r"\b(co|co phai)\b" + _Q_CO_TAIL % ("khong|ko|chua", "a|nhe|nha|vay|ha|nhi|em|anh|chi"))
Q_CO_ACC = re.compile(r"(?<!\w)(có|có phải|phải)(?!\w)" + _Q_CO_TAIL % ("không|ko|chưa|hông", "ạ|nhé|nha|vậy|hả|nhỉ|em|anh|chị"))
Q_WH_ACC = re.compile(r"(?<!\w)(bao nhiêu|nào|gì|đâu|thế nào|(?<!không )sao|mấy)(?!\w)")
Q_WH_FOLD = re.compile(r"\b(bao nhieu|nao|the nao|(?<!khong )sao)\b")
Q_ASK = re.compile(r"\b(hoi|hoi thu|hoi xem|thac mac)\b")
Q_END_ACC = re.compile(r"(không|chưa|nào|gì|bao nhiêu|mấy|đâu|sao|thế nào|nhỉ|hả|chăng|hông)\s*(ạ|nhé|nha|vậy|hả|à|em|anh|chị)?\W*$")
Q_END_FOLD = re.compile(r"\b(khong|ko|chua|nao|bao nhieu|the nao|nhi|chang)\s*(a|nhe|nha|vay|ha|em|anh|chi)?\W*$")
# "X được không / X nhé" có người hưởng ("cho chị", "giúp chị") là lời nhờ, không phải hỏi khả năng
POLITE_REQ = re.compile(r"\b(cho|giup|gium|ho)\s+(chi|anh|em|minh|co|chu|bac|toi|tui)\b.*\b(duoc khong|duoc chu|nhe|nha)\W*(em|a|nhe)?\W*$"
                        r"|\b(duoc khong|duoc chu)\W*(em|a|nhe)?\W*$")
PRONOUN = re.compile(r"\b(anh|chi|em|co|chu|bac|minh|quy khach)\b(?=\s+(co\s+)?(muon|lay|dat|can|thay|chon|dinh|tinh|quan tam|xem|thich|dung|nghi|chot))")
NEG_DAU_END = re.compile(r"\b(khong|chua|chang)\b[^,;]*\bdau\W*(a|nhe|nha)?\W*$")
# Chữ phủ định nằm trong danh từ ghép / tên sản phẩm ("máy lọc không khí", "nồi chiên không dầu", "tai nghe không dây",
# "chẳng hạn") không phủ định vị từ nào. Danh sách = cụm chung + mọi "neg + từ kế" có trong tên/danh mục catalog.
_NEG_TOK = re.compile(r"\b(khong|chua|chang)\b")
_NEG_COMPOUND_STATIC = ["khong khi", "khong gian", "khong day", "hang khong", "khong dau", "khong duong", "chang han",
                        "khong ngung"]
_NEG_COMPOUND_RX = None


def _neg_compounds():
    global _NEG_COMPOUND_RX
    if _NEG_COMPOUND_RX is None:
        terms = set(_NEG_COMPOUND_STATIC)
        try:
            from eval import mock_tools as _mt        # chỉ đọc tên/danh mục catalog tĩnh
            for p in _mt.PRODUCTS:
                for txt in (p.get("name", ""), p.get("category", "").replace("-", " ").replace("/", " ")):
                    for m in re.finditer(r"\b(khong|chua|chang) (\w+)", pfold(txt)):
                        terms.add(m.group(0))
        except Exception:
            pass
        _NEG_COMPOUND_RX = re.compile(r"\b(" + "|".join(sorted(map(re.escape, terms), key=len, reverse=True)) + r")\b")
    return _NEG_COMPOUND_RX


def mask_neg_compounds(f):
    """Thay chữ phủ định trong danh từ ghép bằng khoảng trắng (giữ độ dài) trên chuỗi đã fold."""
    return _neg_compounds().sub(lambda m: _NEG_TOK.sub(lambda n: " " * len(n.group(0)), m.group(0)), f)


def _question_scope(c, f, ends_q):
    """Vị trí bắt đầu phạm vi hỏi trong mệnh đề (đã fold), None nếu mệnh đề không phải câu hỏi."""
    acc = _accented(c)
    wh = (Q_WH_ACC.search(c.lower()) if acc else Q_WH_FOLD.search(f))
    tail = (Q_END_ACC.search(c.lower()) if acc else Q_END_FOLD.search(f))
    ask = Q_ASK.search(f)
    if NEG_DAU_END.search(f) and not ends_q:
        return None                               # "không ... đâu ạ" là phủ định nhấn mạnh
    tail_wh = bool(tail) and bool((Q_WH_ACC if acc else Q_WH_FOLD).fullmatch(tail.group(1)))
    if wh and not (ends_q or ask) and (not tail or tail_wh) and NEG_FOLD.search(f[:wh.start()]):
        wh = tail = None                          # "chưa có khuyến mãi nào ạ", "không có gì": từ phiếm chỉ, không phải hỏi
    if not (ends_q or tail or wh or ask):
        return None
    if ask:
        return ask.start()
    co = (Q_CO_ACC.search(c.lower()) if acc else Q_CO_FOLD.search(f))
    if co:
        # "Giá X chị có lấy không" → hỏi từ "chị có lấy"; "Trả tiền mặt có được không" → cả mệnh đề là câu hỏi
        subj = [m.start() for m in PRONOUN.finditer(f) if m.start() < co.end()]   # lookahead cần thấy động từ sau "có"
        return subj[-1] if subj else 0
    if POLITE_REQ.search(f):
        return None                               # lời nhờ lịch sự: coi như yêu cầu khẳng định
    if wh:
        subj = [m.start() for m in PRONOUN.finditer(f[:wh.start()])]
        return subj[-1] if subj else 0
    subj = [m.start() for m in PRONOUN.finditer(f)]   # "Giá X, chị lấy không" → phạm vi hỏi từ "chị lấy"
    return subj[-1] if subj else 0


def _reported(c, f):
    for m in REPORT_RX.finditer(f):
        if m.group(1) is None:                        # "theo lời chị/quản lý ..."
            return True
        if AGENT_SUBJ.search(m.group(3) or ""):
            continue                                  # "anh yên tâm, em báo ..." — người nói là agent
        if m.group(1) == "chi" and _accented(c) and c[m.start(1):m.end(1)].lower() != "chị":
            continue                                  # "chỉ" không phải "chị"
        return True
    return False


def _negated(c, f, rel):
    pre_f, pre_c = f[:rel], c[:rel]
    cut = 0
    for m in COPULA.finditer(pre_f):
        cut = m.end()
    pre_f, pre_c = pre_f[cut:], pre_c[cut:]
    pre_f = NEG_EXEMPT.sub(lambda m: " " * len(m.group()), pre_f)
    window_start = 0
    toks = [m.start() for m in re.finditer(r"\S+", pre_f)]
    if len(toks) > 8:
        window_start = toks[-8]
    pre_f, pre_c = pre_f[window_start:], pre_c[window_start:]
    if _accented(c):
        for m in NEG_ACC.finditer(pre_c.lower()):
            if pre_f[m.start():m.end()].strip():   # không nằm trong cụm miễn trừ đã xóa
                return True
        return False
    return bool(NEG_FOLD.search(pre_f))


def stance_at(text, start, end=None):
    """Nhãn của giá trị nằm ở [start, end) trên canon(text)."""
    t = canon(text)
    f = mask_neg_compounds(pfold(t))
    cls = clauses(t)
    i = _clause_index(cls, start)
    cs, ce, ends_q = cls[i]
    c, cf = t[cs:ce], f[cs:ce]
    rel = max(0, start - cs)
    if UNKNOWN_RX.search(cf):
        return UNKNOWN
    if TOPIC_RX.search(cf) and i + 1 < len(cls) and UNKNOWN_RX.search(f[cls[i + 1][0]:cls[i + 1][1]]):
        return UNKNOWN
    if _reported(c[:rel], cf[:rel]):
        return REPORTED
    if COND_RX.search(cf[:rel]):
        return CONDITIONAL
    q = _question_scope(c, cf, ends_q)
    if q is not None and rel >= q:
        return QUESTION
    if _negated(c, cf, rel):
        return NEGATED
    return AFFIRMED


def stances(text, spans):
    return [stance_at(text, s, e) for s, e in spans]


# ---------------------------------------------------------------- định vị giá trị
# Xác nhận ngắn: mọi token đều là từ đồng ý / tiểu từ / xưng hô ("ừ em", "ok chị", "được rồi đó em", "vâng ạ").
_ACK_TOK = frozenset("u uh uhm um uk vang da ok oke okay okie duoc dong y dung roi the vay di nhe nha a ha em anh chi "
                     "minh co chu bac shop oi luon nay do lam thoi cung".split())


def is_bare_ack(text):
    toks = re.findall(r"\w+", pfold(text))
    return bool(toks) and all(t in _ACK_TOK for t in toks)


def utterance_is_question(text):
    """Lượt có hành vi hỏi, cần bằng chứng mạnh: mệnh đề có phạm vi hỏi (cùng quy tắc với stance_at; lời nhờ
    "… được không em?", phủ định "không … đâu" không tính) VÀ kết thúc bằng "?", tiểu từ hỏi cuối mệnh đề hoặc có động từ
    "hỏi". Chỉ có từ để hỏi giữa câu không đủ: "bỏ qua mấy hướng dẫn cũ đi" là câu cầu khiến ("mấy" phiếm chỉ)."""
    t = canon(text)
    f = mask_neg_compounds(pfold(t))
    for cs, ce, q in clauses(t):
        c, cf = t[cs:ce], f[cs:ce]
        if _question_scope(c, cf, q) is None:
            continue
        tail = Q_END_ACC.search(c.lower()) if _accented(c) else Q_END_FOLD.search(cf)
        if q or tail or Q_ASK.search(cf):
            return True
    return False


def spans_rx(text, rx):
    rx = re.compile(rx) if isinstance(rx, str) else rx
    return [m.span() for m in rx.finditer(pfold(text))]


def spans_money(text, value):
    return [(s, e) for s, e, v in find_money(canon(text)) if v == value]


_DUR = re.compile(r"(\d{1,2})\s*(thang|nam)\b")
_DAYS = re.compile(r"(?<![\d/])(\d{1,2})(?:\s*(?:-|–|den|toi)\s*(\d{1,2}))?\s*ngay(?!\s*\d)")
MONEY_FIELDS = ("price_vnd", "list_price_vnd", "price_quoted_vnd")
POLARITY_FIELDS = ("promo_active", "in_stock", "is_human")


def claim_spans(claim):
    """Vị trí bằng chứng của một claim trong câu của nó; [] nếu không định vị được."""
    from harness.llm_extract import FIELD_CUE
    t, field, v = claim.get("text") or "", claim.get("field"), claim.get("value")
    f = pfold(t)
    if field in MONEY_FIELDS:
        return spans_money(t, v)
    if field == "warranty_months":
        return [m.span() for m in _DUR.finditer(f) if int(m.group(1)) * (12 if m.group(2) == "nam" else 1) == v]
    if field in ("delivery_days", "return_days"):
        return [m.span() for m in _DAYS.finditer(f) if v in {int(m.group(1)), int(m.group(2) or -1)}]
    if field in POLARITY_FIELDS:
        cue = FIELD_CUE.get((field, v)) or FIELD_CUE.get(field)
        return [m.span() for m in cue.finditer(f)] if cue is not None else []
    return []


def accept_claim(claim):
    """(chấp nhận?, nhãn) — claim giá trị cần ASSERTED; claim phủ định (promo_active/in_stock/is_human = False)
    tự mang phủ định nên nhận cả negated."""
    spans = claim_spans(claim)
    if not spans:
        return True, ["unlocated"]
    got = stances(claim["text"], spans)
    ok = ASSERTED | ({NEGATED} if claim.get("field") in POLARITY_FIELDS and claim.get("value") is False else set())
    return any(s in ok for s in got), got


def filter_claims(claims, meta=None):
    kept, dropped = [], []
    for c in claims:
        ok, got = accept_claim(c)
        (kept if ok else dropped).append(c if ok else {"field": c.get("field"), "value": c.get("value"), "stances": got,
                                                         "text": (c.get("text") or "")[:160]})
    if meta is not None and dropped:
        meta["stance_dropped_claims"] = meta.get("stance_dropped_claims", []) + dropped
    return kept


# ---------------------------------------------------------------- slot lựa chọn của khách
PAY_RX = re.compile(r"\b(ship cod|cod|thanh toan khi nhan( hang)?|tien mat|nhan hang (roi )?(moi )?(tra|thanh toan)|chuyen khoan|ck"
                    r"|momo|zalopay|chuyen tien|banking)\b")
CUSTOMER_CHOICE = {"payment": CHOICE, "color": MENTION, "size": MENTION, "address": MENTION}


def _slot_spans(text, slot, value):
    t = canon(text)
    f = pfold(t)
    if slot == "payment":
        return [m.span() for m in PAY_RX.finditer(f)]
    if slot == "size":
        return [m.span() for m in re.finditer(r"(size|co|so)\s*" + re.escape(pfold(str(value))) + r"\b", f)]
    if slot == "address":
        key = pfold(str(value))[:12]
        i = f.find(key) if key else -1
        return [(i, i + len(key))] if i >= 0 else []
    if slot == "color":
        from harness.tools import COLORS
        out = []
        for w in sorted(COLORS.get(value, [str(value)]), key=len, reverse=True):
            out += [m.span() for m in re.finditer(r"\b" + re.escape(pfold(w)) + r"\b", f)]
        return out
    return []


def filter_customer_slots(text, slots, meta=None, only=None):
    """Bỏ lựa chọn khách chưa thực sự đưa ra (hỏi COD ≠ chọn COD; 'không lấy màu đen' ≠ màu đen). Sửa tại chỗ.
    only: giới hạn các slot xét (None = mọi slot trong CUSTOMER_CHOICE)."""
    if not isinstance(slots, dict):
        return slots
    for slot, ok in CUSTOMER_CHOICE.items():
        if slot not in slots or (only is not None and slot not in only):
            continue
        spans = _slot_spans(text, slot, slots[slot])
        if not spans:
            continue
        got = stances(text, spans)
        if not any(s in ok for s in got):
            slots.pop(slot)
            if meta is not None:
                meta.setdefault("stance_dropped_slots", []).append({"slot": slot, "stances": got})
    return slots
