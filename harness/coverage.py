"""Kiểm đủ nội dung của bản nháp theo plan, TRƯỚC khi gửi khách (cùng chỗ với guardrails.check).

1. Nội dung bắt buộc theo goal: giá báo, mã đơn + tổng tiền + ngày giao, tiền hoàn/bù, tổng giỏ, giờ hẹn, trạng thái đơn.
2. Câu hỏi theo `question_slot` của plan: không được hỏi khi plan không hỏi, tối đa 1 câu, không hỏi mở lại slot đã biết.
Trả danh sách lỗi (tiếng Việt, dùng làm retry_note). Hỏi khác slot của plan chỉ ghi log, không chặn.
"""
import logging
import re

from harness import extractor
from harness.textnorm import find_money, fold

log = logging.getLogger("coverage")


def _has_money(text, v):
    return not v or v in {x for _, _, x in find_money(text)}


def _has_date(text, iso):
    if not iso or len(iso) < 10:
        return True
    d, m = int(iso[8:10]), int(iso[5:7])
    return iso[:10] in text or bool(re.search(rf"\b0?{d}/0?{m}\b|\b0?{d} thang 0?{m}\b", fold(text)))


def _has_time(text, iso):
    if not iso or len(iso) < 16:
        return True
    h, mi = int(iso[11:13]), iso[14:16]
    hours = {h, h - 12} if h > 12 else {h}
    alt = "|".join(str(x) for x in hours)
    return bool(re.search(rf"\b0?({alt})\s*(h|gio|:{mi})", fold(text)))


def content(text, goals, facts):
    out = []
    q = facts.get("quote") or {}
    for g in goals:
        if g in ("quote", "recommend") and q.get("final_price_vnd") and not _has_money(text, q["final_price_vnd"]):
            out.append(f"thiếu giá bán {q['final_price_vnd']:,}đ".replace(",", "."))
        elif g == "order_created" and facts.get("order"):
            o = facts["order"]
            miss = [x for x in (o.get("order_id") or "").split(", ") if x and x.lower() not in text.lower()]
            if miss:
                out.append(f"thiếu mã đơn {', '.join(miss)}")
            if not _has_money(text, o.get("total_vnd")):
                out.append(f"thiếu tổng tiền {o['total_vnd']:,}đ".replace(",", "."))
            if not _has_date(text, o.get("estimated_delivery")):
                out.append("thiếu ngày giao dự kiến (dạng ngày/tháng)")
        elif g == "order_updated" and facts.get("update"):
            u = facts["update"]
            for k, name in (("refund_vnd", "tiền hoàn lại"), ("extra_payment_vnd", "tiền bù thêm")):
                if u.get(k) and not _has_money(text, u[k]):
                    out.append(f"thiếu {name} {u[k]:,}đ".replace(",", "."))
        elif g == "cart_total" and facts.get("cart") and not _has_money(text, facts["cart"].get("total_vnd")):
            out.append(f"thiếu tổng tiền giỏ {facts['cart']['total_vnd']:,}đ".replace(",", "."))
        elif g == "callback_scheduled" and facts.get("callback") and not _has_time(text, facts["callback"].get("callback_at")):
            out.append("thiếu giờ hẹn gọi lại")
        elif g == "order_status" and facts.get("orders"):
            f = fold(text)
            if not any((o.get("order_id") and o["order_id"].lower() in text.lower())
                       or (o.get("estimated_delivery") and _has_date(text, o["estimated_delivery"])) for o in facts["orders"]) \
                    and not re.search(r"\b(dang giao|da giao|van chuyen|cho (xu ly|xac nhan|lay hang)|da huy|hoan)\b", f):
                out.append("thiếu trạng thái hoặc ngày giao của đơn")
    return out


def questions(text, question_slot, known):
    qs = extractor.agent_questions(text, known)
    out = []
    if question_slot is None and any(q["type"] == "open" for q in qs):
        out.append("lượt này không được đặt câu hỏi nào")
    elif len(qs) > 1:
        out.append("chỉ được hỏi đúng 1 câu")
    for q in qs:
        if q["type"] == "open" and q["slot"] != question_slot and q["slot"] in known:
            out.append(f"không hỏi lại {q['slot']} (đã biết)")
        elif question_slot and q["slot"] != question_slot:
            log.info("hỏi %s, plan chỉ định %s: %s", q["slot"], question_slot, q["text"][:80])
    return out


def coverage(text, plan, known=None):
    known = plan.get("KNOWN") if known is None else known
    return content(text, plan.get("goals", []), plan.get("facts", {})) + questions(text, plan.get("question_slot"), known or {})
