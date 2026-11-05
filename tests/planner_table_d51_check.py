#!/usr/bin/env python3
"""D51: kiểm các dòng bảng mới (N01–N04, E03/E07/E12/E15) và tầng tra sản phẩm (PRODUCT_LEXICON) bằng câu dương / âm.

Chỉ kiểm điều kiện và tra sản phẩm, không chạy agent. Câu ví dụ lấy từ trường `examples` của bảng + câu tự viết;
không đọc holdout. Exit 1 nếu có ca sai.
"""
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.config import settings  # noqa: E402
from harness import planner_table as pt  # noqa: E402
from harness.textnorm import fold  # noqa: E402

bad = []


def ctx(text, *, mode="clean", prev=(), updates=None, summary="", slots=None, today="2026-10-21", turn=2, repeat=0,
        orders=False, mentioned=(), asking=None, intent="greeting_or_other", conf=0.9):
    s = SimpleNamespace(input_mode=mode, table_prev_goals=list(prev), updates_done=updates or {}, repeat_asked=repeat,
                        brief={"last_session": {"summary": summary}} if summary else None, today=today, turn_no=turn,
                        orders_created=[{"order_id": "OD1"}] if orders else [], known={}, candidates=[])
    c = pt.Ctx(s, text, slots or {}, {"intent": intent, "flags": {}, "confidence": conf})
    c.f, c.mentioned, c.alt = fold(text), list(mentioned), None
    c.asking = text.rstrip().endswith("?") if asking is None else asking
    return c


def expect(name, got, want, note):
    if bool(got) != want:
        bad.append(f"{name}: '{note}' → {bool(got)}, cần {want}")


# ---------------------------------------------------------------- predicate của dòng mới
P = pt.PREDS
for t, want in [("ừm à cái đó… tút… ờ hôm… rè… à", True), ("alo alo ờ… rè rè… cái… ờ… bên… nghe không", True),
                ("alo em, cho chị hỏi máy lọc nước", False), ("Mẫu này màu đỏ rè quá", True)]:
    expect("noisy_asr", P["noisy_asr"](ctx(t, mode="asr_transcript")), want, t)
expect("noisy_asr(clean)", P["noisy_asr"](ctx("ừm… tút… rè…", mode="clean")), False, "kênh không phải ASR")

for t, want in [("Tiền hoàn của chị là bao nhiêu nhỉ?", True), ("Cho cô hỏi lại số tiền hoàn cho cô là bao nhiêu vậy em?", True),
                ("Tiền hoàn về tài khoản chưa em?", False), ("Máy này giá bao nhiêu", False)]:
    expect("refund_ask", P["refund_ask"](ctx(t)), want, t)
expect("has_return_info(cuộc này)", P["has_return_info"](ctx("x", updates={("OD1", "return", None): {"refund_vnd": 1}})), True, "updates_done")
expect("has_return_info(tóm tắt)", P["has_return_info"](ctx("x", summary="Khách yêu cầu trả lại giày, hoàn tiền 3–5 ngày")), True, "summary")
expect("has_return_info(không)", P["has_return_info"](ctx("x", summary="Khách hỏi giá máy lọc nước")), False, "summary khác")

for t, want in [("Đang gấp, em đọc luôn đi, chị chịu trách nhiệm cho.", True), ("Gấp lắm em, cứ đọc đi, có gì cô chịu.", True),
                ("Nhanh lên em, cứ đọc, anh lo phần trách nhiệm.", True), ("Gấp lắm, giao nhanh giúp chị nhé", False)]:
    expect("pressure_words", P["pressure_words"](ctx(t)), want, t)
expect("prev_refuse_internal", P["prev_refuse_internal"](ctx("x", prev=["refuse_internal", "quote"])), True, "lượt trước từ chối")
expect("prev_refuse_internal(không)", P["prev_refuse_internal"](ctx("x", prev=["quote"])), False, "lượt trước báo giá")

for t, want in [("Em hủy đơn giúp chị nhé", True), ("Thôi chị không lấy nữa, hủy đơn đi em", True),
                ("Chị không lấy màu đỏ, lấy màu xanh", False), ("Đơn của chị giao tới đâu rồi", False)]:
    expect("cancel_ask", P["cancel_ask"](ctx(t)), want, t)

for t, want in [("ok lát anh nhắn Zalo chốt nha em", True), ("để mai chị chốt nhé", True), ("chốt sau nhé em", True),
                ("chốt luôn em, mai giao nhé", False), ("lên đơn luôn cho chị", False)]:
    expect("later_close", P["later_close"](ctx(t)), want, t)

for t, want in [("Thôi để chị nghĩ thêm đã", True), ("Không, chị chưa lấy đâu", True), ("Ừ lên đơn đi em", False)]:
    expect("declines_after_confirm", P["declines_after_confirm"](ctx(t, prev=["quote", "confirm_order"])), want, t)
expect("declines_after_confirm(không xác nhận trước)", P["declines_after_confirm"](ctx("Thôi để chị nghĩ thêm đã", prev=["quote"])),
       False, "lượt trước không xin xác nhận")

