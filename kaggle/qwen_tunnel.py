"""Mở Qwen3-4B (vLLM) trên GPU Kaggle ra ngoài qua tunnel cloudflared, để UI chạy ở MÁY CÁ NHÂN dùng đúng cấu hình đo
(B2-v51-A có Qwen ghép câu), không phải tắt Qwen (UI_QWEN=off).

Chạy TRONG một notebook Kaggle tương tác (Edit, không phải job theo lô), bật Accelerator = GPU T4 và Internet = On:

    !git clone <repo> /kaggle/working/SudoCode          # hoặc giải nén repo.tar.gz của dataset sudocode-repo
    !cd /kaggle/working/SudoCode && python kaggle/qwen_tunnel.py

Script:
  1. cài vLLM vào venv riêng (scripts/setup_env.sh, SETUP_HARNESS=0) nếu chưa có;
  2. bật vLLM bằng scripts/serve_llm.sh với model / tham số của profiles/b2_v51a.json, KHÓA endpoint bằng VLLM_API_KEY
     (ngẫu nhiên mỗi lần chạy, hoặc đặt sẵn QWEN_TUNNEL_KEY);
  3. tải cloudflared, mở quick tunnel (https://<ngẫu nhiên>.trycloudflare.com, không cần tài khoản), kiểm /v1/models qua
     tunnel có khóa;
  4. in hai dòng cần đặt ở máy cá nhân (QWEN_BASE_URL, QWEN_API_KEY) rồi giữ server chạy tới khi dừng cell.

An toàn:
  - URL tunnel là CÔNG KHAI; endpoint chỉ trả lời khi có đúng khóa. Khóa chỉ hiện trong output của notebook: không để
    notebook ở chế độ Public, không chia sẻ output.
  - Khóa DeepSeek / TypeSafe KHÔNG cần ở đây (chúng nằm trong .env trên máy chạy UI).
  - Quick tunnel của Cloudflare dành cho thử nghiệm, không cam kết thời gian sống. Phiên Kaggle tắt / quá giờ thì URL chết;
    chạy lại sẽ được URL và khóa MỚI.
  - Độ trễ qua tunnel cộng thêm vào câu trả lời: số TTFT trên UI kiểu này KHÔNG so với số đo trên Kaggle.
"""
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(ROOT, "profiles", "b2_v52n.json")      # 17/11: env giống hệt b2_v51a (model / tham số Qwen không đổi)
CF_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
CF_BIN = "/tmp/cloudflared"
PORT = int(os.environ.get("QWEN_TUNNEL_PORT", "8000"))


