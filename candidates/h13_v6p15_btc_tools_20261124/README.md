# v6p15 — chỉ tool BTC (24/11/2026)

Nền: `candidates/h13_v6p14_round2b_20261124` (gồm S3 bản sửa sau lượt 1, manifest 3f9f57cf). Người dùng duyệt 24/11: BTC chờ chuyển người cho bỏ món /
hủy đơn; gộp đổi biến thể vào `order.update` với tham số tùy chọn `line_sku`; bỏ `order.update_line` trên đường chạy chính. Không commit.

## Thay đổi
- `harness/order_ext.order_update` + cờ `LINE_SKU_UPDATE`: không `line_sku` → gọi đúng `mock_tools.order_update` (cùng kết quả mock);
  có `line_sku` → ticket đổi size / sản phẩm cho đúng dòng (cùng kiểm tra, cùng dạng ticket, phí DT-03 như mock; giá gốc lấy từ dòng được chọn).
  Đăng ký ở ToolBox (đường trực tiếp) và MCP `commerce_server` (schema BTC + `line_sku`).
- `plan_primitives._amend_via_order_update`: đổi biến thể một dòng của đơn vừa tạo → `order.update` exchange_size / exchange_product + `line_sku`.
- Cấu hình chạy: `ORDER_EXT_TOOLS=0` (không `order.update_line` / `order.cancel` → bỏ món, hủy đơn đi đường chuyển nhân viên kèm brief),
  `DONE_NO_HANDOFF=0` (tắt G7), `LINE_SKU_UPDATE=1`; các cờ 2A/2B giữ như v6p14.

## Kiểm tra
`v6p15_check.py` (tool trực tiếp + MCP, args_match kiểu BTC, luồng agent) + mọi bộ cũ; chấm r7 (`datagen/datasets/releases/h13_revised_r7_btc_tools_20261124`).
