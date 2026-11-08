"""Kaggle diagnostics only: independent labeled probe and extractor gold evaluation."""
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('VLLM_LOG', str(out / 'vllm.log'))
subprocess.run(['bash', 'scripts/serve_llm.sh', 'start'], check=True)
from harness.planner_state import PlannerState
from harness.planner_decision import decide
rows = []
for line in (ROOT / 'datagen/function_probe/partD.jsonl').read_text(encoding='utf-8').splitlines():
    item = json.loads(line)
    raw = item.get('state', {})
    state = PlannerState('after_sale' if raw.get('has_order') else 'considering', raw.get('focus'),
                         tuple(raw.get('cart') or []), ('runtime-existing-order',) if raw.get('has_order') else (),
                         tuple(raw.get('discussed') or []))
    try:
        # Gold/accept/prior_order are never passed to the selector.
        got = decide(item['text'], None, state)
        predicted = set(got['actions']); expected = set(item.get('gold') or [])
        rows.append({'id': item['id'], 'selected_actions': sorted(predicted), 'gold': sorted(expected),
                     'exact': predicted == expected, 'backend': got['backend']})
    except Exception as exc:
        rows.append({'id': item['id'], 'gold': item.get('gold') or [], 'error': type(exc).__name__, 'exact': False})
(out / 'probe.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
from harness.planner_selector import ACTIONS
supported = [r for r in rows if set(r['gold']) <= set(ACTIONS)]
unsupported = sorted({g for r in rows for g in r['gold'] if g not in ACTIONS})
(out / 'probe-contract.json').write_text(json.dumps({'raw_exact': sum(r['exact'] for r in rows), 'raw_total': len(rows),
    'supported_gold_rows': len(supported), 'supported_exact': sum(r['exact'] for r in supported),
    'unsupported_gold_labels': unsupported, 'note': 'Original probe uses a different function contract. Raw exact is not comparable to the old 25-function benchmark; flags and execution require separate evaluation.'}, indent=2), encoding='utf-8')
rc = subprocess.run([sys.executable, 'scripts/extract_eval.py', '--modes', 'hybrid', '--out', str(out / 'extract_eval.json')]).returncode
from harness.jev_adapter import COUNTS
(out / 'audit.json').write_text(json.dumps(COUNTS, indent=2), encoding='utf-8')
print('probe completed:', len(rows), 'exact:', sum(x['exact'] for x in rows), 'real API requests:', COUNTS['real_requests'])
raise SystemExit(rc)
