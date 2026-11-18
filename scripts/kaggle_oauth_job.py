#!/usr/bin/env python3
"""Chạy kaggle_job.py bằng OAuth đã đăng nhập; không ghi hoặc in token."""
import os
from pathlib import Path
import runpy
import sys

from kagglesdk.kaggle_client import KaggleClient
from kagglesdk.kaggle_creds import KaggleCredentials

ROOT = Path(__file__).resolve().parents[1]
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
creds = KaggleCredentials.load(KaggleClient())
if creds is None:
    raise SystemExit("Chưa có phiên đăng nhập Kaggle OAuth")
creds.save = lambda: None  # tài khoản nằm ngoài workspace; chỉ dùng token trong bộ nhớ
os.environ["KAGGLE_API_TOKEN"] = creds.get_access_token()
os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
sys.argv = [str(ROOT / "scripts" / "kaggle_job.py"), *sys.argv[1:]]
runpy.run_path(sys.argv[0], run_name="__main__")
