"""Offline routing checks for Jev labels and safe Qwen fallback."""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from harness import extractor, jev_hybrid, llm_extract


def run():
    with patch.object(extractor.settings, "extractor_backend", "hybrid"), \
         patch.object(extractor.settings, "extractor_confidence_gate", False), \
         patch.object(extractor.settings, "extractor_jev_hybrid", True), \
         patch.object(extractor.settings, "extractor_async", True), \
         patch.object(jev_hybrid, "labels", return_value={"room_area_m2"}), \
         patch.object(llm_extract, "submit_customer_slots", side_effect=AssertionError("grounded Jev should skip Qwen")):
        slots, pending = extractor.customer_slots_start("Phòng 25m².", "2026-10-15", {})
        assert slots == {"room_area_m2": 25} and pending is None

    with patch.object(extractor.settings, "extractor_backend", "hybrid"), \
         patch.object(extractor.settings, "extractor_confidence_gate", False), \
         patch.object(extractor.settings, "extractor_jev_hybrid", True), \
         patch.object(extractor.settings, "extractor_async", True), \
         patch.object(jev_hybrid, "labels", return_value={"budget_vnd"}), \
         patch.object(llm_extract, "submit_customer_slots", return_value={"future": None}) as qwen:
        _, pending = extractor.customer_slots_start("Phòng 25m².", "2026-10-15", {})
        assert pending is not None and qwen.call_count == 1

    with patch.object(extractor.settings, "extractor_backend", "hybrid"), \
         patch.object(extractor.settings, "extractor_confidence_gate", False), \
         patch.object(extractor.settings, "extractor_jev_hybrid", True), \
         patch.object(extractor.settings, "agent_claim_backend", "current"), \
         patch.object(jev_hybrid, "labels", return_value={"gia_ban"}), \
         patch("harness.question_classifiers.jev_slots.classify_agent_questions", return_value=[]), \
         patch.object(llm_extract, "agent", side_effect=AssertionError("grounded claim should skip Qwen")):
        _, claims = extractor.analyze_agent("Giá là 5 triệu.", {}, {})
        assert claims and claims[0]["field"] == "price_vnd"
    print("Jev hybrid checks OK")


if __name__ == "__main__":
    run()
