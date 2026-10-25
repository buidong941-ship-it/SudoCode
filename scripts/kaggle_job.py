#!/usr/bin/env python3
"""Đẩy một lần chạy đánh giá lên Kaggle và kéo kết quả về — chạy ở máy cá nhân (cần `pip install kaggle`).

    python scripts/kaggle_job.py --cred "C:\\Users\\admin\\.kaggle\\MidZid\\kaggle (4).json" quota
    python scripts/kaggle_job.py --cred ... push  --job qwen-dev --sets dev --router qwen --generator qwen --extractor hybrid
    python scripts/kaggle_job.py --cred ... status --job qwen-dev
    python scripts/kaggle_job.py --cred ... wait   --job qwen-dev          # chờ xong rồi tự pull
    python scripts/kaggle_job.py --cred ... pull   --job qwen-dev          # → runs/kaggle/qwen-dev/

`push`:
1. Đóng gói repo (bỏ .git, venv, data, runs, dataset, .env, kaggle.json…) thành repo.tar.gz → dataset RIÊNG TƯ
   `<user>/sudocode-repo` (tạo lần đầu, các lần sau thêm version) và chờ Kaggle xử lý xong.
2. Sinh kernel `<user>/sudocode-<job>` từ kaggle/runner.py (điền JOB = tham số run_suite) — GPU T4, Internet bật, riêng tư.
3. `kaggle kernels push`. Kernel đẩy qua API KHÔNG tự gắn Secrets: job dùng Jev/DeepSeek thì lần đầu phải gắn tay
   (docs/CHAY-KAGGLE-SERVER.md); job chỉ dùng Qwen + rules thì không cần khóa nào.
Khóa Kaggle đọc từ file --cred (hoặc KAGGLE_USERNAME/KAGGLE_KEY) và chỉ truyền qua biến môi trường cho tiến trình con, không in ra.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build", "kaggle")
EXCLUDE_DIRS = {".git", "venv", ".venv", ".vllm-venv", "data", "runs", "dataset", "_upload", "_download", "build", "__pycache__",
                ".pytest_cache", ".mypy_cache", ".idea", ".vscode", "asr/audio"}
EXCLUDE_FILES = {".env", "kaggle.json", "credentials.json"}
DATASET_SLUG = "sudocode-repo"
ACCEL = {"T4": "NvidiaTeslaT4", "P100": "NvidiaTeslaP100", "none": None}


def kaggle_bin():
    exe = shutil.which("kaggle") or os.path.join(os.path.dirname(sys.executable), "kaggle")
    return exe


class K:
    def __init__(self, cred):
        if cred:
            d = json.load(open(cred, encoding="utf-8"))
            self.user, key = d["username"], d["key"]
        else:
            self.user, key = os.environ.get("KAGGLE_USERNAME"), os.environ.get("KAGGLE_KEY")
        if not self.user or not key:
            sys.exit("thiếu thông tin đăng nhập: --cred <kaggle.json> hoặc KAGGLE_USERNAME/KAGGLE_KEY")
        self.env = {**os.environ, "KAGGLE_USERNAME": self.user, "KAGGLE_KEY": key, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}

    def run(self, *args, check=True, quiet=False):
        r = subprocess.run([kaggle_bin(), *args], env=self.env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = (r.stdout + r.stderr).strip()
        if not quiet:
            print(f"$ kaggle {' '.join(args)}\n{out}")
        if check and r.returncode:
            sys.exit(f"kaggle {args[0]} {args[1] if len(args) > 1 else ''} lỗi (mã {r.returncode})")
        return r.returncode, out


def pack(dst, extra=None):
    os.makedirs(os.path.dirname(dst), exist_ok=True)

    def keep(ti):
        rel = ti.name[len("repo/"):] if ti.name.startswith("repo/") else ""
        parts = rel.split("/") if rel else []
        prefixes = {"/".join(parts[:i + 1]) for i in range(len(parts))}
        if prefixes & EXCLUDE_DIRS or set(parts) & EXCLUDE_DIRS:
            return None
        if parts and (parts[-1] in EXCLUDE_FILES or parts[-1].endswith((".pyc", ".db", ".sqlite"))):
            return None
        return ti
    import io
    try:
        commit = subprocess.check_output(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], text=True).strip()
        dirty = bool(subprocess.check_output(["git", "-C", ROOT, "status", "--porcelain"], text=True).strip())
    except Exception:
        commit, dirty = None, None
    info = json.dumps({"commit": commit, "uncommitted_changes": dirty, "packed_at": time.strftime("%Y-%m-%d %H:%M:%S")}).encode()
    with tarfile.open(dst, "w:gz") as t:
        t.add(ROOT, arcname="repo", filter=keep)
        ti = tarfile.TarInfo("repo/BUILD_INFO.json"); ti.size = len(info); ti.mtime = int(time.time())
        t.addfile(ti, io.BytesIO(info))
        for rel, data in (extra or {}).items():
            ti = tarfile.TarInfo("repo/" + rel); ti.size = len(data); ti.mtime = int(time.time())
            t.addfile(ti, io.BytesIO(data))
    with tarfile.open(dst) as t:
        names = t.getnames()
    leaked = [n for n in names if os.path.basename(n) in EXCLUDE_FILES]
    if leaked:
        sys.exit(f"gói có file bí mật: {leaked}")
    print(f"đóng gói {len(names)} mục → {dst} ({os.path.getsize(dst) / 1e6:.1f} MB)")


def push_dataset(k, msg, extra=None):
    ddir = os.path.join(BUILD, "dataset")
    shutil.rmtree(ddir, ignore_errors=True); os.makedirs(ddir)
    pack(os.path.join(ddir, "repo.tar.gz"), extra)
    ds = f"{k.user}/{DATASET_SLUG}"
    json.dump({"title": DATASET_SLUG, "id": ds, "licenses": [{"name": "other"}]}, open(os.path.join(ddir, "dataset-metadata.json"), "w"))
    rc, _ = k.run("datasets", "status", ds, check=False, quiet=True)
    if rc == 0:
        k.run("datasets", "version", "-p", ddir, "-m", msg)
    else:
        k.run("datasets", "create", "-p", ddir)
    for _ in range(60):
        _, out = k.run("datasets", "status", ds, check=False, quiet=True)
        if "ready" in out.lower():
            print(f"dataset {ds}: ready"); return ds
        time.sleep(10)
    sys.exit(f"dataset {ds} chưa sẵn sàng sau 10 phút")


def slug(job):
    s = re.sub(r"[^a-z0-9-]+", "-", job.lower()).strip("-")
    return f"sudocode-{s}"


def push(k, a):
    suite = ["--sets", *a.sets, "--configs", *a.configs, "--router", a.router, "--generator", a.generator,
             "--extractor", a.extractor, "--workers", str(a.workers), "--tag", a.job]
    if a.only:
        suite += ["--only", *a.only]
    if a.smoke:
        suite.append("--smoke")
    needs_qwen = "qwen" in (a.router, a.generator) or a.extractor != "rules"
    needs = []
    if a.router == "jev":
        needs.append("TYPESAFE_API_KEY")
    if a.generator == "deepseek" or a.router == "llm":
        needs.append("DEEPSEEK_API_KEY")
    job = {"job": a.job, "suite_args": suite, "needs_qwen": needs_qwen, "needs_secrets": needs,
           "max_seconds": int(a.max_hours * 3600), "env": dict(x.split("=", 1) for x in a.env)}
    if a.pre:
        import shlex
        job["pre"] = [shlex.split(x) for x in a.pre]
        job["pre_only"] = a.pre_only
    if a.variant:
        job["variants"] = [{"tag": f"{a.job}-{v.split(':', 1)[0]}",
                            "env": dict(x.split("=", 1) for x in v.split(":", 1)[1].split(";") if x)} for v in a.variant]
    extra = {f"kaggle/jobs/{a.job}.json": json.dumps(job, ensure_ascii=False, indent=2).encode()}
    if a.dataset and not a.dataset_only:
        ds = a.dataset
    else:
        ds = push_dataset(k, f"{a.job} {time.strftime('%Y-%m-%d %H:%M')}", extra)
    if a.dataset_only:
        print(f"đã đẩy cấu hình job {a.job} vào dataset {ds}. Chạy lại kernel {k.user}/{slug(a.job)} trên giao diện "
              "(Edit → Input → cập nhật sudocode-repo lên version mới nhất → Save Version → Save & Run All).")
        return
    kdir = os.path.join(BUILD, "kernels", slug(a.job))
    shutil.rmtree(kdir, ignore_errors=True); os.makedirs(kdir)
    src = open(os.path.join(ROOT, "kaggle", "runner.py"), encoding="utf-8").read()
    src = src.replace("JOB = {}   # ĐIỀN BỞI scripts/kaggle_job.py",
                      "JOB = json.loads(" + repr(json.dumps(job, ensure_ascii=False)) + ")   # điền bởi kaggle_job.py", 1)
    try:
        ns = {"__name__": "kaggle_runner_check"}
        exec(compile(src, "runner.py", "exec"), ns)
        assert ns["JOB"] == job
    except Exception as e:
        sys.exit(f"runner.py sinh ra bị lỗi, không đẩy: {type(e).__name__}: {e}")
    open(os.path.join(kdir, "runner.py"), "w", encoding="utf-8").write(src)
    meta = {"id": f"{k.user}/{slug(a.job)}", "title": slug(a.job), "code_file": "runner.py", "language": "python",
            "kernel_type": "script", "is_private": True, "enable_gpu": ACCEL[a.accelerator] is not None,
            "enable_internet": True, "dataset_sources": [ds], "competition_sources": [], "kernel_sources": []}
    if ACCEL[a.accelerator]:
        meta["machine_shape"] = ACCEL[a.accelerator]
    json.dump(meta, open(os.path.join(kdir, "kernel-metadata.json"), "w"), indent=2)
    args = ["kernels", "push", "-p", kdir]
    if ACCEL[a.accelerator]:
        args += ["--accelerator", ACCEL[a.accelerator]]
    if a.timeout:
        args += ["-t", str(a.timeout)]
    k.run(*args)
    if needs:
        print(f"\nLƯU Ý: job cần secrets {needs}. Nếu đây là lần đầu đẩy kernel {meta['id']}: mở kernel trên kaggle.com → "
              "Add-ons → Secrets → bật các secret trên → Save Version. Thiếu secret thì runner dừng ngay và báo rõ.")
    print(f"\nkernel: https://www.kaggle.com/code/{meta['id']}")


def status(k, a):
    _, out = k.run("kernels", "status", f"{k.user}/{slug(a.job)}")
    return out


def logs(k, a):
    dst = os.path.join(ROOT, "runs", "kaggle", a.job)
    os.makedirs(dst, exist_ok=True)
    args = [kaggle_bin(), "kernels", "logs", f"{k.user}/{slug(a.job)}"] + (["-f"] if a.follow else [])
    with open(os.path.join(dst, "live.log"), "a", encoding="utf-8") as fh:
        p = subprocess.Popen(args, env=k.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        for ln in p.stdout:
            try:
                ln = ln.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
            sys.stdout.write(ln); sys.stdout.flush(); fh.write(ln); fh.flush()
        return p.wait()


def pull(k, a):
    dst = os.path.join(ROOT, "runs", "kaggle", a.job)
    os.makedirs(dst, exist_ok=True)
    k.run("kernels", "output", f"{k.user}/{slug(a.job)}", "-p", dst, "-o")
    print(f"kết quả → {dst}")
    for f in sorted(glob_md(dst)):
        print(f"\n===== {os.path.relpath(f, dst)}\n" + open(f, encoding="utf-8").read())


def glob_md(d):
    import glob
    return glob.glob(os.path.join(d, "**", "summary.md"), recursive=True)


def wait(k, a):
    t0 = time.time()
    while True:
        out = status(k, a).lower()
        if any(s in out for s in ("complete", "error", "cancel")):
            break
        if time.time() - t0 > a.max_wait:
            sys.exit(f"quá {a.max_wait}s, kernel vẫn chạy — dùng `status` / `pull` sau")
        time.sleep(a.poll)
    pull(k, a)
    if "error" in out:
        sys.exit("kernel kết thúc với lỗi — xem runs/kaggle/<job>/*.log và log của kernel trên kaggle.com")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cred", help="đường dẫn kaggle.json (mặc định: KAGGLE_USERNAME/KAGGLE_KEY)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("quota")
    sub.add_parser("dataset", help="chỉ đóng gói + đẩy version mới của <user>/sudocode-repo, KHÔNG đẩy kernel "
                                   "(giữ secret đã gắn trên giao diện; chạy lại kernel bằng Save Version trên kaggle.com)")
    p = sub.add_parser("push")
    p.add_argument("--job", required=True)
    p.add_argument("--sets", nargs="+", default=["sample"])
    p.add_argument("--configs", nargs="+", default=["full", "baseline_no_memory"])
    p.add_argument("--router", default="jev", choices=["jev", "laya", "llm", "qwen", "rules"])
    p.add_argument("--generator", default="qwen", choices=["deepseek", "qwen", "offline"])
    p.add_argument("--extractor", default="rules", choices=["rules", "llm", "hybrid"])
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--only", nargs="*")
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--accelerator", default="T4", choices=list(ACCEL))
    p.add_argument("--timeout", type=int, help="truyền cho `kernels push -t` (Kaggle KHÔNG tôn trọng — đo 14/10); dùng --max-hours")
    p.add_argument("--max-hours", type=float, default=3.0, help="hạn chót do runner.py tự giữ: quá giờ thì dừng mọi bước và thoát")
    p.add_argument("--dataset", help="dùng dataset có sẵn <user>/<slug>, không đóng gói lại")
    p.add_argument("--variant", action="append", default=[],
                   help="TAG:KEY=V;KEY=V — chạy lần lượt nhiều biến thể trong một phiên (kết quả <job>/<job>-<TAG>/)")
    p.add_argument("--dataset-only", action="store_true",
                   help="chỉ đẩy dataset kèm cấu hình job, KHÔNG đẩy kernel (giữ Secrets đã gắn; chạy lại trên giao diện)")
    p.add_argument("--pre", action="append", default=[],
                   help="lệnh chạy trên Kaggle sau setup, trước run_suite ({python}, {out} được thay), vd \"{python} scripts/router_agreement.py ...\"")
    p.add_argument("--pre-only", action="store_true", help="chỉ chạy các bước --pre, không chạy run_suite")
    p.add_argument("--env", nargs="*", default=[], help="KEY=VALUE thêm cho lần chạy (vd QWEN_MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ)")
    for name in ("status", "pull", "wait", "logs"):
        q = sub.add_parser(name)
        q.add_argument("--job", required=True)
        if name == "logs":
            q.add_argument("--follow", "-f", action="store_true", help="đọc log trực tiếp khi kernel đang chạy")
        if name == "wait":
            q.add_argument("--poll", type=int, default=60)
            q.add_argument("--max-wait", type=int, default=6 * 3600)
    a = ap.parse_args()
    k = K(a.cred)
    if a.cmd == "quota":
        k.run("quota")
    elif a.cmd == "dataset":
        push_dataset(k, f"code {time.strftime('%Y-%m-%d %H:%M')}")
    else:
        {"push": push, "status": status, "pull": pull, "wait": wait, "logs": logs}[a.cmd](k, a)


if __name__ == "__main__":
    main()
