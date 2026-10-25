# Bảng tra hàm của `harness/tools.py`

[harness/tools.py](../harness/tools.py) làm hai việc:

1. **Lớp tool `ToolBox`:** bọc [eval/mock_tools.py](../eval/mock_tools.py) của BTC (logic tham chiếu), giữ đúng tên tool và tham số trong `schemas/tools.schema.json`. Mọi lời gọi đi qua `ToolBox.call()` để gắn ngày cuộc gọi, ghi log cho trace, bắt lỗi tool, và chọn đường đi: qua MCP server `mcp-commerce` (`TOOL_TRANSPORT=mcp`, mặc định) hoặc gọi hàm trực tiếp (`direct`). Hai đường cho cùng kết quả (`tests/mcp_parity.py`).
2. **Nhận diện sản phẩm trong câu nói:** tên sản phẩm (kể cả cách đọc kiểu ASR: "e pia", "xiao mi", "sờ mát"), biến thể theo size / màu, "còn mẫu X thì sao".

Dữ liệu catalog **tĩnh** (tên, biến thể, danh sách KM, ngày nghỉ) đọc trực tiếp từ `mt` để hiểu câu khách. Mọi thao tác có trạng thái hoặc phụ thuộc ngày (giá, tồn kho, đơn, lịch, chuyển máy, CRM) đi qua tool. Số dòng ứng với code ngày 17/10/2026.

**Ai dùng file này:** `harness/agent.py` (gần như mọi hàm), `extractor.py` (`find_color`, `find_products`, `mt`, `product_name`), `llm_extract.py` (`find_color`), `rag.py` (`find_products`), `run_eval.py` (`ToolBox.reset_world`), `datagen/`, `asr/`, `tests/mcp_check.py` (`mt`).

## 1. Hằng số và biến

