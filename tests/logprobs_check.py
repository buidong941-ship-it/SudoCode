#!/usr/bin/env python3
import math
import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("RAG_MODE", "bm25")

from core.llm.cache import make_key
from core.llm.deepseek import LLM, _label_logprobs
from harness import llm_extract
from harness.llm_extract import _logprob_ok
from core.config import settings


def main():
    text = '{"slot":"objection","label":"dat_qua"}'
    tokens = [{"token": c, "logprob": -0.2} for c in text]
    probs = _label_logprobs(text, tokens)
    assert math.isclose(probs["objection"][0], math.exp(-0.2))
    assert math.isclose(probs["dat_qua"][0], math.exp(-0.2))
    assert _label_logprobs(text, tokens[:-1]) == {}
    assert make_key("m", [], logprobs=False) != make_key("m", [], logprobs=True, top_logprobs=5)
    client = LLM.__new__(LLM)
    client.model, client.extra, client.provider = "mock", {}, "qwen"
    calls = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content=text),
                logprobs=SimpleNamespace(content=tokens))])

    client.c = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    captured = {}
    assert client.json("prompt", logprobs=True, top_logprobs=5, metadata=captured, cache=False) == {"slot": "objection", "label": "dat_qua"}
    assert calls[0]["logprobs"] is True and calls[0]["top_logprobs"] == 5
    assert captured["label_logprobs"]["objection"]
    old = settings.extract_logprob_thresholds
    old_on = settings.extract_logprobs
    old_call = llm_extract._call
    try:
        settings.extract_logprob_thresholds = {"objection": 0.7}
        settings.extract_logprobs = True
        assert _logprob_ok("objection", 0.8)
        assert not _logprob_ok("objection", 0.6)
        assert _logprob_ok("objection", None)
        def fake(prompt, schema, texts, meta):
            meta["label_logprobs"] = {"objection": [0.5], "ep_gia": [0.95]}
            return {"slots": [{"slot": "objection", "span": "giảm thêm", "label": "ep_gia"}]}, None
        llm_extract._call = fake
        meta = {}
        out = llm_extract.customer_slots("Em giảm thêm cho chị được không?", "2026-10-27", {}, "llm", meta)
        assert "objection" not in out and meta["dropped_spans"] == 1
    finally:
        settings.extract_logprob_thresholds = old
        settings.extract_logprobs = old_on
        llm_extract._call = old_call
    print("TẤT CẢ OK: ánh xạ logprob, cache key và ngưỡng tùy chọn")


if __name__ == "__main__":
    main()
