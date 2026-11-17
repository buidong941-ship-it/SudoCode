"""Kaggle CPU gate cho cấu hình đích ARCH=target (11/11, K01–K14): compileall + bài kiểm đích + hồi quy R0 (contract_v2_cpu).
Không gọi model / API thật. Dùng: python scripts/target_arch_cpu.py <out_dir>"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
results = []


import re  # noqa: E402

# Bài kiểm chạy với env SẠCH: bỏ mọi biến cấu hình mà core/config.py đọc (job GPU đặt ARCH=target, EXTRACTOR_LLM=qwen...
# — để lọt vào kiểm R0 thì các check gọi Qwen khi server chưa chạy). Mỗi check tự đặt cờ nó cần.
_CFG = set(re.findall(r'_env\("([A-Z0-9_]+)"', (ROOT / 'core' / 'config.py').read_text(encoding='utf-8')))
_CFG |= set(re.findall(r'_check_(?:choice|set)\("([A-Z0-9_]+)"', (ROOT / 'core' / 'config.py').read_text(encoding='utf-8')))
_CFG -= {"RUN_PROFILE", "DATABASE_URL"}
CLEAN = {k: v for k, v in os.environ.items() if k not in _CFG}


def run(name, cmd, env_extra=None):
    env = dict(CLEAN, PYTHONIOENCODING='utf-8', **(env_extra or {}))
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    (out / f'{name}.log').write_text(r.stdout + r.stderr, encoding='utf-8')
    results.append({'check': name, 'rc': r.returncode})
    tail = '\n'.join((r.stdout + r.stderr).strip().splitlines()[-40:])
    print(f'== {name}: {"OK" if r.returncode == 0 else "FAILED"}\n{tail}', flush=True)


run('compileall', [sys.executable, '-m', 'compileall', '-q', 'harness', 'core', 'scripts', 'tests', 'run_eval.py'])
run('target_arch_check', [sys.executable, 'tests/target_arch_check.py'])
run('planner_target_matrix_check', [sys.executable, 'tests/planner_target_matrix_check.py'])
run('understanding_check', [sys.executable, 'tests/understanding_check.py'])
run('btc_1111_check', [sys.executable, 'tests/btc_1111_check.py'])
run('r0_regression', [sys.executable, 'scripts/contract_v2_cpu.py', str(out / 'r0')])
(out / 'target_checks.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps({'failed': [x['check'] for x in results if x['rc']]}), flush=True)
raise SystemExit(int(any(x['rc'] for x in results)))
