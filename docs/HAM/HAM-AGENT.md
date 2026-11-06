# Bảng tra hàm của `harness/agent.py`

[harness/agent.py](../harness/agent.py) là lõi của harness: lớp `CallSession` điều phối một cuộc gọi từ lúc nhận diện khách tới lúc lưu tóm tắt phiên. Tài liệu này liệt kê từng hàm trong file: làm gì, nhận gì, trả gì, gọi tới đâu. Số dòng ứng với code ngày 17/10/2026.

Mỗi file khác trong `harness/` có bảng tra riêng: [HAM-EXTRACTOR](HAM-EXTRACTOR.md), [HAM-LLM-EXTRACT](HAM-LLM-EXTRACT.md), [HAM-GUARDRAILS](HAM-GUARDRAILS.md), [HAM-KNOWLEDGE](HAM-KNOWLEDGE.md), [HAM-RAG](HAM-RAG.md), [HAM-LOADER](HAM-LOADER.md), [HAM-MEMORY](HAM-MEMORY.md), [HAM-MCP-CLIENT](HAM-MCP-CLIENT.md), [HAM-TEXTNORM](HAM-TEXTNORM.md), [HAM-TOOLS](HAM-TOOLS.md). Sơ đồ tổng thể: [SO-DO-CODE.md](SO-DO-CODE.md).

## 1. Cách đọc

`run_eval.py` dùng `CallSession` theo đúng ba bước:

```
sess = CallSession(...)     # tạo trạng thái
sess.start()                # 1 lần: nhận diện khách, dựng Call Brief
row = sess.turn(câu_khách)  # lặp lại cho từng câu khách nói → 1 dòng trace
sess.end()                  # 1 lần: lưu tóm tắt phiên
```

Phần lớn hàm nhận ít tham số vì đọc và ghi trạng thái chung trên `self` (mục 2). Hai từ dùng xuyên suốt:

- **goals**: danh sách việc agent phải nói ở lượt này, ví dụ `["quote", "confirm_order"]`. Generator viết câu theo danh sách này.
- **facts**: dữ liệu đi kèm goals, lấy từ tool hoặc bộ nhớ, ví dụ `{"quote": {...giá, khuyến mãi...}}`. LLM chỉ được dùng con số có trong đây.

## 2. Trạng thái của `CallSession`

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `mem` | `Memory` / `RemoteMemory` | Cửa vào bộ nhớ khách hàng ([HAM-MEMORY](HAM-MEMORY.md)) |
| `tools` | `ToolBox` | Cửa vào 9 tool của BTC ([HAM-TOOLS](HAM-TOOLS.md)) |
| `router`, `gen` | `Router`, `Generator` | Bộ phân loại intent và bộ viết câu (`core/llm/`) |
| `config` | chuỗi | `full` hoặc `baseline_no_memory` (bản thân `CallSession` không đọc; baseline do `mem.read_enabled` quyết định) |
| `today`, `call_name`, `session_id` | chuỗi | Ngày cuộc gọi, tên cuộc (`call_1`), mã phiên (`<kịch bản>:call_1`) |
| `channel`, `channel_identity`, `phone`, `input_mode` | chuỗi | Kênh (`hotline`, `chat_fanpage`, `zalo_oa`), FB/Zalo ID, SĐT gọi đến, dạng đầu vào (`text`, `asr_transcript`, `chat_teencode`) |
| `customer` | dict / `None` | `{customer_id, name, honorific, phone}` của khách đã nhận diện |
| `candidates` | list | Các hồ sơ dùng chung một SĐT, chờ khách xưng tên |
| `known` | dict | Mọi slot đã biết trong cuộc này: nạp từ bộ nhớ cộng với khách vừa nói |
| `carried` | dict | Riêng các slot nạp từ phiên trước, dùng tính `facts_used` (CCR) |
| `expired` | dict | Slot đã quá hạn TTL (ví dụ địa chỉ cũ), chỉ được hỏi xác nhận |
| `focus`, `focus_by` | chuỗi | Mã sản phẩm đang bàn và nguồn của nó: `memory`, `customer`, `recommend` |
| `quote`, `prev_quotes` | dict, list | Báo giá gần nhất của sản phẩm đang bàn; các báo giá phiên trước nạp từ bộ nhớ |
| `cart`, `discussed` | list | Giỏ hàng (mỗi dòng sản phẩm một biến thể); các sản phẩm đã nhắc trong cuộc |
| `orders_created`, `updates_done` | list, dict | Đơn vừa tạo; yêu cầu đổi/trả vừa tạo (khóa `(order_id, action, sku mới)`) |
| `history`, `turn_no` | list, số | Các lượt đã qua `{role, text}`; số thứ tự lượt hiện tại |
| `brief`, `brief_ms`, `start_tool_log` | dict, số, list | Call Brief, thời gian dựng, tool đã gọi lúc mở cuộc gọi (ghi vào trace lượt 1) |
| `outcome`, `blockers` | chuỗi, list | Kết quả cuộc gọi (`chot_don`, `hen_goi_lai`, `chuyen_may`); `blockers` khai báo nhưng không dùng |
| `open_questions` | list | Câu khách hỏi mà agent chưa trả lời được (đi vào Call Brief lần sau) |
| `repeat_asked` | số | Số lần đã xin khách nói lại trong cuộc (tối đa 2) |
| `seen_money` | set | Mọi số tiền được phép nói trong cuộc; dùng kiểm câu tóm tắt LLM |
| `last_sentiment` | chuỗi | Cảm xúc khách do LLM tóm tắt handoff trả về |
| `buy_intent`, `price_change_told`, `size_asked`, `window_told`, `old_addr_asked` | bool | Cờ "đã xảy ra một lần", để không lặp cùng một câu hỏi hay thông báo |
| `pending_size`, `category` | chuỗi | Size mới khách muốn đổi; ngành hàng đang tư vấn |
| `deleted`, `_deleted_turn` | bool, số | Khách đã yêu cầu xóa dữ liệu, và ở lượt nào |

