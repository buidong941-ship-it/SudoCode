"""Kiểm phép đo địa chỉ ghi vào đơn (scripts/dev_report.address_audit, 14/11 phương án C). Dữ liệu tổng hợp, không chạy agent.

Loại: ok / tail_extra (đúng + đuôi thừa) / mismatch / no_expected / tail_extra_vs_previous_call (call không có địa chỉ riêng, so
với địa chỉ call trước CHỈ để bắt đuôi thừa); địa chỉ cuối tính sau order.update update_address; so không phân biệt dấu phẩy / hoa
thường / dấu tiếng Việt. Dùng: python tests/address_audit_check.py"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import dev_report as R  # noqa: E402

FAIL, PASS = [], [0]


def ok(name, got, want):
    if got == want:
        PASS[0] += 1
        print(f"OK   {name}", flush=True)
    else:
        FAIL.append(name)
        print(f"FAIL {name}: got={got!r} want={want!r}", flush=True)


A = "12 Lê Lợi, Huế"


def scen(calls):
    return {"S": {"calls": calls}}


def create(call, turn, addr, oid="OD1"):
    return {"scenario_id": "S", "call": call, "turn": turn,
            "tool_calls": [{"name": "order.create", "args": {"address": addr}, "result": {"order_id": oid}}]}


def update(call, turn, addr, oid="OD1"):
    return {"scenario_id": "S", "call": call, "turn": turn,
            "tool_calls": [{"name": "order.update", "args": {"order_id": oid, "action": "update_address", "reason": f"địa chỉ mới: {addr}"}}]}


def kinds(sc, rows):
    return R.address_audit(sc, rows)["counts"]


one = scen({"call_1": {"facts_established": {"address": A}}})
ok("đúng địa chỉ → ok", kinds(one, [create("call_1", 1, A)]), {"ok": 1})
ok("khác dấu phẩy / hoa thường / dấu → vẫn ok", kinds(one, [create("call_1", 1, "12 le loi hue")]), {"ok": 1})
ok("đuôi ', COD' → tail_extra", kinds(one, [create("call_1", 1, A + ", COD")]), {"tail_extra": 1})
ok("đuôi 'cho chị nhé' → tail_extra", kinds(one, [create("call_1", 1, A + " cho chị nhé")]), {"tail_extra": 1})
ok("địa chỉ khác → mismatch", kinds(one, [create("call_1", 1, "5 Trần Phú, Huế")]), {"mismatch": 1})
ok("args_match ưu tiên hơn facts",
   kinds(scen({"call_1": {"success_if": {"args_match": {"address": "5 Trần Phú, Huế"}}, "facts_established": {"address": A}}}),
         [create("call_1", 1, "5 Trần Phú, Huế")]), {"ok": 1})
ok("tạo bằng địa chỉ cũ rồi order.update sang đúng địa chỉ → ok + corrected_by_update",
   kinds(one, [create("call_1", 1, "9 Bà Triệu, Huế"), update("call_1", 2, A)]), {"ok": 1, "corrected_by_update": 1})
two = scen({"call_1": {"facts_established": {"address": A}}, "call_2": {}})
ok("call 2 không có địa chỉ riêng, đơn = địa chỉ call 1 + đuôi → tail_extra_vs_previous_call",
   kinds(two, [create("call_2", 1, A + " có")]), {"tail_extra_vs_previous_call": 1})
ok("call 2 không có địa chỉ riêng, đơn = địa chỉ KHÁC (người khác / chuyển nhà) → no_expected, không kết luận mismatch",
   kinds(two, [create("call_2", 1, "45 Trần Hưng Đạo, Cần Thơ")]), {"no_expected": 1})
ok("call 2 không có địa chỉ riêng, đơn = đúng địa chỉ call 1 → no_expected", kinds(two, [create("call_2", 1, A)]), {"no_expected": 1})
ok("không có order.create → rỗng", kinds(one, [{"scenario_id": "S", "call": "call_1", "turn": 1, "tool_calls": []}]), {})

print(f"\n{PASS[0]} OK, {len(FAIL)} lỗi")
raise SystemExit(1 if FAIL else 0)
