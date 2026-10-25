# Bảng tra hàm của `harness/mcp_client.py`

[harness/mcp_client.py](../harness/mcp_client.py) là **client MCP đồng bộ** để harness gọi hai MCP server:

- `mcp-commerce` ([mcp_servers/commerce_server.py](../mcp_servers/commerce_server.py)): 9 tool của BTC + `world.reset`;
- `mcp-memory` ([mcp_servers/memory_server.py](../mcp_servers/memory_server.py)): đọc / ghi bộ nhớ khách hàng.

Harness viết đồng bộ còn MCP SDK là async. Vì vậy mỗi server chạy thành **tiến trình con** (stdio), và một **thread riêng** giữ event loop + `ClientSession` sống suốt tiến trình harness; `call()` gửi coroutine sang loop đó rồi chờ kết quả. Kết nối tạo lười và tách theo PID, nên khi `run_eval.py --workers N` tạo nhiều tiến trình, mỗi worker tự mở server riêng và trạng thái mock không lẫn nhau. Số dòng ứng với code ngày 17/10/2026.

**Ai dùng file này:** `harness/tools.py` (`ToolBox.call`, `ToolBox.reset_world`), `harness/memory.py` (`RemoteMemory`), `tests/mcp_check.py`. Chỉ dùng khi `TOOL_TRANSPORT=mcp`.

## 1. Biến và lớp

| Tên | Ý nghĩa |
|---|---|
| `SERVERS` [:18](../harness/mcp_client.py#L18) | Tên server → đường dẫn script: `commerce`, `memory` |
| `_conns` [:20](../harness/mcp_client.py#L20) | Bộ nhớ đệm kết nối, khóa `(tên server, PID)` |
| `McpToolError` [:23](../harness/mcp_client.py#L23) | Lỗi khi tool trả `isError = True`; thông điệp dạng `<TênLỗi>: <chi tiết>` như ngoại lệ gốc phía server |

## 2. Hàm

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `McpConnection.__init__(name, script, env)` [:28](../harness/mcp_client.py#L28) | Tạo event loop trên thread riêng; khởi động server bằng `python <script>` (cwd = gốc repo, `PYTHONPATH` = gốc repo); mở `ClientSession`, `initialize`, lấy danh sách tool. Chờ tối đa `MCP_TIMEOUT_S`; không kịp thì ném `RuntimeError` kèm lỗi gốc | tên server; đường dẫn script; biến môi trường thêm | không (kết nối sẵn sàng; `self.tools` = tên các tool) | `mcp.ClientSession`, `mcp.client.stdio.stdio_client` |
| `McpConnection.call(tool, args)` [:57](../harness/mcp_client.py#L57) | Gọi một tool, chờ tối đa `MCP_TIMEOUT_S`. Ghép phần text của kết quả; `isError` → ném `McpToolError`; còn lại parse JSON | tên tool; dict tham số | kết quả đã parse (dict / list / `None`) | `ClientSession.call_tool` |
| `McpConnection.close()` [:65](../harness/mcp_client.py#L65) | Báo task chính dừng (đóng session và tiến trình con trong cùng task, theo yêu cầu của anyio), chờ tối đa 5 giây, rồi dừng event loop | không | không | |
| `connection(name)` [:75](../harness/mcp_client.py#L75) | Lấy kết nối của tiến trình hiện tại, tạo mới nếu chưa có | `commerce` hoặc `memory` | `McpConnection` | `McpConnection` |
| `_close_all()` [:83](../harness/mcp_client.py#L83) | Đăng ký `atexit`: đóng mọi kết nối do tiến trình này mở | không | không | `McpConnection.close` |

## 3. Ghi chú khi đọc code

- **Mỗi worker một bộ server.** Trạng thái runtime của mock (đơn, lịch hẹn, ticket) sống trong tiến trình `mcp-commerce` và được xóa giữa các kịch bản bằng `world.reset`.
- **Độ trễ thêm của MCP:** trung vị khoảng 35 ms mỗi lượt, p95 khoảng 85 ms; trace qua MCP giống hệt gọi trực tiếp ([ARCHITECTURE.md](ARCHITECTURE.md) mục 4.5, `tests/mcp_parity.py`).
