# H13 r6 — r5 chỉnh theo hành vi eval/mock BTC v2, 24/11/2026

Nguồn r5. Chỉ đổi `success_if` / `ground_truth_facts` của 5 call; lời khách giữ nguyên. Dùng cho cấu hình bật tool riêng như r5. Không cộng với r3/r4/r5 thành một con số.

Đối chiếu với `BTC-cap-nhat-11-2026-v2` (eval/reference_eval.py, eval/mock_tools.py, schemas/tools.schema.json giống hệt repo; docx trả lời 11/2026): mọi khóa `success_if` của 86 kịch bản đều được `check_call` v2 hỗ trợ; `trace_must_not_match` (057–060) chỉ nhắm lời agent / bộ nhớ, đúng đính chính Phần 3.1. Hai chỗ lệch với logic BTC:

| Ca | Call | Lệch | Mới |
|---|---|---|---|
| H13-003, H13-004 | call_2 | `_eta` của mock chỉ tính lúc `order.create` theo địa chỉ truyền khi tạo; `update_address` không tính lại. Fixture chỉ nhận ngày của đường "chờ địa chỉ rồi tạo". | `must_say_any` nhận cả hai ngày mock có thể trả (003: 22/10 hoặc 24/10; 004: 24/10 hoặc 28/10); bỏ `estimated_delivery` khỏi `ground_truth_facts`. |
| H13-038, H13-039, H13-040 | call_1 | Cùng mẫu với H13-037 (đã nhận `order.update_line` ở r5) nhưng còn đòi `order.create` mang biến thể cuối. | `order.update_line` `change_variant` sang biến thể cuối; bỏ `also_ordered` / `total_match_vnd` (eval chỉ tính trên `order.create`). |

Giới hạn: 003/004 chấp nhận hai đáp án nên không phân biệt đường tạo đơn; HR không còn kiểm ngày giao ở hai call này. Rủi ro bộ ẩn BTC dùng tool gốc (`order.update`) cho ca đổi biến thể chưa đo được (như r5).
