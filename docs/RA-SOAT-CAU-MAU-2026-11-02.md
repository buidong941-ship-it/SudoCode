# Rà soát câu mẫu `render_offline` (D24 + D26, 02/11/2026)

Phạm vi: mọi goal trong `core/llm/generator.py::render_offline`. Câu mẫu được dùng ở 23–26% lượt Full của C5 (`coverage_template` + `safe_template`), nên câu mơ hồ ảnh hưởng trực tiếp tới khách và tới trace mà giám khảo đọc.

**Duyệt:** người dùng cho phép trợ lý tự duyệt bảng này (02/11, khuya). Trạng thái: **đã duyệt (trợ lý, theo ủy quyền 02/11)**.

**Tiêu chí "mơ hồ"** (PLAN-2026-11-02-TOI bước 3): (1) con số hiểu được hai nghĩa; (2) tình trạng KM/thời hạn không rõ; (3) không rõ ai làm gì; (4) câu hỏi/câu kể không khớp goal; (5) hứa điều tool không xác nhận.

**Ràng buộc:** mọi số vẫn lấy từ FACTS/tool; giữ ý goal; ngắn như nói điện thoại. Câu mới phải được luật trích claim đọc đúng field (kiểm bằng `tests/template_review_check.py`); câu nào luật đọc sai thì sửa câu, không sửa luật.

## Câu viết lại

| Goal | Câu cũ | Câu mới | Lý do |
|---|---|---|---|
| `quote` / `recommend` (có KM giảm giá) | "Dạ mẫu X giá 7.690.000đ, đang có ưu đãi Giảm 300.000đ … ạ." | "Dạ mẫu X giá niêm yết 7.990.000đ, áp dụng ưu đãi Giảm 300.000đ … nên còn 7.690.000đ ạ." | (1) Người nghe hiểu 7.690.000đ là giá gốc và tưởng còn được trừ 300.000đ (ca gốc của D24). Câu mới nói rõ giá niêm yết → ưu đãi → giá khách trả. Luật đọc `list_price_vnd` 7.990.000 và `price_vnd` 7.690.000 |
| `quote` / `recommend` (KM quà tặng, giá không đổi) | "…giá 5.200.000đ, đang có ưu đãi Tặng 1 màng lọc… ạ." | "…giá 5.200.000đ, kèm ưu đãi Tặng 1 màng lọc… ạ." | (1) "đang có ưu đãi" ngay sau giá dễ hiểu là giá còn được giảm; "kèm" cho thấy ưu đãi là quà, không đổi giá |
| `alternative_quote` | "Còn mẫu Y giá Z ạ." | "Ngoài ra bên em có mẫu Y, giá Z ạ." (có KM giảm giá thì dùng cùng mẫu câu niêm yết → còn như `quote`) | (1) "Còn … giá" dễ nghe thành "còn (lại) Z"; không nói giá có KM hay không |
| `opening_returning` | "…hôm 14/10 bên em có tư vấn anh mẫu X cho phòng 30m² giá 5.200.000đ." | "…hôm 14/10 bên em có tư vấn anh mẫu X cho phòng 30m², lúc đó em báo giá 5.200.000đ." | (1) Giá cũ nghe như giá hiện tại; câu mới nói rõ là giá đã báo hôm đó. Luật vẫn đọc `price_quoted_vnd` |
| `budget_fit` | "Dạ mức này nằm trong ngân sách 5.500.000đ của anh ạ." | "Dạ giá 5.200.000đ nằm trong ngân sách 5.500.000đ của anh ạ." | (1) "mức này" không rõ là giá nào; nêu rõ giá đang so. Luật đọc `price_vnd`, bỏ qua số ngân sách |
| `ask_size_for_price` | "Dạ giá và ưu đãi mẫu này khác nhau theo size, …" | "Dạ giá mẫu này có thể khác nhau theo size, …" | (5) Khẳng định "ưu đãi khác theo size" cả khi chỉ có chênh giá theo biến thể |
| `ask_phone` | "Dạ anh cho em xin số điện thoại và địa chỉ nhận hàng để shipper liên hệ giao ạ?" | Đã có địa chỉ: "Dạ anh cho em xin số điện thoại để shipper liên hệ khi giao hàng ạ?" Chưa có: giữ câu cũ | (4) Goal chỉ xin SĐT; hỏi lại địa chỉ đã biết là hỏi lặp (RQR) |
| `order_created` | "…dự kiến giao ngày {ngày} ạ." (in "None" khi tool không có ngày) | Chỉ nói ngày giao khi tool có ngày | (5) Không đọc "ngày None" |
| `order_exists` | "…dự kiến giao ngày 2026-10-18." (ISO, có thể "None") | "…dự kiến giao ngày 18/10 ạ." chỉ khi có ngày | (1) Ngày dạng ISO khó nghe; không đọc "None" |
| `order_status` | "Dạ đơn OD… đang shipping …" | "Dạ đơn OD… đang giao …" (shipping → đang giao, delivered → đã giao, created/queued → đang chờ xử lý, pickup_scheduled → đang chờ lấy hàng, updated → đã được cập nhật) | (1) Mã trạng thái tiếng Anh, "đang delivered" sai nghĩa |
| `exchange_offer` (hết hàng) | "Dạ size mới đang tạm hết, đổi size lần đầu bên em miễn phí ạ. Em làm thủ tục đổi cho anh nhé?" | "Dạ size mới hiện đang tạm hết hàng ạ. Anh muốn chọn mẫu khác cùng giá hay hoàn tiền ạ?" | (4)(5) Mời làm thủ tục đổi trong khi size mới hết hàng; câu mới theo chính sách đổi trả (hết hàng → chọn sản phẩm khác cùng giá hoặc hoàn tiền) |
| `exchange_offer` (còn hàng) | "…còn hàng, đổi size lần đầu bên em miễn phí ạ. Em làm thủ tục đổi cho anh nhé?" | "…còn hàng ạ, theo chính sách bên em đổi size lần đầu của mỗi đơn được miễn phí. Em làm thủ tục đổi cho anh nhé?" | (5) Lúc xem trước chưa biết đây có phải lần đổi đầu của đơn; câu mới nói đúng chính sách thay vì hứa ca này miễn phí |
| `order_updated` | "…bên em hoàn lại R, …, bên vận chuyển sẽ qua lấy hàng ạ." | "…bên em hoàn lại R trong 3-5 ngày làm việc, …" + "bên vận chuyển sẽ qua lấy hàng" chỉ khi tool trả `pickup_scheduled`; nói phí đổi khi tool có `fee_vnd` > 0 | (5) Hứa lấy hàng/không nói phí khi tool không xác nhận; thời hạn hoàn tiền lấy từ tool |
| `defer_ack` | "Dạ vâng, anh cứ trao đổi thêm, em gọi lại cho anh sau ạ." | "Dạ vâng, anh cứ trao đổi thêm ạ, khi nào cần anh liên hệ lại em nhé." | (3)(5) Khách nói "để anh bàn rồi gọi lại", câu cũ lại hứa shop gọi lại mà chưa có lịch hẹn (lịch hẹn thật dùng goal `callback_scheduled`) |
| `callback_scheduled` | "…lúc 15:00  ngày 16/10" (2 dấu cách khi thiếu thứ) | Bỏ phần trống | Lỗi trình bày, không đổi nội dung |

