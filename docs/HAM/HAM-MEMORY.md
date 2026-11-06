# Bảng tra hàm của `harness/memory.py`

[harness/memory.py](../harness/memory.py) là **bộ nhớ dài hạn của khách hàng**: hồ sơ và định danh đa kênh, phiên (episodic), fact (profile), báo giá, lượt thoại. Viết bằng SQLAlchemy Core, chạy trên SQLite (mặc định `data/memory.db`) hoặc PostgreSQL (`DATABASE_URL`).

Ba nguyên tắc:
- **Namespace:** mọi bảng có cột `ns` = `<run_id>:<config>:<scenario_id>`, nên nhiều kịch bản và nhiều lần chạy dùng chung một DB mà không nhiễm chéo.
- **Không ghi đè fact:** khách đổi ý thì fact cũ chuyển `superseded` và trỏ sang fact mới. Không bao giờ có hai giá trị `current` cho cùng một slot.
- **Baseline:** `read_enabled = False` làm ba hàm đọc phiên trước (`past_sessions`, `current_facts`, `past_quotes`) luôn trả rỗng; ghi vẫn chạy bình thường.

Hai lớp cùng giao diện: `Memory` (gọi SQL trực tiếp) và `RemoteMemory` (đi qua MCP server `mcp-memory`). `open_memory()` chọn theo `TOOL_TRANSPORT`. Số dòng ứng với code ngày 17/10/2026.

**Ai dùng file này:** `harness/agent.py` (qua `self.mem`), `run_eval.py` (`open_memory`, `engine`), `mcp_servers/memory_server.py` (bọc `Memory` thành tool MCP).

## 1. Bảng SQL và hằng số

