import json
from pathlib import Path
import sys
root = Path(sys.argv[1])
ids = set(sys.argv[2:])
for path in root.rglob('full.jsonl'):
    for line in path.read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        if row.get('scenario_id') not in ids: continue
        print(json.dumps({k: row.get(k) for k in ('scenario_id', 'call', 'turn', 'customer_text', 'agent_text', 'goals', 'claims', 'question_slot', 'guardrail')}, ensure_ascii=False))
        semantic = (row.get('planner') or {}).get('semantic') or {}
        print(json.dumps({'semantic': semantic, 'contract': (row.get('planner') or {}).get('contract'),
                          'tools': [{'name': t.get('name'), 'result': t.get('result')} for t in row.get('tool_calls', [])]}, ensure_ascii=False))
