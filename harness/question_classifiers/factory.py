"""Select a pretrained question detector without loading trained local artifacts."""

from functools import lru_cache

from core.config import settings


@lru_cache(maxsize=1)
def get_classifier(backend=None):
    name = (backend or settings.question_classifier_backend).strip().lower()
    if name == "jev":
        from harness.question_classifiers.jev import JevQuestionClassifier
        return JevQuestionClassifier()
    raise ValueError(f"QUESTION_CLF_BACKEND không hỗ trợ: {name!r}; chỉ hỗ trợ jev")
