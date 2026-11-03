"""D24: câu mẫu viết lại (docs/RA-SOAT-CAU-MAU-2026-11-02.md) phải được luật trích claim đọc đúng field, qua coverage và guardrail."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("RAG_MODE", "bm25")

from core.llm.generator import render_offline  # noqa: E402
from harness import extractor, guardrails  # noqa: E402
from harness.coverage import content  # noqa: E402
from harness.textnorm import find_money  # noqa: E402


def claims(text):
    return sorted((c["field"], c["value"]) for c in extractor.agent_claims(text))


def say(goals, facts, known=None):
    return render_offline({"honorific": "anh", "goals": goals, "facts": facts, "KNOWN": known or {}})


def run():
    air_oct = {"name": "Máy lọc không khí AirPure Pro", "list_price_vnd": 7_990_000, "final_price_vnd": 7_690_000,
               "promo_names": ["Giảm 300.000đ máy lọc không khí AirPure Pro (đến 30/10)"]}
    gift = {"name": "Máy lọc không khí AirPure Y", "list_price_vnd": 5_200_000, "final_price_vnd": 5_200_000,
            "promo_names": ["Tặng 1 màng lọc khi mua AirPure X/Y (đến 22/10)"]}
    plain = {"name": "Giày sneaker Urban Classic", "list_price_vnd": 890_000, "final_price_vnd": 890_000, "promo_names": []}

    # Ca gốc D24: giá sau KM phải là price_vnd, giá niêm yết là list_price_vnd.
    t = say(["quote"], {"quote": air_oct})
    assert "giá niêm yết 7.990.000đ" in t and "nên còn 7.690.000đ" in t, t
    c = claims(t)
    assert ("price_vnd", 7_690_000) in c and ("list_price_vnd", 7_990_000) in c and ("promo_active", True) in c, (t, c)
    assert not [x for x in c if x[0] == "price_vnd" and x[1] != 7_690_000], c
    assert content(t, ["quote"], {"quote": air_oct}) == []

    t = say(["quote"], {"quote": gift})
    c = claims(t)
    assert "kèm ưu đãi" in t and ("price_vnd", 5_200_000) in c and ("promo_active", True) in c, (t, c)
    assert not [x for x in c if x[0] == "list_price_vnd"], c

    t = say(["recommend"], {"quote": plain})
    assert claims(t) == [("price_vnd", 890_000)], (t, claims(t))

    # Mọi số tiền trong câu mẫu đều phải có trong dữ liệu (guardrail số tiền).
    for q in (air_oct, gift, plain):
        allowed = {q["list_price_vnd"], q["final_price_vnd"]} | {v for n in q["promo_names"] for _, _, v in find_money(n)}
        assert not guardrails.check(say(["quote"], {"quote": q}), allowed), q["name"]

    t = say(["alternative_quote"], {"alternative": air_oct})
    assert t.startswith("Ngoài ra bên em có mẫu") and ("price_vnd", 7_690_000) in claims(t), t

    t = say(["opening_returning"], {"brief": {"product_name": "Máy lọc không khí AirPure Y", "last_date_ddmm": "14/10",
                                              "need": {"room_area_m2": 30}, "price_quoted_vnd": 5_200_000}})
    assert "lúc đó em báo giá 5.200.000đ" in t and claims(t) == [("price_quoted_vnd", 5_200_000)], (t, claims(t))

    t = say(["budget_fit"], {"budget_fit": {"budget_vnd": 5_500_000, "final_price_vnd": 5_200_000, "within_budget": True}})
    assert claims(t) == [("price_vnd", 5_200_000)], (t, claims(t))
    assert not guardrails.check(t, {5_200_000, 5_500_000}, customer_money={5_500_000}), t

    t = say(["ask_size_for_price"], {})
    assert "ưu đãi" not in t, t

    t = say(["ask_phone"], {}, {"address": "12 Nguyễn Trãi, Thanh Xuân, Hà Nội"})
    assert "địa chỉ" not in t and "số điện thoại" in t, t
    assert "địa chỉ" in say(["ask_phone"], {}), "chưa có địa chỉ thì vẫn xin"

    order = {"order_id": "OD600001", "total_vnd": 4_890_000, "estimated_delivery": None}
    t = say(["order_created"], {"order": order})
    assert "None" not in t and "OD600001" in t, t
    t = say(["order_created"], {"order": {**order, "estimated_delivery": "2026-10-18"}})
    assert "18/10" in t and content(t, ["order_created"], {"order": {**order, "estimated_delivery": "2026-10-18"}}) == [], t
    t = say(["order_exists"], {"order": {**order, "estimated_delivery": "2026-10-18"}})
    assert "18/10" in t and "2026-10-18" not in t, t
    assert "None" not in say(["order_exists"], {"order": order})

    for status, vi in (("shipping", "đang giao"), ("delivered", "đã giao"), ("created", "đang chờ xử lý")):
        orders = [{"order_id": "OD1", "status": status}]
        t = say(["order_status"], {"orders": orders})
        assert vi in t and status not in t and content(t, ["order_status"], {"orders": orders}) == [], t

    t = say(["exchange_offer"], {"exchange_preview": {"new_variant": "Giày RunLite size 42", "in_stock": False}})
    assert "thủ tục đổi" not in t and "hoàn tiền" in t, t
    t = say(["exchange_offer"], {"exchange_preview": {"new_variant": "Giày RunLite size 42", "in_stock": True}})
    assert "theo chính sách" in t and "thủ tục đổi" in t, t

    upd = {"order_id": "OD1", "refund_vnd": 100_000, "refund_days": "3-5 ngày làm việc", "status": "pickup_scheduled"}
    t = say(["order_updated"], {"update": upd})
    assert "3-5 ngày làm việc" in t and "qua lấy hàng" in t and content(t, ["order_updated"], {"update": upd}) == [], t
    t = say(["order_updated"], {"update": {"order_id": "OD1", "status": "updated"}})
    assert "lấy hàng" not in t, t

    t = say(["defer_ack"], {})
    assert "em gọi lại" not in t, t
    t = say(["callback_scheduled"], {"callback": {"callback_at": "2026-10-16T15:00:00", "ddmm": "16/10"}})
    assert "  " not in t and "15:00" in t, t
    print("template review checks OK")


if __name__ == "__main__":
    run()
