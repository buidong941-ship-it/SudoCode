"""Kiểm harness/improve_hook.py (mục E): tắt mặc định thì agent/trace như cũ; bật thì chỉ approved/ được nạp.

- IMPROVE_DIR rỗng: không có khóa `improve` trong trace, plan không có PLAYBOOK/EXEMPLARS, knowledge không thêm FAQ;
- bật với thư mục tạm: FAQ khớp câu hỏi được thêm vào kết quả tra chính sách, playbook khớp trigger, exemplar theo goal,
  cue đã duyệt chặn chứng nhận rỗng; đề xuất PENDING không bao giờ được nạp; trace ghi approved_hash + id đã dùng;
- Exemplar Bank: che số tiền / ngày / mã đơn trước khi đề xuất.
"""
import os
import sys
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tmp = tempfile.mkdtemp(prefix="improve_hook_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "m.db").replace("\\", "/")
os.environ["TOOL_TRANSPORT"] = "direct"
os.environ.setdefault("RUN_PROFILE", "local")
os.environ.setdefault("RAG_MODE", "bm25")

from core.config import settings  # noqa: E402
from core.llm.generator import Generator  # noqa: E402
from core.llm.router import Router  # noqa: E402
from harness import agent, improve_hook, knowledge, lexicon  # noqa: E402
from harness.memory import Memory  # noqa: E402
from harness.textnorm import fold  # noqa: E402
from harness.tools import ToolBox  # noqa: E402
from improve import exemplars as EX  # noqa: E402
from improve import store as S  # noqa: E402

FAILS = []


def ok(c, m):
    if not c:
        FAILS.append(m); print("FAIL:", m)


root = os.path.join(tmp, "imp")
faq = S.propose({"kind": "faq", "payload": {"topic": "giữ hàng cuối tuần", "question": "Để cuối tuần mới lấy thì giữ hàng được không?",
                                            "answer": "Bên em giữ hàng tối đa trong thời gian đơn còn ở trạng thái chờ xác nhận; em ghi chú giữ giúp mình ạ."}},
                root=root)[1]
pb = S.propose({"kind": "playbook", "payload": {"trigger": "re:\\b(doi chieu|sap lich|ban lai)\\b",
                                                "instruction": "Khách cần thời gian: ghi nhận, hẹn gọi lại, không ép chốt."}}, root=root)[1]
ex = S.propose({"kind": "exemplar", "payload": {"customer_text": "Để chị bàn lại với nhà đã.",
                                                "agent_text": "Dạ vâng, chị cứ trao đổi thêm, mai em gọi lại chị nhé ạ.",
                                                "goals": ["defer_ack"]}}, root=root)[1]
cue = S.propose({"kind": "cue", "payload": {"slot": "blocker", "pattern": "\\bdoi chieu nhu cau\\b"}}, root=root)[1]
pending_only = S.propose({"kind": "playbook", "payload": {"trigger": "re:\\bdoi chieu\\b", "instruction": "KHÔNG ĐƯỢC NẠP"}},
                         root=root)[1]
for pid in (faq, pb, ex, cue):
    S.approve(pid, "tester", root=root)

# ---------- tắt ----------
with patch.object(settings, "improve_dir", ""):
    improve_hook.reset()
    ok(not improve_hook.enabled() and improve_hook.apply_to_plan({}, "x", ["quote"]) == [], "tắt: không gắn gì")
    hits = knowledge.search("Để cuối tuần mới lấy thì giữ hàng được không?", k=2)
    ok(not any(str(h.get("chunk_id", "")).startswith("FAQ:") for h in hits), "tắt: knowledge không có FAQ")
    ok(lexicon.cue_hit(fold("chờ anh đối chiếu nhu cầu đã")) is None or not str(
        lexicon.cue_hit(fold("chờ anh đối chiếu nhu cầu đã"))).startswith("P-"), "tắt: không có cue improve")

# ---------- bật ----------
with patch.object(settings, "improve_dir", root):
    improve_hook.reset()
    hits = knowledge.search("Nếu để cuối tuần mới lấy thì giữ hàng được không ạ?", k=2)
    ok(any(h.get("chunk_id") == f"FAQ:{faq}" for h in hits), f"bật: FAQ phải được thêm: {[h.get('chunk_id') for h in hits]}")
    plan = {}
    used = improve_hook.apply_to_plan(plan, "Chờ anh đối chiếu nhu cầu đã.", ["defer_ack"])
    ok(plan.get("PLAYBOOK") == ["Khách cần thời gian: ghi nhận, hẹn gọi lại, không ép chốt."], f"playbook: {plan}")
    ok(plan.get("EXEMPLARS") and plan["EXEMPLARS"][0]["khach"].startswith("Để chị bàn lại"), f"exemplar: {plan}")
    ok(pending_only not in used and "KHÔNG ĐƯỢC NẠP" not in str(plan), "đề xuất pending không được nạp")
    ok(lexicon.cue_hit(fold("Chờ anh đối chiếu nhu cầu đã.")) == cue, "cue improve phải chặn chứng nhận rỗng")
    mem = Memory("improve_hook:on")
    mem.wipe()
    ToolBox.reset_world()
    s = agent.CallSession(memory=mem, today="2026-10-15", call_name="call_1", session_id="ih:1", channel="hotline",
                          channel_identity=None, phone="0911333444", input_mode="text", router=Router("rules"),
                          generator=Generator("offline"), config="full")
    s.start()
    s.turn("Máy lọc không khí AirPure Y giá bao nhiêu em?")
    row = s.turn("Chờ anh đối chiếu nhu cầu đã.")
    imp = row.get("improve") or {}
    ok(imp.get("approved_hash") == S.approved_hash(root) and pb in imp.get("used", []), f"trace improve: {imp}")
improve_hook.reset()

# ---------- trace khi tắt không có khóa improve ----------
with patch.object(settings, "improve_dir", ""):
    mem = Memory("improve_hook:off")
    mem.wipe()
    ToolBox.reset_world()
    s = agent.CallSession(memory=mem, today="2026-10-15", call_name="call_1", session_id="ih:2", channel="hotline",
                          channel_identity=None, phone="0911333555", input_mode="text", router=Router("rules"),
                          generator=Generator("offline"), config="full")
    s.start()
    row = s.turn("Chờ anh đối chiếu nhu cầu đã.")
    ok("improve" not in row, "tắt: trace không có khóa improve")

# ---------- Exemplar Bank che số ----------
m = EX.mask("Dạ đơn OD600001 tổng 5.200.000đ, giao ngày 22/10, giảm 10% ạ, gọi 0912345678.")
ok("OD600001" not in m and "5.200.000" not in m and "22/10" not in m and "10%" not in m and "0912345678" not in m, f"mask: {m}")
ok(not S.validate({"kind": "exemplar", "payload": {"customer_text": "x", "agent_text": m}}), "câu đã che phải qua validate")

print("TẤT CẢ OK" if not FAILS else f"{len(FAILS)} LỖI")
sys.exit(1 if FAILS else 0)
