"""Che PII trước khi dữ liệu rời hệ thống (LLM ngoài) hoặc vào file log.

- `Redactor`: thay SĐT / địa chỉ bằng mã ([SĐT_1], [ĐỊA_CHỈ_1]) trước khi gửi DeepSeek/Jev, rồi `restore()` câu trả lời
  về giá trị thật. Nghiệp vụ vẫn dùng được (đơn hàng, hẹn gọi lại cần SĐT thật) mà model ngoài không thấy.
  CCCD / số tài khoản đã được che từ lúc nhận câu nói (`harness.textnorm.mask_pii`) và không bao giờ khôi phục.
- `mask_for_log()`: che một chiều cho dòng log (098****714, [địa chỉ]).
"""
import functools
import os
import re

PHONE_RX = re.compile(r"(?<![\d*])(?:\+84|84|0)(?:[\s.-]?\d){9}(?![\d*])")
ADDRESS_RX = re.compile(
    r"(?:\b(?:số|sn)\s*)?\b\d+[\w/]*\s*,?\s*(?:đường|phố|ngõ|ngách|hẻm|kiệt|khu phố|thôn|ấp)\s+[^,.;!?\n]+"
    r"(?:\s*,\s*(?:(?:phường|p\.?|xã|thị trấn|quận|q\.?|huyện|thị xã|tp\.?|thành phố|tỉnh)\s*)?[^,.;!?\n]+){0,4}", re.I)
_UP = "A-ZĐÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ"
_CAPWORD = r"[%s][^\s,.;!?]*" % _UP
PLAIN_ADDRESS_RX = re.compile(r"\b\d{1,4}[A-Za-z]?(?:/\d+)*\s+%s(?:\s+(?:%s|\d+))*(?:\s*,\s*%s(?:\s+(?:%s|-|\d+))*){2,}"
                              % (_CAPWORD, _CAPWORD, _CAPWORD, _CAPWORD))
from harness.extractor import ADDRESS_RX as CUE_ADDRESS_RX  # noqa: E402

TOKEN_RX = re.compile(r"\[\s*(?:SĐT|ĐỊA[_ ]?CHỈ)[^\]\n]*\]|(?:SĐT|ĐỊA_CHỈ)_\d+", re.I)

PHONE_KEYS = {"phone", "customer_phone", "sdt", "so_dien_thoai"}
ADDRESS_KEYS = {"address", "dia_chi", "delivery_address", "new_address", "shipping_address"}


# ------------------------------------------------------------------ v6p7 (23/11): ranh giới địa chỉ bằng NER cục bộ
# Theo docs/DE-XUAT/DE-XUAT-NER-CHE-DIA-CHI-PII-2026-11-23.md + POC Kaggle runs/kaggle/ner-pii-poc-1123 (cấu hình 5 "hybrid"):
# NER Aster (chạy CỤC BỘ, không gửi câu đi đâu) xác định span ADDRESS; đoạn mà regex hiện có coi là địa chỉ nhưng NER không phủ
# vẫn bị che (dự phòng bảo thủ, không để lộ hơn regex). Bật bằng PII_NER=1; model không nạp được → giữ nguyên regex hiện tại.
# Chỉ đổi Redactor (dữ liệu gửi model ngoài); mask_for_log giữ nguyên. Model card không ghi license ("research checkpoint") →
# chưa đủ điều kiện vào main / bản nộp khi chưa làm rõ.
NER_MODEL = "Keithsel/Aster-Vietnamese-NER-MiniLM"
_NER = {"pipe": None, "tried": False, "error": None}


def ner_enabled():
    return os.environ.get("PII_NER", "0") == "1"


def ner_preload():
    """Nạp model một lần (gọi lúc khởi động tiến trình agent, ngoài thời gian của lượt). Lỗi → ghi lại, dùng regex."""
    if _NER["tried"] or not ner_enabled():
        return _NER["pipe"] is not None
    _NER["tried"] = True
    try:
        from transformers import pipeline
        _NER["pipe"] = pipeline("token-classification", model=NER_MODEL, aggregation_strategy="simple", device=-1)
    except Exception as e:                                  # noqa: BLE001
        _NER["error"] = f"{type(e).__name__}: {e}"[:300]
    return _NER["pipe"] is not None


def ner_status():
    return {"enabled": ner_enabled(), "loaded": _NER["pipe"] is not None, "error": _NER["error"], "model": NER_MODEL}


@functools.lru_cache(maxsize=4096)
def _ner_address_spans(s):
    ents = _NER["pipe"](s)
    spans = sorted((int(e["start"]), int(e["end"])) for e in ents
                   if "ADDR" in str(e.get("entity_group") or e.get("entity") or "").upper())
    merged = []
    for a, b in spans:                                      # gộp mảnh ADDRESS liền kề chỉ cách dấu phẩy / khoảng trắng
        if merged and s[merged[-1][1]:a].strip(" ,") == "":
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return tuple((a, b) for a, b in merged if b > a)


