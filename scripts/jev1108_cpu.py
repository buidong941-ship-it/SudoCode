"""Kaggle gate, intentionally excludes smoke.sh (it evaluates seven BTC samples)."""
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
checks = ['jev1108_check', 'jev1108_extractor_check', 'jev1108_observed_check', 'jev1108_results_check', 'jev1108_identity_check', 'llm_extract_check', 'question_detection_check', 'coverage_check', 'cert_v2_check', 'planner_rules_check']
results = []
for name in checks:
    env = dict(os.environ)
    if not name.startswith('jev1108_'):
        # Existing regression fixtures exercise the preserved legacy contract.
        env.update(GOAL_CONTRACT='0', PLANNER_SELECTOR='rules')
    r = subprocess.run([sys.executable, f'tests/{name}.py'], capture_output=True, text=True, env=env)
    (out / f'{name}.log').write_text(r.stdout + r.stderr, encoding='utf-8')
    results.append({'check': name, 'rc': r.returncode})
    print(name, 'OK' if r.returncode == 0 else 'FAILED', flush=True)
(out / 'checks.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
raise SystemExit(int(any(x['rc'] for x in results)))
