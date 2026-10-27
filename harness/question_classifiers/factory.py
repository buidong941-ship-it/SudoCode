"""Backend selection: rules, local CPU model, or Jev; initialized once per process."""

from functools import lru_cache

from core.config import settings


@lru_cache(maxsize=3)
def get_classifier(backend=None):
    name = (backend or settings.question_classifier_backend).strip().lower()
    if name == "local":
        from harness.question_classifiers.local import LocalQuestionClassifier
        return LocalQuestionClassifier()
    if name == "jev":
        from harness.question_classifiers.jev import JevQuestionClassifier
        return JevQuestionClassifier()
    raise ValueError(f"QUESTION_CLF_BACKEND không hỗ trợ: {name!r}; chọn local hoặc jev")
