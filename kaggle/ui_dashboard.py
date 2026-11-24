"""Mở dashboard mới bằng luồng tunnel, mật khẩu và backend hiện có.

    python kaggle/ui_dashboard.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ui_tunnel_v2 import patched_source as source_v2  # noqa: E402


def patched_source():
    source = source_v2()
    if source.count('"ui/app_v2.py"') != 1:
        raise SystemExit("Không tìm thấy duy nhất một entrypoint UI v2; dừng để tránh mở sai giao diện.")
    return source.replace('"ui/app_v2.py"', '"ui/dashboard.py"', 1).replace(
        '"--server.port"', '"--theme.base", "light", "--server.port"', 1)


if __name__ == "__main__":
    original = os.path.join(HERE, "ui_tunnel.py")
    exec(compile(patched_source(), original, "exec"), {"__name__": "__main__", "__file__": original})
