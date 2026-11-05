#!/usr/bin/env python3
"""L1 + L3 (05/11): tối ưu latency không được đổi đầu ra.

1. PARALLEL_ROUTER=1 (router chạy song song với trích slot) cho CÙNG trace với =0 (chỉ khác latency), offline, các bộ dev.
2. QWEN_EXTRACT_BASE_URL: extractor + summarizer dùng endpoint riêng, generator vẫn dùng QWEN_BASE_URL; rỗng = như cũ.

    python tests/latency_parallel_check.py [--sets ...] [--out-dir DIR]
Exit 1 nếu có lệch.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
from mcp_parity import first_diff, strip  # noqa: E402

DEFAULT_SETS = ["test_set/public_sample", "datagen/out_v3/final/dev", "datagen/out_btc_like_final_v2_1/final/dev"]


def run(out_dir, tag, scen, config, par, table):
    out = os.path.join(out_dir, f"{tag}-{config}-p{par}.jsonl")
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{out_dir}/{tag}-{config}-p{par}.db", "PARALLEL_ROUTER": str(par),
           "LLM_CACHE": "off", "IMPROVE_DIR": "", "PLANNER_TABLE": table, "PRODUCT_LEXICON": table}
    subprocess.run([sys.executable, os.path.join(ROOT, "run_eval.py"), "--scenarios", os.path.join(ROOT, scen), "--config", config,
                    "--out", out, "--router", "rules", "--generator", "offline", "--extractor", "rules", "--transport", "direct",
                    "--run-id", "par-parity", "--workers", "2"], check=True, env=env, cwd=ROOT, stderr=subprocess.DEVNULL)
    return [json.loads(l) for l in open(out, encoding="utf-8")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="*", default=DEFAULT_SETS)
    ap.add_argument("--out-dir")
    a = ap.parse_args()
    out_dir = a.out_dir or tempfile.mkdtemp(prefix="par_parity_")
    os.makedirs(out_dir, exist_ok=True)
    bad = n = 0
    # 1. trùng trace (cả với bảng D51 bật, vì job L6 chạy chung PLANNER_TABLE=1)
    for table in ("0", "1"):
        for scen in a.sets:
            if not os.path.isdir(os.path.join(ROOT, scen)):
                print(f"[bỏ qua] {scen}"); continue
            tag = scen.replace("/", "_") + f"-t{table}"
            for config in ("full", "baseline_no_memory"):
                x, y = run(out_dir, tag, scen, config, 0, table), run(out_dir, tag, scen, config, 1, table)
                k = 0
                if len(x) != len(y):
                    print(f"[{scen} {config} table={table}] số lượt khác {len(x)} ≠ {len(y)}"); bad += 1; continue
                for r0, r1 in zip(x, y):
                    n += 1
                    d = first_diff(strip(r0), strip(r1))
                    if d:
                        bad += 1; k += 1
                        if k <= 3:
                            print(f"  LỆCH {scen} {config} {r0.get('scenario_id')} {r0.get('call')} t{r0.get('turn')}: {d[:240]}")
                print(f"[{scen} {config} table={table}] {len(x)} lượt, lệch {k}")
    # 2. định tuyến endpoint Qwen
    from core.config import settings
    from core.llm.deepseek import LLM
    with patch.object(settings, "qwen_base_url", "http://127.0.0.1:8000/v1"), \
            patch.object(settings, "qwen_extract_base_url", "http://127.0.0.1:8001/v1"):
        gen, ext = LLM("qwen"), LLM("qwen", role="extract")
        if "8000" not in str(gen.c.base_url) or "8001" not in str(ext.c.base_url):
            bad += 1; print(f"SAI định tuyến: generator {gen.c.base_url}, extractor {ext.c.base_url}")
    with patch.object(settings, "qwen_base_url", "http://127.0.0.1:8000/v1"), patch.object(settings, "qwen_extract_base_url", ""):
        if "8000" not in str(LLM("qwen", role="extract").c.base_url):
            bad += 1; print("SAI: QWEN_EXTRACT_BASE_URL rỗng thì extractor phải dùng QWEN_BASE_URL")
    src = open(os.path.join(ROOT, "harness", "llm_extract.py"), encoding="utf-8").read() + \
        open(os.path.join(ROOT, "core", "llm", "summarizer.py"), encoding="utf-8").read()
    if src.count('role="extract"') < 2:
        bad += 1; print("SAI: extractor / summarizer chưa dùng role=extract")
    print(f"latency_parallel_check: {n} lượt so, {'OK' if not bad else str(bad) + ' lỗi'}")
    sys.exit(1 if bad or n == 0 else 0)


if __name__ == "__main__":
    main()
