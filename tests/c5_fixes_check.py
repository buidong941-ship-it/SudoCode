"""Kiểm các sửa lỗi do C5 làm lộ (02/11): D23 (giữ claim của luật khi chuyển câu sang Qwen)."""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from harness import extractor, jev_hybrid, llm_extract

TEXT = "Dạ máy giá 7.690.000đ, đang có ưu đãi Giảm 300.000đ ạ."
QWEN_REPLY = {"sentences": [{"i": 0, "ask": "none", "confirm": False, "facts": [],
                             "numbers": [{"span": "7.690.000đ", "role": "gia_niem_yet"},
                                         {"span": "300.000đ", "role": "so_tien_giam"}]}]}


def _hybrid():
    return (patch.object(extractor.settings, "extractor_backend", "hybrid"),
            patch.object(extractor.settings, "extractor_confidence_gate", False),
            patch.object(extractor.settings, "extractor_jev_hybrid", True),
            patch.object(extractor.settings, "agent_claim_backend", "current"),
            patch.object(extractor.settings, "extract_logprobs", False),
            patch.object(jev_hybrid, "labels", return_value={"gia_ban", "so_tien_giam"}),
            patch.object(llm_extract, "_call", return_value=(QWEN_REPLY, None)))


def _money(claims):
    return sorted((c["field"], c["value"]) for c in claims if c["field"] in llm_extract.MONEY_FIELDS)


def check_d23():
    rules = extractor.agent_claims(TEXT)
    assert ("price_vnd", 7690000) in _money(rules), rules

    # Nhánh chính: Jev bỏ câu (2 số tiền) → Qwen gán gia_niem_yet → luật phải thắng.
    p = _hybrid()
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6] as qwen, \
         patch("harness.question_classifiers.jev_slots.classify_agent_questions", return_value=[]):
        meta = {}
        _, claims = extractor.analyze_agent(TEXT, {}, meta)
        assert qwen.call_count == 1, "câu mơ hồ phải được gửi Qwen"
        assert _money(claims) == [("price_vnd", 7690000)], claims

    # Nhánh dự phòng: Jev lỗi khi phân loại câu hỏi → gọi lại Qwen trên toàn bộ câu chưa chắc.
    def jev_q_error(text, known, meta):
        meta["jev_slot_errors"] = ["timeout"]
        return []

    p = _hybrid()
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], \
         patch("harness.question_classifiers.jev_slots.classify_agent_questions", side_effect=jev_q_error):
        _, claims = extractor.analyze_agent(TEXT, {}, {})
        assert _money(claims) == [("price_vnd", 7690000)], claims

    # Qwen lỗi → vẫn còn claim của luật (trước đây mất hết).
    p = _hybrid()
    with p[0], p[1], p[2], p[3], p[4], p[5], \
         patch.object(llm_extract, "_call", side_effect=RuntimeError("down")), \
         patch("harness.question_classifiers.jev_slots.classify_agent_questions", return_value=[]):
        _, claims = extractor.analyze_agent(TEXT, {}, {})
        assert _money(claims) == [("price_vnd", 7690000)], claims
    print("D23 OK")


def _session_promos(*results):
    from harness.agent import CallSession
    s = CallSession.__new__(CallSession)
    s.call_promo_active, s.call_promo_expired = set(), set()
    out = None
    for r in results:
        out = s._call_promos([{"name": "pricing.get_quote", "result": r}])
    return out


