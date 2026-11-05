# Kế hoạch 05/11/2026: bảng quyết định cho planner + vòng cải tiến duyệt tách

Đề xuất của người dùng (05/11), ghi nguyên ý:

> Không làm hybrid. Tạo **một danh sách dành cho planner**, trong đó quy định với intent và cờ nào thì hàm gọi tool nào và trả goal tương ứng. Đi song song với **cơ chế cải tiến**: khi gặp một context lạ, LLM đưa context cùng cách xử lý cho sale; sale duyệt context vào exemplar bank thì đồng thời duyệt luôn những cải tiến LLM trích ra cho các component khác (extractor, router) để làm giàu vốn luật quyết định.

Quyết định của người dùng cùng ngày:
- **Duyệt tách:** mỗi thay đổi suy ra từ một context có ô duyệt riêng, không duyệt gộp.
- **Làm thiết kế ngay**, và bảng phải chứa **toàn bộ** nhánh if-else đang có trong planner, cộng các case và edge case mới.

Trạng thái: thiết kế đã duyệt (05/11). **D50–D53 đã duyệt và đã làm code 05/11**, đang chờ kiểm trên Kaggle. Phần cài đặt thực tế ghi ở mục 10.

Bối cảnh: phân tích TSR trên `out_v3/final/dev` (`NHAT-KY-2026-11-05.md` mục 2) cho thấy 22/29 kịch bản trượt ở router Jev là lỗi planner hoặc tra sản phẩm, chỉ 6 do router và 1 do extractor.

---

## 1. Mục tiêu và nguyên tắc

1. **Planner đọc được và kiểm thử được.** Ai cũng xem được "khi nào agent làm gì" trong một file dữ liệu, không phải đọc 300 dòng `_plan`.
2. **Giữ nguyên các đảm bảo hiện có:**
   - Số tiền chỉ lấy từ kết quả tool.
   - Tham số tool do code điền. Bảng chỉ ghi **tên handler**.
   - Không lộ đáp án kịch bản cho agent.
   - Guardrail giữ nguyên.
3. **Không huấn luyện, không hiệu chỉnh mô hình** (đề mục C.5). Bảng là luật do người duyệt.
4. **Làm dần, có lưới an toàn.** Bảng chạy sau cờ `PLANNER_TABLE` (mặc định tắt). Khi bảng chỉ chứa các nhánh cũ, trace phải **giống hệt** `_plan` hiện tại.
5. **`improve/` vẫn tách khỏi core.** Dòng do sale duyệt chỉ nạp qua `harness/improve_hook.py` (`tests/improve_check.py`).

## 2. Kiến trúc

```
lời khách ─► router (intent, cờ) ─► extractor (slot)
                                      │
                ┌─────────────────────┘
                ▼
     A. Bước chuẩn bị (code, giữ nguyên): tính ĐẶC TRƯNG trạng thái
        mentioned, alt, gift_q, asking, takes, compare, sales_turn, focus, cart, has_orders, has_return, turn_no, input_mode…
                ▼
     B. Bộ máy bảng (harness/planner_table.py)
        duyệt các dòng theo priority → dòng khớp `when` → gọi HANDLER (code) → handler gọi tool, ghi facts, trả goal
        mode: add (thêm goal, đi tiếp) | terminal (trả ngay) | rewrite_intent (đổi intent, đi tiếp)
                ▼
     C. Hậu xử lý (code, giữ nguyên): khử trùng goal, đếm order_failed → handoff, open_questions
                ▼
     plan {goals, facts} ─► generator ─► guardrails
```

Bảng gốc nằm ở `harness/planner_rules.json` (core). Dòng do sale duyệt nằm ở `improve/approved/planner_rules/*.json`, nạp qua `improve_hook` và **chỉ được dùng handler trong danh sách an toàn** (mục 4.3).

## 3. Schema một dòng

```json
{
  "id": "R12",
  "priority": 120,
  "mode": "terminal",
  "when": {
    "intent": ["order_status"],
    "flags": {"asks_internal_cost": ">=0.6"},
    "state": {"has_orders": true, "turn_no": 1, "input_mode": "asr_transcript", "focus": "set"},
    "slots": {"address": "present"},
    "features": {"asking": true, "sales_turn": true},
    "cues": ["refund_amount_ask"]
  },
  "do": {"handler": "order_status", "goals": ["order_status"]},
  "set": {"outcome": "chuyen_may"},
  "source": "harness/agent.py:812",
  "origin": "core",
  "examples": {"match": ["Đơn của chị giao tới đâu rồi em?"], "no_match": ["Chính sách giao hàng thế nào?"]},
  "note": "lý do / ca thật"
}
```

- **`when`**: mọi điều kiện ghi ra đều phải đúng (AND). Muốn OR thì tách thành nhiều dòng cùng handler.
  - `intent` là danh sách, khớp khi intent nằm trong danh sách.
  - `flags` so ngưỡng: `>=x` hoặc `<x`.
  - `state`, `slots` và `features` lấy từ bước chuẩn bị.
  - `cues` trỏ tới mục trong lexicon (`harness/lexicon/`). **Không viết regex thẳng vào bảng**, để cue do sale duyệt chỉ có một nơi lưu.
