"""Qwen naturalizer request shape and fact anchors without a live model."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datagen.naturalize import anchors_kept, rewrite_call  # noqa: E402


class Client:
    def __init__(self):
        self.chat = SimpleNamespace(completions=self)
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps({"turns": ["À, cho chị hỏi AirPure X giá 5 triệu nhé."]}, ensure_ascii=False)))])


def run():
    original = "Chị hỏi AirPure X giá 5 triệu."
    c = Client()
    out = rewrite_call({"honorific": "chị", "persona": "khach_so_gia"}, "call_1",
                       {"customer_turns": [original]}, {}, c, "Qwen/Qwen3-4B", .7,
                       {"chat_template_kwargs": {"enable_thinking": False}})
    assert out == ["À, cho chị hỏi AirPure X giá 5 triệu nhé."]
    assert c.kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
    d = Client()
    rewrite_call({"honorific": "chị", "persona": "khach_so_gia"}, "call_1",
                 {"customer_turns": [original]}, {}, d, "deepseek-v4-flash", .7)
    assert "extra_body" not in d.kwargs
    assert anchors_kept(original, out[0])[0]
    assert not anchors_kept(original, "À, cho chị hỏi AirPure X giá 6 triệu nhé.")[0]
    print("naturalize backend checks OK")


if __name__ == "__main__":
    run()
