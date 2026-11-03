"""Kiểm 3 lỗi agent do bộ D-7 (dev BTCD7-*) làm lộ ngày 02/11 — chỉ dùng câu dev D-7 và câu tự viết.

1. riêng tư: "xin số họ", "địa chỉ nhà người mua gần đây" phải khớp OTHER_PII_RX; câu hỏi số shop thì không;
2. ý định đặt hàng (router rules): "Lấy cho anh cái mẫu hôm trước nhé", "Anh quyết lấy AirPure Y rồi";
3. cắt địa chỉ: dừng trước ", bên em…" và ", anh trả tiền…".
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.llm.router import _rules  # noqa: E402
from harness import agent, extractor  # noqa: E402
from harness.textnorm import fold  # noqa: E402

FAILS = []


def ok(c, m):
    if not c:
        FAILS.append(m); print("FAIL:", m)


for t in ("Chị muốn hỏi thử người mua trước, em cho chị xin số họ được không?",
          "Em cho chị xin địa chỉ nhà người mua gần đây được không?",
          "Cho anh xin số zalo của họ để hỏi review nha.",
          "Bên em có thể cho số của khách từng mua mẫu này để anh hỏi không?"):
    ok(agent.OTHER_PII_RX.search(fold(t)), f"riêng tư phải khớp: {t}")
for t in ("Cho chị xin số zalo của shop nhé.", "Em cho chị xin địa chỉ cửa hàng bên em.",
          "Chị gửi số tài khoản cho em rồi đó.", "Người mua trước có hài lòng không em?"):
    ok(not agent.OTHER_PII_RX.search(fold(t)), f"riêng tư không được khớp: {t}")

for t in ("Lấy cho anh cái mẫu hôm trước nhé.", "Anh quyết lấy AirPure Y rồi em.", "Chị quyết mua rồi, lên đơn nha."):
    r = _rules(t)
    ok(r["intent"] == "place_order" and r["flags"]["agrees_to_buy"] >= 0.5, f"phải là place_order: {t} → {r['intent']}")
ok(_rules("Lấy cho chị giá mới nhất nhé")["intent"] != "place_order", "hỏi giá không phải đặt hàng")

for t, want in (("Nhà chị ở 80 Ngô Quyền, Sơn Trà, Đà Nẵng, bên em giao tới được không?", "80 Ngô Quyền, Sơn Trà, Đà Nẵng"),
                ("Giao về 133 Trần Hưng Đạo, Ninh Kiều, Cần Thơ, anh trả tiền mặt khi nhận nha.", "133 Trần Hưng Đạo, Ninh Kiều, Cần Thơ"),
                ("Giao về 1 Võ Văn Ngân, Thủ Đức, TP HCM, trả tiền mặt khi nhận nha.", "1 Võ Văn Ngân, Thủ Đức, TP HCM"),
                ("Ship đến 5 Trần Phú, Nha Trang, Khánh Hòa mất mấy ngày em?", "5 Trần Phú, Nha Trang, Khánh Hòa"),
                ("Có hàng để giao tới 54 Hùng Vương, TP Việt Trì, Phú Thọ không?", "54 Hùng Vương, TP Việt Trì, Phú Thọ")):
    got = extractor.customer_slots_rules(t, "2026-10-20").get("address")
    ok(got == want, f"địa chỉ: {t!r} → {got!r}, cần {want!r}")

# D12 (lỗi L2): hỏi tình trạng đơn có tên sản phẩm chen giữa
for t in ("Em ơi đơn máy lọc không khí của anh giao tới đâu rồi?", "Đơn hôm trước của chị bao giờ tới vậy em?",
          "Hàng tới đâu rồi em?", "Khi nào thì nhận được hàng vậy em?"):
    ok(_rules(t)["intent"] == "order_status", f"phải là order_status: {t} → {_rules(t)['intent']}")
for t in ("Máy lọc không khí AirPure Y giá bao nhiêu em?", "Giao tới Đà Nẵng mất mấy ngày em?"):
    ok(_rules(t)["intent"] != "order_status", f"không phải order_status: {t}")

print("TẤT CẢ OK" if not FAILS else f"{len(FAILS)} LỖI")
sys.exit(1 if FAILS else 0)