def _regex_address_spans(s):
    """Các đoạn mà ba regex địa chỉ hiện có bắt được trên chuỗi (không thay thế) — chỉ để làm dự phòng cho NER."""
    out = [m.span(1) for m in CUE_ADDRESS_RX.finditer(s)]
    out += [m.span() for m in ADDRESS_RX.finditer(s)] + [m.span() for m in PLAIN_ADDRESS_RX.finditer(s)]
    return sorted(out)


def _hybrid_address_spans(s):
    tokens = [m.span() for m in TOKEN_RX.finditer(s)]
    clash = lambda a, b: any(x < b and a < y for x, y in tokens)
    ner = [(a, b) for a, b in _ner_address_spans(s) if not clash(a, b)]
    keep = list(ner)
    for a, b in _regex_address_spans(s):
        a2, b2 = a, b
        while a2 < b2 and s[a2] in " ,":
            a2 += 1
        while b2 > a2 and s[b2 - 1] in " ,.":
            b2 -= 1
        if b2 > a2 and not clash(a2, b2) and not any(x < b2 and a2 < y for x, y in keep):
            keep.append((a2, b2))                          # regex thấy địa chỉ mà NER không phủ → vẫn che
    keep.sort()
    out = []
    for a, b in keep:                                       # gộp đoạn chồng nhau
        if out and a < out[-1][1]:
            out[-1] = (out[-1][0], max(b, out[-1][1]))
        else:
            out.append((a, b))
    return out


def _digits(s):
    d = re.sub(r"\D", "", s)
    return "0" + d[2:] if d.startswith("84") and len(d) == 11 else d


class Redactor:
    def __init__(self):
        self.token_of, self.value_of, self.n = {}, {}, {"SĐT": 0, "ĐỊA_CHỈ": 0}

    def _token(self, kind, key, original):
        if key not in self.token_of:
            self.n[kind] += 1
            tok = f"[{kind}_{self.n[kind]}]"
            self.token_of[key], self.value_of[tok] = tok, original
        return self.token_of[key]

    def _collect(self, obj, key=None):
        if isinstance(obj, dict):
            for k, v in obj.items():
                self._collect(v, str(k).lower())
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                self._collect(v, key)
        elif isinstance(obj, str) and obj.strip():
            if key in PHONE_KEYS and len(_digits(obj)) >= 9:
                self._token("SĐT", _digits(obj), obj)
            elif key in ADDRESS_KEYS and len(obj) >= 6:
                self._token("ĐỊA_CHỈ", obj.strip().lower(), obj.strip())

    def redact_text(self, s):
        for key, tok in sorted(self.token_of.items(), key=lambda kv: -len(kv[0])):
            if not key.isdigit():
                s = re.sub(re.escape(key), tok, s, flags=re.I)
        s = PHONE_RX.sub(lambda m: self._token("SĐT", _digits(m.group()), m.group()), s)
        if ner_enabled() and ner_preload():
            for a, b in reversed(_hybrid_address_spans(s)):
                val = s[a:b].strip()
                s = s[:a] + self._token("ĐỊA_CHỈ", val.lower(), val) + s[b:]
            return s
        s = CUE_ADDRESS_RX.sub(lambda m: m.group()[:m.start(1) - m.start()]
                               + self._token("ĐỊA_CHỈ", m.group(1).strip().lower(), m.group(1).strip()), s)
        s = ADDRESS_RX.sub(lambda m: self._token("ĐỊA_CHỈ", m.group().strip().lower(), m.group().strip()), s)
        return PLAIN_ADDRESS_RX.sub(lambda m: self._token("ĐỊA_CHỈ", m.group().strip().lower(), m.group().strip()), s)

    def redact(self, obj):
        self._collect(obj)

        def walk(o):
            if isinstance(o, dict):
                return {k: walk(v) for k, v in o.items()}
            if isinstance(o, (list, tuple)):
                return [walk(v) for v in o]
            return self.redact_text(o) if isinstance(o, str) else o
        return walk(obj)

    def restore(self, s):
        for tok, val in self.value_of.items():
            s = s.replace(tok, val)
        return s


KEYED_ADDRESS_RX = re.compile(r'(\b(?:%s)"?\s*[:=]\s*"?)([^"\n…]+?)(?=["…]|\s\(|$)' % "|".join(sorted(ADDRESS_KEYS)), re.M)


def mask_for_log(s):
    s = KEYED_ADDRESS_RX.sub(lambda m: m.group(1) + "[địa chỉ]", s)
    s = PHONE_RX.sub(lambda m: (lambda d: d[:3] + "****" + d[-3:])(_digits(m.group())), s)
    s = CUE_ADDRESS_RX.sub(lambda m: m.group()[:m.start(1) - m.start()] + "[địa chỉ]", s)
    s = ADDRESS_RX.sub("[địa chỉ]", s)
    return PLAIN_ADDRESS_RX.sub("[địa chỉ]", s)