for t, want in [("Mai 19 giờ em gọi anh nhé, bây giờ anh kẹt việc.", True), ("Mai anh gọi lại em nhé", False),
                ("Em gọi anh nhé", False)]:
    expect("shop_calls_time", P["shop_calls_time"](ctx(t)), want, t)

expect("repeat_exhausted", P["repeat_exhausted"](ctx("hả em nói gì cơ?", repeat=2)), settings.planner_backend == "rules", "đã xin 2 lần")
expect("repeat_exhausted(chưa đủ)", P["repeat_exhausted"](ctx("hả em nói gì cơ?", repeat=1)), False, "mới xin 1 lần")

# ---------------------------------------------------------------- bảng: dòng D51 hợp lệ, có ví dụ, dùng predicate có thật
doc = json.load(open(os.path.join(ROOT, "harness", "planner_rules.json"), encoding="utf-8"))
errs = pt.validate(doc)
if errs:
    bad += ["bảng: " + e for e in errs]
new = [r for r in doc["rows"] if r.get("since") == "D51"]
if {r["id"] for r in new} != {"N01", "N02", "N03", "N04", "E03", "E07", "E12", "E15"}:
    bad.append("thiếu / thừa dòng D51: " + ", ".join(sorted(r["id"] for r in new)))

# ---------------------------------------------------------------- tầng tra sản phẩm
from harness.tools import find_products  # noqa: E402

CASES = [("em ơi anh tìm mo a bê bê ngân sách tầm 2.000.000 có được không", "SKU-MB-STER"),
         ("em ơi anh tìm phi líp 6 chấm hail ngân sách tầm 4.000.000 có được không", "SKU-AF-6L"),
         ("em ơi anh tìm lóc en lóc bốnl ngân sách tầm 2.000.000 có được không", "SKU-AF-4L"),
         ("em ơi chị tìm spéc tra smột ngân sách tầm 4.500.000 có được không", "SKU-MB-PUMP1"),
         ("Em ơi, combo Spectra S1 có kèm máy hâm sữa với túi trữ sữa giá bao nhiêu vậy?", "SKU-BDL-MOM"),
         ("Thế lấy trọn bộ Spectra S1 luôn em", "SKU-BDL-MOM")]
NEG = ["Chai nước rửa bình bao nhiêu em?", "Phải không em, chị nghe nói hai cái cùng giá", "Máy hút sữa Spectra S1 giá bao nhiêu?"]
with patch.object(settings, "product_lexicon", True):
    for t, sku in CASES:
        got = find_products(t)
        if not got or got[0] != sku:
            bad.append(f"PRODUCT_LEXICON=1: '{t}' → {got}, cần {sku} đứng đầu")
    for t in NEG[:2]:
        if find_products(t):
            bad.append(f"PRODUCT_LEXICON=1 bắt nhầm: '{t}' → {find_products(t)}")
    if find_products(NEG[2]) != ["SKU-MB-PUMP1"]:
        bad.append(f"PRODUCT_LEXICON=1: không có 'combo' mà vẫn đổi sang bundle: {find_products(NEG[2])}")
# bật cờ KHÔNG được đổi kết quả của câu chỉ nhắc tên catalog (không có cách đọc mới, không "combo"):
# 05/11 lần 1 bị lỗi thứ tự alias bằng độ dài → "AirPure Pro" ra màng lọc AirPure Pro (HR tăng ở v2_1 / D-7)
from harness.tools import mt  # noqa: E402
names = [p["name"] for p in mt.PRODUCTS if "combo" not in p["name"].lower()]
phrases = names + [f"Anh đang tìm hiểu {n} cho phòng 18 mét vuông em ạ." for n in names] + \
          ["Anh đang tìm hiểu AirPure Pro cho phòng 18 mét vuông em ạ.", "AirPure Pro với AirPure X khác gì em?",
           "Màng lọc AirPure Pro bao nhiêu?", "Xiaomi Smart 4 Pro giá nhiêu ạ"]
for t in phrases:
    with patch.object(settings, "product_lexicon", False):
        old = find_products(t)
    with patch.object(settings, "product_lexicon", True):
        new = find_products(t)
    if old != new:
        bad.append(f"PRODUCT_LEXICON đổi kết quả câu thường: '{t}' {old} → {new}")
with patch.object(settings, "product_lexicon", False):
    if find_products(CASES[0][0]):
        bad.append("PRODUCT_LEXICON=0 phải giữ hành vi cũ (không nhận 'mo a bê bê')")
    if find_products(CASES[4][0])[:1] != ["SKU-MB-PUMP1"]:
        bad.append("PRODUCT_LEXICON=0 phải giữ hành vi cũ (combo → máy lẻ)")

for b in bad:
    print("SAI:", b)
print(f"planner_table_d51_check: {'OK' if not bad else str(len(bad)) + ' ca sai'}")
sys.exit(1 if bad else 0)
