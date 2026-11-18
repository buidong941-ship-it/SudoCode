"""Chạy UI v2 (ui/app_v2.py) trên Kaggle — y hệt kaggle/ui_tunnel.py (Qwen nội bộ, tunnel có mật khẩu, dữ liệu UI ở /kaggle/working),
chỉ đổi tệp Streamlit được mở. Không sửa kaggle/ui_tunnel.py (tệp trong freeze v52n-ui2): đọc nguồn, thay đúng MỘT chỗ
"ui/app.py" → "ui/app_v2.py", rồi chạy như __main__ với __file__ của tệp gốc.

    !cd /kaggle/working/SudoCode && python kaggle/ui_tunnel_v2.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "ui_tunnel.py")


def patched_source():
    src = open(SRC, encoding="utf-8").read()
    if src.count('"ui/app.py"') != 1:
        raise SystemExit("ui_tunnel_v2: không tìm thấy đúng một chỗ \"ui/app.py\" trong kaggle/ui_tunnel.py — dừng, không đoán")
    return src.replace('"ui/app.py"', '"ui/app_v2.py"', 1)


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    exec(compile(patched_source(), SRC, "exec"), {"__name__": "__main__", "__file__": SRC})
