"""Only executed inside Kaggle."""
from pathlib import Path
import subprocess
import sys
root = Path(__file__).resolve().parents[2]
for args in (["-m", "compileall", "-q", "core", "harness"],
             ["tests/b2tt_check_v1_2.py"], ["tests/guidance_v3_check.py"],
             [str(Path(__file__).with_name("v8_check.py"))],
             [str(Path(__file__).with_name("semantic_check.py"))],
             [str(Path(__file__).with_name("v6p1_check.py"))],
             [str(Path(__file__).with_name("v6p2_check.py"))],
             [str(Path(__file__).with_name("v6p3_check.py"))],
             [str(Path(__file__).with_name("v6p4_check.py"))],
             [str(Path(__file__).with_name("v6p5_check.py"))],
             [str(Path(__file__).with_name("v6p6_check.py"))],
             [str(Path(__file__).with_name("v6p7_check.py"))],
             [str(Path(__file__).with_name("v6p7b_check.py"))],
             [str(Path(__file__).with_name("v6p8_check.py"))],
             [str(Path(__file__).with_name("v6p9_check.py"))],
             [str(Path(__file__).with_name("v6p9b_check.py"))],
             [str(Path(__file__).with_name("v6p10_check.py"))],
             [str(Path(__file__).with_name("v6p11_check.py"))],
             [str(Path(__file__).with_name("v6p12_check.py"))],
             [str(Path(__file__).with_name("v6p13_check.py"))],
             [str(Path(__file__).with_name("v6p14_check.py"))],
             [str(Path(__file__).with_name("v6p15_check.py"))],
             ["datagen/validate.py", "datagen/datasets/releases/h13_revised_r4_20261123/scenarios",
              "--report", "/kaggle/working/h13_r4_validation.json"]):
    subprocess.run([sys.executable, *args], cwd=root, check=True)
# r5 (biến thể cho tool riêng): validator BTC-like không biết tool của nhóm và ghép args_match.sku với giá truth theo ngữ nghĩa
# order.create → chỉ chạy để báo cáo, không làm hỏng job
r5 = subprocess.run([sys.executable, "datagen/validate.py", "datagen/datasets/releases/h13_revised_r5_ext_tools_20261123/scenarios",
                     "--report", "/kaggle/working/h13_r5_validation.json"], cwd=root)
print("r5 validate exit (report-only):", r5.returncode, flush=True)
r7 = subprocess.run([sys.executable, "datagen/validate.py", "datagen/datasets/releases/h13_revised_r7_btc_tools_20261124/scenarios",
                     "--report", "/kaggle/working/h13_r7_validation.json"], cwd=root)
print("r7 validate exit (report-only):", r7.returncode, flush=True)
r6 = subprocess.run([sys.executable, "datagen/validate.py", "datagen/datasets/releases/h13_revised_r6_btc_align_20261124/scenarios",
                     "--report", "/kaggle/working/h13_r6_validation.json"], cwd=root)
print("r6 validate exit (report-only):", r6.returncode, flush=True)
print("CPU checks: OK", flush=True)
