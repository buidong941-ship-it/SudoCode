## 1. Vì sao `.env` / `.env.example` không có đủ biến, và model được nạp từ đâu

Tôi nói "`.env` chỉ có 10/30 biến" thì cần nói rõ hơn:
- `.env.example` có **24/30 biến**, nhưng phần lớn là dòng ghi chú (`# QWEN_MODEL=…`), để làm mẫu chứ không bắt buộc. 6 biến thêm sau ngày 14/10 (`REPLY_STYLE`, `LLM_TIMEOUT_S`…) chưa được ghi vào.
- `.env` của bạn tạo ngày 01/10, chỉ chứa khóa API và vài giá trị DeepSeek / Jev. Hệ thống không cần `.env` đủ biến, vì biến nào thiếu thì dùng mặc định trong code.

**Model của các lần test trên Kaggle không lấy từ `.env`.** `.env` còn bị loại khỏi gói đẩy lên Kaggle, để khóa không lọt ra ngoài; khóa đi qua Kaggle Secrets. Model được nạp theo thứ tự ưu tiên *biến môi trường > profile > `.env` > mặc định trong code*:

| Lần chạy | Model ghi trong `config.json` | Nguồn |
|---|---|---|
| `eval-b` 8B-AWQ | `Qwen/Qwen3-8B-AWQ` | `profiles/kaggle.env` (`QWEN_MODEL=Qwen/Qwen3-8B-AWQ`) |
| `eval-b-4b` | `Qwen/Qwen3-4B` | biến thể trong job Kaggle (`--variant 4b:QWEN_MODEL=Qwen/Qwen3-4B`), là biến môi trường nên thắng profile |
| `eval-b-4b-short-w1` | `Qwen/Qwen3-4B`, `reply_style=short`, `llm_max_tokens=160` | như trên |

Mỗi lần chạy, `run_eval.py` ghi cấu hình **thực tế** đã dùng vào `<out>.config.json` (`settings.describe()`). Đó là nơi để kiểm lần chạy nào dùng model nào.

## 2. Các slot nằm ở đâu, gồm những gì

Đúng, cả ba trường đều dùng tên slot cố định, nhưng **không có một danh sách chung**. Mỗi phía có danh sách riêng:

