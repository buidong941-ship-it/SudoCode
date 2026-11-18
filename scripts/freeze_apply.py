#!/usr/bin/env python3
"""Áp và kiểm một bản code ĐÓNG BĂNG (14/11, §8.11 của docs/PLAN/TRIEN-KHAI-LATENCY-EMIT-VA-DEV-2026-11-13.md).

runs/freeze/<tên>/code_sha256.txt = sha256 từng file code của đúng gói dataset Kaggle mà job đo đã chạy:
  20261114-roundF-v36 = elylish11/sudocode-repo v36 (rf-full-1113 / rf-base-1113);
  20261114-F1b-v37    = elylish11/sudocode-repo v37 (rf1b-full-1113 / rf1b-base-1113).
--overlay chép runs/freeze/<tên>/overlay/* đè lên repo (bản v36 = 5 file khác v37), rồi kiểm MỌI file trong danh sách.
Lệch một file → exit 3 (không đo trên code không đúng bản đóng băng).

    python scripts/freeze_apply.py --freeze runs/freeze/20261114-roundF-v36 --overlay --out <dir>
    python scripts/freeze_apply.py --freeze runs/freeze/20261114-F1b-v37 --out <dir>          # chỉ kiểm"""
import argparse
import hashlib
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", required=True)
    ap.add_argument("--overlay", action="store_true")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    fz = os.path.join(ROOT, a.freeze)
    copied = []
    if a.overlay:
        od = os.path.join(fz, "overlay")
        for dp, _, fn in os.walk(od):
            for f in fn:
                src = os.path.join(dp, f)
                rel = os.path.relpath(src, od).replace("\\", "/")
                shutil.copyfile(src, os.path.join(ROOT, rel))
                copied.append(rel)
    bad, n = [], 0
    for ln in open(os.path.join(fz, "code_sha256.txt"), encoding="utf-8"):
        if not ln.strip():
            continue
        h, rel = ln.rstrip("\n").split("  ", 1)
        n += 1
        p = os.path.join(ROOT, rel)
        got = hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.isfile(p) else None
        if got != h:
            bad.append({"file": rel, "want": h[:12], "got": (got or "MISSING")[:12]})
    rep = {"freeze": a.freeze, "overlay_copied": sorted(copied), "checked": n, "mismatch": bad, "ok": not bad}
    os.makedirs(a.out, exist_ok=True)
    json.dump(rep, open(os.path.join(a.out, "freeze_check.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: rep[k] for k in ("freeze", "checked", "ok")} | {"mismatch": bad[:10], "copied": len(copied)}, ensure_ascii=False))
    if bad:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
