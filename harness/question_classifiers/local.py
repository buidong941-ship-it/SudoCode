"""CPU classifier trained by scripts/evaluate_question_clf_labels.py."""

import os
import pickle
import time

from core.config import settings
from harness.question_classifiers.base import QuestionPrediction
from harness.textnorm import fold


class LocalQuestionClassifier:
    def __init__(self, model_path=None):
        self.model_path = model_path or settings.question_clf_path
        with open(self.model_path, "rb") as fh:
            self.model = pickle.load(fh)
        if not all(k in self.model for k in ("clf", "vec", "tau")):
            raise ValueError(f"model question classifier thiếu khóa bắt buộc: {os.path.basename(self.model_path)}")

    def predict(self, text):
        started = time.perf_counter()
        p = float(self.model["clf"].predict_proba(self.model["vec"].transform([fold(text)]))[0, 1])
        return QuestionPrediction("local", p, float(self.model["tau"]), (time.perf_counter() - started) * 1000)
