#!/usr/bin/env python3
"""Kiểm phần CODE của bộ trích LLM (harness/llm_extract.py) bằng LLM giả — không cần GPU/mạng:

1. span không có trong câu (LLM bịa) → bị loại; giá trị đọc bằng hàm của luật (find_money…), không lấy số từ LLM.
2. hybrid: luật thắng khi cùng slot; LLM bổ sung slot luật bỏ sót; claims là hợp hai bên, không mất claim nào của luật.
3. LLM lỗi → dùng kết quả luật, ghi `fallback`.
4. Luật đã sửa: "bên em" / "màu be" không còn là has_children; claim is_human; STK 10 số bắt đầu bằng 0 bị che.

    python tests/llm_extract_check.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("RAG_MODE", "bm25")

from harness import extractor, llm_extract  # noqa: E402
from harness.textnorm import mask_pii  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(("  OK  " if cond else "  SAI ") + msg)
    ok &= bool(cond)


def fake(reply):
    def _call(prompt, schema, texts, meta):
        if isinstance(reply, Exception):
            raise reply
        meta["backend"] = "test:fake"
        return reply, None
    llm_extract._call = _call


print("lời khách")
text = "Phòng chị tầm 20 mét vuông, ngân sách khoảng 5 triệu, bên kia bán 4tr2 thôi"
rules = extractor.customer_slots_rules(text, "2026-10-15")
fake({"slots": [{"slot": "room_area_m2", "span": "20 mét vuông"},
                {"slot": "budget_vnd", "span": "khoảng 5 triệu"},
                {"slot": "competitor_price_vnd", "span": "bán 4tr2"},
                {"slot": "address", "span": "12 Lê Lợi, Hà Nội"},
                {"slot": "has_children", "span": "tầm", "label": "khong"}]})
m = {}
got = llm_extract.customer_slots(text, "2026-10-15", rules, "llm", m)
check(got.get("room_area_m2") == 20 and got.get("budget_vnd") == 5_000_000 and got.get("competitor_price_vnd") == 4_200_000,
      f"giá trị do code đọc từ span: {got}")
check("address" not in got and m.get("dropped_spans") == 1, "span không có trong câu bị loại")
check("has_children" not in got, "label 'khong' không ghi has_children")

text2 = "Chị lấy size 38 nhé, giao về 41 Trần Hưng Đạo, Ninh Kiều, Cần Thơ"
rules2 = extractor.customer_slots_rules(text2, "2026-10-15")
fake({"slots": [{"slot": "size", "span": "size 39"}, {"slot": "payment", "span": "giao về", "label": "COD"}]})
got2 = llm_extract.customer_slots(text2, "2026-10-15", rules2, "hybrid", {})
check(got2.get("size") == rules2.get("size") == "38", "hybrid: luật thắng khi cùng slot (span 'size 39' không có trong câu)")
check(got2.get("payment") == "COD" and got2.get("address") == rules2.get("address"), "hybrid: LLM bổ sung slot luật bỏ sót")

fake(TimeoutError("vllm chậm"))
m = {}
check(llm_extract.customer_slots(text, "2026-10-15", rules, "llm", m) == rules and "TimeoutError" in m.get("fallback", ""),
      "LLM lỗi → dùng luật, ghi fallback")

print("lời agent")
agent = "Dạ máy này giá niêm yết 5.200.000đ, giảm còn 4.890.000đ ạ. Bên em đang tặng màng lọc. Chị cho em xin địa chỉ giao hàng ạ."
q_r, c_r = extractor.agent_questions(agent, {}), extractor.agent_claims(agent)
fake({"sentences": [{"i": 0, "ask": "none", "facts": [],
                     "numbers": [{"span": "giá niêm yết 5.200.000đ", "role": "gia_niem_yet"},
                                 {"span": "còn 4.890.000đ", "role": "gia_ban"},
                                 {"span": "còn 3.000.000đ", "role": "gia_ban"}]},
                    {"i": 1, "ask": "none", "numbers": [], "facts": ["dang_co_khuyen_mai"]},
                    {"i": 2, "ask": "address", "numbers": [], "facts": []},
                    {"i": 9, "ask": "none", "numbers": [], "facts": ["con_hang"]}]})
m = {}
q, c = llm_extract.agent(agent, {}, q_r, c_r, "llm", m)
check([(x["slot"], x["type"]) for x in q] == [("address", "open")], f"câu hỏi không có dấu '?' vẫn được tính: {q}")
vals = sorted((x["field"], x["value"]) for x in c)
check(vals == [("list_price_vnd", 5200000), ("price_vnd", 4890000), ("promo_active", True)], f"claims đã kiểm: {vals}")
check(m.get("dropped_spans") == 2, "bỏ claim span bịa + chỉ số câu sai")
fake({"sentences": []})
q, c = llm_extract.agent(agent, {}, q_r, c_r, "hybrid", {})
check({(x["field"], x["value"]) for x in c_r} <= {(x["field"], x["value"]) for x in c}, "hybrid: không mất claim nào của luật")

req = "Dạ em lên đơn rồi ạ. Chị lên địa chỉ giúp em nhé. Anh gọi lại em sau nhé."
q_r = extractor.agent_questions(req, {})
fake({"sentences": [{"i": 1, "ask": "address", "numbers": [], "facts": []},
                    {"i": 2, "ask": "callback_time", "numbers": [], "facts": []}]})
q, _ = llm_extract.agent(req, {}, q_r, [], "hybrid", {})
check(not q_r and [(x["slot"], x["text"]) for x in q] == [("address", "Chị lên địa chỉ giúp em nhé.")],
      f"câu yêu cầu luật bỏ sót được LLM nhận; câu dặn dò không có từ khóa slot bị chặn: {q}")

print("luật đã sửa")
check(not any(x["slot"] == "has_children" for x in extractor.agent_questions("Bên em giao trong 2 ngày, chị nhận ở đâu ạ?", {})),
      "'bên em' không gán slot has_children")
check("has_children" not in extractor.customer_slots_rules("Chị lấy màu be nhé", "2026-10-15"), "'màu be' không phải có trẻ nhỏ")
check(extractor.customer_slots_rules("Nhà chị có bé 2 tuổi", "2026-10-15").get("has_children") is True, "'có bé' vẫn là có trẻ nhỏ")
check({"field": "is_human", "value": False, "text": "Dạ em là trợ lý AI của shop ạ."} in extractor.agent_claims("Dạ em là trợ lý AI của shop ạ."),
      "claim is_human=false")
check(any(x["field"] == "is_human" and x["value"] is True for x in extractor.agent_claims("Dạ em là người thật ạ.")), "claim is_human=true")
check("0123456789" not in mask_pii("số tài khoản 0123456789 Vietcombank") and "0984726714" in mask_pii("số em 0984726714"),
      "STK 10 số bắt đầu bằng 0 bị che, SĐT giữ nguyên")

print("TẤT CẢ OK" if ok else "CÓ LỖI")
sys.exit(0 if ok else 1)
