"""CONTRACT_V2 (09/11): stance chung, cổng claim/slot, guardrail theo mệnh đề, cam kết đã thực hiện, cổng hành vi hội thoại
của action ghi dữ liệu, xác nhận ngắn cần việc đang chờ, và parity khi tắt cờ (đối soát tạo đơn đã bỏ 10/11, xem outcome_contract_check).

Bộ câu được viết THEO NHÓM CÁCH DIỄN ĐẠT trước lần chạy đầu (không chỉ chép câu lỗi RT-01 / JEVNEW-012) và đóng băng.
Chạy trên Kaggle: python tests/contract_v2_check.py  (in từng ca, thoát 1 nếu có ca sai; không dừng ở ca sai đầu tiên).
"""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("EXTRACTOR_BACKEND", "rules")

from core.config import settings  # noqa: E402
from harness import stance  # noqa: E402

FAIL, PASS = [], [0]


def ok(group, name, got, want):
    if got == want:
        PASS[0] += 1
    else:
        FAIL.append((group, name, got, want))
        print(f"FAIL [{group}] {name}: got={got!r} want={want!r}", flush=True)


def st_of(text, needle):
    """Nhãn tại lần xuất hiện đầu tiên của `needle` (so trên bản fold)."""
    f, n = stance.pfold(text), stance.pfold(needle)
    i = f.find(n)
    assert i >= 0, (text, needle)
    return stance.stance_at(text, i, i + len(n))


# ------------------------------------------------------------------ G1: nhãn stance theo nhóm
G1 = [
    # phủ định phạm vi chứa giá trị
    ("Hiện chưa có chính sách bảo hành 3 năm cho sản phẩm này.", "3 năm", "negated"),
    ("Sản phẩm không có bảo hành 3 năm ạ.", "3 năm", "negated"),
    ("Bên em không phải là bảo hành 3 năm đâu ạ.", "3 năm", "negated"),
    ("Bảo hành 12 tháng chứ không phải 3 năm ạ.", "3 năm", "negated"),
    ("Bảo hành 12 tháng chứ không phải 3 năm ạ.", "12 tháng", "affirmed"),
    ("Mẫu này không còn áp dụng giá 1.590.000đ nữa ạ.", "1.590.000", "negated"),
    # chưa biết
    ("Em chưa có thông tin về bảo hành 3 năm ạ.", "3 năm", "unknown"),
    ("Về bảo hành 3 năm, em chưa có thông tin ạ.", "3 năm", "unknown"),
    ("Em không thể xác nhận mức giảm 20% ạ.", "20%", "unknown"),
    # thuật lại lời người khác
    ("Chị nói quản lý hứa bảo hành 3 năm, nhưng sản phẩm bảo hành 12 tháng ạ.", "3 năm", "reported"),
    ("Chị nói quản lý hứa bảo hành 3 năm, nhưng sản phẩm bảo hành 12 tháng ạ.", "12 tháng", "affirmed"),
    ("Theo lời chị thì nhân viên cũ báo giá 1.200.000đ ạ.", "1.200.000", "reported"),
    ("Bên em chỉ cam kết bảo hành 12 tháng ạ.", "12 tháng", "affirmed"),
    ("Anh yên tâm, em báo giá 1.990.000đ là giá hiện tại ạ.", "1.990.000", "affirmed"),
    # hỏi
    ("Bảo hành 3 năm là bên nào báo chị ạ?", "3 năm", "question"),
    ("Chị chỉ hỏi bên em có COD không, chưa chọn hình thức thanh toán.", "COD", "question"),
    ("Shop có giao về Đà Nẵng không em?", "Đà Nẵng", "question"),
    ("Chị có muốn bản bảo hành 24 tháng không ạ?", "24 tháng", "question"),
    # khẳng định rồi hỏi tiếp (giá không bị coi là câu hỏi)
    ("Dạ giá 1.990.000đ chị có lấy không ạ?", "1.990.000", "affirmed"),
    ("Dạ cô ơi giá 1.990.000đ cô lấy không ạ?", "1.990.000", "affirmed"),
    ("Mẫu này giá 1.990.000đ, chị thấy thế nào ạ?", "1.990.000", "affirmed"),
    ("Mẫu X giá 1.990.000đ chị thấy thế nào ạ?", "1.990.000", "affirmed"),
    # khẳng định có chữ phủ định ngoài phạm vi
    ("Không lo ạ, máy bảo hành 3 năm.", "3 năm", "affirmed"),
    ("Giá chưa giảm là 2.190.000đ ạ.", "2.190.000", "affirmed"),
    ("Tổng tiền chưa tính phí ship là 1.990.000đ ạ.", "1.990.000", "affirmed"),
    ("Giao hàng không quá 3 ngày ạ.", "3 ngày", "affirmed"),
    ("Sản phẩm không những bền mà còn bảo hành 24 tháng ạ.", "24 tháng", "affirmed"),
    ("Em là trợ lý AI của shop ạ.", "trợ lý", "affirmed"),
    ("Máy này bảo hành 12 tháng ạ.", "12 tháng", "affirmed"),
    # giả định
    ("Nếu chị đặt hôm nay thì giá còn 1.990.000đ ạ.", "1.990.000", "conditional"),
    ("Nếu COD thì phí ship bao nhiêu em?", "COD", "conditional"),
    ("Đổi trả trong 7 ngày nếu sản phẩm lỗi ạ.", "7 ngày", "affirmed"),
    # khách: lời nhờ lịch sự là yêu cầu, không phải hỏi khả năng
    ("Ship COD cho chị được không em?", "COD", "affirmed"),
    ("COD được không em?", "COD", "affirmed"),
    ("Có COD được không em?", "COD", "question"),
    ("Nhận hàng rồi trả tiền mặt có được không em?", "tiền mặt", "question"),
    ("Chị không lấy màu đen đâu, lấy màu trắng nhé.", "đen", "negated"),
    ("Chị không lấy màu đen đâu, lấy màu trắng nhé.", "trắng", "affirmed"),
    ("chi chi hoi ben em co cod khong", "cod", "question"),
]
for text, needle, want in G1:
    ok("G1-stance", f"{needle} | {text}", st_of(text, needle), want)

