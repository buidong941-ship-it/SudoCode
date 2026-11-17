"""Guardrails: kiểm câu trả lời TRƯỚC khi gửi khách.

1. Số tiền lạ: mọi số tiền trong lời agent phải có trong tập "được phép" (kết quả tool lượt này, báo giá đã lưu, số khách vừa nói).
2. Lộ nội bộ: giá nhập (policy NB-01), giá sàn `_internal_*` của tool, tên nhà cung cấp.
3. PII: CCCD / STK không được xuất hiện nguyên văn.
4. Nhận là người thật.
5. Bình luận/chê giá đối thủ.
Vi phạm → trả danh sách lý do; harness sinh lại 1 lần, vẫn sai thì dùng câu an toàn.
"""
import os
import re

from core.config import settings
from harness.lexicon import rx as lexrx
from harness.textnorm import BANK_RX, CCCD_RX, PHONE_RX, find_money, fold


def _import_prices():
    out = set()
    try:
        txt = open(os.path.join(settings.btc_dir, "policy", "ghi-chu-nhap-hang-NOI-BO.md"), encoding="utf-8").read()
        out = {int(m.group(1).replace(".", "")) for m in re.finditer(r"\|\s*SKU-[A-Z0-9-]+\s*\|\s*([\d.]{6,})\s*\|", txt)}
    except OSError:
        pass
    return out


IMPORT_PRICES = _import_prices()
# 06/11: mẫu kiểm câu trả lời nằm trong harness/lexicon/guardrails.json (ghi chú nguồn + ví dụ ở đó)
HUMAN_RX = lexrx.rx("guardrails", "HUMAN_RX")
COMPETITOR_RX = lexrx.rx("guardrails", "COMPETITOR_RX")
INTERNAL_MENTION_RX = lexrx.rx("guardrails", "INTERNAL_MENTION_RX")


def collect_numbers(obj, out=None):
    out = set() if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not str(k).startswith("_"):
                collect_numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_numbers(v, out)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool) and obj >= 1000:
        out.add(int(obj))
    return out


PAST_RX = lexrx.rx("guardrails", "PAST_RX")
# goal → (mẫu bắt buộc phải có trong câu trả lời, ghi chú gửi generator khi sinh lại): các mục REQUIRED_* của guardrails.json
REQUIRED = {e["goal"]: (lexrx.rx("guardrails", k), e["message"])
            for k, e in lexrx.load("guardrails")["patterns"].items() if e.get("goal")}


def _sentence_at(text, pos):
    starts = [m.end() for m in re.finditer(r"[.!?]\s+", text[:pos])]
    st = starts[-1] if starts else 0
    m = re.search(r"[.!?](\s|$)", text[pos:])
    return text[st:pos + (m.start() + 1 if m else len(text))]


PRICE_CUE_RX = lexrx.rx("guardrails", "PRICE_CUE_RX")     # cụm đứng ngay trước số tiền → số đó là "giá sản phẩm"
PROMO_NOUN_RX = lexrx.rx("guardrails", "PROMO_NOUN_RX")
PROMO_POS_RX = lexrx.rx("guardrails", "PROMO_POS_RX")
PROMO_NEG_RX = lexrx.rx("guardrails", "PROMO_NEG_RX")
SHIP_ONLY_RX = lexrx.rx("guardrails", "SHIP_ONLY_RX")


def _promo_signature(pr, s):
    f = fold(s)
    if pr.get("type") == "gift" and pr.get("gift_name"):
        if re.search(r"\btang\b", f) and " ".join(fold(pr["gift_name"]).split()[:2]) in f:
            return True
    if pr.get("type") == "fixed" and pr.get("discount_vnd") and any(v == pr["discount_vnd"] for _, _, v in find_money(s)):
        return True
    if pr.get("discount_percent") and re.search(rf"\b{pr['discount_percent']}\s*%", f):
        return True
    end = pr.get("end") or ""
    if len(end) == 10:
        d, m = int(end[8:]), int(end[5:7])
        if re.search(rf"\b0?{d}/0?{m}\b", f):
            return True
    return False


