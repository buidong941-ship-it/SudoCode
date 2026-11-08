# Vì sao không dùng RRF cho extractor hybrid (06/11/2026)

Câu hỏi của người dùng (06/11): có nên đổi extractor hybrid (rules + Jev + Qwen) sang gộp kết quả bằng RRF (Reciprocal Rank Fusion) không. **Kết luận: không chọn.** Lý do ở dưới, kèm số liệu đã có trong nhật ký.

Lưu ý: RAG chính sách (`harness/rag.py:258`) **đã** dùng RRF để gộp BM25 và vector. Ở đó RRF hợp lý vì cả hai nguồn đều trả về danh sách chunk có thứ hạng. File này chỉ bàn về extractor.

## 1. Extractor hybrid hiện tại là chuỗi tầng, không phải gộp

`harness/extractor.py:56` (`customer_slots`) chạy theo thứ tự và dừng ở tầng đầu tiên đủ tin cậy:

1. **Rules** cắt slot. Nếu CERT (`harness/rule_confidence.py`) chứng nhận được thì dừng (`hybrid:certified_rules` / `hybrid:certified_empty`), không gọi LLM.
2. **Jev** (`harness/jev_hybrid.py`) chỉ trả lời có/không cho từng nhãn. Giá trị luôn lấy từ rules (`hybrid:jev_grounded_rules`). Nếu Jev chọn một nhãn mà rules không có giá trị, hoặc Jev bỏ slot `address`/`payment` mà rules đã bắt (`JEV_DROP_POLICY`), thì chuyển xuống tầng 3.
3. **Qwen** trích slot, có kiểm span (giá trị phải xuất hiện trong câu).

## 2. Lý do không chọn RRF

### 2.1 Không có danh sách xếp hạng để gộp

RRF cộng `1/(k + hạng)` của cùng một ứng viên qua nhiều danh sách đã xếp hạng. Extractor không tạo ra danh sách như vậy: mỗi nguồn cho **tối đa một giá trị cho mỗi slot**.

- Mỗi "danh sách" chỉ có một phần tử, nên mọi nguồn đóng góp cùng một điểm `1/(k+1)`. RRF lúc này chỉ còn là **đếm phiếu**.
- Khi hai nguồn bất đồng 1–1, RRF cho điểm hòa, và vẫn phải có luật ưu tiên để phá hòa. Cascade hiện tại chính là luật ưu tiên đó, viết tường minh.

### 2.2 Jev không tạo ra giá trị

Jev chỉ bỏ phiếu được cho việc slot **có mặt hay không**, không đưa ra được giá trị (địa chỉ, số điện thoại, diện tích...). Về giá trị, chỉ có hai nguồn là rules và Qwen, nên "bỏ phiếu ba bên" không có ý nghĩa.

### 2.3 Tốn latency đúng chỗ vừa gỡ được

Muốn bỏ phiếu thì **mỗi lượt phải chạy cả ba nguồn**, trong khi cascade bỏ qua LLM ở nhiều lượt. Số đo đã có:

| Số đo | Nguồn |
|---|---|
| Extractor trung bình 8,9 s khi có Jev, so với 14,9 s khi mọi lượt đều qua Qwen | Nhật ký 03/11 mục 2.2 |
| TTFT p95 3,06 s khi Qwen trích slot chạy chung GPU với generator, so với 1,36 s khi chỉ dùng rules | Nhật ký 03/11 mục 2.2 |
| 8–9% lượt bỏ qua LLM hoàn toàn (`certified_empty`, 11–13/140) | Nhật ký 02/11 mục 5.2 |
| Total p95 hiện khoảng 6,0–6,2 s, ngưỡng là 8 s | Nhật ký 06/11 mục 1 |

Bước trích slot của khách (`customer_slots_start`) nằm trên đường tính `total_ms`. Nếu Qwen chạy ở mọi lượt, nhiều khả năng Total p95 lại vượt 8 s.

### 2.4 Gần như không có bất đồng để giải quyết

| Số đo | Kết quả | Nguồn |
|---|---|---|
| Jev bỏ slot `address`/`payment` (`jev_dropped_rule_slots`) | 0 lần ở mọi lần chạy | Nhật ký 02/11 mục 5.2, 03/11 mục 2.5 |
| `JEV_DROP_POLICY=accept` so với `qwen` | Chỉ số giống hệt; chính sách không bao giờ được dùng tới | Nhật ký 03/11 mục 2.5 |
| Jev trả sai kiểu slot (`slot_type_mismatch`) | 7–11/140 lượt, đã tự chuyển sang Qwen | Nhật ký 02/11 mục 5.2 |
| CERT tắt / CERT1 / CERT2 | Không đổi chỉ số chính thức hay bộ nhớ nào | Nhật ký 06/11 mục 1 và 12 |

Một cơ chế gộp chỉ có lợi khi các nguồn hay bất đồng, mà số trên cho thấy điều đó hiếm khi xảy ra.

### 2.5 Ràng buộc của đề

- Extractor không được tinh chỉnh để làm đẹp RQR/HR, vì giám khảo đọc tay `questions[]` và `claims[]`.
- Nếu muốn RRF phá được hòa thì phải gắn trọng số cho từng nguồn. Chọn trọng số trên dev là hiệu chỉnh mô hình, mà brief C.5 cấm.

## 3. Nếu sau này muốn xem lại

Trace hiện tại chỉ ghi nguồn đã thực sự chạy (`meta["backend"]`), nên chưa đo được tỉ lệ bất đồng thật giữa rules, Jev và Qwen. Cách rẻ nhất là một job Kaggle chạy **shadow**: cả ba nguồn chạy song song chỉ để ghi log, không đổi đầu ra, rồi đếm số lượt bất đồng theo từng slot.

- Nếu tỉ lệ gần 0 (như mục 2.4 gợi ý), có thể bỏ hẳn ý tưởng này.
- Nếu cao, ta mới bàn cách gộp (vẫn ưu tiên luật tường minh hơn là trọng số).

Chưa đề xuất vào `CHO-DUYET.md`. Chỉ thêm khi người dùng yêu cầu.
