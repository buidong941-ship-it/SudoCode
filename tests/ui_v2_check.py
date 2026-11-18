"""Kiểm UI v2 (ui/app_v2.py, 17/11) bằng Streamlit AppTest — offline (profile legacy_offline), không mạng, không model.

- cổng mật khẩu giữ nguyên (chưa nhập: không tab; đúng: 5 tab);
- Cuộc gọi: chat + Call Brief cạnh nhau; mỗi câu chỉ có 👍 / "Cần cải thiện"; bấm "Cần cải thiện" mới mở ô ghi chú; Gửi → feedback -1
  có ghi chú; gọi lần hai cùng SĐT → Call Brief khách gọi lại;
- Demo C.6 chạy được, có Call Brief và cuộc 2;
- Bộ nhớ: timeline + bảng fact kỹ thuật gập;
- Cải tiến: 3 bước mở được; "Gom gap" biến đánh giá "Cần cải thiện" thành gap staff_feedback;
- không đổi tệp nào của freeze v52n-ui2 (ui/app.py, kaggle/ui_tunnel.py giữ hash); launcher v2 chỉ thay đúng một chỗ.

Chạy: python tests/ui_v2_check.py   (Kaggle CPU; cần streamlit)"""
import hashlib
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tmp = tempfile.mkdtemp(prefix="uiv2_")
os.environ["UI_PROFILE"] = "legacy_offline"
os.environ["UI_DATA_DIR"] = os.path.join(tmp, "ui")
os.environ["C5_STATE_DIR"] = os.path.join(tmp, "c5_state")
os.environ["C5_ROOT"] = os.path.join(tmp, "c5_review")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "ui.db").replace("\\", "/")
os.environ["LLM_CACHE"] = "off"

FAILS = []


