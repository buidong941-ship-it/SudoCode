"""Kiểm B-H (planner hybrid có giới hạn, harness/planner_llm.py) bằng mock — không gọi Jev/Qwen thật.

- PLANNER_BACKEND=rules (mặc định): không bao giờ gọi LLM; trace planner.backend = rules, không có khóa llm;
- danh sách goal đóng theo trạng thái: không có đơn → không có order_status; có sản phẩm → quote, chưa có → ask_product;
- Jev: tin cậy dưới ngưỡng → abstain, KHÔNG gọi Qwen; Jev lỗi → Qwen; goal ngoài danh sách → bị code từ chối;
- tích hợp: lượt fallback gọi LLM, code kiểm điều kiện, trace ghi đề xuất + quyết định.
"""
import os
import sys
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tmp = tempfile.mkdtemp(prefix="planner_llm_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "m.db").replace("\\", "/")
os.environ["TOOL_TRANSPORT"] = "direct"
os.environ.setdefault("RUN_PROFILE", "local")
os.environ.setdefault("RAG_MODE", "bm25")

from core.config import settings  # noqa: E402
from core.llm.generator import Generator  # noqa: E402
from core.llm.router import Router  # noqa: E402
from harness import agent, planner_llm  # noqa: E402
from harness.memory import Memory  # noqa: E402
from harness.tools import ToolBox  # noqa: E402

FAILS = []


def ok(c, m):
    if not c:
        FAILS.append(m); print("FAIL:", m)


# danh sách đóng
g0 = planner_llm.allowed_goals({"focus": None, "has_orders": False})
g1 = planner_llm.allowed_goals({"focus": "SKU-AP-Y", "has_orders": True})
ok("order_status" not in g0 and "ask_product" in g0 and "quote" not in g0, f"goal khi chưa có gì: {g0}")
ok("order_status" in g1 and "quote" in g1 and "ask_product" not in g1, f"goal khi có sản phẩm + đơn: {g1}")
ok(not any(x.startswith("order_c") or x.startswith("order_u") for x in planner_llm.GOALS), "không được có goal tạo/sửa đơn")

with patch.object(settings, "planner_jev_min_conf", 0.6):
    with patch.object(planner_llm, "_jev", return_value=("quote", 0.9)), \
         patch.object(planner_llm, "_qwen", side_effect=AssertionError("không được gọi Qwen")):
        s = planner_llm.suggest("giá sao em", [], {"focus": "SKU-AP-Y"}, backend="jev")
        ok(s["goal"] == "quote" and s["backend"] == "jev", f"jev chọn quote: {s}")
    with patch.object(planner_llm, "_jev", return_value=("closing", 0.3)), \
         patch.object(planner_llm, "_qwen", side_effect=AssertionError("dưới ngưỡng không được gọi Qwen")):
        s = planner_llm.suggest("ừm", [], {}, backend="jev")
        ok(s["goal"] is None and s.get("abstain"), f"dưới ngưỡng phải abstain: {s}")
    with patch.object(planner_llm, "_jev", side_effect=TimeoutError("chậm")), \
         patch.object(planner_llm, "_qwen", return_value=("defer_ack", None)) as q:
        s = planner_llm.suggest("để chị tính", [], {}, backend="jev")
        ok(q.call_count == 1 and s["goal"] == "defer_ack" and s["backend"] == "qwen" and "jev" in s["fallback"],
           f"Jev lỗi phải rơi sang Qwen: {s}")
    with patch.object(planner_llm, "_jev", side_effect=AssertionError("rules không được gọi Jev")):
        ok(planner_llm.suggest("x", [], {}, backend="rules")["goal"] is None, "rules → không gọi gì")


def session(name, phone="0911222333"):
    mem = Memory(f"planner_llm:{name}")
    mem.wipe()
    ToolBox.reset_world()
    s = agent.CallSession(memory=mem, today="2026-10-15", call_name="call_1", session_id=f"{name}:1", channel="hotline",
                          channel_identity=None, phone=phone, input_mode="text", router=Router("rules"),
                          generator=Generator("offline"), config="full")
    s.start()
    return s


FALLBACK_TURN = "Ừm vậy hả, thế thì sao nhỉ?"     # câu không khớp nhánh code nào → fallback
# rules: không gọi LLM, trace như cũ
with patch.object(settings, "planner_backend", "rules"), \
     patch.object(planner_llm, "suggest", side_effect=AssertionError("rules không được gọi planner LLM")):
    s = session("rules")
    s.turn("Máy lọc không khí AirPure Y giá bao nhiêu em?")
    row = s.turn(FALLBACK_TURN)
    ok(row["planner"]["backend"] == "rules" and "llm" not in row["planner"], f"trace rules phải như cũ: {row['planner']}")

# jev (mock): đề xuất được code chấp nhận
with patch.object(settings, "planner_backend", "jev"), \
     patch.object(planner_llm, "suggest", return_value={"goal": "quote", "confidence": 0.92, "backend": "jev",
                                                        "fallback": None, "ms": 5}):
    s = session("jev_ok")
    s.turn("Máy lọc không khí AirPure Y giá bao nhiêu em?")
    row = s.turn(FALLBACK_TURN)
    llm = row["planner"].get("llm") or {}
    ok(row["goals"] == ["quote"] and llm.get("accepted") and llm.get("goal") == "quote", f"jev quote: {row['goals']} {llm}")
    ok(any(t["name"] == "pricing.get_quote" for t in row["tool_calls"]), "goal quote phải lấy giá từ tool")

# jev (mock) chọn goal không hợp lệ ở trạng thái này → code từ chối, quay về nhánh code
with patch.object(settings, "planner_backend", "jev"), \
     patch.object(planner_llm, "suggest", return_value={"goal": "order_status", "confidence": 0.9, "backend": "jev",
                                                        "fallback": None, "ms": 5}):
    s = session("jev_reject", phone="0911222444")
    s.turn("Máy lọc không khí AirPure Y giá bao nhiêu em?")
    row = s.turn(FALLBACK_TURN)
    llm = row["planner"].get("llm") or {}
    ok(not llm.get("accepted") and "order_status" not in row["goals"], f"không có đơn thì phải từ chối order_status: {llm} {row['goals']}")
    ok(row["goals"][0] in ("ask_repeat", "closing"), f"bị từ chối thì quay về nhánh code: {row['goals']}")
    ok(s._apply_llm_goal("order_create", "x", {})[0] == [], "goal tạo đơn luôn bị từ chối")

print("TẤT CẢ OK" if not FAILS else f"{len(FAILS)} LỖI")
sys.exit(1 if FAILS else 0)
