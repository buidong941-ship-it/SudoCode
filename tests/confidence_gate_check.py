"""Focused, offline checks for the experimental hybrid confidence gate."""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from harness import extractor, llm_extract
from harness.rule_confidence import customer, empty, question


def run():
    c = customer("Phòng 25m².", {"room_area_m2": 25})
    assert c["certified"] and all(c["checks"].values()), c
    assert not customer("Phòng 25m², ngân sách 5 triệu.",
                        {"room_area_m2": 25, "budget_vnd": 5_000_000})["certified"]
    assert not customer("Dạ 25.", {}, "Phòng rộng bao nhiêu?")["certified"]
    assert not customer("Không phải phòng 25m².", {"room_area_m2": 25})["certified"]
    q = extractor.agent_questions("Phòng rộng bao nhiêu?", {})
    assert question("Phòng rộng bao nhiêu?", q)["certified"]
    assert not question("Chị lên địa chỉ giúp em nhé.",
                        extractor.agent_questions("Chị lên địa chỉ giúp em nhé.", {}))["certified"]
    with patch.object(extractor.settings, "extractor_backend", "hybrid"), \
         patch.object(extractor.settings, "extractor_confidence_gate", True), \
         patch.object(extractor.settings, "agent_question_backend", "current"), \
         patch.object(extractor.settings, "agent_claim_backend", "current"), \
         patch.object(llm_extract, "agent", side_effect=AssertionError("Qwen should be skipped")):
        meta = {}
        questions, claims = extractor.analyze_agent("Phòng rộng bao nhiêu?", {}, meta)
        assert questions == q and claims == [] and meta["rule_certified_sentences"] == 1, meta
        assert meta["agent_qwen_skipped"] is True
    uncertain = "Chị lên địa chỉ giúp em nhé."
    with patch.object(extractor.settings, "extractor_backend", "hybrid"), \
         patch.object(extractor.settings, "extractor_confidence_gate", True), \
         patch.object(extractor.settings, "agent_question_backend", "current"), \
         patch.object(extractor.settings, "agent_claim_backend", "current"), \
         patch.object(llm_extract, "agent", return_value=([{"slot": "address", "type": "open", "text": uncertain}], [])) as call:
        questions, _ = extractor.analyze_agent(uncertain, {})
        assert questions[0]["slot"] == "address" and call.call_count == 1
    with patch.object(extractor.settings, "extractor_backend", "hybrid"), \
         patch.object(extractor.settings, "extractor_confidence_gate", True), \
         patch.object(extractor.settings, "agent_question_backend", "jev_slots_experimental"), \
         patch.object(extractor.settings, "agent_claim_backend", "current"), \
         patch.object(llm_extract, "agent", side_effect=AssertionError("question-only sentence must not reach Qwen")), \
         patch("harness.question_classifiers.jev_slots.classify_agent_questions",
               return_value=[{"slot": "address", "type": "open", "text": uncertain}]) as jev:
        questions, claims = extractor.analyze_agent(uncertain, {})
        assert questions[0]["slot"] == "address" and claims == [] and jev.call_count == 1
    def failed_jev(text, known_values, meta):
        meta["jev_slot_errors"] = ["timeout"]
        return []
    with patch.object(extractor.settings, "extractor_backend", "hybrid"), \
         patch.object(extractor.settings, "extractor_confidence_gate", True), \
         patch.object(extractor.settings, "agent_question_backend", "jev_slots_experimental"), \
         patch.object(extractor.settings, "agent_claim_backend", "current"), \
         patch("harness.question_classifiers.jev_slots.classify_agent_questions", side_effect=failed_jev), \
         patch.object(llm_extract, "agent", return_value=([{"slot": "address", "type": "open", "text": uncertain}], [])) as fallback:
        questions, _ = extractor.analyze_agent(uncertain, {}, {})
        assert questions[0]["slot"] == "address" and fallback.call_count == 1
    with patch.object(extractor.settings, "extractor_backend", "hybrid"), \
         patch.object(extractor.settings, "extractor_confidence_gate", True), \
         patch.object(extractor.settings, "extractor_async", True), \
         patch.object(llm_extract, "submit_customer_slots", side_effect=AssertionError("Qwen should be skipped")):
        meta = {}
        slots, pending = extractor.customer_slots_start("Phòng 25m².", "2026-10-15", meta)
        assert slots == {"room_area_m2": 25} and pending is None and meta["customer_qwen_skipped"]
    # Chứng nhận rỗng: không giá trị luật, không cue nào (cả bản có dấu lẫn mất dấu).
    assert empty("Dạ em cảm ơn nhé.", {})["certified"]
    for t, ctx in [("Chị sẽ so thêm rồi phản hồi.", None), ("Anh muốn chờ bạn quyết cùng.", None),
                   ("Anh muốn đợi bạn quyết định cùng nhau.", None), ("ship ve 12 le loi giup em", None),
                   ("chi muon chuyen khoan truoc", None), ("Vậy giá bên kia rẻ hơn.", None),
                   ("Ừ được em.", "Chị lấy màu xám nhé?"), ("cái hôm trước ấy em", None)]:
        assert not empty(t, extractor.customer_slots_rules(t, "2026-10-15"), ctx)["certified"], t
    assert not empty("Phòng 25m².", {"room_area_m2": 25})["certified"]
    with patch.object(extractor.settings, "extractor_backend", "hybrid"),          patch.object(extractor.settings, "extractor_confidence_gate", True),          patch.object(extractor.settings, "extractor_jev_hybrid", True),          patch.object(extractor.settings, "extractor_async", True),          patch("harness.jev_hybrid.labels", side_effect=AssertionError("Jev should be skipped")),          patch.object(llm_extract, "submit_customer_slots", side_effect=AssertionError("Qwen should be skipped")):
        meta = {}
        slots, pending = extractor.customer_slots_start("Dạ em cảm ơn nhé.", "2026-10-15", meta)
        assert slots == {} and pending is None and meta["backend"] == "hybrid:certified_empty", meta
    print("confidence gate checks OK")


if __name__ == "__main__":
    run()
