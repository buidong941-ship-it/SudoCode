#!/usr/bin/env python3
"""Đồng bộ registry / lock / resolved TRƯỚC khi đo (13/11) rồi materialize suite chạy.

    python scripts/registry_sync_check.py --suite dev --materialize /tmp/suites/dev --out <dir>

1. Dựng lại lock + index từ registry.json và file dữ liệu hiện có (`dataset_registry.py index` ra thư mục tạm), so với
   registry.lock.json / index.jsonl đang có trong repo: registry_sha256, sha256 + số kịch bản từng phần.
2. Giải lại suites (`dataset_registry.py suites`) và so suites/resolved/*.json với bản trong repo.
3. Materialize suite cần chạy (kiểm sha256 với index, chặn trùng scenario_id) và đếm số kịch bản = resolved.n.
Thoát mã 3 nếu phần dữ liệu / suite dùng cho lần đo lệch với lock / resolved. Phần H13 (guarded) chỉ báo cùng / khác,
không in nội dung, không chép index mới ra output (quy ước holdout).
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS = os.path.join(ROOT, "datagen", "datasets")


def run(cmd):
    p = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "dataset_registry.py"), *cmd], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout + p.stderr)[-1500:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", required=True)
    ap.add_argument("--materialize", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rep = {"suite": a.suite}
    lock0 = json.load(open(os.path.join(DS, "registry.lock.json"), encoding="utf-8"))
    idx0 = open(os.path.join(DS, "index.jsonl"), encoding="utf-8").read().splitlines()
    res0 = {os.path.basename(p): json.load(open(p, encoding="utf-8")) for p in glob.glob(os.path.join(DS, "suites", "resolved", "*.json"))}
    tmp = tempfile.mkdtemp(prefix="regsync_")
    rc, log = run(["index", "--lock", os.path.join(tmp, "lock.json"), "--index", os.path.join(tmp, "index.jsonl")])
    rep["index_rc"] = rc
    lock1 = json.load(open(os.path.join(tmp, "lock.json"), encoding="utf-8")) if rc == 0 else {}
    idx1 = open(os.path.join(tmp, "index.jsonl"), encoding="utf-8").read().splitlines() if rc == 0 else []
    p0 = {p["key"]: p for p in lock0.get("parts") or []}
    p1 = {p["key"]: p for p in lock1.get("parts") or []}
    strip = lambda p: {k: v for k, v in p.items() if k not in ("generated_at",)}
    diff_parts = sorted(k for k in set(p0) | set(p1) if strip(p0.get(k) or {}) != strip(p1.get(k) or {}))
    rep["registry_sha_same"] = lock0.get("registry_sha256") == lock1.get("registry_sha256")
    rep["index_same"] = idx0 == idx1
    rep["lock_parts_differ"] = [k if not k.startswith("h13") else "h13:<guarded>" for k in diff_parts]
    rc2, log2 = run(["suites"])
    rep["suites_rc"] = rc2
    res1 = {os.path.basename(p): json.load(open(p, encoding="utf-8")) for p in glob.glob(os.path.join(DS, "suites", "resolved", "*.json"))}
    rep["resolved_differ"] = sorted(k for k in set(res0) | set(res1) if res0.get(k) != res1.get(k))
    used = res0.get(f"{a.suite}.json") or {}
    used_parts = sorted({f"{m['dataset_id']}@{m['version']}/{m['part']}" for m in used.get("members") or []})
    rep["suite_parts"] = used_parts
    rep["suite_parts_differ"] = [k for k in diff_parts if k in used_parts]
    if os.path.exists(a.materialize):
        shutil.rmtree(a.materialize)
    rc3, log3 = run(["materialize", "--suite", a.suite, "--out", a.materialize])
    files = [f for f in os.listdir(a.materialize) if f.endswith(".json") and not f.startswith("_")] if rc3 == 0 else []
    rep.update(materialize_rc=rc3, materialized=len(files), resolved_n=used.get("n"))
    rep["ok"] = (rc == 0 and rc2 == 0 and rc3 == 0 and rep["registry_sha_same"] and not rep["suite_parts_differ"]
                 and f"{a.suite}.json" not in rep["resolved_differ"] and len(files) == used.get("n"))
    rep["logs"] = {"index": log if rc else "", "suites": log2 if rc2 else "", "materialize": log3 if rc3 else ""}
    json.dump(rep, open(os.path.join(a.out, "registry_sync.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in rep.items() if k != "logs"}, ensure_ascii=False, indent=1))
    if not rep["ok"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