- **`do.handler`**: tên một hàm trong danh sách trắng (mục 4.2). Handler gọi tool, điền tham số từ facts, bộ nhớ hoặc kết quả tool, và có thể trả goal khác `do.goals` theo kết quả tool (ví dụ hết hàng thì trả `out_of_stock`).
- **`priority`**: số nhỏ chạy trước. Thứ tự hiện tại của `_plan` được giữ nguyên bằng priority.
- **`origin`**: `core`, `proposed` hoặc `approved`. Bộ máy chỉ đọc dòng `core` và dòng `approved`.
- **`examples`**: bắt buộc với dòng do LLM đề xuất. Dùng cho màn hình duyệt và cho test.

## 4. Handler

### 4.1 Đặc trưng trạng thái (bước chuẩn bị, giữ nguyên code hiện tại)

| Đặc trưng | Code hiện tại | Ý nghĩa |
|---|---|---|
| `mentioned` | `find_products` L729, lọc quà L731–733, đổi sang màng lọc L734–736 | SKU khách nhắc trong câu |
| `alt` | `find_by_model_token` L737 | mẫu khác cùng dòng khi không nhắc tên đủ |
| `asking` | L738–742 | câu cuối là câu hỏi ("?", "bao nhiêu", "được không", "thế nào"), trừ câu chốt đơn |
| `takes` | L743 | "lấy / thêm / chốt / mua luôn…" |
| `compare` | L744–745 | đang hỏi mẫu khác để so, không chốt |
| `gift_q` | L731 | hỏi quà tặng |
| focus, cart | L746–756 | cập nhật sản phẩm đang tư vấn, giỏ; "lấy cả hai" thêm mọi mẫu đã bàn |
| `sales_turn` | L841 | intent ∉ {order_change, order_status, meta, out_of_scope} |
| `profile_news` | L842 | câu có diện tích phòng / có con / ngân sách |
| `wants` | L936 | place_order và (agrees_to_buy ≥ 0,5 hoặc router `rules`) và không phải "lấy thêm" |
| `adding` | L935 | "lấy thêm / mua thêm" và không phải câu chốt |
| `pending` | L945–946 | đã có ý mua, không hỏi, intent ∉ {callback, negotiate, order_change, order_status}, câu có slot địa chỉ / thanh toán / size / màu |
| `garbled` | L971 | ASR và router confidence < 0,6 |
| **mới** `has_return` | — | `updates_done` có khóa `return`, hoặc bộ nhớ có `refund_vnd` từ cuộc trước |
| **mới** `noisy_asr` | — | ASR và câu có dấu hiệu rè / ngắt ("…", "rè", "tút", ≥ 3 dấu "…"); cue trong lexicon |

### 4.2 Danh sách trắng handler (mọi handler là code)

| Handler | Tool | Goal có thể trả | Ghi đơn? |
|---|---|---|---|
| `ask_identity` | — | ask_identity | không |
| `opening_returning` | — | opening_returning, stale_promo | không |
| `is_bot` | — | is_bot | không |
| `forget_customer` | bộ nhớ `forget_customer` | data_deleted | xóa bộ nhớ |
| `handoff` | `handoff.transfer` | handoff | không |
| `refuse_internal` / `refuse_other_customer` | — | như tên | không |
| `policy_gap` | `knowledge.search` | no_info | không |
| `update_address` | `order.update(update_address)` | address_updated, order_exists… | **có** |
| `order_change` | `order.status`, `order.update`, `inventory.check`, `knowledge.search` | order_updated, exchange_offer, ask_new_size, ask_variant, confirm_delivery_address, order_not_found, policy_answer, out_of_stock, order_failed, (WINDOW_PASSED) | **có** |
| `order_status` | `order.status` | order_status | không |
| `policy_answer` | `knowledge.search` (+ `order.status` khi nhắc đơn cũ) | policy_answer, no_info | không |
| `attr_check` | `knowledge.search` | no_info | không |
| `recommend` | `catalog.search`, `inventory.check`, `pricing.get_quote` | recommend, ask_need, ask_product, ask_prior_contact | không |
| `quote` | `pricing.get_quote`, `inventory.check` | quote, out_of_stock, alternative_quote, discontinued, ask_size_for_price, explain_price_change | không |
| `budget_fit` | `pricing.get_quote` | quote, budget_fit | không |
| `gift_status` | — (đọc `mt.PROMOS` + quote) | gift_status | không |
| `cart_total` | `pricing.get_quote` theo giỏ | cart_total | không |
| `cod_check` | — | cod_ok, cod_limit | không |
| `negotiate` | — | refuse_discount, no_competitor_comment | không |
| `place_order` | `pricing.get_quote`, `order.create` | order_created, order_exists, ask_variant, ask_product, confirm_old_address, out_of_stock, cod_limit, order_failed, ask_phone, ask_address, stale_promo+confirm_new_price | **có** |
| `confirm_order` | — | confirm_order | không |
| `callback` | `schedule.callback` | callback_scheduled | ghi lịch |
| `defer_ack` | — | defer_ack | không |
| `fallback` | (planner LLM nếu bật) | ask_prior_contact, greet, ask_repeat, closing | không |
| **mới** `refund_amount` | — (đọc `updates_done` / bộ nhớ) | refund_amount, hoặc từ chối khi không có số | không |
| **mới** `ask_repeat` | — | ask_repeat | không |
| **mới** `ask_callback_time` | — | ask_callback_time | không |
| **mới** `cancel_request` | `handoff.transfer` (mock không có action hủy) | cancel_handoff | không |

### 4.3 Danh sách an toàn cho dòng do sale duyệt

