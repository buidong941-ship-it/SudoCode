"""Interchangeable question classifiers used by the agent extractor and Kaggle comparison."""

from harness.question_classifiers.factory import get_classifier

__all__ = ["get_classifier"]
