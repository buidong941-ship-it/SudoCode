"""Read downloaded artifacts; report Full quality and API audit, omit latency acceptance."""
import collections
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
results = []
for job in sorted((ROOT / 'runs/kaggle').glob('jev1108-*')):
    for path in sorted(job.rglob('report.json')):
        report = json.loads(path.read_text(encoding='utf-8'))
        system = report.get('system') or {}
        if not system: continue
        trace = path.with_name('full.jsonl')
        rows = [json.loads(l) for l in trace.read_text(encoding='utf-8').splitlines() if l] if trace.exists() else []
        real = max((r.get('api_audit', {}).get('real_requests', 0) for r in rows), default=0)
        blocked = max((r.get('api_audit', {}).get('blocked_real_requests', 0) for r in rows), default=0)
        contracts = [e for r in rows for e in ((r.get('planner') or {}).get('contract') or {}).get('errors', [])]
        selection_errors = [r for r in rows if (((r.get('planner') or {}).get('semantic') or {}).get('fallback') or ((r.get('planner') or {}).get('semantic') or {}).get('errors'))]
        tsr = system.get('task_success_rate') or {}
        results.append({'job': job.name, 'variant': path.parent.parent.name, 'set': path.parent.name,
                        'TSR': tsr.get('value'), 'passed': tsr.get('passed'), 'total': tsr.get('total'),
                        'CCR': (system.get('context_carryover_rate') or {}).get('value'),
                        'RQR': (system.get('repeat_question_rate') or {}).get('value'),
                        'HR': ((system.get('hallucination_rate') or {}).get('price_promo_only') or {}).get('value'),
                        'guardrail': (system.get('guardrail_violations') or {}).get('total'),
                        'real_jev_requests': real, 'blocked_real_attempts': blocked,
                        'audit_rows': sum('api_audit' in r for r in rows), 'rows': len(rows),
                        'contract_errors': dict(collections.Counter(contracts)), 'selector_error_turns': len(selection_errors),
                        'failures': tsr.get('failures', []), 'report': str(path.relative_to(ROOT))})
out = ROOT / 'runs/jev1108'; out.mkdir(parents=True, exist_ok=True)
(out / 'quality.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
lines = ['# Kết quả Jev planner giả lập 08/11', '', 'Chỉ Full; không BTC 7 sample; không dùng latency làm tiêu chí. Không có số đo Jev/DeepSeek thật.', '', '| Job / biến thể | Bộ | TSR | CCR | RQR | HR giá/KM | Guardrail | Jev thật |', '|---|---|---:|---:|---:|---:|---:|---:|']
for r in results:
    lines.append(f'| {r["job"]}/{r["variant"]} | {r["set"]} | {r["TSR"]} | {r["CCR"]} | {r["RQR"]} | {r["HR"]} | {r["guardrail"]} | {r["real_jev_requests"]} |')
(out / 'quality.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('\n'.join(lines))