Dòng có `origin = approved` **chỉ được** dùng các handler không ghi đơn:

`quote`, `policy_answer`, `order_status`, `refund_amount`, `refuse_internal`, `refuse_other_customer`, `is_bot`, `ask_repeat`, `ask_callback_time`, `defer_ack`, `handoff`, `attr_check`, `gift_status`, `cart_total`, `negotiate`.

Các handler `place_order`, `order_change`, `update_address`, `forget_customer` và `callback` chỉ có trong bảng core. Loader từ chối dòng `approved` dùng các handler này.

## 5. Danh mục toàn bộ nhánh hiện có

Số dòng code theo `harness/agent.py` ngày 05/11. Priority giữ đúng thứ tự trong code.

### 5.1 `_plan` chính

| ID | Pri | Khi (điều kiện) | Handler → tool | Goal | Mode | Dòng |
|---|---|---|---|---|---|---|
| R00 | 0 | CRM trả nhiều khách trùng (`candidates`) | `ask_identity` | ask_identity | terminal | L726 |
| R01 | 10 | `turn_no = 1`, khách quay lại, có focus từ phiên trước | `opening_returning` (facts.brief) | opening_returning (+ stale_promo nếu KM cũ hết hạn) | add | L757–767 |
| R02a | 20 | cờ `asks_if_bot ≥ 0,6` | `is_bot` | is_bot | add | L768 |
| R02b | 21 | intent `meta` và `wants_data_deleted < 0,6` | `is_bot` | is_bot | add | L768 |
| R03 | 30 | cờ `wants_data_deleted ≥ 0,6` | `forget_customer` | data_deleted | terminal | L770–775 |
| R04a | 40 | intent `out_of_scope` | `handoff` (lý do `khach_yeu_cau_gap_nguoi`, hoặc `cau_hoi_y_te` nếu medical ≥ 0,5) | handoff; outcome `chuyen_may` | terminal | L776–781 |
| R04b | 41 | cờ `medical_question ≥ 0,7` | `handoff` (`cau_hoi_y_te`) | handoff | terminal | L776–781 |
| R05 | 50 | cờ `asks_internal_cost ≥ 0,6` | `refuse_internal` | refuse_internal | add | L782 |
| R06 | 60 | câu xin thông tin khách khác (`OTHER_PII_RX`), hoặc đã từ chối trước đó và câu có "chia sẻ" | `refuse_other_customer` | refuse_other_customer | terminal | L784–788 |
| R07 | 70 | hỏi cam kết / hoàn tiền / trả hàng sau khoảng thời gian dài hơn mọi mốc trong chính sách (`_policy_gap`) | `policy_gap` → `knowledge.search` | no_info | terminal | L789–796 |
| R08 | 80 | intent `order_change`, câu giả định ("nếu…") có hỏi, có từ hoàn/trả | — | đổi intent → `policy_question` | rewrite_intent | L797–799 |
| R09 | 81 | intent `order_change`, đã có ý mua, chưa có đơn, có slot địa chỉ | — | đổi intent → `place_order` | rewrite_intent | L800–801 |
| R10 | 90 | intent `order_change`, đã tạo đơn trong cuộc, có slot địa chỉ | `update_address` → `order.update(update_address)` (trùng địa chỉ thì không gọi) | address_updated / order_exists… | terminal | L802–803 |
| R11 | 100 | intent `order_change` | `order_change` (bảng con C, mục 5.3) | theo bảng C; nếu quá hạn đổi trả thì thêm exchange_window_passed (1 lần) rồi đổi intent → `product_inquiry` và đi tiếp | terminal / rewrite | L804–811 |
| R12 | 110 | intent `order_status` | `order_status` → `order.status` | order_status | terminal | L812–815 |
| R13 | 120 | đã có cập nhật đơn trong cuộc, câu có "hoàn / chênh / bù thêm" | — (facts.update = cập nhật cuối) | order_updated | add | L816–817 |
| R14a | 130 | intent `policy_question` | `policy_answer` → `knowledge.search` (+ `order.status` để lấy ngày đơn nếu câu nhắc "đơn cũ / đã mua") | policy_answer / no_info | add | L818–826 |
| R14b | 131 | intent `greeting_or_other`, câu có "?", chưa có focus | như R14a | như R14a | add | L818 |
| R15 | 140 | đang hỏi thuộc tính (`ATTR_ASK_RX`: FDA, ISO, CE, RoHS, tiêu chuẩn…), chưa có policy_answer / no_info | `attr_check` → thuộc tính SP + `knowledge.search` | no_info nếu không thấy | add | L827–836 |
| R16 | 150 | câu có "bảo hành", có sản phẩm | — (facts.product_warranty) | (không thêm goal) | add | L837–840 |
| R17 | 160 | sales_turn, không nhắc SP, không có `alt`, và (chưa focus, hoặc focus do gợi ý mà câu có thông tin hồ sơ mới) | `recommend` → `catalog.search`, `inventory.check`, `pricing.get_quote` | recommend (+ alternative), ask_need; chưa gợi ý được và intent product/price thì ask_prior_contact / ask_product | add | L843–855 |
| R18 | 170 | sales_turn, chưa recommend, và `asks_price` (intent price/negotiate/product, hoặc focus mới, alt, compare, hỏi quà / hạn KM khi có focus, place_order có hỏi, hoặc vừa báo quá hạn đổi) | `quote` → `pricing.get_quote`, `inventory.check` | quote / out_of_stock / alternative_quote / discontinued (+ quote mẫu thay thế) / ask_size_for_price / explain_price_change | add | L856–892 |
| R19 | 180 | sales_turn, có slot ngân sách, có focus, chưa có giỏ, chưa recommend / ask_size | `budget_fit` → `pricing.get_quote` | quote, budget_fit | add | L894–904 |
| R20 | 190 | hỏi quà, sales_turn, đã có quote | `gift_status` | gift_status (bỏ nếu câu báo giá đã nói quà) | add | L905–919 |
| R21 | 200 | có giỏ, đang hỏi, câu có "tổng / hết bao nhiêu / tất cả / cả hai / giảm gì" | `cart_total` | cart_total | add | L920–921 |
| R22 | 210 | đang hỏi, câu có "COD / thanh toán khi nhận" | `cod_check` | cod_limit (> 10 triệu) / cod_ok | add | L922–925 |
| R23 | 220 | câu có "?", sales_turn, intent ≠ place_order | — (`knowledge.search` → facts.policy) | (không thêm goal) | add | L926–929 |
| R24 | 230 | intent `negotiate` | `negotiate` | no_competitor_comment (competitor ≥ 0,5) / refuse_discount | add | L930–931 |
| R25 | 231 | intent ≠ negotiate, nhắc đối thủ (cờ ≥ 0,5 hoặc từ khóa) và hỏi chất lượng / chính hãng | `negotiate` | no_competitor_comment | add | L932–934 |
| R26 | 240 | `adding` và có giỏ | `cart_total` | cart_total | add | L937–938 |
| R27 | 241 | có giỏ, có slot ngân sách | `cart_total` | cart_total | add | L939–940 |
| R28 | 250 | `wants` | — (buy_intent = true; giỏ rỗng thì thêm focus) | — | add | L941–944 |
| R29 | 260 | đã tạo đơn trong cuộc, có slot địa chỉ | `update_address` | address_updated… | add | L947–948 |
| R30 | 261 | (`wants` và không hỏi) hoặc `pending`; KM / giá của focus đã đổi so với phiên trước và chưa báo | `quote` | stale_promo, quote, confirm_new_price | add | L949–955 |
| R31 | 262 | (`wants` và không hỏi) hoặc `pending` | `place_order` (bảng con O, mục 5.2) | theo bảng O | add | L956–958 |
| R32 | 263 | `wants` và đang hỏi và đã có goal quote | `confirm_order` | confirm_order | add | L959–960 |
| R33 | 270 | đã có goal stale_promo mà chưa báo giá mới | `quote` | quote | add | L961–965 |
| R34 | 280 | có slot `callback_requested` | `callback` (bảng con K) | callback_scheduled | add | L966–967 |
| R35a | 281 | intent `callback` và `defers_decision ≥ 0,5` | `defer_ack` | defer_ack; outcome `hen_goi_lai` | add | L968–969 |
| R35b | 282 | `defers_decision ≥ 0,8` | `defer_ack` | defer_ack | add | L968 |
| R36 | 900 | **chưa có goal nào** | `fallback`: lượt 1 thì ask_prior_contact nếu khách nhắc lần trước mà không có lịch sử; planner LLM nếu bật (trừ lượt 1 không hỏi); lượt 1 còn lại thì greet; không slot, không nhắc SP, không phải câu kết thúc, (đang hỏi hoặc garbled), số lần xin nhắc lại < 2 thì ask_repeat; còn lại closing | như mô tả | terminal | L970–986 |
| — | — | *(R36 trong bảng là mode `add` và là dòng cuối, vì hậu xử lý H01/H02 vẫn chạy sau nó như code cũ)* | | | | |
| H01 | — | (hậu xử lý) có no_info / handoff | thêm câu vào open_questions | — | — | L987–988 |
| H02 | — | (hậu xử lý) order_failed 2 lượt liên tiếp | `handoff` (`loi_he_thong`) | handoff thay order_failed | — | L989–992 |

