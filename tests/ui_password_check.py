"""Kiểm cổng mật khẩu và xuất dữ liệu của UI (16/11, phương án B: UI mở ra ngoài qua tunnel). Không mạng, không model.
- UI_PASSWORD đặt → chưa nhập / nhập sai: không hiện tab nào; nhập đúng: hiện đủ 5 tab.
- UI_PASSWORD không đặt (máy cá nhân) → vào thẳng.
- export_ui_data: zip có dữ liệu UI + EXPORT.json, không chứa khóa API.
Chạy: python tests/ui_password_check.py   (Kaggle CPU; cần streamlit)"""
import io
import json
import os
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tmp = tempfile.mkdtemp(prefix="uipw_")
os.environ["UI_PROFILE"] = "legacy_offline"
os.environ["UI_DATA_DIR"] = os.path.join(tmp, "ui")
os.environ["C5_STATE_DIR"] = os.path.join(tmp, "c5_state")
os.environ["C5_ROOT"] = os.path.join(tmp, "c5_review")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "ui.db").replace("\\", "/")

FAILS = []


def ok(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


from streamlit.testing.v1 import AppTest  # noqa: E402

APP = os.path.join(ROOT, "ui", "app.py")
PW = "mat-khau-thu-123"

os.environ["UI_PASSWORD"] = PW
at = AppTest.from_file(APP, default_timeout=120).run()
ok(not at.exception, f"mở app có mật khẩu không lỗi: {[e.value for e in at.exception]}")
ok(len(at.tabs) == 0 and any(t.label == "Mật khẩu" for t in at.text_input), "chưa nhập mật khẩu: không có tab nào, chỉ có ô mật khẩu")
at.text_input[0].input("sai-mat-khau").run()
ok(len(at.tabs) == 0 and any("Sai mật khẩu" in e.value for e in at.error), "sai mật khẩu: vẫn chặn")
at.text_input[0].input(PW).run()
ok(not at.exception and len(at.tabs) == 5, f"đúng mật khẩu: hiện 5 tab (có {len(at.tabs)})")

os.environ.pop("UI_PASSWORD")
at2 = AppTest.from_file(APP, default_timeout=120).run()
ok(not at2.exception and len(at2.tabs) == 5, "không đặt UI_PASSWORD (máy cá nhân): vào thẳng")

from ui import engine as E  # noqa: E402
os.makedirs(E.UI_DIR, exist_ok=True)
with open(os.path.join(E.UI_DIR, "feedback.jsonl"), "w", encoding="utf-8") as fh:
    fh.write(json.dumps({"msg_id": "s:1", "rating": 1}) + "\n")
z = zipfile.ZipFile(io.BytesIO(E.export_ui_data()))
names = z.namelist()
ok("EXPORT.json" in names and "ui/feedback.jsonl" in names, f"zip có dữ liệu UI + EXPORT.json: {names[:6]}")
blob = b"".join(z.read(n) for n in names)
ok(not any(k.encode() in blob for k in ("DEEPSEEK_API_KEY=", "TYPESAFE_API_KEY=", PW)), "zip không chứa khóa API / mật khẩu")

print("TẤT CẢ OK" if not FAILS else f"{len(FAILS)} LỖI: {FAILS}")
sys.exit(1 if FAILS else 0)
