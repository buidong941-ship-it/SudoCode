"""Khung cơ chế cải tiến (plan 01/11, mục D) — TÁCH BIỆT với core.

Gói này chỉ ĐỌC trace / report đã chấm và quản lý các đề xuất cải tiến. Nó không import và không sửa
`harness/`, `core/`, `eval/`, `policy/` (test `tests/improve_check.py` kiểm tra chiều import này).
Agent chưa nạp gì từ đây: móc nạp `approved/` sẽ được bật ở mục E, sau ngày đóng băng, sau một cờ mặc định tắt.

Thư mục dữ liệu (mặc định `improve/`, đổi bằng `--root` hoặc env `IMPROVE_ROOT`):
    gaps.jsonl        lỗi gom từ trace dev (D1) — sinh lại được nên không commit
    pending/<id>.json đề xuất chờ duyệt (D2)
    approved/<id>.json đề xuất đã duyệt — bộ DUY NHẤT agent được nạp (D3)
    rejected/<id>.json đề xuất bị loại (giữ lại để không đề xuất lại)
    rounds/<tên>/     ảnh chụp approved/ + report của từng vòng, dùng để quay lui (D5)
    log.jsonl         nhật ký: ai làm gì, lúc nào, lý do

Lệnh: `python -m improve --help`.
"""
import os

PKG_DIR = os.path.dirname(os.path.abspath(__file__))


def root(path=None):
    return os.path.abspath(path or os.environ.get("IMPROVE_ROOT") or PKG_DIR)