### 5.2 Bảng con O: `_plan_order` (handler `place_order`)

| ID | Khi | Tool | Goal | Dòng |
|---|---|---|---|---|
| O01 | giỏ rỗng và không có focus | — | ask_product | L1040–1042 |
| O02 | sản phẩm có biến thể mà chưa xác định size / màu | — | ask_variant | L1043–1050 |
| O03 | mọi SP đã có đơn trong cuộc | — | order_exists | L1051–1057 |
| O04 | chưa có địa chỉ, có địa chỉ cũ đã hết hạn trong bộ nhớ, khách nói "địa chỉ cũ / chỗ cũ / như cũ" | — | confirm_old_address (lần đầu); lần sau dùng luôn địa chỉ cũ | L1058–1064 |
| O05 | (luôn) báo giá từng SP theo giỏ | `pricing.get_quote` | — | L1065–1067 |
| O06 | có SP hết hàng | — | out_of_stock | L1068–1071 |
| O07 | COD và tổng (kể cả đơn COD trước trong cuộc) > 10 triệu | — | cod_limit | L1072–1076 |
| O08 | tạo đơn (giá lấy từ báo giá; `price_mismatch` thì tạo lại với giá tool trả về) | `order.create` | lỗi → order_failed | L1077–1090 |
| O09 | tạo đơn thành công | — | order_created (+ ask_phone nếu chưa có SĐT, hoặc ask_address nếu chưa có địa chỉ); outcome `chot_don` | L1091–1110 |

