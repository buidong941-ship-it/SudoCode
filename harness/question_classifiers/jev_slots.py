"""Experimental Jev slot/type extraction; default runtime path remains unchanged."""

import threading
import time

from core.config import settings
from core.pii import Redactor
from harness.llm_extract import QUESTION_SLOTS

SLOT_INSTRUCTIONS = (
    "Phân loại từng câu nhân viên: none nếu chỉ chào, thông báo, cảm ơn, cam kết, "
    "dặn dò hoặc đề nghị tự mình hỗ trợ mà không yêu cầu khách trả lời/làm gì. "
    "Nếu hỏi, xin thông tin, yêu cầu khách chọn/làm/xác nhận thì chọn slot của yêu cầu đầu tiên. "
    "Câu có dấu hỏi không tự động là yêu cầu khách; câu xin địa chỉ không có dấu hỏi vẫn là yêu cầu. "
    "Nếu có hỏi nhưng không khớp slot cụ thể, chọn other."
)
TYPE_INSTRUCTIONS = (
    "Loại câu hỏi: none khi câu không yêu cầu khách trả lời/làm gì; "
    "confirm chỉ khi đang xác minh một giá trị/điều đã nêu trong câu hoặc known_values; "
    "open nếu hỏi thông tin hay lựa chọn mới. Slot đã có trong bộ nhớ không tự làm câu thành confirm."
)
SLOT_CRITERIA = {"none": "Không có câu hỏi/yêu cầu khách; không cần phản hồi.", **QUESTION_SLOTS}
TYPE_CRITERIA = {
    "none": "Không có câu hỏi/yêu cầu khách.",
    "open": "Hỏi thông tin hoặc lựa chọn mới, không xác minh giá trị đã nêu.",
    "confirm": "Yêu cầu khách xác nhận một giá trị hoặc điều đã nêu rõ.",
}
_LOCAL = threading.local()


def _client():
    if not settings.typesafe_api_key:
        raise RuntimeError("Thiếu TYPESAFE_API_KEY")
    if not hasattr(_LOCAL, "client"):
        from typesafe_sdk import TypeSafeClient
        _LOCAL.client = TypeSafeClient(api_key=settings.typesafe_api_key, timeout=settings.jev_timeout_s,
                                       model=settings.jev_model, base_url=settings.jev_base_url,
                                       headers={"Connection": "close"})
    return _LOCAL.client


def classify_agent_questions(text, known_values, meta=None):
    """Classify every agent sentence; use rules for each invalid or failed result."""
    from typesafe_sdk import Choice
    from harness.extractor import _sentences, agent_questions

    meta = meta if meta is not None else {}
    out, errors = [], []
    start = time.perf_counter()
    requests = 0
    for sentence in _sentences(text):
        safe = Redactor().redact({"agent_sentence": sentence, "known_values": known_values})
        try:
            requests += 1
            result = _client().system_one(
                state={"role": "nhân viên chăm sóc khách hàng", **safe},
                questions={"slot": Choice(instructions=SLOT_INSTRUCTIONS, criteria=SLOT_CRITERIA),
                           "type": Choice(instructions=TYPE_INSTRUCTIONS, criteria=TYPE_CRITERIA)},
                model=settings.jev_model)
            slot = result.choices["slot"].choice
            kind = result.choices["type"].choice
            if slot not in SLOT_CRITERIA or kind not in TYPE_CRITERIA:
                raise ValueError("invalid_choice")
            if (slot == "none") != (kind == "none"):
                raise ValueError("slot_type_mismatch")
            if slot != "none":
                out.append({"slot": slot, "type": kind, "text": sentence})
        except Exception as exc:
            errors.append(type(exc).__name__ + ":" + str(exc)[:40])
            out.extend(agent_questions(sentence, known_values, use_classifier=False))
    meta["jev_slot_requests"] = requests
    meta["jev_slot_ms"] = round((time.perf_counter() - start) * 1000, 2)
    meta["jev_slot_errors"] = errors
    if errors:
        prior = meta.get("fallback")
        detail = "jev_slots:" + ",".join(errors[:3])
        meta["fallback"] = f"{prior} | {detail}" if prior else detail
    return out
