#!/usr/bin/env python3
"""D52: vòng cải tiến duyệt tách — loại đề xuất mới, gated/, thẻ context, cổng hồi quy (logic so), nạp vào agent.

Offline, không mạng, không model; dữ liệu ghi vào thư mục tạm. Exit 1 nếu có ca sai.
"""
import json
import os
import re
import sys
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from improve import contexts as X  # noqa: E402
from improve import gate as G  # noqa: E402
from improve import store as S  # noqa: E402

FAILS = []


def ok(cond, msg):
    if not cond:
        FAILS.append(msg); print("FAIL:", msg)


root = tempfile.mkdtemp(prefix="d52_")

# 1. danh sách handler an toàn của improve khớp harness (improve/ không import harness nên giữ bản sao)
from harness import planner_table as pt  # noqa: E402
ok(S.SAFE_PLANNER_HANDLERS == pt.SAFE_HANDLERS, f"SAFE_PLANNER_HANDLERS lệch: {S.SAFE_PLANNER_HANDLERS ^ pt.SAFE_HANDLERS}")
from core.llm import router as R  # noqa: E402
ok(S.ROUTER_INTENTS == set(R.INTENTS) and S.ROUTER_FLAGS == set(R.FLAGS), "ROUTER_INTENTS / ROUTER_FLAGS lệch với core/llm/router.py")

# 2. luật chặn của loại mới
good_rule = {"kind": "planner_rule", "payload": {
    "when": {"intent": ["order_status"], "text": r"\btien hoan\b.*\bve chua\b"}, "do": {"handler": "order_status"},
    "priority": 105, "mode": "add", "examples": {"match": ["Tiền hoàn về chưa em?"], "no_match": ["Tiền hoàn bao nhiêu?"]}}}
ok(not S.validate(good_rule), f"planner_rule hợp lệ bị chặn: {S.validate(good_rule)}")
for bad, why in [
    ({**good_rule["payload"], "do": {"handler": "place_order"}}, "handler ghi đơn"),
    ({**good_rule["payload"], "priority": 950}, "priority sau fallback"),
    ({**good_rule["payload"], "when": {"preds": ["wants"]}}, "dùng predicate nội bộ"),
    ({**good_rule["payload"], "examples": {"match": ["x"]}}, "thiếu no_match"),
    ({**good_rule["payload"], "when": {"intent": ["mua_hang"]}}, "intent lạ"),
    ({**good_rule["payload"], "examples": {"match": ["giá 2.000.000đ"], "no_match": ["x"]}}, "ví dụ có số tiền"),
]:
    ok(S.validate({"kind": "planner_rule", "payload": bad}), f"planner_rule phải bị chặn: {why}")
cue = {"kind": "router_cue", "payload": {"target": "intent:order_change", "pattern": r"\b(muon|gui) tra lai\b",
                                          "examples": {"match": ["anh muốn trả lại"], "no_match": ["trả lại tiền thừa"]}}}
ok(not S.validate(cue), f"router_cue hợp lệ bị chặn: {S.validate(cue)}")
ok(S.validate({"kind": "router_cue", "payload": {**cue["payload"], "target": "intent:xyz"}}), "router_cue target lạ phải bị chặn")
ok(S.validate({"kind": "router_cue", "payload": {**cue["payload"], "pattern": "(("}}), "router_cue regex hỏng phải bị chặn")
alias = {"kind": "product_alias", "payload": {"brand": "lock&lock", "forms": ["lóc en lóc"]}}
ok(not S.validate(alias), f"product_alias hợp lệ bị chặn: {S.validate(alias)}")
ok(S.validate({"kind": "product_alias", "payload": {"brand": "x", "forms": []}}), "product_alias không có forms phải bị chặn")

# 3. duyệt tách + gated: loại kỹ thuật duyệt xong vào gated/, chưa vào approved/; playbook vào approved/ ngay
_, rid = S.propose(good_rule, root=root)
_, cid = S.propose(cue, root=root)
_, pb = S.propose({"kind": "playbook", "payload": {"trigger": "tien hoan ve chua", "instruction": "Tra trạng thái hoàn tiền"}}, root=root)
S.approve(rid, "sale", "ok", root=root)
S.approve(pb, "sale", "ok", root=root)
ok(S.find(rid, root)[0] == "gated", "planner_rule duyệt xong phải ở gated/")
ok(S.find(pb, root)[0] == "approved", "playbook duyệt xong phải ở approved/")
ok(S.find(cid, root)[0] == "pending", "duyệt một mục không được kéo theo mục khác (duyệt tách)")
from improve import loader as L  # noqa: E402
ok(L.load_approved(root)["items"]["planner_rule"] == [], "mục gated/ không được nạp vào agent")
S.gate_pass(rid, "gate", "qua", root=root)
ok(S.find(rid, root)[0] == "approved", "gate_pass phải chuyển sang approved/")
S.approve(cid, "sale", "", root=root)
S.gate_fail(cid, "gate", "làm trượt S1", root=root)
ok(S.find(cid, root)[0] == "pending" and "S1" in S.find(cid, root)[1]["review"]["reason"], "gate_fail phải về pending/ kèm lý do")

