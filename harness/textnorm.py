"""Perceive: chuẩn hóa lời khách tiếng Việt trước khi vào harness.

- teencode / không dấu / viết tắt → câu chuẩn (đủ để rule và LLM hiểu)
- ITN: "năm triệu rưỡi" → 5500000, "5tr2" → 5200000, "690k" → 690000, "không chín tám…" → SĐT
- ngày tương đối: "thứ hai tuần sau", "mai", "ngày kia" → YYYY-MM-DD (tính từ ngày của cuộc gọi)
- mask PII (CCCD 12 số, STK 9–14 số) trước khi ghi log / gửi model ngoài
"""
import re
import unicodedata
from datetime import date, timedelta

def strip_accents(s):
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def fold(s):
    return re.sub(r"\s+", " ", strip_accents((s or "").lower())).strip()


TEEN = [
    (r"\bk\b|\bko\b|\bkhong\b|\bkg\b", "không"), (r"\br\b", "rồi"), (r"\bdc\b|\bđc\b|\bduoc\b", "được"),
    (r"\bbn\b|\bbao nhieu\b", "bao nhiêu"), (r"\bsp\b", "sản phẩm"), (r"\bv\b", "vậy"), (r"\bj\b", "gì"),
    (r"\bmk\b|\bmik\b", "mình"), (r"\bbik\b|\bbiet\b", "biết"), (r"\bok\b|\boke\b|\bokie\b", "ok"),
    (r"\bz\b", "thế"), (r"\bnhe\b", "nhé"), (r"\bship cod\b", "ship COD"), (r"\blen don\b", "lên đơn"),
    (r"\bvo\b", "vợ"), (r"\bchong\b", "chồng"), (r"\bgia\b", "giá"), (r"\bhom truoc\b", "hôm trước"),
    (r"\bdia chi\b", "địa chỉ"), (r"\bdoi\b", "đổi"),
]


def normalize_teencode(text):
    s = " " + text + " "
    for a, b in TEEN:
        s = re.sub(a, b, s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


DIGIT = {"không": 0, "linh": 0, "lẻ": 0, "một": 1, "mốt": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4, "năm": 5, "lăm": 5,
         "nhăm": 5, "sáu": 6, "bảy": 7, "bẩy": 7, "tám": 8, "chín": 9}
SCALE = {"mươi": 10, "mười": 10, "trăm": 100, "nghìn": 1000, "ngàn": 1000, "triệu": 1_000_000, "tỷ": 1_000_000_000, "tỉ": 1_000_000_000}
_NUM_WORD = r"(?:không|linh|lẻ|một|mốt|hai|ba|bốn|tư|năm|lăm|nhăm|sáu|bảy|bẩy|tám|chín|mươi|mười|trăm|nghìn|ngàn|triệu|tỷ|tỉ|rưỡi)"


def words_to_int(words):
    total, small, cur, scale = 0, 0, 0, None
    prev, tail = None, []
    for w in words.split():
        if w in ("linh", "lẻ"):
            pass
        elif w == "mười":
            small += 10
        elif w == "mươi":
            small += (cur or 1) * 10; cur = 0
        elif w == "trăm":
            small += (cur or 1) * 100; cur = 0
        elif w in ("nghìn", "ngàn", "triệu", "tỷ", "tỉ"):
            total += ((small + cur) or 1) * SCALE[w]; small = cur = 0; scale = SCALE[w]; tail = []; prev = w; continue
        elif w == "rưỡi":
            if scale: total += scale // 2
        elif w in DIGIT:
            if prev in ("mươi", "mười"): small += DIGIT[w]
            else: cur = DIGIT[w]
        tail.append(w); prev = w
    rest = small + cur
    if rest and scale and scale >= 1000 and "nghìn" not in tail and "ngàn" not in tail:
        unit = scale // 1000
        if len(tail) == 1 and tail[0] in DIGIT:
            return total + DIGIT[tail[0]] * unit * 100
        if len(tail) >= 2 and tail[-2] == "trăm" and tail[-1] in DIGIT:
            return total + (small + cur * 10) * unit
        if scale >= 1_000_000:
            return total + rest * unit
    return total + rest


def _num_from_compact(s):
    s = s.lower().replace(" ", "")
    m = re.fullmatch(r"(\d+)(?:tr|triệu|trieu)(\d{1,3})?", s)
    if m:
        a, b = int(m.group(1)), m.group(2)
        if not b: return a * 1_000_000
        return a * 1_000_000 + int(b) * (100_000 if len(b) == 1 else 10_000 if len(b) == 2 else 1000)
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)(k|nghìn|ngàn|nghin)", s)
    if m: return int(float(m.group(1).replace(",", ".")) * 1000)
    m = re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+(?:đ|d|vnd)?", s)
    if m: return int(re.sub(r"\D", "", s))
    return None