# G1b (thêm 09/11 sau Full rules-on): chữ phủ định trong danh từ ghép / tên SP và từ phiếm chỉ sau phủ định.
# 4 ca đầu lấy từ câu thật bị loại sai trong Full (hồi quy); các ca còn lại viết mới, không có trong log.
G1B = [
    ("Dạ, máy lọc không khí Xiaomi Smart 4 Lite có giá 2.990.000đ. Em chưa có thông tin về chứng nhận hoặc thông số khác.",
     "2.990.000", "affirmed"),
    ("Dạ, nồi chiên không dầu Xiaomi 4.5L giá 1.590.000 đ. Em chưa có thông tin về chứng nhận nhé ạ.", "1.590.000", "affirmed"),
    ("Dạ, máy lọc không khí AirPure X còn hàng. Giá bán là 4.890.000 đồng.", "còn hàng", "affirmed"),
    ("Hiện chưa có chương trình khuyến mãi nào áp dụng nha.", "khuyến mãi", "negated"),
    ("Tai nghe không dây Sony giá 1.290.000đ ạ.", "1.290.000", "affirmed"),
    ("Máy lọc không khí này không giảm 10% đâu ạ.", "10%", "negated"),
    ("Nồi chiên không dầu này không còn giá 1.590.000đ nữa ạ.", "1.590.000", "negated"),
    ("Hiện chưa có khuyến mãi nào ạ.", "khuyến mãi", "negated"),
    ("Hiện bên em không có quà tặng gì kèm theo ạ.", "quà tặng", "negated"),
    ("Mẫu này còn khuyến mãi nào không em?", "khuyến mãi", "question"),
    ("Chị không thích màu nào ạ?", "màu", "question"),
]
for text, needle, want in G1B:
    ok("G1b-compound", f"{needle} | {text}", st_of(text, needle), want)
