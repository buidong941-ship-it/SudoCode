"""Cổng E0 (Kaggle CPU) cho B1/B2-Jev/B3-workflow (THIET-KE-B1-B2-JEV-B3-WORKFLOW mục 7): compileall + kiểm biến thể +
hồi quy B1 (ma trận planner đích, kiểm kiến trúc đích, bộ hiểu, BTC 11/2026). Không gọi model / API thật.
Dùng: python scripts/variants_cpu.py <out_dir>"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
results = []
_CFG = set(re.findall(r'_env\("([A-Z0-9_]+)"', (ROOT / 'core' / 'config.py').read_text(encoding='utf-8')))
_CFG |= set(re.findall(r'_check_(?:choice|set)\("([A-Z0-9_]+)"', (ROOT / 'core' / 'config.py').read_text(encoding='utf-8')))
_CFG -= {"RUN_PROFILE", "DATABASE_URL"}
CLEAN = {k: v for k, v in os.environ.items() if k not in _CFG}


def run(name, cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, env=dict(CLEAN, PYTHONIOENCODING='utf-8'))
    (out / f'{name}.log').write_text(r.stdout + r.stderr, encoding='utf-8')
    results.append({'check': name, 'rc': r.returncode})
    tail = '\n'.join((r.stdout + r.stderr).strip().splitlines()[-60:])
    print(f'== {name}: {"OK" if r.returncode == 0 else "FAILED"}\n{tail}', flush=True)


run('compileall', [sys.executable, '-m', 'compileall', '-q', 'harness', 'core', 'scripts', 'tests', 'run_eval.py'])
run('planner_variants_check', [sys.executable, 'tests/planner_variants_check.py'])
run('b2_improve_check', [sys.executable, 'tests/b2_improve_check.py'])          # 13/11: gói cải thiện B2 (G01–G10)
run('emit_audit_check', [sys.executable, 'tests/emit_audit_check.py'])          # 13/11: emit tách audit hậu kỳ + đo latency tại emit
run('b2_round_f_check', [sys.executable, 'tests/b2_round_f_check.py'])          # 13/11: vòng sửa F1/F2/F3/F8 (B2)
run('planner_target_matrix_check', [sys.executable, 'tests/planner_target_matrix_check.py'])
run('target_arch_check', [sys.executable, 'tests/target_arch_check.py'])
run('understanding_check', [sys.executable, 'tests/understanding_check.py'])
run('btc_1111_check', [sys.executable, 'tests/btc_1111_check.py'])
# 14/11 (§8.14, duyệt): kiểm kiểu output understanding + đóng khi sai kiểu; TA1 / chuyển máy theo trạng thái; phép đo địa chỉ
run('understanding_conform_check', [sys.executable, 'tests/understanding_conform_check.py'])
run('b2_ta1_handoff_check', [sys.executable, 'tests/b2_ta1_handoff_check.py'])
run('address_audit_check', [sys.executable, 'tests/address_audit_check.py'])
# 15/11 (§8.17, duyệt): BTCL-066 thu hẹp (A1/A2), ngữ cảnh nhóm (B), F5 tối thiểu (C1–C3)
run('b2_btcl066_f5_check', [sys.executable, 'tests/b2_btcl066_f5_check.py'])
# ống nối của probe E1 (bộ quyết định giả, không API) — để lần chạy thật với key không hỏng vì lỗi script
run('jev_probe_dry', [sys.executable, 'scripts/jev_planner_probe.py', str(out / 'probe_dry'), '--repeat', '1', '--dry'])
(out / 'variants_checks.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps({'failed': [x['check'] for x in results if x['rc']]}), flush=True)
raise SystemExit(int(any(x['rc'] for x in results)))
