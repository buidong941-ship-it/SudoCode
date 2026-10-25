#!/usr/bin/env bash
# Tải dữ liệu ngoài repo từ Drive về đúng chỗ (chạy ở máy mới / server sau khi clone).
#   pip install gdown
#   bash scripts/data_fetch.sh                      # đọc DRIVE_DATASET, DRIVE_RUNS trong .env
#   bash scripts/data_fetch.sh <link dataset.tar.gz> [<link runs.tar.gz>]
# Link là link chia sẻ của TỪNG FILE trên Drive (quyền "Bất kỳ ai có đường liên kết"), hoặc ID của file.
# Kết quả: dataset/ và runs/ ở gốc repo. Thư mục đã có sẽ được ghi đè file trùng tên, file khác giữ nguyên.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  DRIVE_DATASET="${DRIVE_DATASET:-$(grep -E '^DRIVE_DATASET=' .env | tail -1 | cut -d= -f2- || true)}"
  DRIVE_RUNS="${DRIVE_RUNS:-$(grep -E '^DRIVE_RUNS=' .env | tail -1 | cut -d= -f2- || true)}"
fi
DRIVE_DATASET="${1:-${DRIVE_DATASET:-}}"
DRIVE_RUNS="${2:-${DRIVE_RUNS:-}}"
command -v gdown >/dev/null || { echo "thiếu gdown: pip install gdown" >&2; exit 1; }
[ -n "$DRIVE_DATASET$DRIVE_RUNS" ] || { echo "chưa có link: đặt DRIVE_DATASET / DRIVE_RUNS trong .env hoặc truyền link làm tham số" >&2; exit 1; }
mkdir -p _download
fetch() {   # $1 = tên, $2 = link hoặc ID
  [ -n "$2" ] || { echo "bỏ qua $1 (không có link)"; return 0; }
  gdown --fuzzy "$2" -O "_download/$1.tar.gz"
  tar -xzf "_download/$1.tar.gz"
  echo "$1/ → $(find "$1" -type f | wc -l) file"
}
fetch dataset "$DRIVE_DATASET"
fetch runs "$DRIVE_RUNS"