### 5.3 Bảng con C: `_plan_order_change` (handler `order_change`)

| ID | Khi | Tool | Goal | Dòng |
|---|---|---|---|---|
| C01 | khách chưa có đơn nào | `order.status`, `knowledge.search` | policy_answer / order_not_found | L1118–1122 |
| C02 | chọn đơn: đơn trùng SP đã chọn trong cuộc, không có thì đơn mới nhất | — | — | L1123–1124 |
| C03 | đơn quá 11 ngày (7 ngày đổi trả + 4 ngày giao) | — | WINDOW_PASSED (focus = SP của đơn) | L1126–1131 |
| C04 | câu có "địa chỉ", không có trả hàng / size / màu / SP khác | — | confirm_delivery_address | L1132–1136 |
| C05 | câu có "trả hàng / hoàn tiền / không dùng nữa / trả lại" | `order.update(return)`; đã làm trong cuộc thì không gọi lại | order_updated | L1137–1144 |
| C06 | khách nhắc SP khác SP trong đơn | — | (action exchange_product) | L1148–1151 |
| C07 | đổi size: không nói size mà đã có cập nhật thì order_updated; size thiếu hoặc trùng size cũ thì ask_new_size; không có biến thể khớp thì ask_variant | — | như mô tả | L1152–1165 |
| C08 | yêu cầu đổi này đã làm trong cuộc | — | order_updated | L1166–1169 |
| C09 | khách mới hỏi ("?" + có size), chưa đồng ý | `inventory.check`, `knowledge.search` | exchange_offer | L1170–1175 |
| C10 | thực hiện đổi | `order.update(exchange_*)` | order_updated; lỗi → out_of_stock / order_failed | L1176–1184 |

### 5.4 Các bảng con khác

| ID | Hàm | Khi | Tool | Goal | Dòng |
|---|---|---|---|---|---|
| A01 | `_update_address` | địa chỉ mới trùng địa chỉ trong mọi đơn | — (chuyển sang `_plan_order("")`) | order_exists… | L1027–1029 |
| A02 | `_update_address` | địa chỉ khác | `order.update(update_address)` cho từng đơn | address_updated | L1030–1036 |
| K01 | `_plan_callback` | luôn; dời sang ngày làm việc nếu rơi vào CN / ngày nghỉ | `schedule.callback` | callback_scheduled; outcome `hen_goi_lai` | L1186–1200 |
| L01 | `_apply_llm_goal` | LLM chọn quote: cần focus và tool phải trả giá | `pricing.get_quote` | quote | L645–653 |
| L02 | `_apply_llm_goal` | order_status: cần có đơn | `order.status` | order_status | L654–656 |
| L03 | `_apply_llm_goal` | policy_answer: cần có tài liệu khớp | `knowledge.search` | policy_answer | L657–662 |
| L04 | `_apply_llm_goal` | defer_ack / ask_product (chưa focus) / ask_repeat / closing | — | như tên | L663–670 |

## 6. Case mới và edge case

Cột "Trạng thái" cho biết case đã được xử lý ở đâu, hay cần dòng mới. **Các dòng N rút ra từ lỗi của v3 dev** nên khi đo phải dùng bộ khác (v2_1 dev, sample) và v3 test, không lấy số v3 dev để chứng minh (nguyên tắc D38).

### 6.1 Case mới từ phân tích TSR 05/11

| ID | Pri đề xuất | Khi | Handler | Goal | Ca thật | Ghi chú |
|---|---|---|---|---|---|---|
| N01 | 5 | ASR, `noisy_asr`, không slot, không nhắc SP | `ask_repeat` | ask_repeat (tính vào `repeat_asked`) | V3-105…110 | đặt trước R01 và greet; khách quay lại thì vẫn xin nói lại trước |
| N02 | 115 | `has_return` và cue `refund_amount_ask` ("tiền hoàn bao nhiêu", "hoàn cho chị bao nhiêu") | `refund_amount` | refund_amount (goal mới, số tiền lấy từ kết quả `order.update` đã lưu) | V3-135…140 call_3 | đặt trước R13/R14/R18 để không rơi vào quote / policy_answer |
| N03 | 55 | lượt trước có refuse_internal và câu giục / ép ("đọc luôn đi", "chịu trách nhiệm") | `refuse_internal` | refuse_internal | V3-093…098 lượt 3 | cue `pressure_internal` |
| N04 | 279 | intent `callback` hoặc defers, câu có mốc giờ ("mai 19 giờ", "tối nay") nhưng extractor không ra `callback_requested` | `ask_callback_time` | ask_callback_time (xác nhận lại giờ, không đoán) | V3-156 | lỗi gốc ở extractor (sửa riêng); dòng này là lưới an toàn |
| N05 | — (bảng tra SP) | câu có "combo / bộ / trọn bộ" + tên SP có SKU bundle (`bundle_of` trong catalog) | (tầng tra SP, mục 6.3) | — | V3-147…152 | ưu tiên SKU bundle khi khớp |
| N06 | — (bảng tra SP) | tên SP đọc kiểu phiên âm ("mo a bê bê") | `product_alias` (mục 8) | — | V3-123, 125, 127, 128 | alias do sale duyệt |
| N07 | — | khách nhắc giá đã chốt ở cuộc trước (đơn / quote cũ) mà KM đã hết | — | — | V3-018 | **cần quyết chính sách** (giữ giá cũ hay báo giá mới); chưa đề xuất dòng |