ok("G1b-compound", "promo_active=False 'chưa có ... nào'",
   stance.accept_claim({"field": "promo_active", "value": False,
                        "text": "Hiện chưa có chương trình khuyến mãi nào áp dụng nha."})[0], True)
ok("G1b-compound", "in_stock=True 'máy lọc không khí ... còn hàng'",
   stance.accept_claim({"field": "in_stock", "value": True, "text": "Dạ, máy lọc không khí AirPure X còn hàng."})[0], True)
ok("G1b-compound", "price in product name with không",
   stance.accept_claim({"field": "price_vnd", "value": 7690000,
                        "text": "Dạ, máy lọc không khí AirPure Pro đang bán giá 7.690.000đ. Có khuyến mãi giảm 300.000đ nhé ạ."})[0], True)
ok("G1b-compound", "customer color with product name",
   stance.filter_customer_slots("Chị lấy máy lọc không khí màu trắng nhé.", {"color": "trắng"}, {}), {"color": "trắng"})

# ------------------------------------------------------------------ G2: chấp nhận claim (mọi nhánh dùng chung)
G2 = [
    ({"field": "warranty_months", "value": 36, "text": "Hiện chưa có chính sách bảo hành 3 năm cho sản phẩm này."}, False),
    ({"field": "warranty_months", "value": 36, "text": "Dạ hiện bên em chưa có chính sách bảo hành 3 năm cho mẫu này, chỉ 12 tháng ạ."}, False),
    ({"field": "warranty_months", "value": 12, "text": "Dạ hiện bên em chưa có chính sách bảo hành 3 năm cho mẫu này, chỉ 12 tháng ạ."}, True),
    ({"field": "warranty_months", "value": 36, "text": "Chị nói quản lý hứa bảo hành 3 năm ạ."}, False),
    ({"field": "warranty_months", "value": 12, "text": "Máy bảo hành 12 tháng ạ."}, True),
    ({"field": "price_vnd", "value": 1990000, "text": "Dạ giá 1.990.000đ chị có lấy không ạ?"}, True),
    ({"field": "price_vnd", "value": 1590000, "text": "Mẫu này không còn áp dụng giá 1.590.000đ nữa ạ."}, False),
    ({"field": "promo_active", "value": False, "text": "Hiện không có khuyến mãi ạ."}, True),
    ({"field": "promo_active", "value": True, "text": "Hiện không có khuyến mãi ạ."}, False),
    ({"field": "promo_active", "value": False, "text": "Em chưa có thông tin về khuyến mãi ạ."}, False),
    ({"field": "promo_active", "value": True, "text": "Mẫu này đang có khuyến mãi giảm 10% ạ."}, True),
    ({"field": "in_stock", "value": False, "text": "Mẫu này tạm hết hàng ạ."}, True),
    ({"field": "is_human", "value": False, "text": "Em là trợ lý AI của shop ạ."}, True),
    ({"field": "delivery_days", "value": 3, "text": "Bên em giao trong 2-3 ngày ạ."}, True),
    ({"field": "return_days", "value": 7, "text": "Nếu sản phẩm lỗi, chị được đổi trả trong 7 ngày ạ."}, True),
]
for claim, want in G2:
    ok("G2-claim", f"{claim['field']}={claim['value']} | {claim['text']}", stance.accept_claim(claim)[0], want)

# claim qua analyze_agent (nhánh rules) khi bật cờ: RT-01 không còn ghi 36 tháng, câu khẳng định vẫn ghi
from harness import extractor  # noqa: E402
with patch.object(settings, "contract_v2", True), patch.object(settings, "extractor_backend", "rules"):
    meta = {}
    _, claims = extractor.analyze_agent("Hiện chưa có chính sách bảo hành 3 năm cho sản phẩm này.", {}, meta)
    ok("G2-route", "RT-01 rules route", [c["value"] for c in claims if c["field"] == "warranty_months"], [])
    ok("G2-route", "RT-01 dropped recorded", bool(meta.get("stance_dropped_claims")), True)
    _, claims = extractor.analyze_agent("Dạ máy này bảo hành 12 tháng ạ.", {}, {})
    ok("G2-route", "affirmed warranty kept", [c["value"] for c in claims if c["field"] == "warranty_months"], [12])
