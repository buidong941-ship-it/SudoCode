#!/usr/bin/env python3
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("RAG_MODE", "bm25")

from core.config import settings
from core.llm.generator import Generator


def main():
    old_n = settings.gen_parallel_n
    old_generate = Generator.generate
    seen = []

    def fake(self, plan, retry_note=None, temperature=None):
        seen.append(temperature)
        time.sleep(0.08)
        self.fill_problems = []
        return f"candidate-{temperature}", 5, 80, None

    try:
        settings.gen_parallel_n = 2
        Generator.generate = fake
        out = Generator("qwen").generate_candidates({})
    finally:
        settings.gen_parallel_n = old_n
        Generator.generate = old_generate
    assert seen == [0.0, 0.7], seen
    assert [x["temperature"] for x in out] == [0.0, 0.7]
    assert all(x["parallel_total"] < sum(x["total"] for x in out) for x in out)
    print("TẤT CẢ OK: hai nhiệt độ chạy song song, thứ tự ưu tiên ổn định")


if __name__ == "__main__":
    main()