| Tên | Cột chính | Ý nghĩa |
|---|---|---|
| `customers` [:17](../harness/memory.py#L17) | `ns`, `customer_id`, `name`, `honorific`, `phone`, `status` | Hồ sơ khách; `status`: `active`, `merged`, `deletion_requested` |
| `identities` [:21](../harness/memory.py#L21) | `ns`, `kind`, `value`, `customer_id` | Định danh (`phone`, `zalo_id`, `fb_id`); một SĐT có thể thuộc nhiều khách |
| `sessions` [:24](../harness/memory.py#L24) | `session_id`, `customer_id`, `channel`, `started_on`, `outcome`, `summary`, `blockers_json`, `next_action`, `source`, `open_questions_json` | Tóm tắt từng cuộc gọi (episodic); `source` = `harness` hoặc `crm` |
| `turns` [:30](../harness/memory.py#L30) | `session_id`, `turn`, `customer_text`, `agent_text`, `state_json` | Từng lượt thoại (working memory) |
| `facts` [:34](../harness/memory.py#L34) | `fact_id`, `customer_id`, `slot`, `value_json`, `confidence`, `source`, `session_id`, `valid_from`, `expires_on`, `superseded_by`, `status` | Fact profile có nguồn gốc (`call_1#turn3`) và hạn dùng |
| `quotes` [:40](../harness/memory.py#L40) | `customer_id`, `session_id`, `sku`, `role`, `list_price_vnd`, `final_price_vnd`, `promo_code`, `promo_end`, `quoted_on` | Lịch sử báo giá, để Call Brief phát hiện KM hết hạn / giá đổi |
| `TTL_DAYS` [:47](../harness/memory.py#L47) | | Hạn dùng theo slot (ngày): diện tích, trẻ nhỏ 365; size, màu, địa chỉ, thanh toán 180; ngân sách 90; sản phẩm đã tư vấn 60; giá đã báo, rào cản 30; hẹn gọi lại 14; slot khác 90 |
| `_engine` [:50](../harness/memory.py#L50) | | Engine dùng chung trong tiến trình (tạo lười) |
| `_EMPTY` [:229](../harness/memory.py#L229) | | Giá trị trả về khi `RemoteMemory` lỗi: coi như "chưa có gì" |

## 2. Hàm cấp module

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `engine()` [:53](../harness/memory.py#L53) | Tạo engine theo `DATABASE_URL` (SQLite: tạo thư mục, timeout 30 s; Postgres: `pool_pre_ping`), tạo bảng, nâng cấp DB cũ | không | `Engine` | `create_engine`, `meta.create_all`, `_migrate` |
| `_migrate(e)` [:66](../harness/memory.py#L66) | `create_all` không thêm cột vào bảng đã có, nên thêm bằng `ALTER TABLE` (hiện là `sessions.open_questions_json`) | engine | không | |
| `open_memory(ns, read_enabled)` [:273](../harness/memory.py#L273) | Chọn `RemoteMemory` (`TOOL_TRANSPORT=mcp`) hoặc `Memory` (`direct`) | namespace; có đọc phiên trước không | `Memory` / `RemoteMemory` | |

## 3. Lớp `Memory`

| Hàm | Chức năng | Đầu vào | Đầu ra | Bảng |
|---|---|---|---|---|
| `__init__(ns, read_enabled)` [:79](../harness/memory.py#L79) | Gắn namespace, cờ đọc và engine | namespace; cờ đọc | không | |
| `wipe()` [:83](../harness/memory.py#L83) | Xóa mọi dữ liệu của namespace (khi bắt đầu chạy lại một kịch bản) | không | không | cả 6 bảng |
| `upsert_customer(customer_id, name, honorific, phone, identities_)` [:89](../harness/memory.py#L89) | Tạo hồ sơ nếu chưa có (không cập nhật hồ sơ đã có), gắn thêm định danh chưa có | mã khách; thông tin; list `(kind, value)` | không | `customers`, `identities` |
| `lookup(kind, value)` [:99](../harness/memory.py#L99) | Tìm khách theo định danh | `phone` / `zalo_id` / `fb_id`; giá trị | list mã khách | `identities` |
| `set_status(customer_id, status)` [:104](../harness/memory.py#L104) | Đổi trạng thái hồ sơ | mã khách; trạng thái | không | `customers` |
| `add_session(session_id, customer_id, channel, started_on, outcome, summary, blockers, next_action, source, open_questions)` [:109](../harness/memory.py#L109) | Lưu hoặc ghi đè tóm tắt một phiên | như tên tham số | không | `sessions` |
| `past_sessions(customer_id, before_session)` [:118](../harness/memory.py#L118) | Các phiên của khách, cũ đến mới, bỏ phiên `before_session`; kèm `open_questions` đã giải mã. Baseline → `[]` | mã khách; mã phiên bỏ qua | list dict phiên | `sessions` |
| `log_turn(session_id, turn, customer_text, agent_text, state)` [:133](../harness/memory.py#L133) | Lưu một lượt thoại | như tên tham số | không | `turns` |
| `current_facts(customer_id, today, include_expired)` [:139](../harness/memory.py#L139) | Fact `current` của khách; đánh dấu `expired` khi `expires_on < today`, bỏ fact quá hạn trừ khi `include_expired`. Baseline → `{}` | mã khách; ngày; có lấy fact quá hạn không | `{slot: {value, source, fact_id, expires_on, expired, session_id}}` | `facts` |
| `write_fact(customer_id, slot, value, source, session_id, today, confidence, valid_from)` [:155](../harness/memory.py#L155) | Ghi một fact. Giá trị trùng fact hiện hành → không làm gì. Khác → thêm dòng mới với `expires_on = valid_from + TTL`, dòng cũ chuyển `superseded` | như tên tham số; `source` dạng `call_1#turn2`; `valid_from` mặc định là `today` | `{key, value, op: set/supersede, source, customer_id, previous}`, hoặc `None` | `facts` |
| `status(customer_id)` [:177](../harness/memory.py#L177) | Trạng thái hồ sơ | mã khách | chuỗi / `None` | `customers` |
| `forget_customer(customer_id)` [:182](../harness/memory.py#L182) | Yêu cầu xóa dữ liệu: xóa phiên, fact, báo giá; đánh dấu hồ sơ `deletion_requested` (giữ dấu vết yêu cầu) | mã khách | không | `sessions`, `facts`, `quotes`, `customers` |
| `add_quote(customer_id, session_id, sku, role, list_price, final_price, promo_code, promo_end, quoted_on)` [:191](../harness/memory.py#L191) | Lưu một lần báo giá | như tên tham số | không | `quotes` |
| `past_quotes(customer_id)` [:197](../harness/memory.py#L197) | Các báo giá đã lưu, theo thứ tự ghi. Baseline → `[]` | mã khách | list dict báo giá | `quotes` |
| `merge_customer(src, dst)` [:204](../harness/memory.py#L204) | Gộp hồ sơ tạm vào hồ sơ chính (identity resolution): chuyển fact, báo giá, phiên, định danh sang `dst`; đánh dấu `src` là `merged`; hai fact `current` cùng slot thì giữ fact mới hơn | mã nguồn; mã đích | không | `facts`, `quotes`, `sessions`, `identities`, `customers` |

## 4. Lớp `RemoteMemory`

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `__init__(ns, read_enabled)` [:240](../harness/memory.py#L240) | Gắn namespace, cờ đọc và mở kết nối tới `mcp-memory` | namespace; cờ đọc | không | `mcp_client.connection("memory")` |
| `_call(method, *args, **kwargs)` [:245](../harness/memory.py#L245) | Ánh xạ tham số theo chữ ký của `Memory.<method>`, đổi tuple thành list cho JSON, gọi tool `memory.<method>` kèm `ns` và `read_enabled`. Lỗi → thử lại 1 lần; vẫn lỗi → log ERROR, tăng `RemoteMemory.errors`, trả giá trị trong `_EMPTY`, cuộc gọi tiếp tục như khách chưa có bộ nhớ. Riêng `wipe` vẫn ném lỗi | tên phương thức; tham số | kết quả của tool | `McpConnection.call` |
| 14 phương thức công khai [:268](../harness/memory.py#L268) | `wipe`, `upsert_customer`, `lookup`, `set_status`, `add_session`, `past_sessions`, `log_turn`, `current_facts`, `write_fact`, `status`, `forget_customer`, `add_quote`, `past_quotes`, `merge_customer`, sinh tự động bằng vòng `for`, mỗi cái gọi `_call` cùng tên | như `Memory` | như `Memory` | `_call` |

## 5. Ghi chú khi đọc code

- **Baseline vẫn tra được định danh và trạng thái** (`lookup`, `status` không xét `read_enabled`), đúng điều kiện đề: baseline chỉ khác ở việc không nạp bộ nhớ phiên trước.
- **`set_status` và `RemoteMemory.errors` không được agent dùng;** `set_status` có trên `mcp-memory` để giao diện / QA dùng.
- **Không lưu CCCD / STK:** chúng bị che từ `textnorm.perceive` trước khi trích slot, nên không bao giờ tới `write_fact`. SĐT và địa chỉ được lưu nguyên vì nghiệp vụ cần.
- **`upsert_customer` không cập nhật tên / xưng hô của hồ sơ đã có.**
