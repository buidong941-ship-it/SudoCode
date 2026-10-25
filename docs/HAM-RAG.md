# Bảng tra hàm của `harness/rag.py`

[harness/rag.py](../harness/rag.py) là **RAG cho kho chính sách** `policy/`. Mỗi mục `## [XX-nn]` là một chunk, đúng `chunk_id` BTC dùng để gán nhãn Recall@k ([rag/qa_labeled.json](../rag/qa_labeled.json)), nên không cần ánh xạ. Tìm kiếm **lai**: vector (embedding) + BM25, gộp bằng RRF, tùy chọn xếp hạng lại bằng cross-encoder.

Ba luật áp **trước** khi xếp hạng (code quyết định, không để LLM):
- **Phiên bản:** tài liệu `HET-HIEU-LUC` chỉ dùng khi truyền `order_date` trước `2026-10-01` (changelog CL-01).
- **Nội bộ:** chunk tài liệu `NOI-BO` vẫn được truy hồi (để biết câu hỏi chạm thông tin cấm) nhưng mang cờ `restricted`; `search()` cho agent không bao giờ trả chúng.
- **Nhiễu:** nội quy nhân viên bị loại.

Cấu hình bằng biến môi trường, máy yếu tự lùi xuống mà không phải sửa code. Số dòng ứng với code ngày 17/10/2026.

**Ai dùng file này:** `harness/knowledge.py` (`search`, `CHUNKS`), `run_rag_eval.py` (`retrieve`, `describe`, `mode`).

## 1. Hằng số và biến cấu hình