| Dùng cho | Danh sách | File |
|---|---|---|
| Slot lời khách (ghi bộ nhớ) | `room_area_m2`, `has_children`, `budget_vnd`, `competitor_price_vnd`, `claimed_prices`, `size`, `color`, `address`, `payment`, `blocker`, `callback_requested`, `self_name` | luật: [extractor.customer_slots_rules](harness/extractor.py#L46); LLM: `CUSTOMER_SLOTS` trong [llm_extract.py](harness/llm_extract.py) |
| Slot do agent tự ghi vào bộ nhớ | `product_advised`, `price_quoted_vnd`, `promo_code`, `promo_expiry`, `product_chosen`, `order_id`, `variant_sku`, `estimated_delivery` | [agent._remember](harness/agent.py) |
| Slot của câu hỏi (RQR) | `room_area_m2`, `budget_vnd`, `has_children`, `size`, `color`, `address`, `payment`, `customer_name`, `phone`, `blocker`, `callback_time`, `product_advised`, `order_id`, `confirm_order`, `other` | luật: `SLOT_KW` trong [extractor.py](harness/extractor.py); LLM: `QUESTION_SLOTS` |
| Field của claim (HR) | `price_vnd`, `list_price_vnd`, `price_quoted_vnd`, `promo_active`, `in_stock`, `delivery_days`, `warranty_months`, `return_days`, `is_human` | [extractor.agent_claims](harness/extractor.py); LLM: `CLAIM_FIELDS` |
| `facts_used` (CCR) | Mọi slot có trong bộ nhớ của khách (hai dòng đầu bảng) | [extractor.facts_used](harness/extractor.py) |

**Phía đáp án** dùng tên do người viết kịch bản đặt. Quy ước định dạng ở `schemas/scenario_format.md`, nhưng không có danh sách tên chuẩn (đã hỏi BTC ở CAU-HOI-BTC A5). So hai bên thì có chỗ **không khớp**:

| Đáp án đòi | Phía hệ thống | Hậu quả |
|---|---|---|
| `must_carry_over: objection` (BTC sample và kịch bản nhóm); `baby_age` (nhóm) | Không bao giờ ghi `objection` / `baby_age` vào bộ nhớ | Không bao giờ được tính đã mang sang, nên CCR bị chặn trần |
| `must_not_ask: baby_age, household_size, owned_product` (kịch bản nhóm) | `SLOT_KW` không có ba slot này | Agent hỏi "bé mấy tháng" bị xếp vào `other`, không bao giờ bị tính hỏi thừa. RQR thấp giả: đúng loại lỗi BTC chấm tay |
| `ground_truth_facts: promo_GIFT-FILTER_active`, `restock_date` (BTC) | Claim chỉ có `promo_active`, `restock` không phải claim | Claim về KM cụ thể và ngày về hàng không bao giờ được chấm |
| `ground_truth_facts: refund_vnd, total_vnd, order_id, estimated_delivery, freeship…` (kịch bản nhóm) | Không có field claim tương ứng | Những khẳng định này không được tính đúng hay sai |

Nếu bạn muốn, tôi có thể bổ sung các slot còn thiếu (`objection`, `baby_age`, `household_size`, `owned_product`, `restock_date`…) vào bộ trích và bộ nhớ. Việc này **đổi logic**, nên tôi chờ bạn quyết.

## 3. "Dict sau `claims` lặp lại giá trị của claims"

Trường đứng ngay sau `claims` là **`tool_calls`**: danh sách các tool đã gọi trong lượt, mỗi phần tử có `name`, `args`, `result`. Ví dụ GEN-T01-01, `call_2`, lượt 3:

```
claims:      [{"field": "price_vnd", "value": 7690000, "text": "…tổng tiền 7.690.000đ…"}]
tool_calls:  pricing.get_quote → result {"list_price_vnd": 7990000, "final_price_vnd": 7690000, "applied_promos": [... "AIR-OCT" ...]}
             order.create      → result {"order_id": "OD600001", "total_vnd": 7690000, "estimated_delivery": "2026-10-27"}
memory_writes: [{"key": "order_id", "value": "OD600001", ...}, {"key": "estimated_delivery", ...}, ...]
```

Con số lặp lại là **có chủ ý**:
- `tool_calls[].result` là **nguồn** của con số: tool trả 7.690.000;
- `claims` là **điều agent nói ra**: agent nói 7.690.000;
- `memory_writes` (sau `latency`) là **điều được ghi nhớ**.

Guardrail chỉ cho agent nói con số có trong kết quả tool, nên hai bên trùng nhau là dấu hiệu đúng. Nếu ý bạn là một trường khác, ví dụ `call_brief` ở lượt 1 cũng chứa giá đã báo, bạn chỉ cho tôi tên khóa nhé.

## 4. Agent biết fact nào cần mang sang bằng cách nào

Agent **không biết đáp án** `must_carry_over`, vì loader đã ẩn nó. Việc mang ngữ cảnh sang hiện do **thiết kế harness** quyết định, không do cơ chế cải tiến:

1. **Ghi gì vào bộ nhớ:** `_remember` và chính sách TTL. Không ghi thì không thể mang sang; đây là lý do `objection` luôn trượt.
2. **Nạp gì đầu cuộc:** `_bind` / `_build_brief` nạp mọi fact còn hạn vào `known` và `carried`.
3. **Planner dùng fact làm tham số tool:** sản phẩm đã tư vấn thành `focus`, rồi thành `pricing.get_quote` / `order.create(sku, price)`.
4. **Generator được đưa fact vào prompt:** goal `opening_returning` kèm `facts.brief` (sản phẩm, giá, ngày gọi trước, rào cản), cùng toàn bộ `KNOWN`. Nói ra fact nào là do LLM chọn.

GEN-T01-01 trượt `room_area_m2` và `blocker` vì:
- `facts.brief` không có diện tích phòng (câu mẫu trong đề có "cho phòng 25m²");
- `opening_returning` không có `GOAL_NOTES`, nên Qwen câu ngắn bỏ qua câu hỏi về rào cản.

**Cách sửa có hai tầng:**
- **Thiết kế (code), nên làm trước:** đưa diện tích vào `facts.brief`; thêm `GOAL_NOTES` cho `opening_returning` (nhắc sản phẩm, giá, nhu cầu chính, hỏi tiếp rào cản); guardrail kiểm câu mở đầu có đủ ý. Phải giữ ngắn gọn, vì đề trừ điểm "đọc vẹt" mọi thông tin cũ trong câu chào.
- **Cơ chế cải tiến (C.5), dùng để chứng minh bằng số:** vòng 0 thấy cuộc 2 hay bỏ sót rào cản → đề xuất luật hoặc ví dụ mẫu (Exemplar Bank: lấy câu mở đầu của các cuộc chốt thành công làm few-shot) → **người duyệt** → chạy vòng 1 trên cùng bộ test → CCR tăng. Chỉ được học từ bộ dev, không học từ test.

## 5. Ý tưởng: dataset thật + LLM sinh tình huống tương tự

Hướng đi đúng, vì nó giải quyết đúng hai hạn chế đã ghi ở [DATASET.md](docs/DATASET.md): lời khách còn gần câu mẫu, và chưa đa dạng cách nói. Nhưng cần đặt bốn ràng buộc:

1. **Pháp lý (điều kiện loại):** đề cấm dùng ghi âm khách thật chưa ẩn danh và chưa có đồng ý. Chỉ dùng dataset công khai, đã ẩn danh, giấy phép cho phép dùng; ghi rõ nguồn trong báo cáo.
2. **Dữ kiện phải lấy từ catalog của BTC.** Giá, KM, tồn kho trong kịch bản phải khớp `mock_tools`, không thì đáp án sai. Vì vậy dữ liệu thật chỉ nên là **nguồn văn phong và kịch bản tâm lý** (cách khách nói, cách phản đối, teencode, mạch hội thoại), còn con số vẫn do `resolver.py` điền. Quy trình: dataset thật → rút mẫu (persona, loại phản đối, cách nói) → template → `resolver` điền sản phẩm và giá → LLM viết lại theo văn phong thật (few-shot từ dữ liệu thật) → `validate.py` → đọc tay một mẫu.
3. **Đa phiên phải tự dựng.** Dataset thật gần như chỉ có cuộc gọi rời, trong khi trọng tâm của đề là khách đa phiên.
4. **Không lẫn dev / test,** để số đo vòng cải tiến còn ý nghĩa.

**Về ưu tiên:** dataset nằm trong tiêu chí 1 (12%), còn cơ chế cải tiến (13%) và giao diện / demo (13%) chưa bắt đầu. Bộ chấm chính thức là bộ ẩn của BTC, nên dataset tốt hơn chủ yếu giúp số đo trên dev / test sát thực tế hơn. Tôi đề xuất làm bản gọn:
- thêm một template thứ hai cho mỗi ca khó, văn phong lấy từ dữ liệu thật;
- làm sau, hoặc song song với, cơ chế cải tiến.

Một lựa chọn bổ sung là customer simulator của BTC (`simulator/`, M2): khách do LLM đóng vai và phản ứng theo agent, đúng chỗ dataset viết sẵn đang thiếu.

Bạn đang nghĩ tới bộ dataset thật cụ thể nào? Biết nguồn và giấy phép thì tôi đánh giá được nó dùng vào khâu nào.