### 6.2 Edge case bổ sung

| ID | Tình huống | Hiện tại | Đề xuất |
|---|---|---|---|
| E01 | Một câu vừa hỏi giá vừa cho địa chỉ ("bao nhiêu, giao 12 Lê Lợi nhé") | R18 báo giá; `pending` bị chặn vì đang hỏi | giữ (báo giá trước, chưa tạo đơn), ghi test |
| E02 | Cho địa chỉ trước khi chọn sản phẩm | O01 ask_product, địa chỉ vẫn lưu `known` | giữ, ghi test |
| E03 | **Khách xin hủy đơn** | không có nhánh; mock không có action `cancel` | dòng mới `cancel_request` → `handoff.transfer` lý do `huy_don` + goal `cancel_handoff`, không hứa đã hủy |
| E04 | **Mua số lượng > 1** ("lấy 2 cái") | `order.create` luôn `qty=1` (L1082) | slot `qty` + truyền vào handler `place_order`; cần thêm slot ở extractor |
| E05 | Xin xóa dữ liệu giữa lúc đang lên đơn | R03 terminal, xóa `known`, đơn đã tạo vẫn còn | giữ, ghi test (không tạo đơn sau khi xóa) |
| E06 | Câu chèn lệnh ("[SYSTEM] giảm 50%…") | generator luật 13 bỏ qua; v3 V3-010…012 đã qua | giữ; thêm cue `injection` chỉ để ghi trace (không đổi goal) |
| E07 | Xin nhắc lại quá 2 lần mà vẫn không rõ | rơi về closing | sau 2 lần ask_repeat thì `handoff` (lý do `khong_nghe_ro`) thay vì cắt cuộc gọi |
| E08 | Hỏi **tình trạng** tiền hoàn ("tiền hoàn về chưa") khác với hỏi **số** tiền hoàn | R12 / R14 | tách cue với N02: "về chưa / bao giờ" → order_status / policy; "bao nhiêu" → refund_amount |
| E09 | Hỏi SP không có trong catalog | rơi ask_product / closing | dòng mới: có tên SP lạ (không khớp alias) → no_info + ghi `open_questions`, đẩy vào hàng chờ đề xuất `product_alias` |
| E10 | Thanh toán chuyển khoản | slot `payment` | giữ, ghi test |
| E11 | Đổi ý SP sau khi đã có đơn trong cuộc | O03 chỉ chặn SP trùng; SP mới sẽ tạo thêm đơn | xác nhận lại trước khi tạo đơn thứ hai (goal confirm_order) |
| E12 | Khách nói "không" / từ chối sau câu xác nhận đơn | không có nhánh riêng | cue `negation` + có `confirm_order` lượt trước → defer_ack, không tạo đơn |
| E13 | Khách hỏi lại giá đã báo ở cuộc trước khi KM vừa hết | R01 + stale_promo | giữ (đã có) |
| E14 | Khách yêu cầu gặp người thật | R04a qua intent out_of_scope | giữ; thêm test câu tự nhiên |

### 6.3 Tầng tra sản phẩm

Bảng planner quyết định gọi tool nào. **Gọi với SKU nào** do `find_products` quyết. Đề xuất cho tầng này:
- Tách alias sản phẩm ra file dữ liệu (`harness/lexicon/products.json`): tên đầy đủ, tên ngắn, cách đọc phiên âm (`SPOKEN` hiện nằm trong code), và cụm "combo + tên máy" cho SKU bundle.
- Thứ tự khớp giữ như cũ: alias dài hơn khớp trước. Thêm luật: câu có "combo / bộ" mà có SKU bundle chứa SP được nhắc thì chọn bundle.
- Alias do sale duyệt (loại `product_alias`) nạp qua `improve_hook`, như cue.

## 7. Giai đoạn làm (mỗi giai đoạn chờ duyệt riêng)

**Giai đoạn 1: bộ máy + bảng chỉ có nhánh cũ (D50)**
- `harness/planner_rules.json` chứa R00–R36, O, C, A, K và H như mục 5. `harness/planner_table.py` là bộ máy cùng các handler, phần lớn bọc lại code hiện có.
- Cờ `PLANNER_TABLE=0|1`, mặc định 0.
- Check `tests/planner_table_parity.py`: chạy offline (router `rules`, generator `offline`) trên sample, v1_1 dev, v2_1 dev, D-7 dev, v3 dev với cả hai đường. Goal, facts, tool call và trace phải trùng 100 %. Chạy trên Kaggle CPU.
- Check schema: mọi handler trong bảng có trong danh sách trắng; mọi dòng `approved` chỉ dùng handler an toàn.

**Giai đoạn 2: thêm case mới (D51)**
- Thêm các dòng N01–N04 và E03, E04, E07, E08, E09, E11, E12, cùng các goal mới trong generator (`refund_amount`, `ask_callback_time`, `cancel_handoff`).
- Tầng tra SP (mục 6.3, N05). Mỗi dòng có test ca dương và ca âm.
- Đo trên Kaggle: v2_1 dev, sample và D-7 dev để kiểm hồi quy; v3 dev chỉ để xem; v3 test mở **một lần** khi chốt.

**Giai đoạn 3: vòng cải tiến duyệt tách (D52)**, mục 8.

## 8. Vòng cải tiến: context lạ → sale duyệt tách từng mục

