#!/usr/bin/env python3
"""Regression checks for selective customer extraction and facts_used accuracy."""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("RAG_MODE", "bm25")

from harness import extractor  # noqa: E402
from scripts.extract_eval import eval_facts_used  # noqa: E402


def load_jsonl(name):
    path = os.path.join(ROOT, "tests", "extract_eval", name)
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main():
    facts_report = eval_facts_used(load_jsonl("facts_used.jsonl"))
    assert facts_report["f1"] == 1.0, facts_report["errors"]

    missed_by_gate = []
    for row in load_jsonl("customer.jsonl"):
        rules = extractor.customer_slots_rules(row["text"], "2026-10-20")
        missing_from_rules = set(row["slots"]) - set(rules)
        if missing_from_rules and not extractor.customer_llm_candidate(row["text"], row.get("context")):
            missed_by_gate.append({"id": row["id"], "slots": sorted(missing_from_rules), "text": row["text"]})
    assert not missed_by_gate, missed_by_gate
    assert not extractor.customer_llm_candidate("Dạ, em cảm ơn chị ạ.")
    assert extractor.customer_llm_candidate("Dạ, nhà chị 3 người.")
    assert extractor.customer_llm_candidate("Dạ 3 ạ.", "Nhà chị có mấy người?")

    question_cases = [
        ("Anh gọi lại khi nào tiện nhé.", "callback_time"),
        ("Anh có thể lên địa chỉ nhé.", "address"),
        ("Chị lên địa chỉ đi ạ.", "address"),
        ("Chị có còn băn khoăn gì không?", "blocker"),
    ]
    for sentence, expected_slot in question_cases:
        questions = extractor.agent_questions(sentence, {})
        assert len(questions) == 1 and questions[0]["slot"] == expected_slot, (sentence, questions)

    current_price = extractor.agent_claims(
        "Dạ, giá 1.521.000đ đã bao gồm khuyến mãi RUN-10 đến 25/10.")
    assert ("price_vnd", 1_521_000) in {(c["field"], c["value"]) for c in current_price}
    assert ("price_quoted_vnd", 1_521_000) not in {(c["field"], c["value"]) for c in current_price}
    sold_out = extractor.agent_claims("Sản phẩm này hiện đang hết hàng.")
    assert ("promo_active", False) not in {(c["field"], c["value"]) for c in sold_out}
    promo = extractor.agent_claims("Anh có thể dùng mã khuyến mãi AIR-OCT để giảm 300.000đ nhé.")
    assert ("promo_active", True) in {(c["field"], c["value"]) for c in promo}
    print(f"TẤT CẢ OK: facts_used F1=100%, candidate gate không bỏ slot gold trên {len(load_jsonl('customer.jsonl'))} câu khách")


if __name__ == "__main__":
    main()