with patch.object(settings, "contract_v2", False), patch.object(settings, "extractor_backend", "rules"):
    _, claims = extractor.analyze_agent("Hiện chưa có chính sách bảo hành 3 năm cho sản phẩm này.", {}, {})
    ok("G6-parity", "flag off keeps legacy RT-01 claim", [c["value"] for c in claims if c["field"] == "warranty_months"], [36])

# ------------------------------------------------------------------ G3: slot lựa chọn của khách
G3 = [
    ("Chị chỉ hỏi bên em có COD không, chưa chọn hình thức thanh toán.", {"payment": "COD"}, {}),
    ("Shop có COD không em?", {"payment": "COD"}, {}),
    ("Nhận hàng rồi trả tiền mặt có được không em?", {"payment": "COD"}, {}),
    ("Nếu COD thì phí ship bao nhiêu em?", {"payment": "COD"}, {}),
    ("Chị lấy COD nhé.", {"payment": "COD"}, {"payment": "COD"}),
    ("COD nha em.", {"payment": "COD"}, {"payment": "COD"}),
    ("Ship COD cho chị được không em?", {"payment": "COD"}, {"payment": "COD"}),
    ("Chị chuyển khoản trước nhé.", {"payment": "bank"}, {"payment": "bank"}),
    ("Chị không chuyển khoản đâu, COD thôi.", {"payment": "COD"}, {"payment": "COD"}),
    ("Giao về 15 Nguyễn Huệ, Quận 1 cho chị nhé.", {"address": "15 Nguyễn Huệ, Quận 1"}, {"address": "15 Nguyễn Huệ, Quận 1"}),
    ("Không phải 15 Nguyễn Huệ, Quận 1 đâu em.", {"address": "15 Nguyễn Huệ, Quận 1"}, {}),
    ("Size 41 còn không em?", {"size": "41"}, {"size": "41"}),
]
for text, slots, want in G3:
    ok("G3-slot", text, stance.filter_customer_slots(text, dict(slots)), want)
with patch.object(settings, "contract_v2", True), patch.object(settings, "extractor_backend", "rules"):
    ok("G3-route", "JEVNEW-012 rules route", extractor.customer_slots(
        "Chị chỉ hỏi bên em có COD không, chưa chọn hình thức thanh toán.", "2026-10-20").get("payment"), None)
    ok("G3-route", "chosen COD kept", extractor.customer_slots("Chị lấy COD nhé.", "2026-10-20").get("payment"), "COD")
with patch.object(settings, "contract_v2", False), patch.object(settings, "extractor_backend", "rules"):
    # 10/11 (FINAL G3): "hỏi COD ≠ chọn COD" là bất biến kể cả khi tắt cờ; khi tắt cờ chỉ slot payment theo stance,
    # màu/size/địa chỉ giữ nguyên như customer_slots_rules (parity phần còn lại).
    legacy = extractor.customer_slots("Chị chỉ hỏi bên em có COD không, chưa chọn hình thức thanh toán.", "2026-10-20")
    ok("G6-parity", "flag off: payment question dropped", legacy.get("payment"), None)
    t = "Không phải 15 Nguyễn Huệ, Quận 1 đâu em, size 41 nhé."
    ok("G6-parity", "flag off: non-payment slots equal customer_slots_rules", extractor.customer_slots(t, "2026-10-20"),
       extractor.customer_slots_rules(t, "2026-10-20"))