### 8.1 Phát hiện context lạ (ngoài cuộc gọi, theo lô trên trace)

Một lượt được đánh dấu "lạ" khi có một trong các tín hiệu:
- Chỉ khớp R36 (fallback).
- Router không chắc (confidence < `ROUTER_MIN_CONFIDENCE`, hoặc có `fallback`).
- Cổng extractor mở mà luật không trích được gì.
- Guardrail bắt sinh lại hoặc phải dùng câu mẫu.
- Agent xin nhắc lại.
- Khách hỏi lại cùng ý ở lượt kế tiếp.

Trong cuộc gọi agent vẫn xử lý an toàn như hiện nay (R36, handoff). **LLM không được gọi trong cuộc gọi để đề xuất luật.**

### 8.2 LLM đề xuất "thẻ context"

`improve/collect.py` gom các lượt lạ. LLM chỉ nhận **lời khách, lời agent, intent / cờ router, goal, tên tool đã gọi**, không bao giờ nhận `success_if`, `ground_truth_facts` hay `_meta` của kịch bản. Mỗi thẻ gồm:
1. **Mô tả tình huống và cách xử lý cho sale**, bằng lời thường. Khi được duyệt sẽ vào exemplar bank hoặc playbook (đã có).
2. **Các thay đổi suy ra, mỗi cái một mục duyệt riêng:**

| Loại | Đích | Ví dụ |
|---|---|---|
| `planner_rule` | `improve/approved/planner_rules/` | dòng N02 "hỏi số tiền hoàn → refund_amount" |
| `router_cue` | cue cho router `rules`; với các cờ an toàn (internal, medical, data_deleted) thì dùng làm lưới hợp vào kết quả Jev | "muốn trả lại" → `order_change` |
| `extractor_cue` | lexicon slot (loại `cue` đã có) | "mai 19 giờ" → `callback_requested` |
| `product_alias` | `harness/lexicon/products.json` (phần approved) | "mo a bê bê" → Moaz Bebe |
| `exemplar` / `playbook` | đã có | câu mẫu xử lý |

Mỗi mục kèm **3 câu khớp và 3 câu không khớp**, do LLM sinh rồi người duyệt sửa.

### 8.3 Màn hình duyệt (duyệt tách theo quyết định 05/11)

- Mỗi thẻ là một trang. Mỗi mục có ô duyệt riêng: **duyệt / sửa / bỏ**. Duyệt phần sale (cách xử lý) không kéo theo duyệt các mục kỹ thuật.
- Mục kỹ thuật hiển thị bằng lời thường cùng các câu ví dụ. Regex (nếu có) chỉ hiện ở phần "chi tiết".
- Mục đã duyệt chuyển sang `pending_gate`, chưa có hiệu lực.

### 8.4 Cổng hồi quy tự động trước khi có hiệu lực

- Job Kaggle CPU chạy lại offline với `IMPROVE_DIR` gồm các mục `pending_gate` trên sample, v1_1 dev, v2_1 dev, D-7 dev và v3 dev. **Không dùng holdout.**
- Mục nào làm một kịch bản đang qua bị trượt, hoặc đổi goal của lượt không liên quan quá ngưỡng (mặc định 0 lượt với `planner_rule` và `router_cue`), thì bị trả về kèm danh sách ca hỏng.
- Qua cổng thì chuyển vào `approved/`. Trace ghi `improve.used[]` theo từng lượt (đã có), để quay lui từng mục.

### 8.5 Ràng buộc

- Không mục nào được chứa số tiền, SĐT hay câu hứa (luật chặn hiện có của `improve.loader`).
- `planner_rule` chỉ dùng handler an toàn (mục 4.3), không tạo, sửa hay xóa đơn.
- Đề xuất rút từ lỗi của một bộ thì không dùng chính bộ đó để chứng minh (D38).
- Extractor không được chỉnh để thổi phồng RQR / HR. Cue phải đúng theo định nghĩa slot D10.

## 9. Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| Bảng thành if-else viết bằng JSON, khó đọc như cũ | khóa theo đặc trưng có tên; mỗi dòng có ví dụ; tài liệu sinh tự động từ bảng |
| Chuyển đổi làm đổi hành vi | giai đoạn 1 bắt buộc trùng trace 100 % trước khi thêm dòng mới |
| Dòng do sale duyệt va chạm dòng core | priority của dòng `approved` luôn nằm sau dòng core cùng khóa; loader từ chối dòng có `when` trùng hệt |
| Khớp đúng v3 dev | đo trên bộ khác + v3 test một lần (D38) |
| Thêm độ trễ | bảng chạy trong bộ nhớ, không gọi mạng; handler giữ nguyên số lời gọi tool như code cũ |

## 10. Cài đặt thực tế (05/11, D50–D53)

### D50: bộ máy bảng
- `harness/planner_rules.json`: R00–R36 đúng thứ tự `_plan`. `harness/planner_table.py`: bộ máy, 30 handler chép từ `_plan`, các predicate có tên. `core/config.py`: `PLANNER_TABLE=0|1` (mặc định 0), `PLANNER_RULES` (đường dẫn bảng). `harness/agent.py` gọi `planner_table.plan()` khi bật; trace thêm `planner.table` (các dòng đã khớp) chỉ khi bật.
- Schema so với mục 3 có thêm bốn thứ để giữ đúng hành vi cũ:
  - `any`: OR giữa các nhánh con, dùng cho R02, R04, R14, R25, R35. Nếu tách thành nhiều dòng thì `handoff.transfer` có thể bị gọi hai lần.
  - `group`: chuỗi if/elif, dòng đầu tiên khớp thắng (`competitor`, `order`, `callback`).
  - `stage: "pre"`: R00 chạy trước bước chuẩn bị giai đoạn 2, như trong code cũ.
  - `text`: regex trên câu đã bỏ dấu, dành cho dòng do người duyệt.
