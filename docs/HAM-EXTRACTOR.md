# Bảng tra hàm của `harness/extractor.py`

> **Cập nhật 28/10/2026:** `agent_questions(text, known_values, use_classifier=False)` mặc định dùng luật, gồm dấu `?` và `REQUEST_RX`. `coverage` luôn dùng mặc định này. Chỉ `analyze_agent()` có thể gọi Jev có sẵn khi `QUESTION_CLF=1`, sau khi lời agent đã được chọn, để ghi `questions[]` vào trace. Không còn backend model local được huấn luyện.

[harness/extractor.py](../harness/extractor.py) là **bộ trích bằng luật**. Nó làm hai việc:

- trích slot từ **lời khách** (diện tích, ngân sách, size, địa chỉ…) để ghi bộ nhớ và cho planner dùng;
- trích `questions[]`, `claims[]`, `facts_used` từ **lời agent** để ghi trace.

Ba trường sau quyết định ba chỉ số chấm: `questions` → Repeat-Question Rate, `claims` → Hallucination Rate, `facts_used` → Context Carryover Rate. BTC chấm tay ngẫu nhiên 20 lượt của bộ trích, nên luật ở đây phải giải thích được và không được bỏ claim / câu hỏi để làm đẹp số.

Hai hàm cổng `customer_slots` và `analyze_agent` chọn chế độ theo `EXTRACTOR_BACKEND` (`rules` | `llm` | `hybrid`). Chế độ `llm` / `hybrid` chuyển sang [llm_extract.py](../harness/llm_extract.py) ([HAM-LLM-EXTRACT](HAM-LLM-EXTRACT.md)). `facts_used` luôn là code. Số dòng ứng với code ngày 17/10/2026.

**Ai dùng file này:** `harness/agent.py` (ba hàm cổng + `facts_used`), `harness/llm_extract.py` (`CONFIRM_RX`, `mentions_known`), `harness/tools.py` và `core/pii.py` (`ADDRESS_RX`), `asr/itn.py` (`BLOCKERS`, `customer_slots`), `tests/llm_extract_check.py`, `tests/pii_check.py`.

## 1. Hằng số

