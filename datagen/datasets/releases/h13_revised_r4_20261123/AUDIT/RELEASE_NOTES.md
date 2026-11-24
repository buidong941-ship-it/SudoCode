# H13 revised r4 (23/11/2026)

Nguồn: r3 `h13_revised_20261122_utf8`. Chỉ đổi `expected_outcome` + `success_if` của 5 call; lời khách giữ nguyên. Bản r3 giữ nguyên để so điểm cũ.

| Ca | Call | Cũ | Mới |
|---|---|---|---|
| H13-025/026/027/028 | call_2 | chot_don; order.create một món, tổng một món | chuyen_may; handoff.transfer, brief có escalation_reason_detail + next_action |
| H13-037 | call_1 | chot_don; order.create size L | như trên |

**Lý do:** mẫu BTC (`test_set/public_sample/SAMPLE-01/02/04/05`) tạo đơn ngay khi khách nói "lên đơn", không đợi khách nói thanh toán. Theo chuẩn đó agent tạo đơn nhiều món ở lượt chốt đầu là đúng; lời bỏ/đổi một món đến sau khi đơn đã tạo. `order.update` của mock BTC không sửa riêng một dòng (chỉ tạo ticket) và không có hủy, nên với tool chuẩn hành vi đúng là chuyển nhân viên kèm brief. `reference_eval.py` tính tổng từ mọi `order.create` nên fixture cũ không đạt được bằng hành vi đúng.

**Giới hạn:** bộ chấm BTC chỉ kiểm có handoff với brief đủ trường; không kiểm đơn đầu đúng món, brief nêu đúng đơn/món, câu trả lời không nói "đã sửa". Các điều đó nằm ở `AUDIT/SUPPLEMENTAL_CHECKS.jsonl` (kiểm riêng của nhóm, không cộng vào điểm BTC). Không thêm `must_say_any` để tránh chấm theo cụm chữ. H13 đã lộ; r4 vẫn là bộ chẩn đoán.

Biến thể đòi `order.update_line` (bước D) chưa soạn trong r4.
