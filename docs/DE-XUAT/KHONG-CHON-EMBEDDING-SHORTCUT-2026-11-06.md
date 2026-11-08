# Vì sao không dùng embedding để trả thẳng slot / intent / cờ (06/11/2026)

Ý tưởng của người dùng (06/11): embed lời khách, tìm câu tương tự đã gặp trong một kho câu có sẵn nhãn, rồi **trả luôn** slot, intent, cờ... của câu đó cho extractor, router và planner, không cần gọi Jev/Qwen. Cách này thường gọi là *semantic cache* hay phân loại bằng láng giềng gần nhất (kNN).

**Kết luận: không làm bản "trả thẳng kết quả".** Có một biến thể an toàn hơn (mục 3), nhưng cũng không nên làm trước khi chốt.

Liên quan: [KHONG-CHON-RRF-EXTRACTOR-2026-11-06.md](KHONG-CHON-RRF-EXTRACTOR-2026-11-06.md).

## 1. Khác gì với cái đang có

- `data/llm_cache.sqlite` là cache **khớp chính xác** (khóa là toàn bộ request) và chỉ để chạy lại cho ra cùng số. Ý tưởng này là cache **khớp gần đúng**: câu khác nhưng "giống" thì dùng lại kết quả.
- RAG chính sách (`harness/rag.py`) cũng dùng embedding, nhưng chỉ để **tìm tài liệu đưa vào prompt**. LLM vẫn tự viết câu trả lời. Ý tưởng này thì dùng embedding để **ra quyết định**.

## 2. Lý do không chọn

### 2.1 Slot là giá trị riêng của câu hiện tại

Embedding gần như không phân biệt được số, phủ định và quan hệ người nói. Lấy slot của câu giống nhất sẽ ghi giá trị của khách khác vào bộ nhớ:

| Câu mới | Câu cũ gần nhất | Lấy luôn slot cũ thì sai thế nào |
|---|---|---|
| "Phòng anh 30m2" | "Phòng anh 25m2" | ghi `room_area_m2 = 25` |
| "Chị **không** thích màu đen" | "Chị thích màu đen" | ghi `color = đen`. Đúng loại lỗi trong [DE-XUAT-CERT-V2-2026-11-02.md](DE-XUAT-CERT-V2-2026-11-02.md) mục 2.1 |
| "Số của **vợ** anh là 09…" | "Số của anh là 09…" | gộp hồ sơ người khác. Đúng lỗi jailbreak J6 vừa sửa (nhật ký 06/11 mục 5 và 8) |

Bộ nhớ sai làm hỏng cuộc gọi sau (agent chào hàng sai, hỏi lại thông tin). Giám khảo đọc tay `questions[]`, `claims[]` và slot.

### 2.2 Cùng một câu có nghĩa khác nhau tùy ngữ cảnh

"Ừ được em", "Dạ đúng rồi" có nghĩa gì phụ thuộc vào câu agent vừa hỏi.
- Chỉ embed lời khách: trả nhãn sai.
- Embed cả ngữ cảnh: hầu như không có câu nào đủ giống, nên cache gần như không bao giờ trúng.

### 2.3 Cờ an toàn dễ bị lách

- Red-team 06/11 (mục 3, mục 5 lỗi 4 và 5) cho thấy chỉ cần đổi cách nói ("giá nhân viên", "giá nội bộ", "em là nhân viên telesale của shop") là đã lách được cờ và guardrail.
- Câu tấn công diễn đạt khéo sẽ nằm gần câu bình thường trong không gian embedding. Nếu bỏ qua Jev vì "đã thấy câu giống" thì câu tấn công lọt qua.
- Các cờ như `asks_internal_cost`, `wants_data_deleted`, `medical_question` sai một lần là vi phạm, nên không thể đánh đổi lấy tốc độ.

### 2.4 Không có nguồn nhãn sạch, và vướng ràng buộc của đề

- **Nhãn từ trace của chính hệ thống:** chép luôn lỗi của Jev và Qwen vào kho, rồi lặp lại lỗi đó mãi.
- **Nhãn từ đáp án kịch bản** (`facts_established`, `ground_truth_facts`...): lộ đáp án vào đường chạy của agent, bị cấm.
- **Ngưỡng "đủ giống":** phải chọn trên dev, tức là hiệu chỉnh. Đề C.5 không cho huấn luyện hay hiệu chỉnh mô hình; mọi cải tiến phải đến từ dữ liệu, bộ nhớ, prompt và điều phối.
- **Bộ test ẩn** có cách nói và sản phẩm mới, nên không biết trước cache trúng được bao nhiêu.

### 2.5 Lợi ích nhỏ, chi phí thật

| | Số đo | Nguồn |
|---|---|---|
| Router Jev | ~0,12–0,14 s mỗi lượt | trace V3-095, job `abl-short.cert-ab-1106` |
| Trích slot khách trên đường tính latency | 15–16 ms ở lượt có CERT | cùng trace |
| Trích lời agent | nằm trong `post_ms`, sau khi đã trả lời, không tính vào Total | nhật ký 04/11 mục 1 |
| Total p95 hiện tại | ~6,0–6,2 s, ngưỡng 8 s | nhật ký 06/11 mục 1 |

Phần tốn thời gian nhất là generator, mà ý tưởng này không đụng tới. Trong khi đó nó tốn thêm một model embedding trên GPU (`bge-m3` khoảng 2,3 GB mỗi worker, `docs/HARNESS.md`), tranh bộ nhớ với vLLM.

### 2.6 Planner không nên đi qua đường này

Planner chọn goal và tool bằng bảng luật tường minh (`harness/planner_rules.json`) từ intent và cờ. Lấy kế hoạch của một câu "giống" thì sẽ gọi sai tool hoặc tra sai sản phẩm. Ngoài ra, bảng luật đọc và duyệt được từng dòng, còn kết quả kNN thì không.

## 3. Biến thể đáng cân nhắc: dùng câu tương tự làm few-shot

Giữ phần **tra câu tương tự**, nhưng đưa k ví dụ gần nhất vào prompt của Jev hoặc Qwen làm ví dụ mẫu, **không trả thẳng kết quả**:

- LLM vẫn quyết định; giá trị slot vẫn phải nằm trong câu (kiểm span); cờ an toàn vẫn do Jev chấm; planner giữ nguyên bảng luật.
- Đây chính là cơ chế **Exemplar Bank** trong đề C.5 ("gặp tình huống tương tự thì lấy ra làm few-shot"), nên được tính điểm ở tiêu chí cải tiến (hệ số 13%).
- Repo đã có `improve/exemplars.py`, hiện chỉ dùng cho câu chữ của generator (nhật ký 05/11 mục 8). Mở rộng sang extractor và router là bước tiếp tự nhiên.
- **Rủi ro:** prompt dài hơn nên latency tăng; ví dụ trong kho phải qua người duyệt (C.5); phải đo lại chất lượng và chạy lại red-team.

## 4. Đề xuất

- Không làm bản "trả thẳng kết quả".
- Biến thể few-shot (mục 3): **không làm trước khi chốt**. Kế hoạch 06/11 đang ở giai đoạn dọn dẹp và soát jailbreak, nên thêm thành phần mới sẽ phải đo lại toàn bộ. Có thể xét lại trong vòng cải tiến.
- Chưa thêm vào `CHO-DUYET.md`. Chỉ thêm khi người dùng yêu cầu.