MONEY_RX = re.compile(
    r"\d{1,3}[.,]\d{3}\s*k\b"
    r"|\d{1,3}(?:[.,]\d{3})+\s*(?:đ|vnđ|vnd|đồng)?"
    r"|\d+\s*(?:triệu|tr)(?![a-zà-ỹ])\s*(?:rưỡi|\d{1,3}\b)?"
    r"|\d+(?:[.,]\d+)?\s*(?:k|nghìn|ngàn)\b"
    r"|\b\d{5,9}\s*(?:đ|vnđ|vnd|đồng)", re.I)
MONEY_WORDS_RX = re.compile(r"\b(?:%s)(?:\s+%s)*\b" % (_NUM_WORD, _NUM_WORD), re.I)


def find_money(text):
    out = []
    for m in MONEY_RX.finditer(text):
        raw = m.group().strip()
        if re.fullmatch(r"\d{1,3}[.,]\d{3}\s*k", raw, re.I):
            v = int(re.sub(r"\D", "", raw)) * 1000
        elif "rưỡi" in raw:
            v = int(re.match(r"\d+", raw).group()) * 1_000_000 + 500_000
        else:
            v = _num_from_compact(re.sub(r"\s*(đ|vnđ|vnd|đồng)$", "", raw, flags=re.I))
            if v is None and re.fullmatch(r"\d{5,9}\s*(đ|vnđ|vnd|đồng)", raw, re.I):
                v = int(re.sub(r"\D", "", raw))
        if v and v >= 1000:
            out.append((m.start(), m.end(), v))
    for m in MONEY_WORDS_RX.finditer(text.lower()):
        w = m.group()
        if not re.search(r"triệu|nghìn|ngàn|trăm|tỷ|tỉ", w):
            continue
        if any(s <= m.start() < e for s, e, _ in out):
            continue
        v = words_to_int(w)
        if v >= 10_000:
            out.append((m.start(), m.end(), v))
    return sorted(out)


_DIG1 = {"không": "0", "một": "1", "hai": "2", "ba": "3", "bốn": "4", "năm": "5", "sáu": "6", "bảy": "7", "tám": "8", "chín": "9"}


def find_phone(text):
    m = re.search(r"\b0\d{9}\b", re.sub(r"(?<=\d)[ .-](?=\d)", "", text))
    if m: return m.group()
    seq = "".join(_DIG1.get(w, " ") for w in text.lower().split())
    m = re.search(r"0\d{9}", seq.replace(" ", ""))
    return m.group() if m else None


WEEKDAY = {"thứ hai": 0, "thứ 2": 0, "thứ ba": 1, "thứ 3": 1, "thứ tư": 2, "thứ 4": 2, "thứ năm": 3, "thứ 5": 3,
           "thứ sáu": 4, "thứ 6": 4, "thứ bảy": 5, "thứ 7": 5, "chủ nhật": 6}


