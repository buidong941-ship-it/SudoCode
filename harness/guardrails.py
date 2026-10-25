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
HUMAN_RX = re.compile(r"(em|minh|toi) (la|cung la) (nguoi that|nhan vien that|nguoi)\b(?! may)")
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
            "is_bot": (re.compile(r"\b(tro ly (ao|ai)|\bai\b|tri tue nhan tao|chatbot|khong phai (la )?nguoi that)"),
                       "phải nói rõ mình là trợ lý AI")}


def _sentence_at(text, pos):
    starts = [m.end() for m in re.finditer(r"[.!?]\s+", text[:pos])]
    st = starts[-1] if starts else 0
    m = re.search(r"[.!?](\s|$)", text[pos:])
    return text[st:pos + (m.start() + 1 if m else len(text))]


def check(text, allowed_money, internal_numbers=(), forbidden_money=(), stale_money=(), goals=()):
    problems = []
    for s, _, v in find_money(text):
        if v in IMPORT_PRICES or v in internal_numbers:
            problems.append(f"lộ giá nội bộ {v}")
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
