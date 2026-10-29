"""Offline checks for the opt-in Jev slot backend and per-sentence fallback."""

from types import SimpleNamespace
from unittest.mock import patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.question_classifiers import jev_slots
from harness import extractor


def answer(slot, kind):
    return SimpleNamespace(choices={"slot": SimpleNamespace(choice=slot),
                                    "type": SimpleNamespace(choice=kind)})


class FakeClient:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.states = []

    def system_one(self, *, state, questions, model):
        self.states.append(state)
        assert set(questions) == {"slot", "type"}
        return next(self.answers)


def main():
    text = "Anh cho em xin địa chỉ giao hàng ạ. Em sẽ báo giá sau. Chị xác nhận mã đơn nhé."
    fake = FakeClient([answer("address", "open"), answer("none", "none"),
                       answer("order_id", "none")])
    meta = {}
    with patch.object(jev_slots, "_client", return_value=fake):
        questions = jev_slots.classify_agent_questions(text, {}, meta)
    assert len(fake.states) == 3, fake.states
    assert questions[0] == {"slot": "address", "type": "open", "text": "Anh cho em xin địa chỉ giao hàng ạ."}
    assert meta["jev_slot_requests"] == 3 and len(meta["jev_slot_errors"]) == 1, meta
    assert "jev_slots" in meta["fallback"]

    fake = FakeClient([answer("phone", "open")])
    with patch.object(jev_slots, "_client", return_value=fake):
        jev_slots.classify_agent_questions("Anh cho em xin số 0901234567 ạ.", {})
    assert "0901234567" not in str(fake.states), fake.states

    claim = {"field": "promo_active", "value": True, "text": "Giảm giá ạ."}
    with patch.object(extractor.settings, "extractor_backend", "hybrid"), \
         patch.object(extractor.settings, "agent_question_backend", "jev_slots_experimental"), \
         patch("harness.llm_extract.agent", return_value=([], [claim])), \
         patch.object(jev_slots, "classify_agent_questions", return_value=[{"slot": "address", "type": "open", "text": "Địa chỉ ạ?"}]) as classify:
        questions, claims = extractor.analyze_agent("Địa chỉ ạ?", {})
    assert questions[0]["slot"] == "address" and claims == [claim]
    classify.assert_called_once()

    # The latency experiment must not call Qwen on the agent reply at all.
    with patch.object(extractor.settings, "extractor_backend", "hybrid"), \
         patch.object(extractor.settings, "agent_claim_backend", "rules"), \
         patch.object(extractor.settings, "agent_question_backend", "jev_slots_experimental"), \
         patch("harness.llm_extract.agent", side_effect=AssertionError("agent Qwen called")), \
         patch.object(jev_slots, "classify_agent_questions", return_value=[{"slot": "address", "type": "open", "text": "Địa chỉ ạ?"}]):
        meta = {}
        questions, claims = extractor.analyze_agent("Địa chỉ ạ?", {}, meta)
    assert questions[0]["slot"] == "address" and claims == extractor.agent_claims("Địa chỉ ạ?")
    assert meta["agent_qwen_skipped"] is True
    print("jev_slots_check: OK")


if __name__ == "__main__":
    main()
