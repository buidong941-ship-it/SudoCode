"""Kiểm CERT v2 (D18–D20, docs/DE-XUAT-CERT-V2-2026-11-02.md mục 4) — chạy với EXTRACTOR_CERT_VERSION=2.

- phản ví dụ precision: phủ định, câu hỏi, danh từ riêng / mã PII trong chứng nhận rỗng → KHÔNG được chứng nhận;
- phản ví dụ coverage: "25m2" (bug U), "Đúng rồi, phòng 25m2" (đúng/dùng), câu 2 slot, trả lời ngắn khi agent vừa hỏi đúng slot
  → PHẢI chứng nhận;
- phủ định trong LUẬT trích (không chỉ CERT): "chị không lấy màu đen" không còn color; "500k" không bị coi là phủ định;
- precision trên bộ nhãn tay (customer.jsonl + real_ref.jsonl): mọi slot được chứng nhận phải đúng nhãn (0 ca sai),
  in coverage và cận trên 95% của tỉ lệ sai (quy tắc 3/n);
- EXTRACTOR_CERT_VERSION=1 vẫn cho kết quả cũ.
"""
import json
import os
import sys
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from core.config import settings  # noqa: E402
from harness import extractor, rule_confidence as RC  # noqa: E402

FAILS = []
TODAY = "2026-10-15"


def ok(c, m):
    if not c:
        FAILS.append(m); print("FAIL:", m)


def cert(text, context=None, asked=None):
    rules = extractor.customer_slots_rules(text, TODAY)
    return rules, RC.customer(text, rules, context, asked), RC.empty(text, rules, context)