def promo_problems(text, promos):
    """D22: câu khẳng định đang có KM phải có căn cứ trong kết quả tool CỦA CUỘC GỌI NÀY.
    promos = {"active": [KM đang áp dụng, không tính COD-0/freeship], "expired": [KM hết hạn]} (dict theo catalog)."""
    out = []
    from harness.assertions import asserted_text
    for s in re.split(r"(?<=[.!?])\s+", text):
        positive = fold(asserted_text(s))
        if re.search(r"\b(giu|ghi|them|tang)(\s+\w+){0,4}\s+qua\b", positive) and not re.search(r"\b(khong|chua|chang)\b", positive):
            if not any(p.get('type') == 'gift' for p in promos.get('active', [])):
                expired = any(p.get('type') == 'gift' for p in promos.get('expired', []))
                out.append('nói chương trình quà tặng đã hết hạn như còn hiệu lực' if expired else 'hứa quà tặng nhưng tool chưa xác nhận có chương trình quà tặng')
        f = fold(s)
        if s.rstrip().endswith("?") or not PROMO_POS_RX.search(f) or not PROMO_NOUN_RX.search(f) or PROMO_NEG_RX.search(f):
            continue
        if SHIP_ONLY_RX.search(f) and not re.search(r"(giam|\btang\b|qua tang|%)", SHIP_ONLY_RX.sub(" ", f)):
            continue
        if not promos.get("active"):
            out.append("khẳng định đang có khuyến mãi nhưng tool trong cuộc gọi không có khuyến mãi nào đang áp dụng; "
                       "không được nói có khuyến mãi/ưu đãi/quà tặng")
            break
        old = [pr for pr in promos.get("expired") or () if _promo_signature(pr, s)]
        if old and not any(_promo_signature(pr, s) for pr in promos["active"]):
            out.append(f"nói chương trình {old[0]['promo_code']} đã hết hạn như còn hiệu lực")
            break
    # V3-011 (05/11): "giảm 50%" không kèm chữ "khuyến mãi" lọt qua vòng trên. Mức giảm phần trăm khẳng định trong câu trả lời
    # phải trùng discount_percent của một KM đang áp dụng theo tool của cuộc gọi (câu hỏi lại / câu phủ định thì bỏ qua).
    ok_pct = {int(pr["discount_percent"]) for pr in promos.get("active") or () if pr.get("discount_percent")}
    for s in re.split(r"(?<=[.!?])\s+", text):
        f = fold(s)
        if s.rstrip().endswith("?") or PROMO_NEG_RX.search(f) or re.search(r"\b(khong|chua|chang)\b", f):
            continue
        for m in re.finditer(r"(giam|bot|chiet khau|off|uu dai)\D{0,12}?(\d{1,2})\s*%", f):
            if int(m.group(2)) not in ok_pct:
                out.append(f"nói giảm {m.group(2)}% nhưng tool của cuộc gọi không có KM {m.group(2)}% đang áp dụng")
                return out
    return out


_NUM_WORD = {"mot": 1, "hai": 2, "ba": 3, "bon": 4, "nam": 5, "sau": 6, "muoi hai": 12, "muoi tam": 18}
WARRANTY_RX = lexrx.rx("guardrails", "WARRANTY_RX")


def warranty_problems(text, allowed_months):
    """1c J1 (06/11): thời hạn bảo hành khẳng định trong câu trả lời phải trùng `warranty_months` (catalog) của sản phẩm
    đang nói trong cuộc gọi. RT-01: khách viện "quản lý hứa 3 năm", agent nói "đã ghi bảo hành 3 năm" (catalog 12 tháng).
    Bỏ qua câu hỏi lại, câu phủ định, và bảo hành mở rộng / gói mua thêm."""
    if not allowed_months:
        return []
    for s in re.split(r"(?<=[.!?])\s+", text):
        f = fold(s)
        if s.rstrip().endswith("?") or re.search(r"\b(khong|chua|chang|mo rong|goi|mua them)\b", f):
            continue
        for m in WARRANTY_RX.finditer(f):
            n = int(m.group(1)) if m.group(1).isdigit() else _NUM_WORD[m.group(1)]
            months = n * (12 if m.group(2) == "nam" else 1)
            if months not in allowed_months:
                ok = ", ".join(f"{v} tháng" for v in sorted(allowed_months))
                return [f"nói bảo hành {months} tháng nhưng catalog của sản phẩm trong cuộc gọi là {ok}; "
                        f"chỉ được nói đúng thời hạn bảo hành của catalog, không hứa thêm"]
    return []


import json as _json
from pathlib import Path as _Path

COMMITMENTS = [dict(c, rx=re.compile(c["pattern"])) for c in
               _json.loads(_Path(__file__).with_name("commitments.json").read_text(encoding="utf-8"))["commitments"]]


def _committed(text, rx):
    """Các vị trí khớp `rx` (trên bản fold) mà mệnh đề chứa nó có thể bị nghe như cam kết (stance.COMMITMENT)."""
    from harness import stance
    return [sp for sp in stance.spans_rx(text, rx) if stance.stance_at(text, *sp) in stance.COMMITMENT]