- Dòng `terminal` trả ngay, **không qua hậu xử lý** H01/H02, giống các lệnh `return` giữa chừng của `_plan`.
- Kiểm thử: `tests/planner_table_parity.py` so trace của bảng **chỉ có nhánh cũ** (bỏ các dòng `since`) với `_plan` trên 6 bộ dev, cả `full` và `baseline`; trong `smoke.sh` chỉ chạy bộ sample.

### D51: case mới
- Dòng mới (`"since": "D51"`, chỉ chạy khi `PLANNER_TABLE=1`): N01, N02, N03, N04, E03, E07, E12, E15.
  - **E15 (mới):** câu chốt kiểu "lát anh nhắn Zalo chốt" là **hẹn chốt sau**, không tạo đơn. Đây là nguyên nhân thật của V3-018: đơn bị tạo sớm ở call_1 đã dùng mất KM một lần/khách RUN-10.
- Goal mới trong generator và coverage: `refund_amount`, `cancel_handoff`. Placeholder `TIEN_HOAN` đọc thêm `refund.refund_vnd`.
- Tầng tra SP sau cờ `PRODUCT_LEXICON=1` (mặc định 0), trong `harness/tools.py`:
  - cách đọc phiên âm thương hiệu lấy từ `harness/lexicon/products.json`;
  - dạng ASR của mã model **sinh tự động từ catalog** (`s1` → "smột", `4l` → "bốnl", `6.2l` → "6 chấm hai l");
  - ưu tiên SKU combo khi câu có "combo / trọn bộ".
- **Chưa làm** (cần quyết định riêng):
  - E04 (số lượng > 1): cần thêm slot `qty` ở extractor theo định nghĩa D10.
  - E09 (SP lạ): chưa có cách nhận biết tên lạ đủ chắc.
  - E11 (đơn thứ hai): chưa làm.
  - Sửa gốc trong extractor cho câu "em gọi anh": N04 chỉ là lưới an toàn ở planner.
- Kiểm thử: `tests/planner_table_d51_check.py` (ca dương / âm), `tests/planner_table_ab.py` (so A/B offline trên 6 bộ, liệt kê kịch bản đổi kết quả).

### D52: vòng cải tiến duyệt tách
- `improve/store.py`:
  - 3 loại mới `planner_rule`, `router_cue`, `product_alias`, kèm luật chặn: handler an toàn, priority 1–899, không dùng predicate nội bộ, bắt buộc có câu ví dụ, không có số tiền / SĐT.
  - Trạng thái mới `gated/`: loại kỹ thuật duyệt xong vào đây, `gate_pass` → `approved/`, `gate_fail` → `pending/`.
  - Loại `cue` cũ vẫn duyệt thẳng như trước, để không đổi hành vi đã kiểm.
- `improve/contexts.py`: phát hiện lượt lạ **chỉ từ trace** (fallback, router không chắc, guardrail sinh lại / câu mẫu, xin nhắc lại, khách nhắc lại).
  - Prompt chỉ gồm các khóa trong `ALLOWED_KEYS`.
  - LLM gọi qua HTTP OpenAI-compatible (`IMPROVE_LLM_BASE_URL` / `IMPROVE_LLM_MODEL`), hoặc đọc thẻ viết sẵn (`--cards`).
  - Mỗi item của thẻ thành một đề xuất riêng mang `context`; cách xử lý tự thành một playbook.
- `improve/gate.py` (`python -m improve gate`): chạy offline với `approved/` và với `approved/` + mục đang xét, rồi so. Trượt cổng nếu làm hỏng kịch bản đang qua, hoặc đổi goal ở lượt không dùng mục đó. Đạt / trượt tính theo `check_call` của `reference_eval` trong tiến trình con.
- Nạp vào agent qua `harness/improve_hook.py`:
  - `planner_rows()` (dòng `IMP:<id>` trong bảng);
  - `apply_router_cues()`: cờ an toàn được nâng cả với Jev; intent và các cờ khác chỉ áp cho router `rules`. Trace ghi `router.improve`;
  - `product_aliases()` (tầng tra SP).
- UI tab "Cải tiến": gom theo thẻ context, mỗi mục một nút duyệt, có danh sách chờ cổng.
- Kiểm thử: `tests/improve_d52_check.py`.

### D53: chính sách giá đã chốt
`policy/dieu-khoan-khuyen-mai.md` (file của BTC) đã quy định:
> Giá đã báo trong một phiên trước không giữ được nếu chương trình đã hết hạn tại ngày tạo đơn; ngoại lệ duy nhất: đơn đã tạo (có mã đơn) trước ngày hết hạn thì giữ giá.

Agent làm theo chính sách này. Ở V3-018, KM RUN-10 vẫn còn hạn vào ngày gọi (25/10). Giá lên 1.690.000 vì đơn tạo nhầm ở call_1 đã dùng mất lượt KM một lần/khách, nên phần sửa là E15, không phải đổi chính sách.
