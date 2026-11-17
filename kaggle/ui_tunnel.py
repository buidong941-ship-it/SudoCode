"""Phương án B: chạy CẢ UI lẫn Qwen trên Kaggle, mở UI qua tunnel cloudflared CÓ MẬT KHẨU (demo / quay video / người khác mở link).

Chạy TRONG notebook Kaggle tương tác (GPU T4, Internet On). Gắn Secrets (Add-ons → Secrets):
    DEEPSEEK_API_KEY, TYPESAFE_API_KEY   — agent B2 gọi API thật (khóa ở lại trên Kaggle, không hiện ra màn hình UI)
    UI_PASSWORD                          — BẮT BUỘC: không có → script từ chối mở UI ra ngoài

    !cd /kaggle/working/SudoCode && python kaggle/ui_tunnel.py

Script:
  1. nạp Secrets vào môi trường của tiến trình (không in giá trị);
  2. cài requirements-ui (streamlit) cho python của notebook, bật Qwen (vLLM) CHỈ nội bộ máy (127.0.0.1, không tunnel);
  3. chạy Streamlit `ui/app.py` profile b2_v52n (cấu hình chính 17/11; đặt UI_PROFILE=b2_v51a để đối chiếu; Qwen ghép câu), dữ liệu UI ghi vào /kaggle/working/ui_data;
  4. mở quick tunnel tới UI, kiểm /_stcore/health qua URL công khai, in URL (KHÔNG in mật khẩu); giữ chạy tới khi dừng cell.

Dữ liệu UI (bộ nhớ, feedback, trace, kho duyệt FAQ) MẤT khi phiên Kaggle tắt: bấm "Chuẩn bị gói dữ liệu UI để tải về" ở thanh
bên rồi tải ui_data.zip về máy trước khi tắt. Muốn giữ dữ liệu lâu dài / làm vòng C.5 thì dùng phương án A (kaggle/qwen_tunnel.py).
UI_TUNNEL_SELFTEST=1: mật khẩu ngẫu nhiên, không cần khóa API; kiểm UI mở được qua tunnel rồi dừng (job GPU theo lô).
"""
import os
import secrets
import signal
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import qwen_tunnel as QT  # noqa: E402

ROOT = QT.ROOT
UI_PORT = int(os.environ.get("UI_TUNNEL_PORT", "8501"))
DATA = "/kaggle/working/ui_data"
SELFTEST = os.environ.get("UI_TUNNEL_SELFTEST") == "1"


def kaggle_secret(name):
    if os.environ.get(name):
        return os.environ[name]
    try:
        from kaggle_secrets import UserSecretsClient
        return UserSecretsClient().get_secret(name)
    except Exception:  # noqa: BLE001
        return None


def health(url, timeout=10):
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/_stcore/health", timeout=timeout) as r:
            return r.status == 200 and r.read().decode().strip() == "ok"
    except Exception:  # noqa: BLE001
        return False


def main():
    pw = secrets.token_urlsafe(18) if SELFTEST else kaggle_secret("UI_PASSWORD")
    if not pw or len(pw) < 8:
        sys.exit("thiếu UI_PASSWORD (≥ 8 ký tự) trong Kaggle Secrets — không mở UI ra ngoài khi không có mật khẩu")
    keys = {k: kaggle_secret(k) for k in ("DEEPSEEK_API_KEY", "TYPESAFE_API_KEY")}
    QT.log("khóa API: " + ", ".join(f"{k} {'có' if v else 'THIẾU'}" for k, v in keys.items()))
    if not SELFTEST and not all(keys.values()):
        sys.exit("thiếu khóa API trong Kaggle Secrets — agent B2 cần cả DEEPSEEK_API_KEY và TYPESAFE_API_KEY")

    QT.sh("python -m pip install -q -r requirements-ui.txt", dict(os.environ))
    env = QT.start_vllm(None)                                 # Qwen chỉ nội bộ máy: không mở ra ngoài, không cần khóa
    ui_env = dict(env)
    ui_env.pop("VLLM_API_KEY", None)
    ui_env.update({k: v for k, v in keys.items() if v})
    os.makedirs(DATA, exist_ok=True)
    ui_env.update({"UI_PROFILE": os.environ.get("UI_PROFILE", "b2_v52n"), "UI_PASSWORD": pw, "UI_DATA_DIR": DATA, "C5_STATE_DIR": os.path.join(DATA, "c5_state"),
                   "C5_ROOT": os.path.join(DATA, "c5_review"), "DATABASE_URL": f"sqlite:///{DATA}/memory.db",
                   "RUN_PROFILE": "kaggle", "RAG_MODE": "bm25", "TOOL_TRANSPORT": "direct", "PYTHONIOENCODING": "utf-8"})
    ui_env.pop("UI_QWEN", None)                               # Qwen có trên máy → đúng cấu hình đo
    ui_log = "/kaggle/working/streamlit.log"
    st = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "ui/app.py", "--server.port", str(UI_PORT),
                           "--server.address", "127.0.0.1", "--server.headless", "true", "--browser.gatherUsageStats", "false"],
                          cwd=ROOT, env=ui_env, stdout=open(ui_log, "w"), stderr=subprocess.STDOUT)
    local = f"http://127.0.0.1:{UI_PORT}"
    for _ in range(120):
        if health(local):
            break
        if st.poll() is not None:
            sys.exit("Streamlit đã thoát — xem " + ui_log)
        time.sleep(1)
    else:
        sys.exit("Streamlit chưa sẵn sàng sau 120 s — xem " + ui_log)
    QT.log("UI sẵn sàng nội bộ")
    cf, url = QT.open_tunnel(UI_PORT, "ui")
    for _ in range(30):
        if health(url):
            break
        time.sleep(2)
    else:
        cf.kill(); st.terminate()
        sys.exit("không mở được UI qua tunnel")
    QT.log("UI mở được qua URL công khai (trang yêu cầu mật khẩu UI_PASSWORD)")

    def stop(*_):
        QT.log("dừng tunnel, UI, vLLM")
        cf.terminate(); st.terminate()
        subprocess.run("bash scripts/serve_llm.sh stop", shell=True, cwd=ROOT, env=env)

    if SELFTEST:
        stop()
        QT.log("SELFTEST PASS (không in URL / mật khẩu)")
        return
    print("\n================ MỞ UI ================", flush=True)
    print(f"Link: {url}", flush=True)
    print("Mật khẩu: giá trị UI_PASSWORD trong Kaggle Secrets (script không in ra).", flush=True)
    print("Trước khi tắt phiên: thanh bên → 'Chuẩn bị gói dữ liệu UI để tải về' → tải ui_data.zip.", flush=True)
    print("Giữ cell chạy trong lúc dùng UI. Dừng cell (■) để tắt.\n", flush=True)
    signal.signal(signal.SIGTERM, lambda *_: (stop(), sys.exit(0)))
    try:
        while True:
            time.sleep(300)
            QT.log(f"còn chạy: UI {'ok' if health(local) else 'LỖI'} · tunnel {'ok' if cf.poll() is None else 'ĐÃ TẮT'}")
            if cf.poll() is not None or st.poll() is not None:
                stop()
                sys.exit("tunnel hoặc UI đã thoát — chạy lại cell để có URL mới")
    except KeyboardInterrupt:
        stop()


if __name__ == "__main__":
    main()