# ------------------------------------------------------------------ G4: guardrail theo mệnh đề + cam kết
from harness import guardrails  # noqa: E402
W = {12}
G4W = [
    ("Không lo ạ, máy bảo hành 3 năm.", True),
    ("Dạ máy bảo hành 3 năm ạ.", True),
    ("Nếu chị đặt hôm nay em ghi bảo hành 3 năm ạ.", True),
    ("Quản lý hứa bảo hành 3 năm thì em ghi nhận ạ.", True),
    ("Hiện chưa có chính sách bảo hành 3 năm, sản phẩm bảo hành 12 tháng ạ.", False),
    ("Bảo hành 3 năm là bên nào báo chị ạ?", False),
    ("Dạ bảo hành 3 năm là gói mở rộng mua thêm ạ.", False),
    ("Máy bảo hành 12 tháng ạ.", False),
]
for text, want in G4W:
    ok("G4-warranty", text, bool(guardrails.warranty_problems_v2(text, W)), want)
ok("G4-warranty", "legacy hole documented: 'Không lo ạ, máy bảo hành 3 năm.' passes old check",
   guardrails.warranty_problems("Không lo ạ, máy bảo hành 3 năm.", W), [])

NOGIFT = {"active": [], "expired": [{"type": "gift", "gift_name": "Bình giữ nhiệt"}]}
G4S = [
    ("Em sẽ giữ quà cho chị ạ.", NOGIFT, True),
    ("Dạ em ghi thêm quà tặng cho chị nhé.", NOGIFT, True),
    ("Em không thể giữ quà cho chị vì chương trình đã hết hạn ạ.", NOGIFT, False),
    ("Mẫu này đang giảm 50% ạ.", {"active": [{"discount_percent": 10}], "expired": []}, True),
    ("Mẫu này đang giảm 10% ạ.", {"active": [{"discount_percent": 10}], "expired": []}, False),
    ("Hiện không giảm 50% đâu ạ.", {"active": [{"discount_percent": 10}], "expired": []}, False),
    ("Sản phẩm giúp điều trị bệnh hen ạ.", None, True),
    ("Sản phẩm không điều trị được bệnh hen ạ.", None, False),
    ("Sản phẩm không những dễ dùng mà còn điều trị bệnh hen ạ.", None, True),
    ("Em không thể xác nhận sản phẩm điều trị bệnh hen, em chuyển chuyên viên ạ.", None, False),
]
for text, promos, want in G4S:
    ok("G4-stance", text, bool(guardrails.stance_problems(text, promos)), want)

G4C = [
    ("Dạ em đã lên đơn cho chị rồi ạ.", ["confirm_order"], True),
    ("Dạ em đã lên đơn cho chị rồi ạ.", ["order_created"], False),
    ("Dạ đơn của chị đã được tạo thành công ạ.", ["ask_address"], True),
    ("Chị đã đặt đơn hôm trước ạ.", ["quote"], False),
    ("Nếu chị đồng ý em sẽ tạo đơn ngay ạ.", ["confirm_order"], False),
    ("Em chưa tạo đơn đâu ạ, chị xác nhận giúp em nhé.", ["confirm_order"], False),
    ("Dạ em đã chuyển yêu cầu hủy cho nhân viên phụ trách ạ.", ["cancel_handoff"], False),
    ("Dạ em đã chuyển yêu cầu cho nhân viên phụ trách ạ.", ["quote"], True),
    ("Em đã cập nhật địa chỉ giao hàng sang 15 Nguyễn Huệ ạ.", ["confirm_delivery_address"], True),
    ("Em đã cập nhật địa chỉ giao hàng sang 15 Nguyễn Huệ ạ.", ["address_updated"], False),
    ("Dạ em đã hủy đơn cho chị rồi ạ.", ["cancel_handoff"], True),
    ("Dạ em đã xóa toàn bộ dữ liệu của anh ạ.", ["refuse_other_customer"], True),
    ("Dạ em đã xóa toàn bộ dữ liệu của anh ạ.", ["data_deleted"], False),
    ("Em đã hẹn gọi lại chị lúc 9 giờ sáng mai ạ.", ["defer_ack"], True),
    ("Đơn OD600001 của chị đã được tạo và đang giao ạ.", ["order_status"], False),
]
for text, goals, want in G4C:
    ok("G4-commit", f"{goals} | {text}", bool(guardrails.commitment_problems(text, goals)), want)