def parse_relative_datetime(text, today):
    t = text.lower(); d0 = date.fromisoformat(today); day = None
    if re.search(r"\bngày kia\b|\bngày mốt\b", t): day = d0 + timedelta(days=2)
    elif re.search(r"\bmai\b|\bngày mai\b", t): day = d0 + timedelta(days=1)
    elif re.search(r"\bhôm nay\b|\bchiều nay\b|\btối nay\b|\bsáng nay\b", t): day = d0
    for k, wd in WEEKDAY.items():
        if k in t:
            delta = (wd - d0.weekday()) % 7
            if "tuần sau" in t or "tuần tới" in t:
                delta = (7 - d0.weekday()) + wd
            elif delta == 0:
                delta = 7
            day = d0 + timedelta(days=delta)
            break
    m = re.search(r"(\d{1,2})[/-](\d{1,2})", t)
    if m and not day:
        try: day = date(d0.year, int(m.group(2)), int(m.group(1)))
        except ValueError: pass
    if not day:
        return None
    hour = None
    m = re.search(r"(\d{1,2})\s*(?:giờ|h|g)(?:\s*(\d{2}))?", t)
    if m:
        h = int(m.group(1))
        if ("chiều" in t or "tối" in t) and h < 12: h += 12
        hour = f"{h:02d}:{int(m.group(2) or 0):02d}"
    elif "chiều" in t: hour = "15:00"
    elif "sáng" in t: hour = "09:00"
    elif "tối" in t: hour = "19:00"
    return day.isoformat(), hour


CCCD_RX = re.compile(r"\b0\d{11}\b")
BANK_RX = re.compile(r"\b\d{9,14}\b")
PHONE_RX = re.compile(r"\b0\d{9}\b")
ACCOUNT_CTX_RX = re.compile(r"(so tai khoan|\bstk\b|tai khoan|ngan hang|\bck\b|chuyen khoan|\bvcb\b|vietcombank|techcombank|"
                            r"\bacb\b|\bmb\b|bidv|vietinbank|agribank|tpbank|vpbank|sacombank)\W*(\w+\W+){0,3}$")


def _is_account(text, start):
    return bool(ACCOUNT_CTX_RX.search(strip_accents(text[max(0, start - 40):start].lower())))


GROUPED_DIGITS_RX = re.compile(r"(?<![\d*.,])\d{2,6}(?:[ -]\d{2,6}){1,5}(?![\d*]|[.,]\d)")
_SPOKEN_DIGIT = {"khong": "0", "mot": "1", "hai": "2", "ba": "3", "bon": "4", "tu": "4", "nam": "5", "lam": "5", "sau": "6",
                 "bay": "7", "tam": "8", "chin": "9"}
SPOKEN_DIGITS_RX = re.compile(r"(?i)(?<!\w)(?:(?:không|một|hai|ba|bốn|tư|năm|lăm|sáu|bảy|tám|chín)(?:\s+|$)){9,14}")


def _mask_digits(digits, text, start):
    if PHONE_RX.fullmatch(digits) and not _is_account(text, start):
        return None
    return "*" * (len(digits) - 4) + digits[-4:]


def mask_pii(text):
    def grouped(m):
        d = re.sub(r"\D", "", m.group())
        if not 9 <= len(d) <= 14:
            return m.group()
        return _mask_digits(d, m.string, m.start()) or m.group()

    def spoken(m):
        d = "".join(_SPOKEN_DIGIT[strip_accents(w.lower())] for w in m.group().split())
        r = _mask_digits(d, m.string, m.start())
        return m.group() if r is None else r + (" " if m.group().endswith((" ", "\t")) else "")
    text = GROUPED_DIGITS_RX.sub(grouped, text)
    text = SPOKEN_DIGITS_RX.sub(spoken, text)
    text = CCCD_RX.sub(lambda m: m.group()[:2] + "*" * 6 + m.group()[-4:], text)
    return BANK_RX.sub(lambda m: m.group() if PHONE_RX.fullmatch(m.group()) and not _is_account(m.string, m.start())
                       else "*" * (len(m.group()) - 4) + m.group()[-4:], text)


def perceive(raw, today):
    norm = normalize_teencode(raw)
    masked = mask_pii(norm)
    return {"raw": raw, "text": masked, "money": [v for _, _, v in find_money(masked)],
            "phone": find_phone(masked), "when": parse_relative_datetime(norm, today),
            "pii_found": masked != norm}
