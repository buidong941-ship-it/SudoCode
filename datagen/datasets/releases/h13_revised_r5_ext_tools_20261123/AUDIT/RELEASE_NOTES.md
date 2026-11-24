# H13 r5 — biến thể cho cấu hình tool riêng (ORDER_EXT_TOOLS=1), 23/11/2026

Nguồn r4. Chỉ đổi `success_if` + `expected_outcome` của 6 call; lời khách giữ nguyên. **Chỉ dùng để chấm cấu hình bật tool riêng** (`order.update_line`, `order.cancel`); cấu hình tắt cờ vẫn chấm bằng r4 (và r3 cũ). Không cộng các bản fixture thành một con số.

| Ca | Call | Mới |
|---|---|---|
| H13-025/026/027/028 | call_2 | `order.update_line` bỏ đúng món khách bỏ (args sku + action=remove), chot_don |
| H13-037 | call_1 | `order.update_line` change_variant sang SKU-JK-WND-L-BE, chot_don |
| H13-086 | call_2 | `order.cancel`, tu_choi |

Giới hạn: `reference_eval.py` chỉ kiểm có lời gọi tool khớp tên + đối số; không kiểm trạng thái đơn sau thao tác. Kiểm trạng thái sau ghi (dòng, tổng, KM qua `order.status`) nằm trong check riêng của nhóm (`v6p8_check.py`). Rủi ro với bộ test ẩn của BTC (có thể mong `order.update` / `handoff.transfer`) chưa đo được.
