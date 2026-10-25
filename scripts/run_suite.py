#!/usr/bin/env python3
"""Một lệnh chạy trọn bộ đánh giá — giống nhau trên Kaggle, server thuê (SSH/Termius) và máy cá nhân; chỉ khác RUN_PROFILE.

    RUN_PROFILE=kaggle python scripts/run_suite.py --sets sample dev test --router jev --generator qwen --extractor hybrid
    RUN_PROFILE=server python scripts/run_suite.py --sets dev --generator qwen --router qwen       # toàn bộ LLM local
    RUN_PROFILE=local  python scripts/run_suite.py --sets sample --router rules --generator offline  # kiểm logic, không GPU

Các bước:
1. Có backend dùng Qwen → bật server vLLM (scripts/serve_llm.sh) nếu chưa chạy; tắt lại khi xong (trừ --keep-server).
2. (--smoke) chạy tests/smoke.sh trước.
3. Với mỗi bộ kịch bản: run_eval.py cấu hình full + baseline_no_memory → eval/reference_eval.py của BTC → report.json.
4. Ghi <out>/summary.md + summary.json (bảng A.6 rút gọn mỗi bộ) và suite.json (lệnh, cấu hình, thời gian).
Thoát mã 1 nếu có kịch bản lỗi hoặc một bước thất bại — để Kaggle/CI báo đỏ.

Bộ kịch bản: sample = test_set/public_sample, dev = datagen/out_nat/dev, test = datagen/out_nat/test, hoặc một đường dẫn bất kỳ.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core.config import settings  # noqa: E402

SETS = {"sample": "test_set/public_sample", "dev": "datagen/out_nat/dev", "test": "datagen/out_nat/test"}


STEP_TIMEOUT = int(os.environ.get("STEP_TIMEOUT", "5400"))


def sh(cmd, log, timeout=None, **kw):
    import threading
    timeout = timeout or STEP_TIMEOUT
    line = " ".join(shlex.quote(c) for c in cmd)
    print(f"\n$ {line}", flush=True)
    log.write(f"\n$ {line}\n"); log.flush()
    p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                         errors="replace", start_new_session=os.name != "nt", **kw)
    timed_out = []

    def kill():
        timed_out.append(True)
        try:
            if os.name != "nt":
                import signal
                os.killpg(p.pid, signal.SIGKILL)
            else:
                p.kill()
        except Exception:
            pass
    t = threading.Timer(timeout, kill); t.daemon = True; t.start()
    for ln in p.stdout:
        sys.stdout.write(ln); sys.stdout.flush(); log.write(ln)
    p.wait(); t.cancel()
    if timed_out:
        msg = f"TIMEOUT: bước trên chạy quá {timeout}s → đã dừng (đặt STEP_TIMEOUT để đổi)\n"
        sys.stdout.write(msg); log.write(msg)
        log.flush()
        return 124
    log.flush()
    return p.returncode


def bash():
    if os.name != "nt":
        return "bash"
    for c in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe"):
        if os.path.exists(c):
            return c
    return "bash"


def llm_failures(trace):
    bad = 0
    try:
        for line in open(trace, encoding="utf-8"):
            r = json.loads(line)
            fb = " ".join(str(x) for x in ((r.get("router") or {}).get("fallback"), (r.get("extractor") or {}).get("fallback")) if x)
            if (r.get("guardrail") or {}).get("action") == "llm_error_template" or \
                    any(s in fb for s in ("Connection", "Timeout", "APIStatusError", "InternalServerError", "JSONDecodeError")):
                bad += 1
    except FileNotFoundError:
        pass
    return bad


def server_ready():
    return subprocess.run([bash(), "scripts/serve_llm.sh", "status"], cwd=ROOT, capture_output=True).returncode == 0


def ensure_server(log, meta):
    if server_ready():
        return True
    print("vLLM không phản hồi → bật lại", flush=True)
    sh([bash(), "scripts/serve_llm.sh", "stop"], log)
    rc = sh([bash(), "scripts/serve_llm.sh", "start"], log)
    meta["steps"].append({"step": "restart_llm", "rc": rc})
    return rc == 0


def metrics(rep):
    def g(d, *ks):
        for k in ks:
            d = (d or {}).get(k) if isinstance(d, dict) else None
        return d
    out = {}
    for side in ("baseline", "system"):
        s = rep.get(side) or {}
        out[side] = {"RQR": g(s, "repeat_question_rate", "value"), "CCR": g(s, "context_carryover_rate", "value"),
                     "TSR": g(s, "task_success_rate", "value"), "TSR_hard": g(s, "task_success_rate", "hard_cases", "value"),
                     "HR_price": g(s, "hallucination_rate", "price_promo_only", "value"),
                     "guardrail": g(s, "guardrail_violations", "total"),
                     "TTFT_p50": g(s, "latency", "ttft", "p50_ms"), "TTFT_p95": g(s, "latency", "ttft", "p95_ms"),
                     "total_p95": g(s, "latency", "total", "p95_ms"), "brief_p95": g(s, "latency", "call_brief", "p95_ms"),
                     "n_turns": g(s, "latency", "n_turns")}
    out["rqr_reduction_pct"] = g(rep, "comparison", "rqr_relative_reduction_pct")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sets", nargs="+", default=["sample", "dev", "test"])
    ap.add_argument("--configs", nargs="+", default=["full", "baseline_no_memory"])
    ap.add_argument("--router", default=settings.router_backend, choices=["jev", "laya", "llm", "qwen", "rules"])
    ap.add_argument("--generator", default=settings.generator_backend, choices=["deepseek", "qwen", "offline"])
    ap.add_argument("--extractor", default=settings.extractor_backend, choices=["rules", "llm", "hybrid"])
    ap.add_argument("--transport", default=settings.tool_transport, choices=["mcp", "direct"])
    ap.add_argument("--workers", type=int, default=int(os.environ.get("WORKERS", "2")))
    ap.add_argument("--only", nargs="*", help="chỉ chạy các scenario_id này")
    ap.add_argument("--out", default=None, help="thư mục kết quả (mặc định $RUN_OUT/<tag>)")
    ap.add_argument("--tag", default=None, help="tên lần chạy (mặc định thời gian)")
    ap.add_argument("--serve", default="auto", choices=["auto", "never"], help="auto: tự bật vLLM khi có backend qwen")
    ap.add_argument("--keep-server", action="store_true", help="không tắt vLLM khi xong (chạy tiếp lệnh khác)")
    ap.add_argument("--smoke", action="store_true", help="chạy tests/smoke.sh trước")
    a = ap.parse_args()
    a.router = os.environ.get("SUITE_ROUTER") or a.router
    a.extractor = os.environ.get("SUITE_EXTRACTOR") or a.extractor

    tag = a.tag or time.strftime("suite-%Y%m%d-%H%M%S")
    out = os.path.abspath(a.out or os.path.join(os.environ.get("RUN_OUT", "runs/suite"), tag))
    os.makedirs(out, exist_ok=True)
    os.environ.setdefault("VLLM_LOG", os.path.join(out, "vllm.log"))
    log = open(os.path.join(out, "suite.log"), "a", encoding="utf-8")
    t0 = time.time()
    meta = {"tag": tag, "args": vars(a), "profile": os.environ.get("RUN_PROFILE"), "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "settings": settings.describe(), "steps": []}
    failed = False
    uses_qwen = "qwen" in (a.router, a.generator) or (a.extractor != "rules" and settings.extractor_llm == "qwen")
    started_server = False
    try:
        if uses_qwen and a.serve == "auto":
            already = subprocess.run([bash(), "scripts/serve_llm.sh", "status"], cwd=ROOT, capture_output=True).returncode == 0
            if not already:
                rc = sh([bash(), "scripts/serve_llm.sh", "start"], log)
                meta["steps"].append({"step": "serve_llm", "rc": rc})
                if rc:
                    raise SystemExit("không bật được vLLM — xem " + os.environ["VLLM_LOG"])
                started_server = True
        if a.smoke:
            rc = sh([bash(), "tests/smoke.sh"], log, env={**os.environ, "OUT": os.path.join(out, "smoke")})
            meta["steps"].append({"step": "smoke", "rc": rc}); failed |= rc != 0
        if os.environ.get("SUITE_EXTRACT_EVAL") == "1":
            rc = sh([sys.executable, "scripts/extract_eval.py", "--modes", "rules", "llm", "hybrid",
                     "--out", os.path.join(out, "extract_eval.json")], log)
            meta["steps"].append({"step": "extract_eval", "rc": rc})
        summary = {}
        for name in a.sets:
            path = SETS.get(name, name)
            sdir = os.path.join(out, os.path.basename(os.path.normpath(name)))
            os.makedirs(sdir, exist_ok=True)
            traces, fails = {}, {}
            for cfg in a.configs:
                trace = os.path.join(sdir, f"{cfg}.jsonl")
                cmd = [sys.executable, "run_eval.py", "--scenarios", path, "--config", cfg, "--out", trace,
                       "--router", a.router, "--generator", a.generator, "--extractor", a.extractor,
                       "--transport", a.transport, "--workers", str(a.workers), "--run-id", f"{tag}-{name}"]
                if a.only:
                    cmd += ["--only", *a.only]
                for attempt in (1, 2):
                    if uses_qwen and a.serve == "auto" and not ensure_server(log, meta):
                        rc = 1; break
                    t1 = time.time(); rc = sh(cmd, log)
                    nbad = llm_failures(trace)
                    meta["steps"].append({"step": f"run_eval {name} {cfg}", "attempt": attempt, "rc": rc,
                                          "llm_failures": nbad, "seconds": round(time.time() - t1, 1)})
                    if not nbad or attempt == 2:
                        break
                    print(f"{nbad} lượt lỗi LLM ở {name}/{cfg} → chạy lại sau khi kiểm server", flush=True)
                fails[cfg] = nbad
                failed |= rc != 0 or nbad > 0
                traces[cfg] = trace
            if "full" in traces:
                cmd = [sys.executable, os.path.join(ROOT, "eval", "reference_eval.py"), "--scenarios", os.path.join(ROOT, path),
                       "--trace", traces["full"], "--out", os.path.join(sdir, "report.json")]
                if "baseline_no_memory" in traces:
                    cmd += ["--baseline", traces["baseline_no_memory"]]
                rc = sh(cmd, open(os.path.join(sdir, "table.txt"), "w", encoding="utf-8"))
                meta["steps"].append({"step": f"reference_eval {name}", "rc": rc}); failed |= rc != 0
                if rc == 0:
                    summary[name] = metrics(json.load(open(os.path.join(sdir, "report.json"), encoding="utf-8")))
                    summary[name]["llm_failures"] = fails
        json.dump(summary, open(os.path.join(out, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        write_md(os.path.join(out, "summary.md"), summary, a, tag)
        print(open(os.path.join(out, "summary.md"), encoding="utf-8").read())
    finally:
        if started_server and not a.keep_server:
            subprocess.run([bash(), "scripts/serve_llm.sh", "stop"], cwd=ROOT)
        meta.update(seconds=round(time.time() - t0, 1), failed=failed)
        json.dump(meta, open(os.path.join(out, "suite.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        log.close()
    print(f"→ {out}")
    return 1 if failed else 0


def write_md(path, summary, a, tag):
    rows = [("Repeat-Question Rate (%)", "RQR"), ("Context Carryover Rate (%)", "CCR"), ("Task Success Rate (%)", "TSR"),
            ("TSR ca khó (%)", "TSR_hard"), ("Hallucination giá & KM (%)", "HR_price"), ("Vi phạm guardrail", "guardrail"),
            ("TTFT p50 / p95 (ms)", ("TTFT_p50", "TTFT_p95")), ("Total p95 (ms)", "total_p95"), ("Call Brief p95 (ms)", "brief_p95"),
            ("Số lượt đo", "n_turns")]
    L = [f"# {tag}", "", f"router={a.router} · generator={a.generator} · extractor={a.extractor} · transport={a.transport} · "
         f"profile={os.environ.get('RUN_PROFILE')}", "", "Mỗi ô: Baseline / Hệ thống (chấm bằng eval/reference_eval.py).", ""]
    L.append("| Chỉ số | " + " | ".join(summary) + " |")
    L.append("|---|" + "---|" * len(summary))
    for label, k in rows:
        cells = []
        for m in summary.values():
            f = (lambda s: f"{s[k[0]]} / {s[k[1]]}") if isinstance(k, tuple) else (lambda s: s[k])
            cells.append(f"{f(m['baseline'])} / {f(m['system'])}" if not isinstance(k, tuple) else f(m["system"]))
        L.append(f"| {label} | " + " | ".join(str(c) for c in cells) + " |")
    L.append("| Mức giảm RQR (%) | " + " | ".join(str(m.get("rqr_reduction_pct")) for m in summary.values()) + " |")
    L.append("| Lượt lỗi LLM (phải = 0) | " + " | ".join(
        f"{(m.get('llm_failures') or {}).get('baseline_no_memory', '-')} / {(m.get('llm_failures') or {}).get('full', '-')}"
        for m in summary.values()) + " |")
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    sys.exit(main())
