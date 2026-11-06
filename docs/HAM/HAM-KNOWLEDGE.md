# Bảng tra hàm của `harness/knowledge.py`

[harness/knowledge.py](../harness/knowledge.py) là lớp mỏng mà agent dùng để **tra chính sách**. Nó chuyển tiếp sang [harness/rag.py](../harness/rag.py) ([HAM-RAG](HAM-RAG.md)) và đo thời gian tra cứu để ghi vào `latency.parts.plan_rag_ms` của trace.

Ba luật an toàn nằm ở `rag.py` và áp trước khi xếp hạng: tài liệu hết hiệu lực chỉ dùng cho đơn cũ; tài liệu nội bộ không bao giờ trả cho LLM sinh lời; tài liệu nhiễu bị loại. Máy không có model embedding thì `rag.py` tự lùi về BM25. Số dòng ứng với code ngày 17/10/2026.

**Ai dùng file này:** `harness/agent.py` (`search`, `spent_ms`), `run_eval.py` (một truy vấn khởi động để nạp model embedding trước lượt đầu).

## 1. Biến cấp module

| Tên | Ý nghĩa |
|---|---|
| `CHUNKS` [:13](../harness/knowledge.py#L13) | Bí danh của `rag.CHUNKS` (99 chunk `[XX-nn]` của `policy/`) |
| `spent_ms` [:14](../harness/knowledge.py#L14) | Tổng thời gian tra cứu kể từ lần đặt lại gần nhất. `agent.turn()` đặt về 0 trước `_plan`, đọc lại sau đó |

## 2. Hàm

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `search(query, k, include_restricted, order_date)` [:17](../harness/knowledge.py#L17) | Tra chính sách và cộng thời gian vào `spent_ms` (kể cả khi lỗi) | câu hỏi; số kết quả (mặc định 3); có trả tài liệu nội bộ không (mặc định không); ngày đơn (để dùng chính sách cũ) | list chunk, mỗi chunk có `chunk_id`, `doc`, `title`, `text`, `score`… | `rag.search` |

## 3. Ghi chú khi đọc code

- **Agent chưa bao giờ truyền `order_date`,** nên luôn trả lời theo chính sách đang hiệu lực, kể cả khi khách hỏi về đơn đặt trước 01/10/2026 (giới hạn đã ghi ở [HARNESS.md](HARNESS.md)).
- `agent.py` chỉ cắt 600 ký tự đầu của mỗi chunk khi đưa vào FACTS.
