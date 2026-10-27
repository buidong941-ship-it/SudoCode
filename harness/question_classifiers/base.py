"""Shared result contract for question classification backends."""

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class QuestionPrediction:
    backend: str
    probability: Optional[float]
    threshold: float
    latency_ms: float
    error: Optional[str] = None

    @property
    def is_question(self):
        return None if self.probability is None else self.probability >= self.threshold


class QuestionClassifier(Protocol):
    def predict(self, text: str) -> QuestionPrediction: ...