## Câu giữ nguyên

| Goal | Câu | Ghi chú |
|---|---|---|
| `greet`, `ask_identity`, `ask_product`, `ask_variant`, `ask_address`, `ask_need`, `ask_new_size`, `ask_repeat`, `ask_prior_contact` | (như cũ) | Câu hỏi đúng goal, không có số |
| `stale_promo` | "Dạ chương trình khuyến mãi hôm trước đã hết hạn rồi ạ, em báo lại giá hiện tại cho mình." | Rõ KM đã hết |
| `explain_price_change` | "Dạ mức giá anh nhắc là giá khi còn khuyến mãi, chương trình đó nay đã hết hạn nên giá hiện tại là X ạ." | Rõ giá nào là giá cũ, giá nào hiện tại |
| `gift_status` | (như cũ, 2 nhánh còn/hết) | Có ngày kết thúc từ tool |
| `out_of_stock`, `discontinued` | (như cũ) | Lấy từ tool |
| `cart_total` | "Dạ A X, B Y, tổng Z ạ." | Rõ từng món và tổng. Không thêm chữ "giá" trước từng món, vì sẽ sinh claim `price_vnd` cho sản phẩm phụ mà evaluator so với giá sản phẩm chính (lỗi chấm BTCL-021/022) |
| `cod_ok`, `cod_limit`, `confirm_order`, `confirm_new_price`, `confirm_old_address`, `confirm_delivery_address`, `address_updated` | (như cũ) | Không mơ hồ |
| `order_failed`, `order_not_found` | (như cũ) | Không hứa kết quả |
| `refuse_discount`, `refuse_other_customer`, `refuse_internal`, `no_competitor_comment`, `is_bot`, `data_deleted`, `no_info`, `handoff`, `policy_answer`, `closing`, mặc định "Dạ vâng ạ." | (như cũ) | Câu bắt buộc theo guardrail/goal; `policy_answer` lấy nguyên văn từ tài liệu |
| `exchange_window_passed` | "…đã quá thời hạn đổi trả 7 ngày ạ." | Đúng chính sách đổi trả (7 ngày) |
