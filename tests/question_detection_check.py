#!/usr/bin/env python3
"""Check metric-only Jev detection does not change the pre-response coverage path."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("RAG_MODE", "bm25")

from core.config import settings  # noqa: E402
from harness import extractor  # noqa: E402
from harness.coverage import coverage  # noqa: E402
from harness.question_classifiers import get_classifier  # noqa: E402


def main():
    old_enabled = settings.question_clf
    old_extractor = settings.extractor_backend
    old_predict = extractor.question_prob
    calls = []
    try:
        settings.question_clf = True
        settings.extractor_backend = "rules"
        extractor.question_prob = lambda sentence: (calls.append(sentence) or (0.99, 0.75))
        sentence = "Chị cân nhắc thêm nhé."
        plan = {"goals": ["closing"], "facts": {}, "KNOWN": {}, "question_slot": None}
        assert coverage(sentence, plan) == []
        assert calls == []
        questions, _ = extractor.analyze_agent(sentence, {})
        assert len(questions) == 1 and questions[0]["text"] == sentence
        assert calls == [sentence]
        assert extractor.agent_questions(sentence, {}) == []
        assert len(extractor.agent_questions(sentence, {}, use_classifier=True)) == 1
        try:
            get_classifier("local")
        except ValueError:
            pass
        else:
            raise AssertionError("backend model local cũ vẫn còn hoạt động")
    finally:
        settings.question_clf = old_enabled
        settings.extractor_backend = old_extractor
        extractor.question_prob = old_predict
    print("TẤT CẢ OK")


if __name__ == "__main__":
    main()
