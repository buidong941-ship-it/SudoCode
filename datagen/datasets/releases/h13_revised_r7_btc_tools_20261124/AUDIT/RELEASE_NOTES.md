# H13 r7 — chỉ tool BTC (24/11/2026)

Nguồn r4 (đáp án đã theo tool chuẩn: 025–028 bỏ món và 037 → chuyển người; 086 hủy đơn → chuyển người như r3). Người dùng duyệt 24/11:
BTC chờ chuyển người cho bỏ món / hủy đơn; đổi biến thể dùng `order.update` (tool BTC) với tham số riêng tùy chọn `line_sku`.

| Ca | Call | Mới | Căn cứ |
|---|---|---|---|
| H13-003, H13-004 | call_2 | lấy từ r6: nhận cả hai ngày giao mock có thể trả | `mock_tools._eta` chỉ tính lúc `order.create` |
| H13-037, 038, 039, 040 | call_1 | `order.update` `action=exchange_size`, `new_variant_sku` = biến thể cuối (chot_don) | `tools.schema.json` v2: order.update đổi size; `args_match` expected ⊆ actual |

Mọi `success_if.tool_called` chỉ dùng tool trong schema v2 của BTC. r5/r6 (tool riêng) không còn là số chính.
Giới hạn: 037 ở r4 là chuyển người, nay đổi thành order.update theo hướng gộp đã duyệt — BTC có thể chấm khác (chưa có mẫu BTC cho đổi size trong đơn nhiều món vừa tạo). H13 đã lộ: bộ chẩn đoán, không phải holdout.
