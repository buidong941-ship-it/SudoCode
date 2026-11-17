"""Quyết định đổi/trả theo tài liệu BTC; ngày đơn chọn phiên bản, ngày nhận tính hạn."""
from datetime import date, timedelta
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1] / "policy"


def _days(filename):
    body = (ROOT / filename).read_text(encoding="utf-8")
    section = body.split("Thời hạn đổi trả", 1)[1]
    match = re.search(r"trong vòng\s+\*\*(\d+) ngày\*\*", section)
    if not match:
        raise ValueError(f"Không đọc được thời hạn đổi trả: {filename}")
    return int(match.group(1))


def _max_delivery_workdays():
    """VC-01: số ngày làm việc giao hàng LỚN NHẤT trong bảng chính sách vận chuyển (mọi khu vực)."""
    body = (ROOT / "chinh-sach-van-chuyen-thanh-toan.md").read_text(encoding="utf-8")
    table = body.split("[VC-01]", 1)[1].split("## ", 1)[0]
    nums = [int(x) for line in table.splitlines() if line.startswith("|") for pair in re.findall(r"(\d+)\s*[–-]\s*(\d+)", line) for x in pair]
    if not nums:
        raise ValueError("Không đọc được VC-01")
    return max(nums)


def _add_workdays(start, n):
    """Cộng n ngày làm việc (bỏ Chủ nhật và ngày nghỉ trong thong-bao-lich-nghi.md, như mock BTC)."""
    from harness.tools import mt
    d, k = date.fromisoformat(start), 0
    while k < n:
        d += timedelta(days=1)
        if d.weekday() != 6 and d.isoformat() not in mt.HOLIDAYS:
            k += 1
    return d


def exchange_window(order, today):
    """Trả phiên bản, số ngày và kết luận. Không đoán ngày nhận khi đơn không có dữ liệu đó."""
    created = order.get("created_on") or order.get("date")
    received = order.get("delivered_on") or order.get("received_on")
    old = bool(created and date.fromisoformat(created) < date(2026, 10, 1))
    days = _days("chinh-sach-doi-tra-v2026-06-HET-HIEU-LUC.md" if old else "chinh-sach-doi-tra.md")
    elapsed = (date.fromisoformat(today) - date.fromisoformat(received)).days if received else None
    eligible = None if elapsed is None else elapsed <= days
    basis = "received_on" if received else None
    if eligible is None and created and (date.fromisoformat(today) - date.fromisoformat(created)).days <= days:
        # ngày nhận luôn sau ngày đặt → tính từ ngày đặt mà còn hạn thì chắc chắn còn hạn; ngược lại vẫn là chưa xác định
        eligible, basis = True, "created_on_upper_bound"
    if eligible is None and created and (date.fromisoformat(today) - _add_workdays(created, _max_delivery_workdays())).days > days:
        # cụm 2 (10/11): ngay cả khi giao muộn nhất theo VC-01 thì hạn đổi trả cũng đã qua → chắc chắn quá hạn. Thay heuristic
        # "ngày đặt + 11" của đường rules; khoảng giữa hai mốc vẫn là CHƯA XÁC ĐỊNH (không ghi, trả lời theo chính sách).
        eligible, basis = False, "created_plus_max_delivery"
    # eligible=None = CHƯA XÁC ĐỊNH (thiếu ngày nhận): caller không được coi là đủ điều kiện ghi (FINAL 10/11, G2)
    return {"version": "2026-06" if old else "2026-10", "days": days,
            "received_on": received, "eligible": eligible, "basis": basis,
            "elapsed_days": elapsed}