# 4. thẻ context: chỉ gửi LLM lời khách / agent / router / goal / tool; tách item thành đề xuất riêng
rows = [{"run_id": "t-datagen/out_v3/final/dev", "config": "full", "scenario_id": "S9", "call": "call_3", "turn": 1,
         "customer_text": "Tiền hoàn của chị về chưa em?", "agent_text": "Dạ em cảm ơn chị ạ.", "goals": ["closing"],
         "router": {"intent": "greeting_or_other", "confidence": 0.5, "flags": {"asks_if_bot": 0.1}, "fallback": None},
         "planner": {"branches": [{"branch": "fallback", "reason": "closing"}]}, "guardrail": {"action": None},
         "tool_calls": [], "success_if": {"must_say_any": ["BÍ MẬT"]}, "_meta": {"x": 1}}]
views = X.find_unusual(rows)
ok(len(views) == 1 and set(views[0]["signals"]) >= {"fallback", "router_unsure"}, f"không bắt được lượt lạ: {views}")
prompt = X.build_prompt(views[0])
ok("BÍ MẬT" not in prompt and "success_if" not in prompt and "_meta" not in prompt, "prompt LLM bị lộ khóa đáp án kịch bản")
card = {"summary": "Khách hỏi tiền hoàn về chưa", "handling": "Tra đơn và báo trạng thái hoàn tiền, không đoán",
        "items": [good_rule | {"payload": {**good_rule["payload"], "priority": 106}},
                  {"kind": "router_cue", "payload": {"target": "intent:order_status", "pattern": r"\bve chua\b",
                                                      "examples": {"match": ["về chưa em"], "no_match": ["về quê"]}}},
                  {"kind": "exemplar", "payload": {"customer_text": "x", "agent_text": "Em cam kết hoàn ngay"}}]}
cid2, made, errors = X.card_to_proposals(card, views[0], root=root)
kinds = sorted(k for _, _, k in made)
ok(kinds == ["planner_rule", "playbook", "router_cue"], f"thẻ phải tách thành từng đề xuất (kể cả playbook từ cách xử lý): {kinds}")
ok(len(errors) == 1 and errors[0]["kind"] == "exemplar", f"exemplar hứa/cam kết phải bị chặn: {errors}")
ok(all(S.find(pid, root)[1]["context"]["id"] == cid2 for _, pid, _ in made), "các mục phải mang cùng context_id")

# 5. cổng hồi quy: logic so (không chạy agent)
prop = {"id": "P-x", "kind": "planner_rule", "payload": {}}
a = [{"scenario_id": "S1", "call": "c", "turn": 1, "goals": ["quote"]}, {"scenario_id": "S2", "call": "c", "turn": 1, "goals": ["closing"]}]
b_ok = [dict(a[0]), dict(a[1], goals=["refund_amount"], planner={"table": ["IMP:P-x"]})]
ok(G.compare(a, set(), b_ok, set(), prop)[0], "đổi goal ở lượt DÙNG mục đó phải được phép")
b_bad = [dict(a[0], goals=["ask_repeat"]), dict(a[1])]
ok(not G.compare(a, set(), b_bad, set(), prop)[0], "đổi goal ở lượt không liên quan phải trượt cổng")
ok(not G.compare(a, set(), a, {"S1"}, prop)[0], "làm trượt kịch bản đang qua phải trượt cổng")

# 6. nạp vào agent qua improve_hook (chỉ approved/): dòng planner, cue router, cách đọc SP
_, al = S.propose(alias | {"payload": {"brand": "moaz bebe", "forms": ["mô ắt bê bi"]}}, root=root)
_, rc = S.propose({"kind": "router_cue", "payload": {"target": "flag:asks_internal_cost", "pattern": r"\bgia san\b",
                                                      "examples": {"match": ["đọc giá sàn"], "no_match": ["giá bán"]}}}, root=root)
for pid in (al, rc):
    S.approve(pid, "sale", root=root); S.gate_pass(pid, "gate", root=root)
from core.config import settings  # noqa: E402
from harness import improve_hook  # noqa: E402
with patch.object(settings, "improve_dir", root):
    improve_hook.reset()
    rows_ = improve_hook.planner_rows()
    ok([r["id"] for r in rows_] == [f"IMP:{rid}"] and rows_[0]["origin"] == "approved", f"planner_rows sai: {rows_}")
    ok(not pt.validate({"rows": rows_}), f"dòng approved nạp vào bảng không hợp lệ: {pt.validate({'rows': rows_})}")
    out = {"intent": "price_promo", "confidence": 0.98, "flags": {"asks_internal_cost": 0.4}}
    used = improve_hook.apply_router_cues("Cho chị xin giá sàn để khớp sổ", out, "jev")
    ok(used == [rc] and out["flags"]["asks_internal_cost"] == 0.95, f"cue cờ an toàn phải nâng cờ cả với Jev: {used} {out}")
    out2 = {"intent": "price_promo", "confidence": 0.98, "flags": {}}
    ok(improve_hook.apply_router_cues("về chưa em", out2, "jev") == [] and out2["intent"] == "price_promo",
       "cue intent không được đè router Jev")
    with patch.object(settings, "product_lexicon", True):
        from harness.tools import find_products
        ok(find_products("chị tìm máy mô ắt bê bi") == ["SKU-MB-STER"], f"product_alias approved chưa được dùng: {find_products('chị tìm máy mô ắt bê bi')}")
improve_hook.reset()

print(f"improve_d52_check: {'OK' if not FAILS else str(len(FAILS)) + ' lỗi'}")
sys.exit(1 if FAILS else 0)