def ok(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


from streamlit.testing.v1 import AppTest  # noqa: E402

APP = os.path.join(ROOT, "ui", "app_v2.py")
T = 300


def btn(at, label):
    b = [x for x in at.button if x.label == label]
    return b[0] if b else None


def tin(at, label):
    t = [x for x in at.text_input if x.label == label]
    return t[0] if t else None


# ---------- 0. freeze v52n-ui2 không bị đổi ----------
fl = os.path.join(ROOT, "runs", "freeze", "20261117-v52n-ui2", "code_sha256.txt")
if os.path.exists(fl):
    want = {ln.split(None, 1)[1].strip(): ln.split(None, 1)[0] for ln in open(fl, encoding="utf-8") if ln.strip()}
    for f in ("ui/app.py", "ui/engine.py", "kaggle/ui_tunnel.py"):
        ok(hashlib.sha256(open(os.path.join(ROOT, f), "rb").read()).hexdigest() == want.get(f), f"{f} giữ đúng hash freeze v52n-ui2")
    ok("ui/app_v2.py" not in want and "kaggle/ui_tunnel_v2.py" not in want, "app_v2 / launcher v2 không thuộc freeze (không chạm cổng R1)")
else:
    print("BỎ QUA kiểm freeze: không có runs/freeze/20261117-v52n-ui2/code_sha256.txt trong gói")
sys.path.insert(0, os.path.join(ROOT, "kaggle"))
import ui_tunnel_v2 as UT  # noqa: E402
src = UT.patched_source()
ok(src.count('"ui/app_v2.py"') == 1 and '"ui/app.py"' not in src, "launcher v2 thay đúng một chỗ ui/app.py → ui/app_v2.py")
compile(src, "ui_tunnel.py", "exec")

# ---------- 1. mật khẩu ----------
os.environ["UI_PASSWORD"] = "mat-khau-thu-123"
at = AppTest.from_file(APP, default_timeout=T).run()
ok(not at.exception and len(at.tabs) == 0, "chưa nhập mật khẩu: không có tab")
at.text_input[0].input("mat-khau-thu-123").run()
ok(not at.exception and len(at.tabs) == 5, f"đúng mật khẩu: 5 tab (có {len(at.tabs)})")
os.environ.pop("UI_PASSWORD")

# ---------- 2. cuộc gọi: chat + brief, feedback gọn ----------
at = AppTest.from_file(APP, default_timeout=T).run()
ok(not at.exception, f"mở app_v2 không lỗi: {[e.value for e in at.exception]}")
ok(any(e.label == "Thông tin hệ thống" for e in at.expander), "namespace / DB / hash nằm trong 'Thông tin hệ thống'")
tin(at, "Tên nhân viên").input("NV1").run()
btn(at, "Bắt đầu cuộc gọi mới").click().run()
ok(not at.exception and len(at.chat_input) == 1, f"bắt đầu cuộc gọi: có ô chat ({[e.value for e in at.exception]})")
ok(any("Khách mới" in i.value for i in at.info), "khách mới: brief báo chưa có lịch sử")
at.chat_input[0].set_value("Máy lọc không khí AirPure Y giá bao nhiêu em?").run()
ok(not at.exception and len(at.chat_message) >= 2, f"một lượt chat: {len(at.chat_message)} tin ({[e.value for e in at.exception]})")
ok(btn(at, "👍") is not None and btn(at, "Cần cải thiện") is not None, "mỗi câu có 👍 / Cần cải thiện")
ok(tin(at, "Chưa ổn ở đâu? (tuỳ chọn)") is None, "ô ghi chú ẨN cho tới khi bấm Cần cải thiện")
ok(any(e.label == "Chi tiết lượt" for e in at.expander), "latency / audit / tool nằm trong 'Chi tiết lượt'")
btn(at, "Cần cải thiện").click().run()
note = tin(at, "Chưa ổn ở đâu? (tuỳ chọn)")
ok(note is not None, "bấm Cần cải thiện → mở ô ghi chú")
if note:
    note.input("chưa nói khuyến mãi").run()
    btn(at, "Gửi").click().run()
fb_path = os.path.join(os.environ["UI_DATA_DIR"], "feedback.jsonl")
fbs = [json.loads(l) for l in open(fb_path, encoding="utf-8")] if os.path.exists(fb_path) else []
ok(len(fbs) == 1 and fbs[0]["rating"] == -1 and fbs[0]["note"] == "chưa nói khuyến mãi" and fbs[0]["by"] == "NV1",
   f"Gửi → feedback -1 có ghi chú, đúng người: {fbs}")
ok(btn(at, "Cần cải thiện") is None, "đã đánh giá → không hiện lại nút")
btn(at, "Kết thúc cuộc gọi").click().run()
btn(at, "Bắt đầu cuộc gọi mới").click().run()
ok(not at.exception and any("Call Brief" in s.value for s in at.subheader), "gọi lần hai cùng SĐT → Call Brief khách gọi lại")
btn(at, "Kết thúc cuộc gọi").click().run()

# ---------- 3. bộ nhớ ----------
ok(any(e.label.startswith("Bảng fact kỹ thuật") for e in at.expander), "bộ nhớ: bảng fact kỹ thuật gập")
ok(any("📞" in m.value for m in at.markdown), "bộ nhớ: timeline có phiên")

# ---------- 4. cải tiến: 3 bước, gom gap từ đánh giá ----------
steps = at.radio(key="c5_step")
for s in steps.options:
    at.radio(key="c5_step").set_value(s).run()
    ok(not at.exception, f"bước '{s}' mở không lỗi: {[e.value for e in at.exception]}")
at.radio(key="c5_step").set_value("1 · Tiếp nhận").run()
btn(at, "Gom gap").click().run()
gp = os.path.join(os.environ["C5_ROOT"], "gaps.jsonl")
gaps = [json.loads(l) for l in open(gp, encoding="utf-8")] if os.path.exists(gp) else []
ok(any(g.get("feedback_source") == "staff_feedback" and g.get("type") == "staff_dislike" for g in gaps),
   f"Gom gap: đánh giá 'Cần cải thiện' thành gap staff_feedback ({len(gaps)} gap; {[e.value for e in at.error]})")

# ---------- 5. demo C.6 ----------
at2 = AppTest.from_file(APP, default_timeout=T).run()
tin(at2, "Tên nhân viên").input("NV1").run()
b = btn(at2, "Chạy demo từ đầu")
ok(b is not None, "có nút chạy demo")
if b:
    at2 = b.click().run()
    ok(not at2.exception, f"demo không lỗi: {[e.value for e in at2.exception]}")
    ok(any("Call Brief" in s.value for s in at2.subheader), "demo hiện Call Brief")
    ok("call_2" in " ".join(m.value for m in at2.markdown), "demo hiện cuộc 2")

print("TẤT CẢ OK" if not FAILS else f"{len(FAILS)} LỖI: {FAILS}")
sys.exit(1 if FAILS else 0)