def commitment_problems(text, goals):
    """CONTRACT_V2: nói 'đã làm X' phải có goal kết quả X (đã qua validator) trong lượt này."""
    have = set(goals or ())
    return [c["message"] for c in COMMITMENTS if not have & set(c["allowed_goals"]) and _committed(text, c["rx"])]


def warranty_problems_v2(text, allowed_months):
    """Như warranty_problems nhưng xét từng giá trị theo mệnh đề chứa nó (stance) thay vì bỏ qua cả câu có chữ 'không'.
    'Không lo ạ, máy bảo hành 3 năm' bị bắt; 'hiện chưa có chính sách bảo hành 3 năm' không bị bắt."""
    if not allowed_months:
        return []
    from harness import stance
    f = stance.pfold(text)
    for m in WARRANTY_RX.finditer(f):
        sents = stance.clauses(text)
        cl = next(((s, e) for s, e, _ in sents if s <= m.start() < max(e, s + 1)), (0, len(f)))
        if re.search(r"\b(mo rong|goi|mua them)\b", f[cl[0]:cl[1]]):
            continue
        if stance.stance_at(text, m.start(), m.end()) not in stance.COMMITMENT:
            continue
        n = int(m.group(1)) if m.group(1).isdigit() else _NUM_WORD[m.group(1)]
        months = n * (12 if m.group(2) == "nam" else 1)
        if months not in allowed_months:
            ok = ", ".join(f"{v} tháng" for v in sorted(allowed_months))
            return [f"nói bảo hành {months} tháng nhưng catalog của sản phẩm trong cuộc gọi là {ok}; "
                    f"chỉ được nói đúng thời hạn bảo hành của catalog, không hứa thêm"]
    return []


GIFT_PROMISE_RX = re.compile(r"\b(giu|ghi|them|tang)(\s+\w+){0,4}\s+qua\b")
PCT_RX = re.compile(r"(giam|bot|chiet khau|off|uu dai)\D{0,12}?(\d{1,2})\s*%")
CURATIVE_RX = re.compile(r"\b(chua|dieu tri|tri)\s+(duoc\s+)?(benh|hen|tac tia|viem)|\btang tiet sua\b")


def stance_problems(text, promos):
    """CONTRACT_V2: hứa quà, mức giảm %, công dụng chữa bệnh — xét theo stance của từng vị trí (một luật phủ định chung)."""
    out = []
    if promos is not None:
        if _committed(text, GIFT_PROMISE_RX) and not any(p.get("type") == "gift" for p in promos.get("active", [])):
            expired = any(p.get("type") == "gift" for p in promos.get("expired", []))
            out.append('nói chương trình quà tặng đã hết hạn như còn hiệu lực' if expired
                       else 'hứa quà tặng nhưng tool chưa xác nhận có chương trình quà tặng')
        ok_pct = {int(pr["discount_percent"]) for pr in promos.get("active") or () if pr.get("discount_percent")}
        from harness import stance
        for s, e in _committed(text, PCT_RX):
            pct = int(PCT_RX.match(stance.pfold(text), s).group(2))
            if pct not in ok_pct:
                out.append(f"nói giảm {pct}% nhưng tool của cuộc gọi không có KM {pct}% đang áp dụng")
                break
    if _committed(text, CURATIVE_RX):
        out.append('không được khẳng định công dụng điều trị/y tế chưa có nguồn; chuyển chuyên viên và không xác nhận công dụng')
    return out


# CONTRACT_V2: số tiền khách nêu bị đọc như giá sản phẩm khi "giá" làm chủ ngữ của số trong cùng mệnh đề, kể cả có tên
# SP chen giữa ("giá HikePro hiện là 1.000.000đ"); không tính khi khoảng giữa nói ngân sách / chênh lệch / phí / bên khác,
# hoặc mệnh đề là thuật lại / hỏi / phủ định (stance chung). Full 09/11 V3-089: PRICE_CUE_RX chỉ xét cụm sát số nên lọt.
PRICE_GAP_EXCLUDE_RX = re.compile(r"\b(ngan sach|tam|khoang|duoi|tren|giam|phi|coc|hoan|ship|chenh|hon|bot|ben (kia|khac)"
                                  r"|cho khac|tiet kiem)\b")


def _price_subject_v2(text, s):
    from harness import stance
    t = stance.canon(text)
    if t != text:
        return False
    pre = next((stance.pfold(t[cs:s]) for cs, ce, _ in stance.clauses(t) if cs <= s < ce), None)
    if not pre:
        return False
    hits = list(re.finditer(r"\bgia\b", pre))
    if not hits:
        return False
    gap = pre[hits[-1].end():]
    if len(gap.split()) > 6 or PRICE_GAP_EXCLUDE_RX.search(gap):
        return False
    return stance.stance_at(t, s) in stance.ASSERTED


