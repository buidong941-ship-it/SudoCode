"""Kaggle CPU gate cho CONTRACT_V2 (09/11) và bất biến G1–G3 của bàn giao FINAL (10/11): kiểm hàm mới + hồi quy các check hiện có khi tắt cờ (parity) và khi bật cờ.
Không chạy smoke.sh (gồm 7 sample BTC đã loại khỏi phạm vi), không gọi model."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
LEGACY = ['jev1108_observed_check', 'llm_extract_check', 'coverage_check', 'planner_rules_check', 'fixes_1106_check',
          # 10/11 (bàn giao FINAL G1–G3): kết quả tool / bảo toàn / chính sách / projection / COD + các check chạm cùng đường
          'outcome_contract_check', 'jev1108_results_check', 'planner_table_d51_check',
          'planner_b345_check', 'improve_hook_check']
results = []


def run(name, env_extra, tag):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', **env_extra)
    r = subprocess.run([sys.executable, f'tests/{name}.py'], capture_output=True, text=True, env=env)
    (out / f'{name}.{tag}.log').write_text(r.stdout + r.stderr, encoding='utf-8')
    results.append({'check': name, 'variant': tag, 'rc': r.returncode})
    print(name, tag, 'OK' if r.returncode == 0 else 'FAILED', flush=True)


r = subprocess.run([sys.executable, '-m', 'compileall', '-q', 'harness', 'core', 'scripts', 'tests'], capture_output=True, text=True)
results.append({'check': 'compileall', 'variant': '-', 'rc': r.returncode})
print('compileall', 'OK' if r.returncode == 0 else 'FAILED\n' + r.stdout + r.stderr, flush=True)
run('contract_v2_check', {'CONTRACT_V2_OUT': str(out)}, 'v2')
run('outcome_contract_check', {'CONTRACT_V2_OUT': str(out)}, 'v2')
for name in LEGACY:
    base = {} if name.startswith('jev1108_') else {'GOAL_CONTRACT': '0', 'PLANNER_SELECTOR': 'rules'}
    run(name, {**base, 'CONTRACT_V2': '0'}, 'off')
    run(name, {**base, 'CONTRACT_V2': '1'}, 'on')
(out / 'checks.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
gate = [x for x in results if x['variant'] in ('-', 'v2', 'off')]
print(json.dumps({'gate_failed': [x for x in gate if x['rc']], 'on_failed': [x['check'] for x in results if x['variant'] == 'on' and x['rc']]}), flush=True)
raise SystemExit(int(any(x['rc'] for x in gate)))