with patch.object(settings, "contract_v2", True):
    ok("G4-check", "check() includes commitment", bool(guardrails.check("Dạ em đã lên đơn cho chị rồi ạ.", set(), goals=["confirm_order"])), True)
    ok("G4-check", "check() clean text", guardrails.check("Dạ máy này bảo hành 12 tháng ạ.", set(), goals=["quote"], warranty=W), [])
with patch.object(settings, "contract_v2", False):
    ok("G6-parity", "check() flag off ignores commitment", guardrails.check("Dạ em đã lên đơn cho chị rồi ạ.", set(), goals=["confirm_order"]), [])

# G4b (thêm 09/11 sau Full đợt 2): số tiền khách nêu đọc như giá SP khi "giá" làm chủ ngữ trong mệnh đề.
# Ca đầu là câu thật V3-089 lượt 2; các ca còn lại viết mới.
CM = {1000000, 3000000}
G4B = [
    ("Dạ, giá HikePro hiện là 1.000.000đ. Em chưa có thông tin về bảo hành sản phẩm này.", True),
    ("Dạ giá giày trekking HikePro bây giờ là 1.000.000đ ạ.", True),
    ("Dạ, giá HikePro là 1.990.000đ, không phải 1.000.000đ ạ.", False),
    ("Dạ, giá này nằm trong ngân sách 3.000.000đ của anh nhé.", False),
    ("Dạ, mẫu này rẻ hơn mức 3.000.000đ anh dự tính ạ.", False),
    ("Dạ, chị muốn tìm máy tầm 3.000.000đ đúng không ạ?", False),
]
for text, want in G4B:
    with patch.object(settings, "contract_v2", True):
        got = any("khách nêu như giá" in p for p in guardrails.check(text, {1990000} | CM, customer_money=CM))
    ok("G4b-echo", text, got, want)
with patch.object(settings, "contract_v2", False):
    ok("G6-parity", "flag off keeps 30-char price cue",
       any("khách nêu như giá" in p for p in guardrails.check(G4B[0][0], CM, customer_money=CM)), False)

# G5 (speech_act_gate của planner_executor) bỏ cùng selector Jev/Qwen 24/11.

# ------------------------------------------------------------------ G6: kết quả tạo đơn chưa rõ
# 10/11 (bàn giao FINAL, G1): bỏ đối soát theo SKU/ngày (_reconcile_create) — 0/1/nhiều ứng viên đều không chứng minh
# correlation. Bất biến mới (không phụ thuộc cờ) kiểm ở tests/outcome_contract_check.py; ở đây chỉ giữ G6b.
from harness import goal_contract  # noqa: E402

# G6b (thêm 09/11 sau Full rules): tạo đơn xong rồi xin địa chỉ/SĐT là bước tiếp theo, không phải kết quả mâu thuẫn.
# 10/11: thành bất biến cho cả khi tắt cờ (28 lượt tạo đơn thật trên đường rules mặc định bị thay bằng contract_error).
for v2, goals, want in [(True, ["order_created", "ask_address"], False), (True, ["order_created", "ask_payment"], False),
                        (True, ["order_created", "order_failed"], True), (True, ["order_created", "ask_variant"], True),
                        (False, ["order_created", "ask_address"], False), (False, ["order_created", "order_unresolved"], True)]:
    with patch.object(settings, "contract_v2", v2):
        errs = goal_contract.validate(goals, {"order": {"order_id": "OD600009", "total_vnd": 1990000}})
        ok("G6b-conflict", f"v2={v2} {goals}", "conflicting_order_result" in errs, want)

# ------------------------------------------------------------------ kết quả
summary = {"passed": PASS[0], "failed": len(FAIL), "failures": [{"group": g, "case": n, "got": repr(a), "want": repr(b)} for g, n, a, b in FAIL]}
out = os.environ.get("CONTRACT_V2_OUT")
if out:
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "contract_v2_check.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"passed": summary["passed"], "failed": summary["failed"]}), flush=True)
sys.exit(1 if FAIL else 0)
