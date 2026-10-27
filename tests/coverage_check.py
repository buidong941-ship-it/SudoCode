#!/usr/bin/env python3
"""Kiểm harness/coverage.py (kiểm đủ nội dung theo plan) — không cần GPU/mạng.

    python tests/coverage_check.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("RAG_MODE", "bm25")

from core.llm.generator import question_slot, render_offline  # noqa: E402
from harness.coverage import coverage  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(("  OK  " if cond else "  SAI ") + msg)
    ok &= bool(cond)


quote = {"name": "Máy lọc không khí AirPure X", "final_price_vnd": 4_490_000, "list_price_vnd": 4_890_000, "promo_names": []}
plan = {"goals": ["quote"], "facts": {"quote": quote}, "KNOWN": {}, "question_slot": None}
check(coverage("Dạ máy này đang bán 4.490.000đ ạ.", plan) == [], "báo đúng giá thì qua")
check(any("thiếu giá bán" in p for p in coverage("Dạ máy này lọc tốt lắm ạ.", plan)), f"thiếu giá bị bắt")

plan = {"goals": ["closing"], "facts": {}, "KNOWN": {}, "question_slot": None}
check(any("không được đặt câu hỏi" in p for p in coverage("Dạ em cảm ơn chị, chị cần gì thêm không ạ?", plan)),
      "closing có câu hỏi bị bắt")
check(coverage("Dạ em cảm ơn chị ạ.", plan) == [], "closing không hỏi thì qua")

known = {"product_advised": "SKU-AP-X"}
plan = {"goals": ["quote"], "facts": {"quote": quote}, "KNOWN": known, "question_slot": None}
p = coverage("Dạ máy giá 4.490.000đ, chị đang quan tâm sản phẩm nào ạ?", plan)
check(any("không hỏi lại product_advised" in x for x in p), f"hỏi mở lại sản phẩm đã biết bị bắt: {p}")

order = {"order_id": "OD600001, OD600002", "total_vnd": 5_480_000, "estimated_delivery": "2026-10-27"}
plan = {"goals": ["order_created"], "facts": {"order": order}, "KNOWN": {}, "question_slot": None}
check(coverage("Dạ em đã lên đơn OD600001 và OD600002, tổng 5.480.000đ, dự kiến giao ngày 27/10 ạ.", plan) == [],
      "đơn nhiều mã, đủ mã + tổng + ngày thì qua")
p = coverage("Dạ em đã lên đơn OD600001, tổng 5.480.000đ, giao trong tuần này ạ.", plan)
check(any("OD600002" in x for x in p) and any("ngày giao" in x for x in p), f"thiếu mã đơn thứ hai và ngày giao bị bắt: {p}")

goals = ["quote", "ask_address"]
plan = {"goals": goals, "facts": {"quote": quote}, "KNOWN": {}, "question_slot": question_slot(goals, {"quote": quote})}
check(plan["question_slot"] == "address" and coverage(render_offline({**plan, "honorific": "chị"}), plan) == [],
      "câu mẫu của plan qua coverage")

print("TẤT CẢ OK" if ok else "CÓ LỖI")
sys.exit(0 if ok else 1)
