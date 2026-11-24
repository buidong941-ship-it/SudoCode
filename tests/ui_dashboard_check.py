"""Kiểm dashboard trên Kaggle CPU: mật khẩu, rerun cuộc gọi, feedback và biểu đồ report thiếu baseline."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TEMP = Path(tempfile.mkdtemp(prefix="dashboard-check-"))
os.environ.update(UI_PROFILE="legacy_offline", UI_PASSWORD="dashboard-test-password", UI_DATA_DIR=str(TEMP / "ui"),
                  C5_STATE_DIR=str(TEMP / "c5"), C5_ROOT=str(TEMP / "review"),
                  DATABASE_URL="sqlite:///" + str(TEMP / "memory.db"), LLM_CACHE="off")

from streamlit.testing.v1 import AppTest  # noqa: E402
import streamlit as st  # noqa: E402
from ui import engine as E  # noqa: E402


def button(app, label):
    return next(item for item in app.button if item.label == label)


def text_input(app, label):
    return next(item for item in app.text_input if item.label == label)


app = AppTest.from_file(str(ROOT / "ui/dashboard.py"), default_timeout=180).run()
assert not app.exception and not app.tabs, [e.value for e in app.exception]
text_input(app, "Mật khẩu").input("wrong").run()
assert not app.tabs and any("Sai mật khẩu" in error.value for error in app.error)
text_input(app, "Mật khẩu").input("dashboard-test-password").run()
assert not app.exception and len(app.tabs) == 5, [e.value for e in app.exception]
text_input(app, "Tên nhân viên").input("Kiểm giao diện").run()
button(app, "Bắt đầu cuộc gọi mới").click().run()
assert not app.exception and len(app.chat_input) == 1
app.chat_input[0].set_value("Máy lọc không khí AirPure Y giá bao nhiêu em?").run()
assert not app.exception and len(app.chat_message) >= 2, [e.value for e in app.exception]
button(app, "Cần cải thiện").click().run()
text_input(app, "Chưa ổn ở đâu? (tuỳ chọn)").input("ghi chú kiểm giao diện").run()
button(app, "Gửi").click().run()
feedback = [json.loads(line) for line in (TEMP / "ui/feedback.jsonl").read_text(encoding="utf-8").splitlines()]
assert len(feedback) == 1 and feedback[0]["rating"] == -1 and feedback[0]["by"] == "Kiểm giao diện"
button(app, "Kết thúc cuộc gọi").click().run()
button(app, "Bắt đầu cuộc gọi mới").click().run()
assert not app.exception and any("Call Brief" in heading.value for heading in app.subheader)
button(app, "Kết thúc cuộc gọi").click().run()
print("PASS: password, five tabs, chat reruns, feedback and returning-customer brief")

report_path = TEMP / "report.json"
report_path.write_text(json.dumps({"n_scenarios": 7, "system": {"task_success_rate": {"value": 75.0}}}), encoding="utf-8")
meta = {"label": "Kiểm report thiếu baseline", "version": "fixture", "dataset": "fixture", "backend": "offline",
        "measured": "fixture", "path": str(report_path)}
os.environ.pop("UI_PASSWORD")
with patch.object(E, "reports", return_value=[meta]), patch("streamlit.altair_chart", wraps=st.altair_chart) as draw_chart:
    charts = AppTest.from_file(str(ROOT / "ui/dashboard.py"), default_timeout=180).run()
assert not charts.exception, [e.value for e in charts.exception]
assert any(heading.value == "So sánh với baseline" for heading in charts.subheader)
assert draw_chart.call_count == 1
spec = draw_chart.call_args.args[0].to_dict()
values = spec["data"].get("values") or next(iter(spec["datasets"].values()))
assert values == [{"metric": "Task Success Rate", "series": "Hệ thống (full)", "value": 75.0}], values
print("PASS: report with no baseline renders without replacing missing measurements")

sys.path.insert(0, str(ROOT / "kaggle"))
import ui_dashboard as launch  # noqa: E402
source = launch.patched_source()
assert source.count('"ui/dashboard.py"') == 1 and '"ui/app_v2.py"' not in source
assert '"--theme.base", "light"' in source
compile(source, "dashboard_launcher", "exec")
print("PASS: cloud launcher preserves the original tunnel implementation")
