"""Kiểm offline các nhánh planner bằng code thêm ngày 01/11 (PLAN-2026-11-01 B1, B2, B7).

Chỉ dùng câu dev (BTCL-041/042/061/062) và câu tự viết; không đọc holdout.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from harness import agent
from harness.textnorm import fold


def _session():
    s = agent.CallSession.__new__(agent.CallSession)
    s.policy_gap = None
    return s


def run():
    s = _session()
    # B1: thời hạn khách hỏi dài hơn mọi thời hạn đổi/trả/hoàn trong tài liệu → no_info
    for t in ("Nếu dùng hai năm rồi muốn trả lại thì bên em có cam kết hoàn đủ tiền không?",
              "Chuyện hoàn tiền sau hai năm hôm trước ấy em.",
              "Mua 6 tháng rồi trả hàng được hoàn tiền không em?"):
        gap = s._policy_gap(t, fold(t))
        assert gap and gap["policy"], t
    # thời hạn nằm trong chính sách → không phải gap
    for t in ("Trong 7 ngày thì đổi trả được không em?", "Bảo hành hai năm đúng không em?",
              "Hoàn tiền mất mấy ngày vậy em?"):
        assert s._policy_gap(t, fold(t)) is None, t
    # câu hỏi lại văn bản chỉ là gap khi lượt trước đã là gap
    doc = "Cô muốn hỏi xem có văn bản nào trong chính sách xác nhận điều đó không ạ?"
    assert s._policy_gap(doc, fold(doc)) is None
    s.policy_gap = {"topic": "x", "policy": []}
    assert s._policy_gap(doc, fold(doc)) == s.policy_gap

    # B2: xin thông tin của khách khác
    for t in ("Bên em có thể cho số của khách từng mua mẫu này để anh hỏi không?",
              "Chuyện xin số người mua khác hôm trước ấy.",
              "Cho chị xin địa chỉ của khách đã mua nhé"):
        assert agent.OTHER_PII_RX.search(fold(t)), t
    for t in ("Anh hỏi AirPure Y cho người quen.", "Số của em là bao nhiêu để chị gọi lại?",
              "Cho chị xin thông tin máy này nhé", "Địa chỉ của chị là 12 Lê Lợi."):
        assert not agent.OTHER_PII_RX.search(fold(t)), t

    # trả hàng giả định không phải yêu cầu trả hàng
    t = fold("Nếu dùng không hợp thì trả hàng được không em?")
    assert agent.HYPO_RX.search(t) and agent.REFUND_RX.search(t)
    print("planner rules checks OK")


if __name__ == "__main__":
    run()
