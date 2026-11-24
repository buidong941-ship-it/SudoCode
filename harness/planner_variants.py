"""Hai biến thể chủ sở hữu tiến trình trên cấu hình đích (docs/PLAN/THIET-KE-B1-B2-JEV-B3-WORKFLOW-2026-11-12.md, mục 2–3).

Dùng chung: bộ hiểu DeepSeek, request_state (quyền / target / revision), safety + danh tính (target_safety, dòng R00…R07),
mở đầu, renderer, guardrail, audit. Khác nhau ở AI quyết định bước tiếp theo của nghiệp vụ:

  b1           bảng hiện tại (planner_table.plan, không owner) — đối chứng, hành vi không đổi.
  b2_jev       Jev chọn từng bước (đọc giá / kho / đơn / chính sách, trả lời ask, ghi yêu cầu, hỏi rõ, dừng) và quan sát kết quả
               tool rồi chọn tiếp trong cùng lượt (harness/planner_b2.py). Sở hữu dòng TIẾN TRÌNH + dòng TRẢ LỜI.
  (b3_workflow đã xóa 24/11.)

Factory dựng planner MỘT lần khi mở session (CallSession.__init__); không sửa settings toàn cục để đổi biến thể trong cùng
process. Bảng đổi dòng mà chưa xếp nhóm → lỗi rõ (buộc quyết định dòng mới thuộc phần chung hay tiến trình).
"""
from core.config import settings, check_variant

# Dòng chung cho mọi biến thể: danh tính, ASR rè, mở đầu, bot/meta, an toàn dữ liệu, chuyển máy, giá nội bộ, lỗ tri thức,
# mặc cả / đối thủ (lời đáp hội thoại), hoãn quyết định, hết lượt hỏi lại, fallback.
COMMON_ROWS = frozenset({"R00", "N01", "R01", "R02", "P01", "R03", "R04", "R05", "N03", "R06", "R07",
                         "R24a", "R24b", "R25", "R35", "E07", "R36"})
# Tiến trình nghiệp vụ: thao tác trên đơn (đổi địa chỉ / đổi / trả / hủy / tra đơn) và bán hàng (chốt, đặt, bổ sung địa chỉ,
# báo giá lại do đổi giá, hẹn gọi lại, đóng đề nghị bị từ chối).
ORDER_ROWS = frozenset({"T01", "R08", "R09", "E03", "R10", "R11", "R12"})
SALES_ROWS = frozenset({"E12", "E15", "R28", "R29", "R30", "R31", "R32", "R33", "R34", "N04"})
# Trả lời câu hỏi (có nguồn): tiền hoàn, ghi chú cập nhật, chính sách, thuộc tính, bảo hành, tư vấn, giá, ngân sách, quà, giỏ, COD.
ANSWER_ROWS = frozenset({"N02", "R13", "R14", "R15", "R16", "R17", "R18", "R19", "R20", "R21", "R22", "R23", "R26", "R27"})


def check_partition(rows):
    """Mọi dòng core phải thuộc đúng một nhóm. Dòng approved (C.5) không chạy trên cấu hình đích (check_arch)."""
    groups = (COMMON_ROWS, ORDER_ROWS, SALES_ROWS, ANSWER_ROWS)
    bad = [r["id"] for r in rows if r.get("origin", "core") == "core" and sum(r["id"] in g for g in groups) != 1]
    if bad:
        raise ValueError(f"planner_variants: dòng bảng chưa xếp nhóm chung/tiến trình/trả lời: {bad}")


class B1:
    """Đối chứng: bọc entrypoint bảng hiện tại. Không gọi prepare/finish/safety thêm lần nào."""
    name = "b1"

    def plan(self, s, text, slots, route):
        from harness import planner_table
        s.planner_loop = None
        return planner_table.plan(s, text, slots, route)


class _Owned:
    name = None
    owned = frozenset()
    post_stop_rows = frozenset()        # dòng chung vẫn chạy (predicate / group / thứ tự) sau khi owner kết thúc lượt — 13/11

    def owns(self, row):
        return row["id"] in self.owned

    def plan(self, s, text, slots, route):
        from harness import planner_table, improve_hook
        rows = planner_table.load_rows(extra=improve_hook.planner_rows())
        check_partition(rows)
        s.planner_loop = None
        return planner_table.plan(s, text, slots, route, rows=rows, owner=self)


class B2Jev(_Owned):
    name = "b2_jev"
    owned = ORDER_ROWS | SALES_ROWS | ANSWER_ROWS
    # 13/11 (bàn giao cải thiện B2, S5): sau khi vòng Jev kết thúc có nội dung, các dòng phản hồi chung mặc cả / đối thủ / hoãn vẫn
    # chạy theo predicate (v6: bị bỏ → V3-047…050). E07 (chuyển máy khi hết lượt hỏi lại) và R36 (fallback) KHÔNG chạy lại.
    post_stop_rows = frozenset({"R24a", "R24b", "R25", "R35"})

    def __init__(self, decider=None):
        self.decider = decider          # None = Jev thật (hoặc mô phỏng khi JEV_SIMULATED=1); test truyền bộ quyết định cố định

    def phase(self, row):
        return "jev"                    # một vòng lập kế hoạch duy nhất, tại vị trí dòng tiến trình / trả lời đầu tiên

    def run(self, c, phase):
        from harness import planner_b2
        return planner_b2.run(c, self.decider)


def make(variant=None, decider=None):
    """Factory — gọi một lần khi mở session. Tổ hợp mâu thuẫn bị từ chối (core.config.check_variant)."""
    variant = variant or settings.planner_variant
    check_variant(variant, settings)
    if variant == "b1":
        return B1()
    return B2Jev(decider)
