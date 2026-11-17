"""Chạy test xác định với env SẠCH (xoá mọi biến cấu hình của core/config.py), giống scripts/variants_cpu.py.

Lý do (14/11, §8.12): test viết cho cấu hình mặc định; gọi thẳng trong job mang theo PLANNER_VARIANT=b2_jev / ARCH=target /
EXTRACTOR_LLM=qwen của job thì test lỗi giả (job d1-check-1114). Không gọi model / API thật.

Dùng: python scripts/clean_env_check.py <out_dir> <tên test> [<tên test> ...]   (tên = tests/<tên>.py)
Ghi <out_dir>/<tên>.log và <out_dir>/clean_checks.json [{check, rc}]; thoát 1 nếu có test lỗi."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
cfg_src = (ROOT / 'core' / 'config.py').read_text(encoding='utf-8')
_CFG = set(re.findall(r'_env\("([A-Z0-9_]+)"', cfg_src)) | set(re.findall(r'_check_(?:choice|set)\("([A-Z0-9_]+)"', cfg_src))
_CFG -= {"RUN_PROFILE", "DATABASE_URL"}
CLEAN = {k: v for k, v in os.environ.items() if k not in _CFG}
results = []
for name in sys.argv[2:]:
    r = subprocess.run([sys.executable, f'tests/{name}.py'], capture_output=True, text=True, env=dict(CLEAN, PYTHONIOENCODING='utf-8'))
    (out / f'{name}.log').write_text(r.stdout + r.stderr, encoding='utf-8')
    results.append({'check': name, 'rc': r.returncode})
    tail = '\n'.join((r.stdout + r.stderr).strip().splitlines()[-30:])
    print(f'== {name}: {"OK" if r.returncode == 0 else "FAILED"}\n{tail}', flush=True)
(out / 'clean_checks.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
raise SystemExit(int(any(x['rc'] for x in results)))