with patch.object(settings, "extractor_cert_version", 2):
    # ---- 3.1 precision: phủ định / câu hỏi ----
    for t in ("Chị không lấy màu đen đâu.", "Màu đen thì chị không thích.", "Anh chưa chọn size 42 đâu em.",
              "Thôi đừng lấy màu trắng nhé."):
        rules, c, _ = cert(t)
        ok(not c["certified"] and "color" not in c.get("certified_slots", []) and "size" not in c.get("certified_slots", []),
           f"phủ định không được chứng nhận: {t} → {rules} {c['reason']}")
    for t in ("Chị không lấy màu đen đâu.", "Màu đen thì chị không thích."):
        ok("color" not in extractor.customer_slots_rules(t, TODAY), f"luật trích phải bỏ color bị phủ định: {t}")
    for t in ("Thanh toán COD không được à?", "Màu đen còn không em?", "Có size 40 không em?", "Ship COD được không em?"):
        _, c, _ = cert(t)
        ok(not c["certified"], f"câu hỏi không được chứng nhận slot sở thích: {t} → {c['reason']}")
    ok(extractor.customer_slots_rules("Ngân sách chị tầm 500k thôi.", TODAY).get("budget_vnd") == 500000, "500k vẫn là ngân sách")
    ok(not RC.negated("Ngân sách chị tầm 500 k thôi.", (21, 26)), "'k' sau chữ số không phải phủ định")
    ok(RC.negated("Chị không lấy màu đen.", RC._anchor("Chị không lấy màu đen.", "color", "den")), "'không' trước giá trị là phủ định")
    ok(not RC.negated("Phòng 25m2 không em?", RC._anchor("Phòng 25m2 không em?", "room_area_m2", 25)),
       "'không' trợ từ cuối câu hỏi không phải phủ định")

    # ---- 3.6 chứng nhận rỗng: danh từ riêng / mã PII ----
    for t in ("Chị ở Hà Nội.", "Gửi cho Dung nhé em.", "Số chị là [SĐT_1] nha.", "Giao về [ĐỊA_CHỈ_1] giúp chị."):
        _, _, e = cert(t)
        ok(not e["certified"], f"chứng nhận rỗng phải bỏ phiếu trắng: {t} → {e['reason']}")
    for t in ("Dạ em cảm ơn nhé.", "Vâng ạ, chào em."):
        _, _, e = cert(t)
        ok(e["certified"], f"câu không slot vẫn chứng nhận rỗng được: {t} → {e['reason']}")
    ok(not RC._proper_nouns("Chị hỏi AirPure Y với Lock&Lock 4L."), "tên sản phẩm trong catalog không phải danh từ riêng")

    # ---- 3.2 / 3.4 / 3.5 coverage ----
    for t, slots in (("Phòng 25m2.", {"room_area_m2"}), ("Phòng chị dùng 25m2.", {"room_area_m2"}),
                     ("Đúng rồi, phòng 25m2 em.", {"room_area_m2"}),
                     ("Phòng 25m2, ngân sách tối đa 5 triệu.", {"room_area_m2", "budget_vnd"}),
                     ("Cho chị size 38 màu trắng.", {"size", "color"})):
        rules, c, _ = cert(t)
        ok(set(c.get("certified_slots", [])) == slots, f"phải chứng nhận {slots}: {t} → {rules} {c.get('slots')}")
    # ---- 3.3 câu ngắn có ngữ cảnh: chỉ đạt khi agent vừa hỏi đúng slot ----
    ctx = "nhân viên: Phòng mình rộng bao nhiêu m2 ạ?"
    _, c, _ = cert("Dạ 25m2.", context=ctx, asked="room_area_m2")
    ok(c["certified"], f"trả lời ngắn đúng slot vừa hỏi phải chứng nhận: {c.get('slots')}")
    _, c, _ = cert("Dạ 25m2.", context=ctx, asked="budget_vnd")
    ok(not c["certified"], "trả lời ngắn khác slot vừa hỏi phải bỏ phiếu trắng")
    _, c, _ = cert("Màu đó em.", context="nhân viên: Chị lấy màu xám nhé?", asked="color")
    ok(not c["certified"], "tham chiếu ngược 'màu đó' phải bỏ phiếu trắng")
    # ---- D20: slot mới ----
    _, c, _ = cert("Giao về 54 Hùng Vương, TP Việt Trì, Phú Thọ giúp anh.")
    ok("address" in c.get("certified_slots", []), f"địa chỉ rõ phải chứng nhận được: {c.get('slots')}")
    _, c, _ = cert("Em ơi, chị tên là Dung nhé.")
    ok("self_name" in c.get("certified_slots", []), f"tên tự xưng rõ phải chứng nhận được: {c.get('slots')}")
    _, c, _ = cert("Nhà chị có bé 2 tuổi.")
    ok("has_children" in c.get("certified_slots", []), f"has_children rõ phải chứng nhận được: {c.get('slots')}")
    _, c, _ = cert("Nhà chị không có bé đâu.")
    ok("has_children" not in c.get("certified_slots", []), "has_children bị phủ định không được chứng nhận")

    # ---- precision trên bộ nhãn tay ----
    from extract_eval import same
    n_cert = wrong = n_turn = n_empty = empty_wrong = 0
    for name in ("customer.jsonl", "real_ref.jsonl"):
        for line in open(os.path.join(ROOT, "tests", "extract_eval", name), encoding="utf-8"):
            it = json.loads(line)
            gold, skip = it["slots"], set(it.get("skip") or [])
            rules = extractor.customer_slots_rules(it["text"], TODAY)
            c = RC.customer(it["text"], rules, it.get("context") or None)
            e = RC.empty(it["text"], rules, it.get("context") or None)
            n_turn += 1
            for k in c.get("certified_slots", []):
                if k in skip:
                    continue
                n_cert += 1
                if k not in gold or not same(k, gold[k], rules[k]):
                    wrong += 1
                    FAILS.append(f"chứng nhận sai {it['id']} {k}={rules[k]!r} gold={gold.get(k)!r}: {it['text']}")
                    print("FAIL:", FAILS[-1])
            if e["certified"]:
                n_empty += 1
                if set(gold) - skip:
                    empty_wrong += 1
                    FAILS.append(f"chứng nhận rỗng sai {it['id']} gold={gold}: {it['text']}")
                    print("FAIL:", FAILS[-1])
    print(f"bộ nhãn tay {n_turn} câu: slot được chứng nhận {n_cert} (sai {wrong}, cận trên 95% ≈ {3 / max(n_cert, 1):.1%}); "
          f"chứng nhận rỗng {n_empty} (sai {empty_wrong}, cận trên 95% ≈ {3 / max(n_empty, 1):.1%})")

    # ---- D16/D27: các bước nới sau cờ đo CERT_V2_RELAX (mặc định rỗng) ----
    with patch.object(settings, "cert_v2_relax", ""):
        _, c, _ = cert("để cô xem thêm", context="ctx")
        ok("blocker" not in c.get("certified_slots", []), "không bật cờ thì blocker không được chứng nhận")
        _, c, _ = cert("tầm 5.500.000 có vừa không em", context="ctx")
        ok("budget_vnd" not in c.get("certified_slots", []), "không bật cờ thì giữ hành vi cũ với ngân sách câu ngắn")
    with patch.object(settings, "cert_v2_relax", "blocker,budget"):
        for t in ("để cô xem thêm", "Okie cảm ơn, để mình xem qua nha."):
            rules, c, _ = cert(t, context="ctx")
            ok("blocker" in c.get("certified_slots", []), f"blocker có entry lexicon đã duyệt phải chứng nhận: {t} → {rules} {c.get('slots')}")
        for t in ("Để chị xem thêm được không em?", "Anh sẽ so sánh thêm rồi gọi lại cho em nhé.", "Để anh hỏi người nhà."):
            rules, c, _ = cert(t, context="ctx")
            ok("blocker" not in c.get("certified_slots", []), f"blocker hỏi / có gọi lại / không có entry lexicon: {t} → {c.get('slots')}")
        rules, c, _ = cert("tầm 5.500.000 có vừa không em", context="ctx")
        ok("budget_vnd" in c.get("certified_slots", []), f"ngân sách 'tầm X có vừa không' phải chứng nhận: {rules} {c.get('slots')}")
        for t in ("giá tầm 5 triệu hả em?", "tầm 5 triệu hả em?"):
            rules, c, _ = cert(t, context="ctx")
            ok("budget_vnd" not in c.get("certified_slots", []), f"nhắc giá / hỏi lại số tiền không chứng nhận ngân sách: {t} → {c.get('slots')}")

    # Đo precision từng mức nới cộng dồn trên bộ nhãn tay: in ra, KHÔNG làm trượt smoke (quyết giữ/bỏ theo số ở D27).
    for level in ("blocker", "blocker,budget"):
        with patch.object(settings, "cert_v2_relax", level):
            n_c = bad = n_e = 0
            by_slot = {}
            for name in ("customer.jsonl", "real_ref.jsonl"):
                for line in open(os.path.join(ROOT, "tests", "extract_eval", name), encoding="utf-8"):
                    it = json.loads(line)
                    gold, skip = it["slots"], set(it.get("skip") or [])
                    rules = extractor.customer_slots_rules(it["text"], TODAY)
                    c = RC.customer(it["text"], rules, it.get("context") or None)
                    n_e += RC.empty(it["text"], rules, it.get("context") or None)["certified"]
                    for k in c.get("certified_slots", []):
                        if k in skip:
                            continue
                        n_c += 1
                        by_slot[k] = by_slot.get(k, 0) + 1
                        if k not in gold or not same(k, gold[k], rules[k]):
                            bad += 1
                            print(f"RELAX[{level}] chứng nhận sai {it['id']} {k}={rules[k]!r} gold={gold.get(k)!r}: {it['text']}")
            print(f"RELAX[{level}] slot được chứng nhận {n_c} (sai {bad}) theo slot {by_slot}; chứng nhận rỗng {n_e}")

# ---- v1 giữ nguyên ----
with patch.object(settings, "extractor_cert_version", 1):
    c = RC.customer("Phòng 25m².", {"room_area_m2": 25})
    ok(c["certified"] and "version" not in c, "v1 phải giữ hành vi cũ")
    ok("color" in extractor.customer_slots_rules("Chị không lấy màu đen đâu.", TODAY), "v1 không đổi luật trích")

print("TẤT CẢ OK" if not FAILS else f"{len(FAILS)} LỖI")
sys.exit(1 if FAILS else 0)