| Tên | Ý nghĩa |
|---|---|
| `CHUNK_RX` [:36](../harness/rag.py#L36) | Regex tách mục `## [XX-nn] tiêu đề` và nội dung tới mục kế tiếp |
| `OLD_POLICY_EFFECTIVE_UNTIL` [:37](../harness/rag.py#L37) | `2026-10-01`: đơn tạo trước ngày này vẫn theo chính sách cũ |
| `STOP` [:38](../harness/rag.py#L38) | Từ dừng tiếng Việt (bỏ dấu) cho BM25 |
| `EMBED_MODEL` [:40](../harness/rag.py#L40), `EMBED_FALLBACKS` [:41](../harness/rag.py#L41) | Model embedding (mặc định `BAAI/bge-m3`); model dự phòng ở chế độ `auto` (`intfloat/multilingual-e5-small`) |
| `RERANK_MODEL` [:42](../harness/rag.py#L42), `RERANK_TOP_N` [:43](../harness/rag.py#L43) | Cross-encoder xếp hạng lại (mặc định `off`) và số ứng viên (20) |
| `RAG_STORE` [:44](../harness/rag.py#L44) | Kho vector: `numpy` (ma trận lưu ở `data/rag/`) hoặc `pgvector` |
| `RAG_MODE` [:45](../harness/rag.py#L45) | `auto` (lai nếu máy có model, không thì BM25) / `hybrid` (bắt buộc có model) / `bm25` |
| `INDEX_DIR` [:46](../harness/rag.py#L46) | Thư mục lưu ma trận embedding |
| `CHUNKS` [:83](../harness/rag.py#L83) | 99 chunk, nạp lúc import |
| `_bm25`, `_index`, `_reranker` (+ `_err`) [:205](../harness/rag.py#L205) | Đối tượng dùng chung trong tiến trình; `_err` ghi lý do không nạp được để không thử lại mãi |

## 2. Hàm cấp module

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `_device()` [:49](../harness/rag.py#L49) | Thiết bị chạy model: `EMBED_DEVICE`, hoặc tự chọn GPU nếu có | không | `cuda` / `cpu` / giá trị đặt tay | `torch.cuda.is_available` |
| `_load(cls, name, **kw)` [:60](../harness/rag.py#L60) | Nạp model **đã có trên máy** (`local_files_only`); chỉ tải mạng khi `RAG_ALLOW_DOWNLOAD=1`, để harness không tải model giữa lúc chạy | lớp model; tên model | đối tượng model | `_device` |
| `load_chunks(policy_dir)` [:70](../harness/rag.py#L70) | Tách mọi file `policy/*.md` thành chunk; gắn cờ `restricted` (NOI-BO), `superseded` (HET-HIEU-LUC), `noise` (nội quy nhân viên) | thư mục (mặc định `policy/` của BTC) | list `{chunk_id, doc, doc_title, title, text, restricted, superseded, noise}` | `CHUNK_RX` |
| `_toks(s)` [:86](../harness/rag.py#L86) | Tách từ cho BM25: bỏ dấu, bỏ từ dừng và từ 1 ký tự | chuỗi | list từ | `fold` |
| `_doc_text(c)` [:90](../harness/rag.py#L90) | Văn bản đưa vào index: tên tài liệu + tiêu đề mục + nội dung (bảng giá nhập, bảng thông số chỉ có nghĩa khi biết thuộc tài liệu nào) | chunk | chuỗi | |
| `expand_query(query)` [:95](../harness/rag.py#L95) | Thêm mã SKU của sản phẩm được nhắc vào câu hỏi (bảng thông số ghi theo SKU, khách gọi bằng tên). Chỉ dùng cho BM25 | câu hỏi | câu hỏi đã mở rộng | `tools.find_products` |
| `_vec_literal(v)` [:189](../harness/rag.py#L189) | Vector → chuỗi `[x,y,…]` cho pgvector | vector | chuỗi | |
| `_vector()` [:210](../harness/rag.py#L210) | Nạp index vector một lần: thử `EMBED_MODEL`, ở `auto` thử thêm model dự phòng. Không nạp được: `hybrid` → ném lỗi; `auto` → cảnh báo, trả `None` (dùng BM25) | không | `_Index` / `None` | `_Index` |
| `_rerank()` [:234](../harness/rag.py#L234) | Nạp reranker một lần nếu bật và có index vector | không | `_Reranker` / `None` | `_Reranker`, `_vector` |
| `mode()` [:249](../harness/rag.py#L249) | Chế độ thực tế đang chạy | không | `hybrid` / `bm25` | `_vector` |
| `describe()` [:253](../harness/rag.py#L253) | Cấu hình RAG thực tế (ghi vào báo cáo để tái lập) | không | `{mode, embed_model, device, store, reranker, n_chunks}` | `_vector`, `_rerank` |
| `_allowed(c, order_date)` [:261](../harness/rag.py#L261) | Luật phiên bản và nhiễu: loại chunk nhiễu; chunk hết hiệu lực chỉ cho phép khi `order_date < 2026-10-01` | chunk; ngày đơn | `True` / `False` | |
| `retrieve(query, k, order_date, rrf_k)` [:269](../harness/rag.py#L269) | Tìm top-k **kể cả chunk nội bộ**: điểm BM25 (câu đã mở rộng) và điểm vector, lọc bằng `_allowed`, gộp thứ hạng bằng RRF (`1/(60 + hạng)`), xếp hạng lại nếu có reranker | câu hỏi; k (mặc định 5); ngày đơn; hằng số RRF | list chunk kèm `score`, `dense`, `bm25`, `rerank` | `expand_query`, `_bm25.scores`, `_vector`, `_rerank`, `_allowed` |
| `search(query, k, include_restricted, order_date)` [:295](../harness/rag.py#L295) | Giao diện cho agent: lấy `k + 4` kết quả rồi bỏ chunk nội bộ (trừ khi `include_restricted`), giữ `k` | câu hỏi; k (mặc định 3); cờ nội bộ; ngày đơn | list chunk | `retrieve` |
| `touches_restricted(query, order_date)` [:301](../harness/rag.py#L301) | Chunk đứng đầu có phải tài liệu nội bộ không (câu hỏi đang dò giá nhập / nhà cung cấp) | câu hỏi; ngày đơn | `True` / `False` | `retrieve` |

## 3. Các lớp

| Hàm | Chức năng | Đầu vào | Đầu ra |
|---|---|---|---|
| `_BM25.__init__(chunks, k1, b)` [:107](../harness/rag.py#L107) | Đếm từ mỗi chunk (tiêu đề tính hai lần), độ dài, tần suất tài liệu | list chunk; tham số BM25 (k1 = 1,4, b = 0,6) | |
| `_BM25.scores(query)` [:114](../harness/rag.py#L114) | Điểm BM25 của câu hỏi với từng chunk | câu hỏi | list điểm |
| `_Index.__init__(chunks, model_name)` [:132](../harness/rag.py#L132) | Nạp model embedding; mã hóa mọi chunk một lần và lưu ma trận vào `data/rag/<model>-<chữ ký>.npy` (chữ ký đổi khi đổi model hoặc nội dung chunk), hoặc nạp vào pgvector | list chunk; tên model | |
| `_Index._encode(texts, query)` [:151](../harness/rag.py#L151) | Mã hóa và chuẩn hóa; model e5 cần tiền tố `query:` / `passage:` | list chuỗi; là câu hỏi hay tài liệu | ma trận |
| `_Index._init_pgvector()` [:157](../harness/rag.py#L157) | Tạo bảng `policy_chunks` trong Postgres, nạp lại khi số dòng của chữ ký hiện tại không khớp | | |
| `_Index.scores(query)` [:177](../harness/rag.py#L177) | Độ tương tự cosine của câu hỏi với từng chunk (nhân ma trận, hoặc truy vấn pgvector) | câu hỏi | list điểm |
| `_Reranker.__init__(model_name)` [:196](../harness/rag.py#L196), `.scores(query, texts)` [:201](../harness/rag.py#L201) | Nạp cross-encoder; chấm từng cặp (câu hỏi, chunk) | tên model; câu hỏi + list văn bản | list điểm |

## 4. Ghi chú khi đọc code

- **`touches_restricted` không có nơi nào gọi.** Agent nhận câu hỏi dò giá nhập qua cờ `asks_internal_cost` của router; `run_rag_eval.py` tự xét chunk đứng đầu.
- **Agent chưa truyền `order_date`,** nên luật "chính sách cũ cho đơn cũ" chưa được dùng trong hội thoại (chỉ đo ở `run_rag_eval.py`).
- **Đường pgvector và reranker `bge-reranker-v2-m3` chưa chạy thử trên server** ([ARCHITECTURE.md](ARCHITECTURE.md) mục 5.3). Số đo RAG: Recall@3 93,2%, Recall@5 93,2% với `bge-m3` + BM25 ([NHAT-KY-2026-10-08.md](NHAT-KY-2026-10-08.md) mục 6).
