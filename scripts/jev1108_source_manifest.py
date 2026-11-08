"""Inventory packaged code/data and action executor contract, no runtime evaluation."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
files = {}
for directory in ('core', 'harness', 'scripts', 'kaggle', 'profiles', 'tests', 'mcp_servers', 'policy', 'catalog', 'datagen/out_v3/final/dev', 'datagen/out_redteam/dev', 'datagen/out_jev1108_new', 'datagen/out_jev1108_identity'):
    for p in sorted((ROOT / directory).rglob('*')):
        if p.is_file() and p.suffix in ('.py', '.json', '.jsonl', '.md', '.env', '.sh'):
            files[p.relative_to(ROOT).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
doc = {'files': files, 'configs': ['full'], 'btc_seven_samples': 'excluded', 'latency_acceptance': 'excluded',
       'live_api_boundary': 'stop_after_credential_loading', 'source_of_truth': 'runtime only; answer keys excluded from agent view'}
p = ROOT / 'docs/PLAN/JEV1108-SOURCE-MANIFEST.json'
p.write_text(json.dumps(doc, indent=2), encoding='utf-8')
print('Source/data manifest written:', len(files), 'files')
