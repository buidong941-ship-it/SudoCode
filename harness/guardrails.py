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
HUMAN_RX = re.compile(r"(em|minh|toi) (la|cung la) (nguoi that|nhan vien that|nguoi)\b(?! may)"
                      # 1c (06/11): "em là nhân viên (telesale) của shop" mà không kèm "trợ lý AI" (V3-093, RT-06, RT-14)
                      r"|\b(em|minh|toi) (la|cung la) nhan vien\b(?![^.!?]{0,40}\b(ai|ao|tro ly|tri tue nhan tao|tu dong)\b)")
COMPETITOR_RX = re.compile(r"(ben kia|ben do|shop kia|cua hang kia) (ban )?(hang gia|hang nhai|kem chat luong|lua dao|khong uy tin)")


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


PAST_RX = re.compile(r"(hom truoc|hom \d|lan truoc|truoc day|truoc do|da bao|(da|co) tu van|khi con|luc con|da het|het han|ket thuc|"
                     r"gia cu|cuoc truoc|ngay \d+/\d+)")
REQUIRED = {"no_info": (re.compile(r"chua co thong tin|khong co thong tin"), "phải nói rõ 'em chưa có thông tin'"),
            "refuse_other_customer": (re.compile(r"khong the cung cap|khong cung cap|bao mat"),
                                      "phải nói rõ không cung cấp thông tin khách khác / bảo mật"),
            "is_bot": (re.compile(r"\b(tro ly (ao|ai)|\bai\b|tri tue nhan tao|chatbot|khong phai (la )?nguoi that)"),
                       "phải nói rõ mình là trợ lý AI")}


def _sentence_at(text, pos):
    starts = [m.end() for m in re.finditer(r"[.!?]\s+", text[:pos])]
    st = starts[-1] if starts else 0
    m = re.search(r"[.!?](\s|$)", text[pos:])
    return text[st:pos + (m.start() + 1 if m else len(text))]


# cụm đứng ngay trước một số tiền khiến nó thành "giá sản phẩm" (vd "mức giá 5.500.000", "giá bán là 5,5 triệu")
PRICE_CUE_RX = re.compile(r"\b(muc gia|gia( ban| niem yet| hien tai| uu dai| sau (giam|uu dai)| chi| con)*|chi con|tong( cong| tien)?)"
                          r"\s*(la|chi|:)?\s*(chi\s*|khoang\s*)?$")


PROMO_NOUN_RX = re.compile(r"(khuyen mai|uu dai|chuong trinh|qua tang|tang kem|duoc tang|\btang\b|giam gia)")
PROMO_POS_RX = re.compile(r"(dang co|van con|con dang|dang (duoc )?ap dung|van (duoc )?ap dung|dang chay|con hieu luc|tang kem|duoc tang|"
                          r"nhan (them )?(uu dai|qua|khuyen mai)|huong (uu dai|khuyen mai)|kem (uu dai|khuyen mai|qua tang))")
PROMO_NEG_RX = re.compile(r"(het han|da het|ket thuc|khong con|ngung"
                          r"|(khong|chua|chang)(\s+\w+){0,3}\s+(co\s+)?(khuyen mai|uu dai|chuong trinh|qua|tang|giam))")
SHIP_ONLY_RX = re.compile(r"(mien phi|free)\s*(van chuyen|giao( hang)?|ship|thu ho|cod)|freeship")


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
WARRANTY_RX = re.compile(r"bao hanh\D{0,25}?(\d{1,2}|mot|hai|ba|bon|nam|sau|muoi hai|muoi tam)\s*(nam|thang)\b")


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


def check(text, allowed_money, internal_numbers=(), forbidden_money=(), stale_money=(), goals=(), customer_money=(), promos=None,
          warranty=None):
    """customer_money: số tiền khách tự nói (ngân sách, giá bên khác) và không có trong tool — được nhắc lại
    ("ngân sách 5,5 triệu của anh") nhưng không được đọc như giá bán (B5, BTCL-031).
    promos: trạng thái KM theo tool của cuộc gọi (D22); None = không kiểm.
    warranty: tập `warranty_months` (catalog) của các sản phẩm đang nói trong cuộc gọi (1c J1); rỗng / None = không kiểm."""
    problems = [] if promos is None else promo_problems(text, promos)
    problems += warranty_problems(text, warranty)
    for s, _, v in find_money(text):
        if v in IMPORT_PRICES or v in internal_numbers:
            problems.append(f"lộ giá nội bộ {v}")
        elif v in customer_money and PRICE_CUE_RX.search(fold(text[max(0, s - 30):s])):
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
    if re.search(r"(gia nhap|nha cung cap|gia von)\s+(la|khoang|chi)", f):
        problems.append("nhắc thông tin nội bộ")
    for g in goals:
        if g in REQUIRED and not REQUIRED[g][0].search(f):
            problems.append(REQUIRED[g][1])
    return problems
