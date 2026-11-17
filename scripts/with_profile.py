"""Chạy một lệnh với env của một profile cấu hình (vd B2-v51-A), hoặc in tham số --env cho scripts/kaggle_job.py.

    python scripts/with_profile.py profiles/b2_v51a.json -- python run_eval.py --scenarios test_set/public_sample \
        --config full --router rules --generator qwen --extractor hybrid --out runs/local/full.jsonl
    python scripts/with_profile.py profiles/b2_v51a.json --kaggle-env      # → "ARCH=target JEV_SIMULATED=0 ..." (một dòng)
    python scripts/with_profile.py profiles/b2_v51a.json --show            # in env (không có khóa API)

Khóa API KHÔNG nằm trong profile: đọc từ .env / biến môi trường như phần còn lại của repo.
Mọi biến CÓ trong profile luôn GHI ĐÈ biến cùng tên đã có trong shell (tránh trộn cấu hình, vd ARCH / PLANNER_VARIANT còn sót).
Biến không có trong profile (DATABASE_URL, UI_PROFILE, UI_QWEN, khóa API…) giữ nguyên.
"""
import json
import os
import subprocess
import sys


def load(path):
    d = json.load(open(path, encoding="utf-8"))
    return {k: str(v) for k, v in (d.get("env") or {}).items()}, d


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    env, meta = load(argv[0])
    rest = argv[1:]
    if rest[:1] == ["--kaggle-env"]:
        print(" ".join(f"{k}={v}" for k, v in env.items()))
        return 0
    if rest[:1] == ["--show"]:
        print(json.dumps({"profile": meta.get("profile"), "freeze": meta.get("freeze"), "env": env}, ensure_ascii=False, indent=1))
        return 0
    if rest[:1] == ["--"]:
        rest = rest[1:]
    if not rest:
        sys.exit("thiếu lệnh sau --")
    run_env = dict(os.environ)
    for k, v in env.items():
        if run_env.get(k) not in (None, v):
            print(f"[with_profile] ghi đè {k}: {run_env[k]!r} → {v!r}", file=sys.stderr)
        run_env[k] = v
    run_env.setdefault("PYTHONIOENCODING", "utf-8")
    return subprocess.call(rest, env=run_env)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
