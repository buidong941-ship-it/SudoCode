"""Quiet polling: print only terminal status/errors; always pull outputs to workspace."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
from kaggle_job import K, ROOT, slug

ap = argparse.ArgumentParser()
ap.add_argument('--cred', required=True); ap.add_argument('--job', required=True)
a = ap.parse_args(); k = K(a.cred)
dst = Path(ROOT) / 'runs/kaggle' / a.job; dst.mkdir(parents=True, exist_ok=True)
previous = None
while True:
    rc, out = k.run('kernels', 'status', f'{k.user}/{slug(a.job)}', check=False, quiet=True)
    if rc:
        if out != previous: print('status API error:', out[:300], flush=True)
        previous = out; time.sleep(60); continue
    (dst / 'watch-status.json').write_text(json.dumps({'account': k.user, 'job': a.job, 'status': out, 'checked_at': time.strftime('%Y-%m-%d %H:%M:%S')}), encoding='utf-8')
    if any(word in out.lower() for word in ('complete', 'error', 'cancel')):
        print(out, flush=True)
        rc, log = k.run('kernels', 'output', f'{k.user}/{slug(a.job)}', '-p', str(dst), '-o', check=False, quiet=True)
        (dst / 'download.log').write_text(log, encoding='utf-8')
        print('results downloaded' if rc == 0 else 'download error: ' + log[-300:], flush=True)
        break
    time.sleep(60)
