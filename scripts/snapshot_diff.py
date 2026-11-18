#!/usr/bin/env python3
"""So source đang chạy với snapshot mốc (sha256.txt của runs/snapshots/<tên>/) — kiểm hash trước khi đo (13/11).

    python scripts/snapshot_diff.py --sha fixtures/snap_sha256.txt --out <dir> [--allow path ...]

Báo file code đổi / mới / mất so với mốc. Thoát mã 3 nếu có file CODE đổi hoặc mới ngoài danh sách --allow (thay đổi đã
duyệt sau mốc). Code = harness, core, scripts, tests, eval, mcp_servers, kaggle, asr, catalog, policy, schemas, run_eval.py,
datagen/datasets (registry / suite). Tài liệu (docs) và fixtures do job đưa vào không tính.
"""
import argparse
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = ("harness/", "core/", "scripts/", "tests/", "eval/", "mcp_servers/", "kaggle/", "asr/", "catalog/", "policy/", "schemas/",
        "datagen/datasets/", "run_eval.py")
JOB_CFG = "kaggle/jobs/"          # cấu hình job do scripts/kaggle_job.py thêm vào gói mỗi lần đẩy — không phải code
SKIP_DIRS = {".git", "venv", "runs", "build", "data", "__pycache__", "fixtures", ".pytest_cache"}


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sha", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--allow", nargs="*", default=[])
    a = ap.parse_args()
    snap = {}
    for ln in open(a.sha, encoding="utf-8"):
        h, _, p = ln.strip().partition(" *")
        p = p[2:] if p.startswith("./") else p
        p = p[5:] if p.startswith("repo/") else p
        snap[p] = h
    changed, missing, new = [], [], []
    for p, h in snap.items():
        fp = os.path.join(ROOT, p)
        if not os.path.exists(fp):
            missing.append(p)
        elif sha(fp) != h:
            changed.append(p)
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            p = os.path.relpath(os.path.join(dp, fn), ROOT).replace(os.sep, "/")
            if p not in snap and p.startswith(CODE) and not p.endswith(".pyc") and not p.startswith(JOB_CFG):
                new.append(p)
    code = lambda xs: sorted(x for x in xs if x.startswith(CODE) and not x.startswith(JOB_CFG))
    unexpected = sorted(x for x in code(changed) + code(new) if x not in set(a.allow))
    rep = {"snapshot_files": len(snap), "changed": sorted(changed), "new_code": sorted(new), "missing": sorted(missing),
           "changed_code": code(changed), "allowed": sorted(a.allow), "unexpected_code_changes": unexpected,
           "ok": not unexpected}
    os.makedirs(a.out, exist_ok=True)
    json.dump(rep, open(os.path.join(a.out, "snapshot_diff.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: rep[k] for k in ("snapshot_files", "changed_code", "new_code", "unexpected_code_changes", "ok")},
                     ensure_ascii=False, indent=1))
    print(f"(file khác mốc ngoài code: {len(rep['changed']) - len(rep['changed_code'])}; mất: {len(missing)})")
    if unexpected:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
