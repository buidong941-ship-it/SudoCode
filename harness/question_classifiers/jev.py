"""Remote Jev binary classifier. PII is redacted before the request leaves Kaggle."""

import time

from core.config import settings
from core.pii import Redactor
from harness.question_classifiers.base import QuestionPrediction


class JevQuestionClassifier:
    def __init__(self, threshold=None):
        self.threshold = settings.question_clf_tau if threshold is None else float(threshold)
        self._client = None
        self._cache = {}

    def _get_client(self):
        if self._client is None:
            from typesafe_sdk import TypeSafeClient
            if not settings.typesafe_api_key:
                raise RuntimeError("TYPESAFE_API_KEY chưa đặt")
            self._client = TypeSafeClient(api_key=settings.typesafe_api_key, timeout=settings.jev_timeout_s,
                                          model=settings.jev_model, base_url=settings.jev_base_url,
                                          headers={"Connection": "close"})
        return self._client

    def predict(self, text):
        if text in self._cache:
            p, elapsed, error = self._cache[text]
            return QuestionPrediction("jev", p, self.threshold, elapsed, error)
        from typesafe_sdk import Choice

        started = time.perf_counter()
        try:
            safe_text = Redactor().redact({"agent_sentence": text})["agent_sentence"]
            question = "Câu agent này có hỏi khách, xin thông tin, yêu cầu khách làm/chọn/xác nhận, hoặc mời khách nêu nhu cầu không?"
            criteria = {
                "yes": "Có hỏi hoặc yêu cầu khách phản hồi/thực hiện điều gì.",
                "no": "Chỉ chào, cảm ơn, thông báo, khẳng định, hứa hẹn hoặc dặn dò; không yêu cầu phản hồi.",
            }
            result = self._get_client().system_one(
                state={"role": "nhân viên chăm sóc khách hàng", "agent_sentence": safe_text},
                questions={"is_question": Choice(instructions=question, criteria=criteria)},
                model=settings.jev_model,
            )
            answer = result.choices["is_question"]
            probs = dict(answer.probabilities or {})
            if "yes" in probs:
                p = float(probs["yes"])
            elif answer.choice == "yes":
                p = float(answer.confidence)
            else:
                p = 1.0 - float(answer.confidence)
            p = max(0.0, min(1.0, p))
            error = None
        except Exception as exc:
            p, error = None, f"{type(exc).__name__}: {str(exc)[:180]}"
        elapsed = (time.perf_counter() - started) * 1000
        if error is None:
            self._cache[text] = (p, elapsed, error)
        return QuestionPrediction("jev", p, self.threshold, elapsed, error)
