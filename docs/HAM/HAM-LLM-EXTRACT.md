# Bảng tra hàm của `harness/llm_extract.py`

[harness/llm_extract.py](../harness/llm_extract.py) là **bộ trích bằng LLM**, dùng khi `EXTRACTOR_BACKEND=llm` hoặc `hybrid`. Nguyên tắc chia việc:

- **LLM phân loại:** thông tin thuộc slot nào, câu nào là câu hỏi, câu nào là claim. Định nghĩa slot / field cố định trong file này, đầu ra ép theo JSON Schema nên LLM không trả được nhãn ngoài danh sách.
- **Code đọc giá trị và kiểm:** mỗi kết quả kèm `span` (đoạn chữ nguyên văn). Code bỏ `span` không có trong câu (LLM bịa), rồi đọc giá trị từ `span` bằng đúng hàm của bộ luật (`find_money`, `parse_relative_datetime`, `find_color`…).

Nhiệt độ 0 và cache theo mã băm request (`core/llm/cache.py`), nên chạy lại ra y hệt. LLM lỗi hoặc quá `EXTRACTOR_TIMEOUT_S` thì dùng kết quả luật và ghi lý do vào `meta["fallback"]`. LLM chọn bằng `EXTRACTOR_LLM` (`qwen` | `deepseek`); với DeepSeek, SĐT / địa chỉ được che trước khi gửi. Số dòng ứng với code ngày 17/10/2026.

**Ai dùng file này:** chỉ [extractor.py](../harness/extractor.py) (hai hàm cổng `customer_slots`, `analyze_agent`) và `tests/llm_extract_check.py`.

## 1. Hằng số (đưa nguyên văn vào prompt)

