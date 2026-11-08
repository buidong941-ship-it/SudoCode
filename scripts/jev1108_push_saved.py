"""Push an explicitly saved, credential-free job using the existing private Kaggle workflow."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
from kaggle_job import K, ROOT, BUILD, push_dataset, slug

ap = argparse.ArgumentParser(); ap.add_argument('--cred', required=True); ap.add_argument('--job-file', required=True)
a = ap.parse_args(); k = K(a.cred)
job = json.loads(Path(a.job_file).read_text(encoding='utf-8'))
ds = push_dataset(k, f'{job["job"]} {time.strftime("%Y-%m-%d %H:%M")}')
directory = Path(BUILD) / 'kernels' / slug(job['job']); directory.mkdir(parents=True, exist_ok=True)
body = (Path(ROOT) / 'kaggle/runner.py').read_text(encoding='utf-8')
body = body.replace('JOB = {}   # ĐIỀN BỞI scripts/kaggle_job.py', 'JOB = json.loads(' + repr(json.dumps(job, ensure_ascii=False)) + ') # saved job')
compile(body, 'runner.py', 'exec')  # package syntax only; no local evaluation or model
(directory / 'runner.py').write_text(body, encoding='utf-8')
meta = {'id': f'{k.user}/{slug(job["job"])}', 'title': slug(job['job']), 'code_file': 'runner.py', 'language': 'python',
        'kernel_type': 'script', 'is_private': True, 'enable_gpu': bool(job['needs_qwen']), 'enable_internet': True,
        'dataset_sources': [ds], 'competition_sources': [], 'kernel_sources': []}
if job['needs_qwen']: meta['machine_shape'] = 'NvidiaTeslaT4'
(directory / 'kernel-metadata.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
args = ['kernels', 'push', '-p', str(directory)]
if job['needs_qwen']: args += ['--accelerator', 'NvidiaTeslaT4']
k.run(*args)
print('kernel: https://www.kaggle.com/code/' + meta['id'])