def _promo_problems_core(text, promos):
    """Phần KM của promo_problems không gồm hứa quà và mức giảm % (hai phần này chuyển sang stance_problems)."""
    out = []
    for s in re.split(r"(?<=[.!?])\s+", text):
        f = fold(s)
        if s.rstrip().endswith("?") or not PROMO_POS_RX.search(f) or not PROMO_NOUN_RX.search(f) or PROMO_NEG_RX.search(f):
            continue
        if SHIP_ONLY_RX.search(f) and not re.search(r"(giam|\btang\b|qua tang|%)", SHIP_ONLY_RX.sub(" ", f)):
            continue
        if not promos.get("active"):
            out.append("khẳng định đang có khuyến mãi nhưng tool trong cuộc gọi không có khuyến mãi nào đang áp dụng; "
                       "không được nói có khuyến mãi/ưu đãi/quà tặng")
            break
        old = [pr for pr in promos.get("expired") or () if _promo_signature(pr, s)]
        if old and not any(_promo_signature(pr, s) for pr in promos["active"]):
            out.append(f"nói chương trình {old[0]['promo_code']} đã hết hạn như còn hiệu lực")
            break
    return out


# Định danh kiểu code (snake_case ASCII, vd moved_reason, order_id, final_price_vnd): không bao giờ là lời nói tiếng Việt với khách.
FIELD_NAME_RX = re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]*[a-z0-9]\b")


def check(text, allowed_money, internal_numbers=(), forbidden_money=(), stale_money=(), goals=(), customer_money=(), promos=None,
          warranty=None):
    """customer_money: số tiền khách tự nói (ngân sách, giá bên khác) và không có trong tool — được nhắc lại
    ("ngân sách 5,5 triệu của anh") nhưng không được đọc như giá bán (B5, BTCL-031).
    promos: trạng thái KM theo tool của cuộc gọi (D22); None = không kiểm.
    warranty: tập `warranty_months` (catalog) của các sản phẩm đang nói trong cuộc gọi (1c J1); rỗng / None = không kiểm.
    CONTRACT_V2: phủ định/hỏi/giả định xét theo harness/stance.py, thêm kiểm cam kết đã thực hiện (commitments.json)."""
    if settings.contract_v2:
        problems = [] if promos is None else _promo_problems_core(text, promos)
        problems += warranty_problems_v2(text, warranty)
        problems += stance_problems(text, promos)
        problems += commitment_problems(text, goals)
    else:
        problems = [] if promos is None else promo_problems(text, promos)
        problems += warranty_problems(text, warranty)
        from harness.assertions import curative_problems
        problems += curative_problems(text)
    for s, _, v in find_money(text):
        if v in IMPORT_PRICES or v in internal_numbers:
            problems.append(f"lộ giá nội bộ {v}")
        elif v in customer_money and (PRICE_CUE_RX.search(fold(text[max(0, s - 30):s]))
                                      or (settings.contract_v2 and _price_subject_v2(text, s))):
            problems.append(f"đọc số tiền {v} khách nêu như giá sản phẩm")
        elif v in forbidden_money:
            problems.append(f"đọc lại giá {v} khách nêu, không khớp báo giá hiện tại")
        elif v in stale_money and not PAST_RX.search(fold(_sentence_at(text, s))):
            problems.append(f"nói giá cũ {v} như giá hiện tại (chỉ được nhắc kèm 'hôm trước', 'đã hết hạn'…)")
        elif v not in allowed_money:
            problems.append(f"số tiền {v} không có trong dữ liệu tool")
    if CCCD_RX.search(text) or any(not PHONE_RX.fullmatch(m.group()) for m in BANK_RX.finditer(text)):
        problems.append("lộ PII (CCCD/STK)")
    f = fold(text)
    if HUMAN_RX.search(f):
        problems.append("nhận là người thật")
    if COMPETITOR_RX.search(f):
        problems.append("bình luận đối thủ")
    if INTERNAL_MENTION_RX.search(f):
        problems.append("nhắc thông tin nội bộ")
    m = FIELD_NAME_RX.search(text)
    if m:
        problems.append(f"lộ tên trường kỹ thuật '{m.group()}'")   # cụm 3 (V3-158 "moved_reason"): lời nói không chứa định danh code
    for g in goals:
        if g in REQUIRED and not REQUIRED[g][0].search(f):
            problems.append(REQUIRED[g][1])
    return problems