| Tên | Ý nghĩa |
|---|---|
| `CUSTOMER_SLOTS` [:30](../harness/llm_extract.py#L30) | 12 slot của lời khách kèm định nghĩa: `room_area_m2`, `has_children`, `budget_vnd`, `competitor_price_vnd`, `claimed_price_vnd`, `size`, `color`, `address`, `payment`, `blocker`, `callback_requested`, `self_name` |
| `LABELS` [:44](../harness/llm_extract.py#L44) | Nhãn cho slot dạng phân loại: `co` / `khong` (trẻ nhỏ), `COD` / `bank` (thanh toán), 5 nhãn rào cản |
| `QUESTION_SLOTS` [:46](../harness/llm_extract.py#L46) | 15 slot cho câu hỏi của agent (cùng tên với `extractor.SLOT_KW`, thêm `other`) |
| `CLAIM_FIELDS` [:53](../harness/llm_extract.py#L53) | 9 field claim: `price_vnd`, `list_price_vnd`, `price_quoted_vnd`, `promo_active`, `in_stock`, `delivery_days`, `warranty_months`, `return_days`, `is_human` |
| `NOT_CLAIMS` [:64](../harness/llm_extract.py#L64) | Danh sách điều **không** phải claim (số tiền bị bác bỏ, ngân sách, phí ship, phụ thu, tiền giảm / hoàn, câu hỏi…) |
| `CUSTOMER_SCHEMA` [:67](../harness/llm_extract.py#L67) | JSON Schema đầu ra lời khách: `{slots: [{slot, span, label}]}` |
| `AGENT_SCHEMA` [:71](../harness/llm_extract.py#L71) | JSON Schema đầu ra lời agent: `{questions: [{i, slot, type}], claims: [{i, field, span, polarity}]}`; `i` là số thứ tự câu |

## 2. Hàm

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `_defs(d)` [:83](../harness/llm_extract.py#L83) | Biến dict định nghĩa thành danh sách gạch đầu dòng cho prompt | dict | chuỗi | |
| `_call(prompt, schema, texts, meta)` [:88](../harness/llm_extract.py#L88) | Gọi LLM trả JSON. Nếu là API ngoài (DeepSeek) thì che PII trong `texts` trước khi chèn vào prompt. Cộng thời gian vào `meta["ms"]`, ghi `meta["backend"]` | prompt; schema; các chuỗi người dùng trong prompt; `meta` | `(dict, redactor hoặc None)` | `core.llm.deepseek.LLM.json`, `core.pii.Redactor` |
| `_span_ok(span, text)` [:107](../harness/llm_extract.py#L107) | `span` có thật sự nằm trong câu không (so dạng bỏ dấu) | đoạn trích; câu | `True` / `False` | `fold` |
| `_slot_value(slot, span, label, text, today)` [:112](../harness/llm_extract.py#L112) | Đọc giá trị từ `span` bằng code: diện tích → số; trẻ nhỏ → `True` khi `label = co` (giống luật, "không có bé" không ghi); tiền → `find_money`; size → regex; màu → `find_color`; địa chỉ → chuỗi ≥ 6 ký tự; thanh toán / rào cản → `label` hợp lệ; hẹn gọi lại → `parse_relative_datetime`; tên → chữ viết hoa cuối, bỏ "chị / anh / em…" | slot; đoạn trích; nhãn; cả câu; ngày | giá trị, hoặc `None` (loại) | `find_money`, `parse_relative_datetime`, `tools.find_color`, `fold` |
| `customer_slots(text, today, rules, mode, meta)` [:144](../harness/llm_extract.py#L144) | Trích slot lời khách bằng LLM. Lỗi → trả kết quả luật. Kết quả có `span` bịa bị loại và đếm vào `meta["dropped_spans"]`. **`llm`:** chỉ dùng kết quả LLM. **`hybrid`:** luật thắng khi cùng slot, LLM bổ sung slot luật bỏ sót; `claimed_prices` là hợp hai bên | câu khách; ngày; kết quả luật; chế độ; `meta` | dict slot | `_call`, `_span_ok`, `_slot_value`, `_defs` |
| `_sentences(text)` [:181](../harness/llm_extract.py#L181) | Tách câu (bản sao của `extractor._sentences`) | đoạn văn | list câu | |
| `_claim_value(field, span, polarity)` [:185](../harness/llm_extract.py#L185) | Đọc giá trị claim: giá → `find_money`; `promo_active` / `in_stock` / `is_human` → `polarity`; `delivery_days` → số lớn nhất ("2-3 ngày" → 3); `warranty_months` → số × 12 nếu là "năm"; còn lại → số đầu tiên | field; đoạn trích; polarity | giá trị, hoặc `None` | `find_money`, `fold` |
| `agent(text, known_values, q_rules, c_rules, mode, meta)` [:201](../harness/llm_extract.py#L201) | Phân tích lời agent bằng **một** lời gọi: câu hỏi (kể cả câu không có "?") và claim theo số thứ tự câu. Loại phần tử có chỉ số câu sai, slot / field ngoài danh sách, hoặc `span` bịa (trừ field có `polarity`). Câu hỏi nhắc giá trị đã biết hoặc khớp `CONFIRM_RX` luôn là `confirm`. **`llm`:** chỉ kết quả LLM. **`hybrid`:** câu hỏi theo LLM với câu nó trả, câu còn lại giữ của luật; claims là **hợp** luật và LLM, khử trùng theo `(field, value, câu)`, nên không bao giờ mất claim luật đã bắt | lời agent; slot đã biết; câu hỏi và claim của luật; chế độ; `meta` | `(questions, claims)` | `_call`, `_span_ok`, `_claim_value`, `_sentences`, `extractor.CONFIRM_RX`, `extractor.mentions_known` |

## 3. Ghi chú khi đọc code

- **`hybrid` không bao giờ bỏ claim mà luật đã bắt,** vì bỏ sót claim làm HR thấp giả và bị trừ khi BTC chấm tay bộ trích.
- **Field có `polarity`** (`promo_active`, `in_stock`, `is_human`) **không bị kiểm `span`,** vì giá trị nằm ở `polarity` chứ không ở đoạn chữ.
- **Chưa đo trên model thật.** Cấu hình C (router Qwen + bộ trích `hybrid`) phải chạy lại sau bản sửa JSON ép schema ([SO-SANH-2026-10-15.md](SO-SANH-2026-10-15.md) mục 4). Kiểm thử không cần GPU: `python tests/llm_extract_check.py`.
