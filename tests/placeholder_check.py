#!/usr/bin/env python3
"""Kiểm chế độ placeholder của generator (GEN_PLACEHOLDERS=1): LLM viết mã {GIA_BAN}…, code điền giá trị — không cần GPU/mạng.

    python tests/placeholder_check.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("RAG_MODE", "bm25")

from core.config import settings  # noqa: E402
from core.llm import deepseek, generator  # noqa: E402
from harness import guardrails  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(("  OK  " if cond else "  SAI ") + msg)
    ok &= bool(cond)


quote = {"name": "Máy lọc không khí AirPure X", "final_price_vnd": 4_490_000, "list_price_vnd": 4_890_000, "promo_names": ["AIR-OCT"]}
order = {"order_id": "OD600001", "total_vnd": 4_490_000, "estimated_delivery": "2026-10-27", "estimated_delivery_ddmm": "27/10"}
plan = {"goals": ["quote", "order_created"], "facts": {"quote": quote, "order": order}, "KNOWN": {}, "question_slot": None}
slots = generator.build_slots(plan)
check(set(slots) == {"GIA_BAN", "GIA_NIEM_YET", "TONG_TIEN", "MA_DON", "NGAY_GIAO"}, f"bảng mã: {sorted(slots)}")
user = generator.payload(plan, slots=slots)
check("{GIA_BAN}" in user and "4490000" not in user and "4890000" not in user and "OD600001" not in user and "27/10" not in user,
      "prompt có mã, không có giá trị")
check(plan["facts"]["quote"]["final_price_vnd"] == 4_490_000, "plan gốc không bị sửa (câu mẫu vẫn dùng số thật)")

text, probs = generator.fill("Dạ giá {GIA_BAN} ạ, đơn {MA_DON} giao ngày {NGAY_GIAO}.", slots)
check(text == "Dạ giá 4.490.000đ ạ, đơn OD600001 giao ngày 27/10." and not probs, f"điền đúng: {text}")
text, probs = generator.fill("Dạ giá {GIA_XYZ} ạ.", slots)
check(any("GIA_XYZ" in p for p in probs), f"mã ngoài bảng bị chặn: {probs}")
text, probs = generator.fill("Dạ giá 4.490.000đ ạ.", slots)
check(any("viết tay" in p for p in probs), f"viết tay số đã có mã bị chặn: {probs}")
text, probs = generator.fill("Dạ giá 1.234.000đ ạ.", slots)
check(guardrails.check(text, {4_490_000, 4_890_000}) != [], "số tiền lạ viết tay vẫn bị guardrail chặn")

same = {"goals": ["quote"], "facts": {"quote": {**quote, "list_price_vnd": 4_490_000}}, "KNOWN": {}, "question_slot": None}
s2 = generator.build_slots(same)
check("GIA_NIEM_YET" not in s2 and "4490000" not in generator.payload(same, slots=s2), "giá niêm yết = giá bán thì dùng chung {GIA_BAN}")

settings.gen_placeholders = True
seen = {}


def fake_chat(self, msgs, **kw):
    seen["user"] = msgs[-1]["content"]
    return "Dạ máy {GIA_BAN} ạ.", 5, 9, None


deepseek.LLM.chat = fake_chat
g = generator.Generator("qwen")
text, *_ = g.generate({**plan, "goals": ["quote"]})
check(text == "Dạ máy 4.490.000đ ạ." and not g.fill_problems and "PLACEHOLDERS" in seen["user"], f"generate điền mã: {text}")
settings.gen_placeholders = False
g.generate({**plan, "goals": ["quote"]})
check("PLACEHOLDERS" not in seen["user"] and "4490000" in seen["user"], "tắt cờ thì prompt như cũ")

print("TẤT CẢ OK" if ok else "CÓ LỖI")
sys.exit(0 if ok else 1)
