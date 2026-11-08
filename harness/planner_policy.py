"""Quyết định đổi/trả theo tài liệu BTC; ngày đơn chọn phiên bản, ngày nhận tính hạn."""
from datetime import date
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


def exchange_window(order, today):
    """Trả phiên bản, số ngày và kết luận. Không đoán ngày nhận khi đơn không có dữ liệu đó."""
    created = order.get("created_on") or order.get("date")
    received = order.get("delivered_on") or order.get("received_on")
    old = bool(created and date.fromisoformat(created) < date(2026, 10, 1))
    days = _days("chinh-sach-doi-tra-v2026-06-HET-HIEU-LUC.md" if old else "chinh-sach-doi-tra.md")
    elapsed = (date.fromisoformat(today) - date.fromisoformat(received)).days if received else None
    return {"version": "2026-06" if old else "2026-10", "days": days,
            "received_on": received, "eligible": None if elapsed is None else elapsed <= days,
            "elapsed_days": elapsed}
