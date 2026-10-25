#!/usr/bin/env bash
# Đóng gói dữ liệu ngoài repo (không commit lên GitHub) thành 2 file để tải lên Drive.
#   bash scripts/data_pack.sh            # → _upload/dataset.tar.gz, _upload/runs.tar.gz
# Sau đó tải hai file này lên một thư mục Drive và ghi link vào .env (DRIVE_DATASET, DRIVE_RUNS) — xem README.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p _upload
for d in dataset runs; do
  if [ -d "$d" ]; then
    tar -czf "_upload/$d.tar.gz" "$d"
    echo "$d → _upload/$d.tar.gz ($(du -h "_upload/$d.tar.gz" | cut -f1), $(tar -tzf "_upload/$d.tar.gz" | grep -vc '/$') file)"
  else
    echo "bỏ qua $d/ (không có)"
  fi
done