## 3. Hằng số và hàm cấp module

| Tên | Chức năng | Đầu vào | Đầu ra |
|---|---|---|---|
| `CATEGORY_WORDS` [:20](../harness/agent.py#L20) | Từ khóa ngành hàng (đã bỏ dấu) → mã ngành của catalog, ví dụ "may loc khong khi" → `gia-dung/may-loc-khong-khi` | | |
| `STACKABLE_SKIP` [:25](../harness/agent.py#L25) | KM phí ship / COD (`COD-0`, `NAM-SHIP0`): không coi là "mã KM" của đơn | | |
| `FILTER_OF` [:26](../harness/agent.py#L26) | Máy lọc → mã màng lọc thay thế, dùng khi khách nói "màng lọc" | | |
| `CLOSING_RX` [:34](../harness/agent.py#L34) | Câu chào / đồng ý kết thúc ("cảm ơn", "ok", "để chị xem"); phân biệt xin nói lại với chào kết thúc | | |
| `_ddmm(d)` [:30](../harness/agent.py#L30) | Đổi ngày ISO sang dạng đọc | `"2026-10-15"` | `"15/10"` |
| `_money_in_strings(obj)` [:38](../harness/agent.py#L38) | Gom số tiền nằm trong **chuỗi** của FACTS (tên KM "… đơn từ 500k"); bỏ khóa bắt đầu bằng `_` | dict / list / chuỗi | set số nguyên |
| `_next_action(last, blockers, open_q, orders, advised, stale)` [:54](../harness/agent.py#L54) | Hành động đề xuất cho Call Brief, theo thứ tự ưu tiên: câu chưa trả lời → đơn đang xử lý → rào cản → sản phẩm đã tư vấn (báo lại giá nếu đổi) → khách cũ chưa có sản phẩm | phiên cuối, rào cản, câu chưa trả lời, đơn, báo giá cũ, cảnh báo | chuỗi / `None` |

## 4. Các hàm của `CallSession`

### 4.1. Mở cuộc gọi

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `__init__` [:71](../harness/agent.py#L71) | Tạo trạng thái ở mục 2 | `memory`, `today`, `call_name`, `session_id`, `channel`, `channel_identity`, `phone`, `input_mode`, `router`, `generator`, `config` | không | `ToolBox(today)`, `Router()`, `Generator()` (khi không truyền) |
| `start()` [:96](../harness/agent.py#L96) | Nhận diện khách rồi dựng Call Brief. Chọn định danh theo kênh (Fanpage → `fb_id`, Zalo → `zalo_id`, còn lại hoặc thiếu ID → SĐT). CRM trả nhiều hồ sơ → chờ xưng tên; một hồ sơ → gắn; không có → tra bộ nhớ; vẫn không có → hồ sơ tạm `N-<định danh>`. Đo `brief_ms` (tính cả bước kiểm tính mới) | không | dict Call Brief (cũng lưu ở `self.brief`) | `tools.call("crm.get_customer")`, `mem.lookup`, `_bind`, `_build_brief`, `tools.take_log` |
| `_bind(cid, name, honorific, phone, crm)` [:119](../harness/agent.py#L119) | Gắn cuộc gọi vào một khách: lưu hồ sơ và mọi định danh (SĐT, Zalo, FB), gộp hồ sơ tạm `N-…` trùng định danh, nhập phiên cũ của CRM, rồi (nếu được đọc bộ nhớ và khách chưa yêu cầu xóa) nạp fact và báo giá cũ, đặt `focus` = sản phẩm đã chốt hoặc đã tư vấn | mã khách, tên, xưng hô, SĐT, kết quả CRM hoặc `None` | không. Ghi `customer`, `carried`, `known`, `prev_quotes`, `focus` | `mem.upsert_customer`, `mem.lookup`, `mem.merge_customer`, `mem.status`, `mem.current_facts`, `mem.past_quotes`, `import_old_session` |
| `import_old_session(s, cid)` [:141](../harness/agent.py#L141) | Đưa một phiên cũ (CRM hoặc `seed_history` của kịch bản) vào bộ nhớ: lưu phiên; trích slot từ câu tóm tắt, sản phẩm đầu tiên → `product_advised`, số tiền đầu tiên → `price_quoted_vnd`; ghi thành fact với ngày gốc (để xét TTL), độ tin 0,8. Bỏ qua phiên đã nhập | `s` = `{session_id, channel, date, outcome, summary}`; `cid` | không | `mem.past_sessions`, `mem.add_session`, `mem.write_fact`, `extractor.customer_slots`, `find_products`, `find_money` |
| `_build_brief()` [:157](../harness/agent.py#L157) | Dựng Call Brief theo `schemas/call_brief.schema.json`. Tách fact còn hạn / quá hạn (quá hạn → `stale_warnings`, chuyển sang `expired`). **Kiểm tính mới** lúc nhận diện: với mỗi sản phẩm đã báo giá, gọi lại `pricing.get_quote` + `inventory.check` để phát hiện KM hết hạn, giá đổi, hết hàng. Lấy đơn của khách qua `order.status` (tool CRM, nên baseline cũng có), câu chưa trả lời của phiên trước, câu mở đầu gợi ý | không | dict: `customer_name`, `is_returning`, `n_previous_sessions`, `last_session`, `profile_facts`, `products_advised`, `orders`, `open_blockers`, `open_questions`, `must_not_ask`, `stale_warnings`, `suggested_opening`, `suggested_next_action`, `precomputed_parts`, `ambiguous_candidates`… | `mem.past_sessions`, `mem.current_facts`, `tools.call("pricing.get_quote" / "inventory.check" / "order.status")`, `public_view`, `product_name`, `_next_action` |
| `_resolve_candidate(name)` [:337](../harness/agent.py#L337) | SĐT dùng chung: khách xưng tên trùng (bỏ dấu) với một hồ sơ → gắn hồ sơ đó, xóa `candidates` | tên khách vừa xưng | không | `fold`, `tools.call("crm.get_customer")`, `_bind` |

### 4.2. Một lượt thoại

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `turn(raw)` [:213](../harness/agent.py#L213) | Điều phối cả lượt, theo thứ tự: (1) ITN nếu đầu vào là ASR; (2) `perceive`; (3) trích slot khách; (4) khách đọc SĐT → gắn định danh, hồ sơ tạm thì tra CRM và gộp; xưng tên khi SĐT dùng chung → chọn hồ sơ; (5) router; (6) `_plan`; (7) dựng tập **số tiền được phép** (số khách nói, slot số đã biết, kết quả tool, báo giá cũ, số trong FACTS, trích chính sách, chuỗi FACTS) và tập **số cấm** (giá khách nêu không khớp báo giá hiện tại); (8) generator, lỗi → câu mẫu (`llm_error_template`); (9) guardrail, sai → sinh lại một lần với lời nhắc ghi rõ con số phải bỏ (`regenerated`), vẫn sai → câu mẫu (`safe_template`), bản nháp bị chặn lưu ở `guardrail.rejected`; (10) trích `questions` / `claims` / `facts_used`; (11) ghi bộ nhớ, lưu lượt. Đo `latency`: TTFT và total tính tới khi câu qua guardrail, phần trích + ghi nhớ sau đó ghi riêng `post_ms`, kèm `parts` từng bước | `raw`: câu khách nói | dict một dòng trace: `customer_text`, `agent_text`, `questions`, `facts_used`, `claims`, `tool_calls`, `latency`, `memory_writes`, `customer_input_mode`, `router`, `goals`, `guardrail`, `llm_usage`, `extractor`; lượt 1 có thêm `call_brief`, `call_brief_latency_ms` (`None` ở `call_1`) | `asr.itn.itn`, `perceive`, `extractor.customer_slots`, `extractor.analyze_agent`, `extractor.facts_used`, `router.route`, `_plan`, `gen.generate`, `render_offline`, `guardrails.collect_numbers`, `guardrails.check`, `_money_in_strings`, `_remember`, `mem.log_turn` |

### 4.3. Planner (code xác định, không để LLM chọn tool)

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `_plan(text, slots, route)` [:397](../harness/agent.py#L397) | Bộ lập kế hoạch. Từ intent + cờ của router và các regex trên câu khách, chọn goals và gọi tool để lấy facts. Thứ tự xử lý: (1) cập nhật `known`; SĐT chung → `ask_identity`; (2) sản phẩm khách nhắc, "màng lọc", "còn mẫu X" (so sánh), "lấy / thêm / chốt" (vào giỏ); (3) lượt 1 của khách quay lại → `opening_returning` (+ `stale_promo`); (4) an toàn: hỏi máy hay người → `is_bot`; xóa dữ liệu → `data_deleted` (xóa bộ nhớ, dừng); y tế / ngoài phạm vi → `handoff` (dừng); hỏi giá nhập → `refuse_internal`; (5) đơn đã mua: đổi địa chỉ, đổi/trả (`_plan_order_change`, quá hạn → `exchange_window_passed` rồi tư vấn mua mới), trạng thái đơn → `order_status` (dừng); (6) chính sách → `policy_answer` / `no_info`; hỏi bảo hành → `product_warranty` đúng sản phẩm; (7) chưa có sản phẩm → `_recommend` (`ask_need` / `recommend` / `ask_product`); (8) báo giá: hỏi size trước nếu giá/KM phụ thuộc size, mẫu ngừng bán → mẫu thay thế, so sánh → `alternative_quote`, hết hàng → `out_of_stock`, khách nhắc giá cũ của KM đã hết → `explain_price_change`; (9) tổng giỏ, COD; (10) mặc cả → `no_competitor_comment` / `refuse_discount`; (11) chốt đơn khi khách đồng ý và không còn đang hỏi (`agrees_to_buy` ≥ 0,5), báo trước nếu giá đổi; (12) hẹn gọi lại / trì hoãn; (13) không khớp nhánh nào → `greet` (lượt 1), `ask_repeat` (khách đang hỏi hoặc câu ASR mà router không chắc, tối đa 2 lần), còn lại `closing` | câu đã chuẩn hóa, slot khách vừa nói, kết quả router | `(goals, facts)` (goals đã khử trùng) | `find_products`, `find_by_model_token`, `fold`, `product_name`, `knowledge.search`, `mem.forget_customer`, `tools.call("handoff.transfer" / "order.status")`, và các hàm `_…` dưới đây |
| `_recommend(text)` [:375](../harness/agent.py#L375) | Chọn sản phẩm gợi ý trong ngành hàng: bỏ mẫu dưới 400.000đ, hết hàng, hoặc diện tích nhỏ hơn phòng khách; ưu tiên khóa trẻ em khi có trẻ nhỏ, trừ điểm khi vượt ngân sách 10%. Máy lọc không khí mà chưa biết trẻ nhỏ / ngân sách → hỏi nhu cầu trước | câu khách | mã sản phẩm; `"ASK_NEED"`; `None` | `mt.catalog_search`, `tools.call("inventory.check")` |
| `_quote(sku, role, basket)` [:346](../harness/agent.py#L346) | Lấy giá + tồn kho của một sản phẩm, gom thành một báo giá (bỏ trường nội bộ, bỏ KM phí ship), ghi vào `self.quote` nếu là sản phẩm chính, thêm vào `discussed`, lưu báo giá vào bộ nhớ | `sku`; `role` = `advised` / `chosen` / `alternative`; `basket` = sản phẩm khác cùng đơn (KM máy thứ 2) | dict `{sku, name, list_price_vnd, final_price_vnd, promo_codes, promo_names, promo_end, freeship, expired_promos, in_stock, restock_expected, discontinued, successor_sku, attributes}` | `tools.call("pricing.get_quote" / "inventory.check")`, `public_view`, `product_name`, `mt._parent`, `mt.PROMOS`, `mem.add_quote` |

### 4.4. Giỏ hàng và biến thể

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `_cart_add(sku)` [:611](../harness/agent.py#L611) | Thêm vào giỏ; mỗi dòng sản phẩm (mã cha) chỉ giữ một biến thể | `sku` | không. Ghi `cart` | `mt._parent` |
| `_resolve_variant(sku, text)` [:616](../harness/agent.py#L616) | Đổi mã cha thành mã biến thể theo size/màu trong câu hoặc đã nhớ | `sku`, câu | mã biến thể, hoặc chính `sku` | `mt._parent`, `find_variant` |
| `_price_depends_on_size(sku, text)` [:622](../harness/agent.py#L622) | Có cần biết size trước khi báo giá không: sản phẩm có biến thể, chưa rõ size, và có phụ thu size lớn hoặc KM loại trừ size | `sku`, câu | `True` / `False` | `mt._parent`, `_resolve_variant`, `_promo_depends_on_size` |
| `_promo_depends_on_size(sku)` [:629](../harness/agent.py#L629) | Sản phẩm có KM loại trừ một số size (`exclude_variant_size`) không | `sku` | `True` / `False` | `mt._parent`, `mt.PROMOS` |
| `_cart_quote(text)` [:637](../harness/agent.py#L637) | Báo giá từng món trong giỏ (mỗi món truyền các món còn lại làm `basket`) và tính tổng | câu | `{items, total_vnd, budget_vnd}` | `_resolve_variant`, `_quote` |

### 4.5. Đơn hàng và hẹn gọi lại

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `_plan_order(text, facts)` [:651](../harness/agent.py#L651) | Lên đơn. Kiểm lần lượt: có sản phẩm → đã rõ biến thể → chưa đặt trùng → địa chỉ cũ quá hạn (hỏi xác nhận một lần, lần sau khách nhắc "địa chỉ cũ" là đồng ý) → còn hàng → COD không quá 10 triệu. Rồi gọi `order.create` từng món với **giá lấy từ báo giá của tool**; lệch giá thì gọi lại một lần với giá tool yêu cầu. Thành công: nhớ `product_chosen`, `order_id`, `variant_sku`, `estimated_delivery`, đặt `outcome = chot_don` | câu; `facts` (được ghi thêm) | goals: `order_created` (+ `ask_address`), hoặc `ask_product`, `ask_variant`, `order_exists`, `confirm_old_address`, `out_of_stock`, `cod_limit`, `order_failed` | `_resolve_variant`, `_quote`, `product_name`, `tools.call("order.create")` |
| `_update_address(address, facts)` [:643](../harness/agent.py#L643) | Đổi địa chỉ cho các đơn vừa tạo trong cuộc. Tool không có tham số địa chỉ (CAU-HOI-BTC B4) nên địa chỉ mới đi trong `reason` | địa chỉ; `facts` | `["address_updated"]` | `tools.call("order.update")` |
| `_customer_orders()` [:715](../harness/agent.py#L715) | Danh sách đơn của khách | không | list đơn | `tools.call("order.status")` |
| `_plan_order_change(text, facts)` [:720](../harness/agent.py#L720) | Đổi size, đổi sản phẩm, trả hàng, hỏi địa chỉ giao. Chọn đơn khớp sản phẩm đã nhớ (không có thì đơn cuối); quá hạn đổi trả (> 11 ngày từ ngày đặt ≈ 7 ngày từ ngày nhận) → `WINDOW_PASSED`; hỏi địa chỉ → `confirm_delivery_address`; trả hàng → `order.update(return)`; đổi size / sản phẩm: khách đang hỏi mà chưa đồng ý → báo trước (`exchange_offer`), đồng ý → tạo yêu cầu; khách xác nhận lại → không tạo yêu cầu lần hai | câu; `facts` | goals: `order_updated`, `exchange_offer`, `ask_new_size`, `ask_variant`, `confirm_delivery_address`, `policy_answer`, `order_not_found`, `out_of_stock`, `order_failed`, hoặc `["WINDOW_PASSED"]` | `_customer_orders`, `knowledge.search`, `find_products`, `find_variant`, `product_name`, `public_view`, `tools.call("order.update" / "inventory.check")` |
| `_plan_callback(when, facts)` [:783](../harness/agent.py#L783) | Đặt lịch gọi lại; rơi vào ngày nghỉ hoặc Chủ nhật thì dời sang ngày kế và ghi lý do | `when` = `"2026-10-20T09:00"`; `facts` | `["callback_scheduled"]` | `mt.HOLIDAYS`, `tools.call("schedule.callback")` |

### 4.6. Tóm tắt, bàn giao, ghi nhớ, đóng cuộc gọi

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `_summary_facts()` [:799](../harness/agent.py#L799) | Gom dữ kiện có cấu trúc (khách, sản phẩm, giá, KM, đơn, rào cản, hẹn, kết quả, câu chưa trả lời) để LLM viết tóm tắt; LLM chỉ được viết lại những thứ này | không | dict | `product_name` |
| `_handoff_brief(text, reason)` [:814](../harness/agent.py#L814) | Dựng bản tóm tắt bàn giao khi chuyển máy theo `schemas/handoff_brief.schema.json`. Câu tóm tắt do LLM viết nếu `HANDOFF_SUMMARY` cho phép và qua kiểm số tiền; không thì ghép 6 lượt gần nhất | câu hỏi của khách; lý do chuyển | dict `customer_phone`, `customer_name`, `customer_id`, `channel`, `escalation_reason`, `conversation_summary`, `summary_source`, `product_advised`, `price_quoted_vnd`, `facts_confirmed`, `open_questions`, `sentiment`, `next_action`, `history_refs`… | `core.llm.summarizer.summarize`, `_summary_facts`, `product_name` |
| `_remember(slots, route)` [:838](../harness/agent.py#L838) | Ghi fact của lượt: slot khách vừa nói (trừ tên tự xưng, giá khách nêu), sản phẩm + giá + KM đang bàn, đơn vừa tạo. Chưa nhận diện / đang chờ xưng tên / đã xóa dữ liệu → không ghi (lượt xóa ghi một dòng `op: delete`) | slot khách; `route` (không dùng) | list `{key, value, op, source, customer_id, previous}` cho `memory_writes` | `mem.write_fact`, `mt._parent` |
| `end()` [:864](../harness/agent.py#L864) | Lưu tóm tắt phiên (precompute cho Call Brief lần sau): câu ghép từ dữ liệu, thay bằng câu LLM nếu qua kiểm; kèm rào cản (nếu chưa chốt), câu chưa trả lời, hành động tiếp theo. Bỏ qua khi chưa nhận diện hoặc khách đã yêu cầu xóa | không | không | `product_name`, `core.llm.summarizer.summarize`, `mem.add_session` |

## 5. Hàm ở file khác mà `agent.py` gọi

| File | Hàm được gọi | Bảng tra |
|---|---|---|
| `harness/textnorm.py` | `perceive`, `find_money`, `fold` | [HAM-TEXTNORM](HAM-TEXTNORM.md) |
| `harness/extractor.py` | `customer_slots`, `analyze_agent`, `facts_used` | [HAM-EXTRACTOR](HAM-EXTRACTOR.md) |
| `harness/guardrails.py` | `collect_numbers`, `check` | [HAM-GUARDRAILS](HAM-GUARDRAILS.md) |
| `harness/knowledge.py` | `search`, biến `spent_ms` | [HAM-KNOWLEDGE](HAM-KNOWLEDGE.md) |
| `harness/tools.py` | `ToolBox`, `find_products`, `find_variant`, `find_by_model_token`, `product_name`, `public_view`, `mt` | [HAM-TOOLS](HAM-TOOLS.md) |
| `harness/memory.py` | mọi phương thức của `Memory` / `RemoteMemory` qua `self.mem` | [HAM-MEMORY](HAM-MEMORY.md) |
| `asr/itn.py` | `itn` (chỉ khi đầu vào là ASR) | |
| `core/llm/router.py`, `generator.py`, `summarizer.py` | `Router.route`, `Generator.generate`, `render_offline`, `summarize` | [HARNESS.md](HARNESS.md) |

### Chín tool của BTC mà agent gọi qua `ToolBox.call`

| Tool | Trường agent đọc trong kết quả | Gọi từ |
|---|---|---|
| `crm.get_customer` | `found`, `ambiguous`, `candidates`, `customer_id`, `name`, `honorific`, `phone`, `identities`, `sessions` | `start`, `turn`, `_resolve_candidate` |
| `pricing.get_quote` | `list_price_vnd`, `final_price_vnd`, `applied_promos`, `expired_promos`, `freeship` | `_build_brief`, `_quote` |
| `inventory.check` | `in_stock`, `restock_expected`, `discontinued`, `successor_sku` | `_build_brief`, `_quote`, `_recommend`, `_plan_order_change` |
| `catalog.search` | `items` (`sku`, `list_price_vnd`, `attributes`) | `_recommend` (gọi thẳng `mt.catalog_search`, tự ghi log tool) |
| `order.create` | `order_id`, `total_vnd`, `estimated_delivery`; lỗi: `error`, `expected_price_vnd` | `_plan_order` |
| `order.update` | `error`, `restock_expected`; còn lại đưa nguyên vào `facts["update"]` | `_update_address`, `_plan_order_change` |
| `order.status` | `orders` (`order_id`, `sku`, `status`, `tracking`, `created_on`, `estimated_delivery`, `address`) | `_build_brief`, `_plan`, `_customer_orders` |
| `schedule.callback` | đưa nguyên vào `facts["callback"]` | `_plan_callback` |
| `handoff.transfer` | đưa nguyên vào `facts["handoff"]` | `_plan` |

`order.update` được gọi với bốn `action`: `update_address`, `return`, `exchange_size`, `exchange_product`.

## 6. Ghi chú khi đọc code

- **Tham số và biến không dùng:** `route` trong `_remember`; biến `full` trong `_resolve_candidate` (lời gọi CRM vẫn vào trace); biến `out` trong `_update_address`; trường `self.blockers` và `self.config`.
- **`catalog.search` không đi qua `ToolBox.call`.** `_recommend` gọi thẳng hàm của BTC rồi tự thêm một dòng vào log tool, nên ở chế độ MCP lời gọi này không qua `mcp-commerce`.
- **`_plan` dựa vào nhiều regex trên câu khách** (ví dụ "lấy", "chốt", "COD", "địa chỉ cũ"), không chỉ kết quả router. Ngưỡng chốt đơn là `agrees_to_buy ≥ 0,5`: cờ sát ngưỡng có thể làm lên đơn sớm (GEN-T16, [SO-SANH-2026-10-15.md](SO-SANH-2026-10-15.md)).
- **Sau `return`, câu "ok làm thủ tục" rơi vào nhánh đổi size** và sinh `ask_new_size` (GEN-T12-02, SO-SANH mục 7.1).
- **Tập số được phép gồm cả giá đã báo ở phiên trước** (`prev_quotes`), nên guardrail không chặn được việc đọc giá KM cũ thành giá hiện tại (SAMPLE-05, SO-SANH mục 7.1).
- **Bảng `turns` chỉ được ghi** (`mem.log_turn`); không hàm nào đọc lại.