def check_d22():
    from harness import guardrails

    cod_only = {"applied_promos": [{"promo_code": "COD-0", "type": "freecod", "discount_vnd": 0}], "expired_promos": []}
    gift_expired = {"applied_promos": [{"promo_code": "COD-0", "type": "freecod", "discount_vnd": 0}],
                    "expired_promos": ["GIFT-FILTER", "AP-SEP"]}
    gift_active = {"applied_promos": [{"promo_code": "COD-0", "type": "freecod", "discount_vnd": 0},
                                      {"promo_code": "GIFT-FILTER", "type": "gift", "discount_vnd": 0, "gift_sku": "SKU-AP-FLT-X"}],
                   "expired_promos": ["AP-SEP"]}
    air_oct = {"applied_promos": [{"promo_code": "AIR-OCT", "type": "fixed", "discount_vnd": 300000}],
               "expired_promos": ["GIFT-FILTER"]}

    # BTCL-036 call_1 lượt 3 (chào kết, không gọi tool; tool cả cuộc chỉ có COD-0).
    p = _session_promos(cod_only)
    assert p["active"] == [], p
    t = "Dạ anh/chị ạ, em cảm ơn ạ. Sản phẩm này đang có khuyến mãi, anh/chị vui lòng đặt hàng ngay để nhận ưu đãi nhé!"
    assert guardrails.promo_problems(t, p), "BTCL-036 phải bị chặn"
    assert guardrails.check(t, set(), promos=p), "check() phải trả lỗi KM"
    assert not guardrails.check(t, set()), "promos=None → không kiểm (tương thích cũ)"

    # BTCL-052 call_2 lượt 2: lượt 1 đã nói hết hạn, lượt 2 nói ngược lại.
    p = _session_promos(gift_expired)
    t1 = ("Máy lọc không khí AirPure X hiện đang có giá 4.890.000đ, chương trình tặng màng lọc đã hết hạn rồi ạ. "
          "Anh/chị còn băn khoăn điều gì không ạ?")
    t2 = ("Dạ anh/chị ạ, em xin chân thành cảm ơn ạ. Chương trình khuyến mãi hiện đang còn hiệu lực đến 22/10/2026, "
          "anh/chị có thể yên tâm ạ.")
    assert not guardrails.promo_problems(t1, p), "câu 'đã hết hạn' phải được cho qua"
    assert guardrails.promo_problems(t2, p), "BTCL-052 phải bị chặn"

    # KM đang áp dụng thật → cho qua; nhắc KM đã hết hạn như còn hiệu lực → chặn.
    p = _session_promos(gift_active)
    ok = "Dạ mẫu Máy lọc không khí AirPure X giá 4.890.000đ, đang có ưu đãi Tặng 1 màng lọc khi mua AirPure X/Y (đến 22/10) ạ."
    assert not guardrails.promo_problems(ok, p)
    p = _session_promos(air_oct)
    assert not guardrails.promo_problems("Dạ máy giá 7.690.000đ, đang có ưu đãi Giảm 300.000đ ạ.", p)
    bad = "Dạ bên em vẫn đang tặng kèm 1 màng lọc khi mua máy ạ."
    assert guardrails.promo_problems(bad, p) == ["nói chương trình GIFT-FILTER đã hết hạn như còn hiệu lực"], \
        guardrails.promo_problems(bad, p)

    # KM gom theo cả cuộc gọi: lượt sau không gọi tool vẫn biết KM đã thấy ở lượt trước.
    p = _session_promos(gift_active, {"orders": []})
    assert [x["promo_code"] for x in p["active"]] == ["GIFT-FILTER"], p

    # Không coi là khẳng định KM: freeship, câu hỏi, câu phủ định.
    p = _session_promos(cod_only)
    for t in ("Dạ đơn này đang có ưu đãi miễn phí vận chuyển ạ.",
              "Anh/chị có muốn em kiểm tra chương trình khuyến mãi không ạ?",
              "Dạ hiện sản phẩm này chưa có chương trình khuyến mãi ạ.",
              "Dạ em cảm ơn anh/chị, chúc anh/chị một ngày tốt lành ạ."):
        assert not guardrails.promo_problems(t, p), t
    print("D22 OK")


def check_d31_d32():
    from harness.tools import find_color
    rules = lambda t: extractor.customer_slots_rules(t, "2026-10-15")  # noqa: E731

    # D31: "mẫu đó" không phải màu đỏ; câu mất dấu vẫn so như cũ
    for t in ("Với mức tiền hôm qua, mẫu đó còn phù hợp không em?", "Lần trước em nói mẫu đó có hàng.",
              "Nhà chị có em bé nên cần máy êm."):
        assert "color" not in rules(t), (t, rules(t))
    assert rules("Chị lấy màu đỏ nhé.").get("color") == "do"
    assert rules("chi lay mau do nhe").get("color") == "do", "câu mất dấu vẫn nhận màu"
    assert rules("Cho chị size 38 màu trắng.").get("color") == "trang"
    assert find_color("lấy cái đó") is None and find_color("Giày màu đen size 40") == "den"
    assert find_color("đen") == "den" and find_color("den") == "den", "extract_eval.same so mã màu"

    # D32: khách tự gọi lại → không phải callback_requested; nhờ shop gọi lại vẫn nhận
    for t in ("Mai anh sẽ gọi lại em nhé.", "Mai anh gọi lại được không em?", "Mai cô sẽ gọi lại cho em."):
        assert "callback_requested" not in rules(t), (t, rules(t))
    for t in ("Thôi để mai khoảng 10 giờ em gọi lại cho cô nhé.",
              "Anh đang bận chút, thứ hai tuần sau khoảng 14 giờ em gọi lại cho anh được không?",
              "Mai em có gọi lại cho anh lúc 9 giờ không?"):
        assert "callback_requested" in rules(t), (t, rules(t))
    print("D31/D32 OK")


def run():
    check_d23()
    check_d22()
    check_d31_d32()
    print("C5 fixes checks OK")


if __name__ == "__main__":
    run()
