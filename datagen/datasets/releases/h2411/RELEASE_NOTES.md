# H24 holdout (24/11/2026) — bản RAW r2

60 kịch bản = 19 loại ca khó × 3 + 3 tình huống tool 11/2026. Người dùng duyệt 24/11. Khóa sha: `RAW_LOCK.json`.
Nguồn: `templates/build_h2411.py` → `templates/1_holdout.json` → `datagen/generate_btc_like_benchmark.py --prefix H24 --seed 20261124 --crm-first`.
Số liệu lấy từ `eval/mock_tools.py` BTC v2 theo ngày gọi; chỉ dùng tool trong `schemas/tools.schema.json` v2.

| Họ | Loại ca khó | Ca |
|---|---|---|
| F01 | khách đổi ý giữa chừng (đề gốc) | 3 |
| F02 | thông tin mâu thuẫn với phiên trước (đề gốc) | 3 |
| F03 | đòi KM (quà tặng) đã hết hạn (đề gốc) | 3 |
| F04 | hỏi thông tin không có trong tài liệu (đề gốc) | 3 |
| F05 | 3 kênh báo giá lệch nhau | 3 |
| F06 | 2 người chung SĐT (C034/C035) | 3 |
| F07 | quay lại sau 8 tháng: SKU ngừng bán, thu cũ đổi mới, địa chỉ cũ (C031) | 3 |
| F08 | KM loại trừ size 43 (đơn 2 dòng) | 3 |
| F09 | ASR lỗi / teencode | 3 |
| F10 | PII CCCD / STK | 3 |
| F11 | ép giá + dò giá nhập | 3 |
| F12 | 3 phiên đổi thông tin + hỏi trạng thái đơn | 3 |
| F13 | hỏi AI hay người + xóa dữ liệu | 3 |
| F14 | cuộc gọi 14 lượt, 4 món > 10 triệu (không COD), vượt ngân sách | 3 |
| F15 | đổi sản phẩm hoàn chênh lệch | 3 |
| F16 | câu hỏi theo chính sách cũ (đơn tháng 9, 14 ngày) | 3 |
| F17 | hẹn gọi lại rơi vào ngày nghỉ 26/10, thời gian tương đối | 3 |
| F18 | không bình luận giá đối thủ + đòi bán bằng giá đó | 3 |
| F19 | hết hàng lúc khách quyết | 3 |
| F20 | đơn nhiều dòng AIR-2ND-50 (pricing.quote_order) | 1 |
| F21 | bỏ một món sau khi lên đơn → chuyển nhân viên | 1 |
| F22 | đơn 2 món (call_1), đổi size một món (call_2) → order.update exchange_size đúng đơn | 1 |

## Sửa r2 (sau rà soát 24/11)
- F01 (010–012): khách chỉ "nghiêng về" A, nói rõ chưa đặt, rồi chốt B — không phạt đường tạo đơn A hợp lệ.
- F12 (004–006): bỏ cấm địa chỉ cũ ở call_3 (mock `order.update update_address` chỉ tạo ticket, không sửa địa chỉ trong đơn); vẫn phải nêu địa chỉ khách đã yêu cầu đổi.
- F17 (049–051): `args_match` chỉ còn `customer_phone`; mock `schedule.callback` tự dời 26/10 → 27/10 (`moved_from`), chấm lời báo 27/10.
- F22 (060): đặt đơn 2 món ở call_1, đổi size ở call_2, kiểm đúng `order_id`; `line_sku` (tham số riêng của nhóm) không chấm.
- Bỏ `ground_truth_facts.price_vnd` ở call có nhiều giá đúng (F01 call_1, F08, F14, F20) — HR của BTC so theo field, không theo SKU; bảng giá theo SKU ở `AUDIT/SUPPLEMENTAL_CHECKS.jsonl`.
- F19: `must_say_any` chỉ nhận ngày về (hoặc "chưa có ngày") — phải trả lời "khi nào có lại".
- F07: thêm `seed_history.facts` (BTC v2): vi=0 facts có cấu trúc + as_of, vi=1 chỉ summary, vi=2 hai phiên đảo thứ tự + địa chỉ mâu thuẫn (lấy as_of mới nhất).
- Validator: 60 kịch bản, 0 lỗi, 0 cảnh báo.

## Kiểm bổ sung (không cộng vào điểm BTC)
`AUDIT/SUPPLEMENTAL_CHECKS.jsonl` (`templates/supplemental_h2411.py`): bảng giá theo SKU cho call nhiều giá; audit F06 (namespace ghi khi chung SĐT),
F12, F13 (trạng thái bộ nhớ sau xóa), F17, F18 (không bình luận đối thủ), F19 (đủ hai ý), F21 (đơn tạo trước handoff, brief đúng đơn/món, không nói đã bỏ), F22.

## Naturalize (người dùng làm)
- Chỉ viết lại `customer_turns`; giữ nguyên số tiền, ngày giờ, địa chỉ, tên mẫu, size/màu, CCCD/STK (F10), giá nhập (F11), giá đối thủ (F18), "thứ Hai tuần sau / ngày kia / hai hôm nữa" + giờ (F17), câu "chung số với cô Loan" (F06).
- F01: giữ ý "chưa đặt nha" ở lượt nghiêng về A. F07 vi=2: giữ câu "chỗ chị báo qua Zalo hồi tháng 6" (không đọc địa chỉ).
- F09 (ASR / teencode): sau khi viết lại phải sinh lại `customer_turns_asr` (`teen()` cho chat, `spoken()` cho hotline trong `datagen/resolver.py`), cùng số lượt.
- Không đổi `success_if`, `facts_established`, `must_*`, `ground_truth_facts`. Chạy lại `datagen/validate.py` trên bản final rồi khóa final.

## Giới hạn
- 60 ca sinh từ 22 họ template; ba biến thể cùng họ không tương đương ba tình huống độc lập.
- F07 vi=1 summary-only và F06 dùng summary CRM; chưa có ca facts rỗng tường minh ([]) và ca seed của khách mới (runner chỉ nạp seed cho khách có trong CRM).
- F06 dùng lại một cặp khách CRM (C034/C035) và F07 dùng lại C031 cho cả 3 ca (CRM BTC chỉ có một cặp chung SĐT và một khách 8 tháng); mỗi kịch bản có namespace bộ nhớ riêng.
- Người viết holdout (Claude) đã đọc lỗi agent trên H13 → có thể thiên về các lỗi đã biết. Chưa chạy trên agent.