def log(msg):
    print(f"[qwen_tunnel {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sh(cmd, env, check=True):
    log("$ " + cmd)
    r = subprocess.run(cmd, shell=True, cwd=ROOT, env=env)
    if check and r.returncode != 0:
        sys.exit(f"lệnh lỗi (mã {r.returncode}): {cmd}")
    return r.returncode


def get_models(base, key, timeout=15):
    req = urllib.request.Request(base.rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def start_vllm(key):
    """Bật Qwen của profiles/b2_v51a.json trên GPU 0, cổng PORT, khóa = key (None = không khóa, chỉ dùng nội bộ máy).
    → env đã dùng (QWEN_BASE_URL nội bộ). Dùng chung cho kaggle/ui_tunnel.py."""
    if subprocess.run("nvidia-smi -L", shell=True, capture_output=True).returncode != 0:
        sys.exit("không thấy GPU: bật Settings → Accelerator → GPU T4 cho notebook")
    prof = json.load(open(PROFILE, encoding="utf-8"))["env"]
    env = dict(os.environ)
    env.update({"RUN_PROFILE": "kaggle", "QWEN_MODEL": prof["QWEN_MODEL"], "QWEN_BASE_URL": f"http://127.0.0.1:{PORT}/v1",
                "VLLM_MAX_MODEL_LEN": prof.get("VLLM_MAX_MODEL_LEN", "8192"), "VLLM_DTYPE": "half", "VLLM_GPUS": "0", "VLLM_TP": "1",
                "VLLM_VENV": env.get("VLLM_VENV", "/tmp/vllm-venv"), "VLLM_LOG": "/kaggle/working/vllm_tunnel.log"})
    env.pop("VLLM_API_KEY", None)
    if key:
        env["VLLM_API_KEY"] = key
    log(f"model {env['QWEN_MODEL']} (theo profiles/b2_v52n.json), cổng {PORT}, khóa {'có' if key else 'không (chỉ nội bộ)'}")
    if not os.path.exists(os.path.join(env["VLLM_VENV"], "bin", "python")):
        sh("SETUP_HARNESS=0 SETUP_VLLM=1 bash scripts/setup_env.sh", env)          # vài phút ở lần đầu của phiên
    sh("bash scripts/serve_llm.sh start", env)
    local = get_models(env["QWEN_BASE_URL"], key or "local")
    if not any(m.get("id") == env["QWEN_MODEL"] for m in local.get("data") or []):
        sys.exit(f"vLLM không phục vụ đúng model: {local}")
    log("vLLM sẵn sàng")
    return env


def open_tunnel(port, name):
    """Quick tunnel cloudflared tới 127.0.0.1:port. → (tiến trình, URL https công khai)."""
    if not os.path.exists(CF_BIN):
        sh(f"curl -fsSL -o {CF_BIN} {CF_URL} && chmod +x {CF_BIN}", dict(os.environ))
    cf_log = f"/kaggle/working/cloudflared_{name}.log"
    cf = subprocess.Popen([CF_BIN, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
                          stdout=open(cf_log, "w"), stderr=subprocess.STDOUT)
    for _ in range(90):
        time.sleep(1)
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", open(cf_log, encoding="utf-8", errors="replace").read())
        if m:
            return cf, m.group(0)
        if cf.poll() is not None:
            break
    cf.kill()
    sys.exit("cloudflared không cấp được URL (Internet của notebook đã bật chưa?) — xem " + cf_log)


def main():
    key = os.environ.get("QWEN_TUNNEL_KEY") or secrets.token_urlsafe(24)
    env = start_vllm(key)
    cf, url = open_tunnel(PORT, "qwen")
    base = url + "/v1"
    err = "model không khớp"
    for i in range(30):                                     # DNS của URL mới có thể cần vài giây
        try:
            got = get_models(base, key)
            if any(m.get("id") == env["QWEN_MODEL"] for m in got.get("data") or []):
                break
            err = f"model không khớp: {got}"
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(2)
    else:
        cf.kill()
        sys.exit(f"không gọi được vLLM qua tunnel: {err}")
    log("tunnel OK: gọi /v1/models qua URL công khai có khóa → đúng model")
    if os.environ.get("QWEN_TUNNEL_SELFTEST") != "1":
        show(base, key)
    else:
        log("selftest: không in khóa / URL ra log")
    selftest_and_guard(base, key, env, cf)


def show(base, key):
    print("\n================ ĐẶT Ở MÁY CÁ NHÂN (PowerShell) ================", flush=True)
    print(f'$env:QWEN_BASE_URL = "{base}"', flush=True)
    print(f'$env:QWEN_API_KEY = "{key}"', flush=True)
    print('Remove-Item Env:UI_QWEN -ErrorAction SilentlyContinue   # bật lại Qwen compose', flush=True)
    print("---------------- hoặc Bash ----------------", flush=True)
    print(f'export QWEN_BASE_URL="{base}" QWEN_API_KEY="{key}"; unset UI_QWEN', flush=True)
    print("==================================================================", flush=True)
    print("Giữ cell này chạy trong lúc dùng UI. Dừng cell (■) để tắt tunnel và vLLM.\n", flush=True)


def selftest_and_guard(base, key, env, cf):
    """Kiểm endpoint đã khóa; SELFTEST thì gọi thử một câu rồi dừng; còn lại giữ tunnel + vLLM chạy tới khi dừng cell."""
    # gọi KHÔNG có khóa qua URL công khai phải bị từ chối (401) — endpoint không mở cho người lạ
    try:
        urllib.request.urlopen(urllib.request.Request(base + "/models"), timeout=15)
        open_ok = True
    except urllib.error.HTTPError as e:
        open_ok = e.code not in (401, 403)
    except Exception:  # noqa: BLE001
        open_ok = False
    log("gọi không khóa qua tunnel: " + ("BỊ TỪ CHỐI (đúng)" if not open_ok else "VẪN TRẢ LỜI — ENDPOINT KHÔNG ĐƯỢC KHÓA"))
    if open_ok:
        cf.kill()
        subprocess.run("bash scripts/serve_llm.sh stop", shell=True, cwd=ROOT, env=env)
        sys.exit("endpoint không yêu cầu khóa — dừng để không mở GPU ra ngoài")

    if os.environ.get("QWEN_TUNNEL_SELFTEST") == "1":       # job theo lô: kiểm xong rồi dừng (không in khóa ra log job)
        t0 = time.time()
        got = json.loads(urllib.request.urlopen(urllib.request.Request(
            base + "/chat/completions", data=json.dumps({"model": env["QWEN_MODEL"], "max_tokens": 16, "temperature": 0,
                                                         "messages": [{"role": "user", "content": "Chào em"}]}).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}), timeout=60).read().decode())
        log(f"selftest: chat qua tunnel OK sau {int((time.time() - t0) * 1000)} ms, {len(got.get('choices') or [])} choice")
        cf.terminate()
        subprocess.run("bash scripts/serve_llm.sh stop", shell=True, cwd=ROOT, env=env)
        log("SELFTEST PASS")
        return

    def stop(*_):
        log("dừng tunnel và vLLM")
        cf.terminate()
        subprocess.run("bash scripts/serve_llm.sh stop", shell=True, cwd=ROOT, env=env)
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    try:
        while True:
            time.sleep(300)
            alive_cf = cf.poll() is None
            try:
                ok = bool(get_models(env["QWEN_BASE_URL"], key, timeout=10).get("data"))
            except Exception:  # noqa: BLE001
                ok = False
            log(f"còn chạy: vLLM {'ok' if ok else 'LỖI'} · tunnel {'ok' if alive_cf else 'ĐÃ TẮT'}")
            if not alive_cf:
                sys.exit("cloudflared đã thoát — chạy lại cell để có URL mới")
    except KeyboardInterrupt:
        stop()


if __name__ == "__main__":
    main()