| Tên | Ý nghĩa |
|---|---|
| `KIDS_RX` [:18](../harness/extractor.py#L18) | Từ chỉ trẻ nhỏ trên câu đã bỏ dấu ("be", "con nho", "em be"…), loại "màu be". "bên em" bỏ dấu thành "ben em" nên không khớp |
| `BLOCKERS` [:21](../harness/extractor.py#L21) | Cặp (regex, nhãn) cho rào cản: hỏi chồng / hỏi vợ / hỏi người nhà / so sánh giá / cân nhắc |
| `ADDRESS_RX` [:24](../harness/extractor.py#L24) | Địa chỉ đứng sau cụm dẫn ("giao về", "địa chỉ là", "giờ chị ở", "chuyển nhà ra"…), dừng trước "nhé / ạ / thì / mất / bao lâu / hả…" |
| `SLOT_KW` [:83](../harness/extractor.py#L83) | Cặp (slot, regex từ khóa) để biết **câu hỏi** của agent hỏi về slot nào. Thứ tự quan trọng: slot đầu tiên khớp được chọn |
| `CONFIRM_RX` [:99](../harness/extractor.py#L99) | Dấu hiệu câu xác nhận: "đúng không", "phải không", "vẫn lấy / vẫn giữ", "như cũ", "xác nhận"… |
| `HUMAN_CLAIM_RX` [:186](../harness/extractor.py#L186) | Agent tự nhận là người thật ("em là người thật", "em là con người"); chặt hơn `guardrails.HUMAN_RX` |
| `AI_CLAIM_RX` [:187](../harness/extractor.py#L187) | Agent nói mình là AI / trợ lý ảo / robot / "không phải người thật" |

## 2. Hàm

### 2.1. Hàm cổng (chọn chế độ)

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `customer_slots(text, today, meta)` [:28](../harness/extractor.py#L28) | Slot khách nói trong câu này theo `EXTRACTOR_BACKEND`. Luôn chạy luật trước; `llm` / `hybrid` thì đưa kết quả luật sang bộ trích LLM để gộp hoặc dự phòng | câu khách đã chuẩn hóa; ngày cuộc gọi; `meta` (dict nhận thông tin chạy cho trace) | dict slot | `customer_slots_rules`, `llm_extract.customer_slots` |
| `analyze_agent(text, known_values, meta)` [:37](../harness/extractor.py#L37) | `questions[]` + `claims[]` của một lượt agent. Chế độ LLM dùng **một** lời gọi cho cả hai | lời agent; slot đã biết; `meta` | `(questions, claims)` | `agent_questions`, `agent_claims`, `llm_extract.agent` |

### 2.2. Lời khách → slot

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `customer_slots_rules(text, today)` [:46](../harness/extractor.py#L46) | Luật trích slot. Từng slot: `room_area_m2` (số + "m2 / mét vuông"); `has_children` (`KIDS_RX`, trừ "không có bé"); với mỗi số tiền, xét ngữ cảnh 30 ký tự trước và 15 ký tự sau: bên khác / Shopee → `competitor_price_vnd`, "báo / nói / thấy / còn" → `claimed_prices` (giá khách nói shop đã báo), "ngân sách / tầm / khoảng / tối đa" → `budget_vnd`; `size` ("size / cỡ / số" + giá trị); `color` (`find_color`, phải có chữ "màu"); `address` (`ADDRESS_RX`, bỏ qua "địa chỉ cũ / như cũ"); `payment` (COD / chuyển khoản); `blocker` (`BLOCKERS`); `callback_requested` (ngày giờ tương đối + "gọi lại / liên lạc / báo lại"); `self_name` ("chị là Dung", "chị Dung đây") | câu khách; ngày cuộc gọi | dict có thể chứa `room_area_m2`, `has_children`, `budget_vnd`, `competitor_price_vnd`, `claimed_prices` (list), `size`, `color`, `address`, `payment`, `blocker`, `callback_requested`, `self_name` | `fold`, `find_money`, `parse_relative_datetime`, `tools.find_color` |

### 2.3. Lời agent → `questions[]`

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `_sentences(text)` [:102](../harness/extractor.py#L102) | Tách câu theo dấu `.` `!` `?` | đoạn văn | list câu | |
| `agent_questions(text, known_values, use_classifier=False)` [:165](../harness/extractor.py#L165) | Tìm câu hỏi theo dấu `?` hoặc mẫu xin thông tin/yêu cầu `REQUEST_RX`; khi bật tùy chọn chỉ cho phép ở bước đo metric, Jev có sẵn bổ sung câu luật bỏ sót. Gán slot bằng `SLOT_KW`, loại `confirm`/`open` theo giá trị đã biết và `CONFIRM_RX` | lời agent; slot đã biết; cờ tùy chọn | list `{slot, type, text}` | `_sentences`, `fold`, `mentions_known`, `tools.find_products`, `question_prob` |
| `mentions_known(s, slot, known_values)` [:122](../harness/extractor.py#L122) | Câu hỏi có nhắc đúng giá trị đã biết của slot không ("vẫn phòng 25m² ạ?"). Riêng `product_advised`: giá trị nhớ là mã SKU, câu nhắc bằng tên, nên so qua `find_products` | câu; slot; slot đã biết | `True` / `False` | `tools.find_products`, `tools.mt._parent` |

### 2.4. Lời agent → `claims[]`

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `agent_claims(text, quote, focus_sku)` [:133](../harness/extractor.py#L133) | Tìm khẳng định kiểm chứng được, từng câu một. **Giá:** số tiền có ngữ cảnh "giá / còn / chỉ / tổng / là / bán / niêm yết"; bỏ số bị phủ định ("không phải 1.161.000đ"), số tiền giảm / phí ship / phụ thu / chênh lệch / tiền hoàn / ngân sách. Số sau "còn" là `price_vnd`; số đứng trước cấu trúc "giảm … còn" hoặc có "niêm yết" là `list_price_vnd`; câu nhắc giá trong quá khứ ("hôm trước", "là giá khi…") là `price_quoted_vnd`. **KM:** hết hạn / "chưa có chương trình" → `promo_active = false`; "đang có / tặng kèm / ưu đãi" → `true`; miễn phí giao hàng không tính. **Tồn kho:** `in_stock`. **Giao hàng:** "giao … N(-M) ngày" → `delivery_days` (lấy số lớn). **Bảo hành:** "bảo hành N tháng / năm" → `warranty_months`. **Đổi trả:** "đổi trả trong N ngày" → `return_days`, bỏ câu về hàng lỗi / bảo hành. **Là người hay AI:** `is_human` | lời agent; `quote`, `focus_sku` (không dùng) | list `{field, value, text}` | `_sentences`, `fold`, `find_money` |

### 2.5. `facts_used` (CCR)

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `facts_used(text, tool_args_list, carried)` [:192](../harness/extractor.py#L192) | Fact nào của **phiên trước** được dùng lại ở lượt này. Với mỗi slot trong `carried`: số nguyên → có trong số tiền của câu, hoặc "N m²", hoặc trong tham số tool; `has_children` → câu nhắc "bé / trẻ nhỏ"; `blocker` → câu nhắc "anh nhà / người nhà / trao đổi / cân nhắc…"; `product_advised` → mã có trong tham số tool hoặc hai từ cuối tên sản phẩm có trong câu; còn lại → giá trị có trong câu hoặc tham số tool | lời agent; tham số các tool đã gọi; `carried` | list tên slot | `fold`, `find_money`, `tools.product_name` |

## 3. Ghi chú khi đọc code

- **Luật nhận dấu `?` và mẫu `REQUEST_RX`.** Các câu xin thông tin không khớp mẫu này có thể được Jev/LLM bổ sung trong `questions[]` sau khi agent đã trả lời. Chỉ dùng nhãn người rà để đánh giá độ đúng phép trích; không fit model.
- **`claimed_prices` không vào bộ nhớ.** `agent._plan` và `_remember` bỏ trường này; nó chỉ dùng để chặn đọc lại giá cũ (`forbidden_money`) và để chọn goal `explain_price_change`.
- **Bất kỳ "bảo hành N tháng" nào cũng thành claim `warranty_months`,** kể cả câu nói về sản phẩm khác hoặc gói mở rộng (GEN-T23, GEN-T26 ở [SO-SANH-2026-10-15.md](SO-SANH-2026-10-15.md) mục 7.1).
- **Script BTC chỉ tính claim có `field` trùng khóa trong `ground_truth_facts`** của kịch bản; tên field ở đây phải khớp cách BTC đặt tên (CAU-HOI-BTC A5).
