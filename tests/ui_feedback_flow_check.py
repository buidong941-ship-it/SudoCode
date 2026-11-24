"""Kaggle CPU: feedback → DeepSeek giả → nháp thật chờ duyệt; lỗi/timeout không báo thành công."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
TMP = Path(tempfile.mkdtemp(prefix="feedback-flow-"))
os.environ.update(UI_PROFILE="legacy_offline", UI_DATA_DIR=str(TMP / "ui"),
                  C5_ROOT=str(TMP / "faq"), C5_STATE_DIR=str(TMP / "state"),
                  GUIDE_ROOT=str(TMP / "guides"), GUIDE_STATE_DIR=str(TMP / "guide-state"),
                  DATABASE_URL="sqlite:///" + str(TMP / "memory.db"))
os.environ.pop("UI_PASSWORD", None)
os.environ.pop("DEEPSEEK_API_KEY", None)
from streamlit.testing.v1 import AppTest
from ui import engine as E
from improve import store as S
import guidance_draft as GD


def button(app, label):
    return next(b for b in app.button if b.label == label)


guide = {"title": "Trả lời giá mẫu khách đang hỏi", "audience": "both", "tags": ["gia"],
         "applies_when": ["Khách hỏi giá mẫu đã nêu"], "exceptions": ["Chưa biết mẫu khách muốn hỏi"],
         "guidance": ["Chọn read_quote cho mẫu khách nêu trước answer_ask"],
         "avoid": ["Chọn finish khi chưa trả lời giá"], "examples": ["Máy lọc đó giá bao nhiêu"],
         "requires_capabilities": ["price_read"], "asks_any": ["price"]}


class FakeDeepSeek:
    def json(self, prompt, **kwargs):
        assert "du_lieu_feedback" in prompt and "Chưa báo giá" in prompt
        return {"class": "guidance_fixable", "reason": "Có bước đọc giá chưa dùng",
                "proposal": {"mode": "new", "guide": guide}}


real_run = subprocess.run
calls = []


def run_draft(args, **kwargs):
    if not isinstance(args, list) or str(ROOT / "scripts/guidance_draft.py") not in args:
        return real_run(args, **kwargs)
    calls.append(args)
    trace_index = args.index("--ui-trace")
    traces = args[trace_index + 1:]
    assert traces and all(Path(p).is_file() for p in traces)
    assert kwargs["cwd"] == E.ROOT and kwargs["env"]["DEEPSEEK_API_KEY"] == "fake-key"
    options = SimpleNamespace(root=E.GUIDE_ROOT, feedback=E.FEEDBACK, ui_trace=traces,
                              trace=None, report=None, existing=None, limit=10, skip_drafted=True)
    assert "--skip-drafted" in args
    result = GD.run(options, FakeDeepSeek())
    output = {k: len(v) if isinstance(v, list) else v for k, v in result.items()}
    return SimpleNamespace(returncode=0, stdout=json.dumps(output), stderr="")


with patch.object(E, "CANDIDATE", True), patch.object(E, "startup_check", return_value={
        "ok": True, "label": "internal", "arch": "", "planner_variant": "b1"}):
    app = AppTest.from_file(str(ROOT / "ui/dashboard.py"), default_timeout=120).run()
    assert not app.exception
    assert button(app, "Soạn hướng dẫn từ feedback").disabled
    assert button(app, "Nhập vào hàng chờ duyệt").disabled
    assert any(s.value == "Sẵn sàng tiếp nhận cuộc gọi" for s in app.success)
    Path(E.UI_DIR).mkdir(parents=True, exist_ok=True)
    Path(E.TRACES).mkdir(parents=True, exist_ok=True)
    row = {"session_id": "S1", "turn": 1, "customer_text": "Máy lọc đó giá bao nhiêu",
           "agent_text": "Anh cần mẫu nào", "tool_calls": [], "goals": [], "planner": {}}
    (Path(E.TRACES) / "S1.jsonl").write_text(json.dumps(row), encoding="utf-8")
    Path(E.FEEDBACK).write_text(json.dumps({"msg_id": "S1:1", "rating": -1,
                                          "note": "Chưa báo giá", "by": "NV"}), encoding="utf-8")
    app.run()
    assert button(app, "Soạn hướng dẫn từ feedback").disabled
    os.environ["DEEPSEEK_API_KEY"] = "fake-key"
    app.run()
    assert not button(app, "Soạn hướng dẫn từ feedback").disabled
    with patch("subprocess.run", side_effect=run_draft):
        button(app, "Soạn hướng dẫn từ feedback").click().run()
    assert not app.exception, [e.value for e in app.exception]
    assert len(calls) == 1
    pending = S.list_state("pending", E.GUIDE_ROOT)
    assert len(pending) == 1 and pending[0]["kind"] == "planner_guidance", {
        "pending": pending, "errors": [e.value for e in app.error]}
    assert not S.list_state("approved", E.GUIDE_ROOT)
    assert not Path(E.GUIDE_STATE, "active.json").exists()
    assert any("Đã đưa 1 bản nháp" in s.value for s in app.success)
    print("PASS: feedback and key gates; UI invokes drafter with traces; real pending only; neutral ready label")
    with patch("subprocess.run", side_effect=run_draft):
        button(app, "Soạn hướng dẫn từ feedback").click().run()
    assert not app.exception and len(S.list_state("pending", E.GUIDE_ROOT)) == 1
    assert any("Chưa có bản nháp hợp lệ" in s.value for s in app.info)
    print("PASS: repeated drafting skips feedback already represented in pending or approved")
    with patch("subprocess.run", return_value=SimpleNamespace(returncode=1, stdout="", stderr="provider unavailable")):
        button(app, "Soạn hướng dẫn từ feedback").click().run()
    assert not app.exception and any("provider unavailable" in e.value for e in app.error)
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("draft", 1200)):
        button(app, "Soạn hướng dẫn từ feedback").click().run()
    assert not app.exception and any("quá thời gian" in e.value for e in app.error)
    assert len(S.list_state("pending", E.GUIDE_ROOT)) == 1
    print("PASS: provider errors and timeout preserve draft and approval state")