| Tên | Ý nghĩa |
|---|---|
| `mt` [:19](../harness/tools.py#L19) | Module `eval/mock_tools.py` của BTC, nạp trực tiếp. Agent dùng `mt._parent(sku)`, `mt.PRODUCTS`, `mt.PROMOS`, `mt.HOLIDAYS`, `mt.catalog_search()`, `mt.TOOLS` |
| `DATED` [:22](../harness/tools.py#L22) | Tool phụ thuộc ngày, tự gắn `on` = ngày cuộc gọi: `inventory.check`, `pricing.get_quote`, `order.create`, `order.update` |
| `NAME_PREFIXES` [:64](../harness/tools.py#L64) | Tiền tố loại sản phẩm ("máy lọc không khí", "giày chạy bộ"…), bỏ đi để có tên ngắn ("AirPure X") |
| `SPOKEN` [:67](../harness/tools.py#L67) | Cách đọc / ASR của thương hiệu: "airpure" → "e pia", "xiaomi" → "xiao mi", "smart" → "sờ mát", "pro" → "pờ rô"… |
| `COLORS` [:70](../harness/tools.py#L70) | Mã màu → các cách nói ("navy" ← "navy / xanh navy / xanh than") |
| `_INDEX` [:100](../harness/tools.py#L100) | Mọi alias của mọi sản phẩm, sắp theo độ dài giảm dần (khớp alias dài trước) |
| `_DIGITS` [:103](../harness/tools.py#L103) | Chữ số đọc bằng chữ (bỏ dấu) → chữ số |

## 2. Lớp `ToolBox`

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `__init__(today)` [:26](../harness/tools.py#L26) | Gắn ngày cuộc gọi; `log` = các tool gọi chưa lấy ra | ngày cuộc gọi | không | |
| `reset_world()` [:31](../harness/tools.py#L31) | Xóa trạng thái runtime của mock giữa các kịch bản: đơn mới, lịch gọi lại, ticket, KM một lần mỗi khách. Ở MCP gọi tool `world.reset` | không | không | `mcp_client.connection("commerce")` hoặc `mt._ORDERS` / `_CALLBACKS` / `_TICKETS` / `_ONCE_USED` |
| `call(name, **args)` [:39](../harness/tools.py#L39) | Gọi một tool: bỏ tham số `None`, gắn `on` cho tool trong `DATED`, gọi qua MCP hoặc trực tiếp. **Tool lỗi không làm sập cuộc gọi:** trả `{"error": "tool_exception", "detail": …}`. Ghi `{name, args, result, ms}` vào `log` | tên tool; tham số | kết quả của tool | `McpConnection.call` hoặc `mt.TOOLS[name]` |
| `take_log()` [:58](../harness/tools.py#L58) | Lấy và xóa danh sách tool đã gọi từ lần lấy trước (thành `tool_calls` của trace) | không | list `{name, args, result, ms}` | |

## 3. Nhận diện sản phẩm

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `_aliases(p)` [:74](../harness/tools.py#L74) | Sinh mọi cách gọi một sản phẩm: tên đầy đủ, tên ngắn (bỏ `NAME_PREFIXES`), mã SKU, cách đọc thương hiệu (`SPOKEN`), tên bắt đầu từ thương hiệu ("karofi 9 lõi"), tên bỏ "smart / inverter" ("xiaomi 4 pro"); trả dạng `fold`, chỉ giữ alias ≥ 3 ký tự | sản phẩm của catalog | set alias | `fold` |
| `_spoken_digits(f)` [:106](../harness/tools.py#L106) | Đổi chữ số đọc bằng chữ thành chữ số trong câu đã bỏ dấu ("ka ro phi chin loi" → "ka ro phi 9 loi") | câu đã `fold` | chuỗi | |
| `find_products(text)` [:111](../harness/tools.py#L111) | Các SKU cha được nhắc trong câu, theo thứ tự xuất hiện. Khớp alias dài nhất trước, không khớp chồng lên đoạn đã khớp, có ranh giới từ | câu | list mã SKU cha | `fold`, `_spoken_digits`, `_INDEX` |
| `find_variant(sku, text, fallback_size, fallback_color)` [:127](../harness/tools.py#L127) | Chọn biến thể theo size và màu. Bỏ địa chỉ khỏi câu trước khi tìm size (số nhà "41 Trần Hưng Đạo" không phải size 41); size dạng "size / cỡ / số + giá trị", hoặc số trần 35–46 nếu sản phẩm có size đó; thiếu thì dùng giá trị đã nhớ | mã cha; câu; size / màu dự phòng | mã biến thể; chính `sku` nếu sản phẩm không có biến thể; `None` nếu chưa xác định được | `mt._parent`, `extractor.ADDRESS_RX`, `find_color` |
| `find_color(text, prefix)` [:145](../harness/tools.py#L145) | Mã màu nhắc trong câu, khớp cụm dài nhất ("xanh navy" là `navy`, không phải `xanh`). `prefix="mau "` để bắt buộc có chữ "màu" | câu; tiền tố | mã màu / `None` | `fold` |
| `product_name(sku)` [:155](../harness/tools.py#L155) | Mã → tên đọc được, kèm size và màu nếu là biến thể | mã | chuỗi (mã không có trong catalog thì trả chính mã) | `mt._parent` |
| `find_by_model_token(text, family_sku)` [:162](../harness/tools.py#L162) | Hiểu câu "còn mẫu X thì sao" khi đang nói về một sản phẩm: tìm sản phẩm cùng hãng, cùng ngành, có từ cuối của tên trùng `X` | câu; mã sản phẩm đang bàn | mã / `None` | `mt._parent`, `mt.PRODUCTS`, `fold` |
| `public_view(result)` [:175](../harness/tools.py#L175) | Bỏ trường nội bộ (tên bắt đầu bằng `_`, ví dụ `_internal_price_floor_vnd` = giá sàn) trước khi đưa kết quả tool cho LLM hoặc lưu | dict / list | bản sao đã lọc | gọi đệ quy chính nó |

## 4. Ghi chú khi đọc code

- **`find_variant` trả `None`** khi sản phẩm có nhiều biến thể khớp mà chưa đủ size **và** màu; `agent._resolve_variant` khi đó giữ mã cha và planner hỏi biến thể (`ask_variant`).
- **Lỗi tool về đến planner dưới dạng dict có `error`,** không phải ngoại lệ; planner chuyển thành goal `order_failed` / `out_of_stock`, và câu mẫu không đọc mã lỗi cho khách.
- **`harness/agent.py` và file này đọc thẳng thành phần nội bộ của `mock_tools`** (`_parent`, `PRODUCTS`, `PROMOS`, `HOLIDAYS`, `_ORDERS`…). BTC phát bản vá đổi tên thì phải sửa theo ([PLAN.md](PLAN.md) mục 2).
