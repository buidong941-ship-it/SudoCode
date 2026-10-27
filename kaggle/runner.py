#!/usr/bin/env python3
"""Chạy trên Kaggle (script kernel do scripts/kaggle_job.py đẩy lên). Không chứa logic đánh giá: chỉ dựng môi trường rồi gọi
đúng lệnh `scripts/run_suite.py` như trên server thuê — profile `kaggle` lo phần khác biệt (GPU nào cho model nào, đường dẫn).

1. Tìm repo trong /kaggle/input (dataset riêng tư `<user>/sudocode-repo`, file repo.tar.gz hoặc đã giải nén) → /tmp/repo.
2. Nạp khóa từ Kaggle Secrets nếu notebook đã gắn (DEEPSEEK_API_KEY, TYPESAFE_API_KEY, HF_TOKEN). Không in giá trị.
3. Kiểm GPU: backend dùng Qwen mà máy không phải T4 (vd P100, compute 6.0) → dừng, vì vLLM không chạy được.
4. scripts/setup_env.sh (harness + venv vLLM) → scripts/run_suite.py với JOB["suite_args"].
Kết quả trong /kaggle/working/out (output của notebook; tải về bằng `python scripts/kaggle_job.py pull`).
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time

JOB = {}   # ĐIỀN BỞI scripts/kaggle_job.py: {"job", "suite_args": [...], "needs_qwen": bool, "env": {...}}

WORK, OUT, REPO = "/kaggle/working", "/kaggle/working/out", "/tmp/repo"


def log(msg):
    print(f"[runner {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def find_repo():
    for p in glob.glob("/kaggle/input/**/run_eval.py", recursive=True):
        return os.path.dirname(p), None
    for p in glob.glob("/kaggle/input/**/repo.tar.gz", recursive=True) + glob.glob("/kaggle/input/**/repo.tgz", recursive=True):
        return None, p
    raise SystemExit("không tìm thấy repo trong /kaggle/input — dataset sudocode-repo đã gắn vào notebook chưa?")


def load_secrets():
    try:
        from kaggle_secrets import UserSecretsClient
        c = UserSecretsClient()
    except Exception:
        log("không có kaggle_secrets — bỏ qua"); return []
    got = []
    for name in ("DEEPSEEK_API_KEY", "TYPESAFE_API_KEY", "HF_TOKEN"):
        try:
            v = c.get_secret(name)
            if v:
                os.environ[name] = v; got.append(name)
        except Exception:
            pass
    log(f"secrets đã nạp: {got or 'không có'}")
    return got


def gpus():
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True)
        return [x.strip() for x in r.stdout.splitlines() if x.strip()]
    except FileNotFoundError:
        return []


T0 = time.time()
DEADLINE = T0 + int(JOB.get("max_seconds", 3 * 3600))


def run(cmd, env, limit=None):
    import signal
    budget = int(min(limit or 1e9, DEADLINE - time.time()))
    if budget <= 0:
        log("đã hết thời gian của job — bỏ qua bước này"); return 124
    log("$ " + " ".join(cmd) + f"   (tối đa {budget}s)")
    p = subprocess.Popen(cmd, cwd=REPO, env=env, start_new_session=True)
    try:
        return p.wait(timeout=budget)
    except subprocess.TimeoutExpired:
        log(f"TIMEOUT sau {budget}s → dừng cả nhóm tiến trình")
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except Exception:
            p.kill()
        return 124


def main():
    global DEADLINE
    os.makedirs(OUT, exist_ok=True)
    json.dump(JOB, open(os.path.join(OUT, "job.json"), "w"), ensure_ascii=False, indent=2)
    src, tar = find_repo()
    shutil.rmtree(REPO, ignore_errors=True)
    if src:
        shutil.copytree(src, REPO)
    else:
        os.makedirs(REPO); tarfile.open(tar).extractall(REPO)
    log(f"repo → {REPO} (từ {src or tar})")
    ov = os.path.join(REPO, "kaggle", "jobs", f"{JOB.get('job')}.json")
    if os.path.exists(ov):
        JOB.update(json.load(open(ov, encoding="utf-8")))
        DEADLINE = T0 + int(JOB.get("max_seconds", 3 * 3600))
        log(f"cấu hình job lấy từ dataset: {ov}")
        json.dump(JOB, open(os.path.join(OUT, "job.json"), "w"), ensure_ascii=False, indent=2)
    secrets = load_secrets()
    g = gpus(); log(f"GPU: {g or 'không có'}")
    json.dump({"gpus": g, "secrets": secrets, "python": sys.version}, open(os.path.join(OUT, "machine.json"), "w"), indent=2)
    if JOB.get("needs_qwen") and (not g or any("P100" in x for x in g)):
        raise SystemExit(f"job cần vLLM (Qwen) nhưng GPU là {g} — vLLM cần compute ≥ 7.0 (T4). Đẩy lại với --accelerator T4.")
    if JOB.get("needs_secrets") and not set(JOB["needs_secrets"]) <= set(secrets):
        raise SystemExit(f"job cần secrets {JOB['needs_secrets']} nhưng notebook chỉ gắn {secrets} — vào Add-ons → Secrets của "
                         "notebook này trên kaggle.com, bật các secret đó, rồi chạy lại (Save Version) hoặc đẩy lại job.")
    env = {**os.environ, "RUN_PROFILE": "kaggle", "PYTHONIOENCODING": "utf-8", **JOB.get("env", {})}
    rc = 0
    if JOB.get("setup", True):
        rc = run(["bash", "scripts/setup_env.sh"], {**env, "SETUP_VLLM": "1" if JOB.get("needs_qwen") else "0"}, limit=45 * 60)
    for cmd in (JOB.get("pre") or []) if rc == 0 else []:
        cmd = [c.replace("{out}", os.path.join(OUT, JOB.get("job", "job"))).replace("{python}", sys.executable) for c in cmd]
        log(f"=== bước trước: {' '.join(cmd)}")
        rc = run(cmd, env, limit=60 * 60)
        if rc:
            log(f"bước trước thất bại mã {rc}; dừng các bước sau")
            break
    if rc == 0 and not JOB.get("pre_only"):
        variants = JOB.get("variants") or [{"tag": None, "env": {}}]
        for v in variants:
            out = os.path.join(OUT, JOB.get("job", "job"), *([v["tag"]] if v["tag"] else []))
            args = list(JOB.get("suite_args", []))
            if v["tag"] and "--tag" in args:
                args[args.index("--tag") + 1] = v["tag"]
            if v["env"].get("WORKERS") and "--workers" in args:
                args[args.index("--workers") + 1] = v["env"]["WORKERS"]
            log(f"=== biến thể {v['tag'] or '(mặc định)'}: {v['env']}")
            rc_v = run([sys.executable, "scripts/run_suite.py", "--out", out, *args], {**env, **v["env"]})
            rc = rc or rc_v
    subprocess.run(["bash", "scripts/serve_llm.sh", "stop"], cwd=REPO, env=env)
    log(f"xong sau {time.time() - T0:.0f}s, mã thoát {rc}")
    sys.exit(rc)


if __name__ == "__main__":
    main()
