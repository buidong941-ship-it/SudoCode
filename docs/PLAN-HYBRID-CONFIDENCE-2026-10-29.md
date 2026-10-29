# Kế hoạch 29/10/2026: dữ liệu mới và cổng confidence cho bộ trích hybrid

## Mục tiêu và trạng thái

Đề xuất của người dùng: luật chạy trước vì nhanh; nếu kết quả đủ tin cậy thì dùng ngay, còn không thì gọi Jev để phân loại slot lời khách, câu hỏi và claim lời agent. Chỉ dùng Qwen khi Jev phát hiện thông tin nhưng code không thể xác định đoạn chữ gốc (`span`) hoặc gán giá trị an toàn. Đây là **thiết kế thử nghiệm**, chưa phải kết quả đã chạy hay cấu hình mặc định. Không huấn luyện/fine-tune model.

Bộ nhãn hiện có `tests/extract_eval/agent.jsonl` (120 câu) và `customer.jsonl` (60 câu) lấy từ trace/dev cũ; các kịch bản `datagen/out_nat/test` cũng đã dùng nhiều lần. Không dùng các bộ này để chọn ngưỡng rồi tuyên bố kết quả test mới.

## 1. Tạo hai lớp dữ liệu mới

1. **Bộ câu có nhãn:** chuẩn bị tối thiểu 300 câu khách và 300 câu agent mới. Lấy từ kịch bản, cách diễn đạt và chuỗi hội thoại mới; tránh sửa vài từ trong câu của trace cũ. Gồm câu không có nhãn, câu nhiều nhãn, trả lời ngắn phụ thuộc ngữ cảnh, phủ định, trích dẫn lời người khác, nhiều con số có vai trò khác nhau, khuyến mãi, tồn kho, bảo hành, câu hỏi không có dấu `?`, câu xác nhận và lỗi chính tả thông dụng. Tách theo *họ kịch bản/nguồn câu*, khử trùng gần giống với dev/test cũ. Gán nhãn tay cho `slots` lời khách (field, value, span), `questions` (slot, open/confirm, nguyên câu), `claims` (field, value, sản phẩm, câu chứa claim). Jev/Qwen có thể gợi ý nhãn nhưng không được dùng làm đáp án cuối khi chưa có người rà.
2. **Bộ hội thoại mới:** ít nhất 20–30 kịch bản nhiều lượt, có sự thật sản phẩm/chính sách để chấm TSR/CCR/RQR/HR và đo toàn lượt. Không lấy câu hay chuỗi tình huống từ bộ test đã dùng. Bản này kiểm tác động của việc trích slot sớm/muộn tới kế hoạch và bộ nhớ, điều mà bộ câu độc lập không đo được.
3. Chia bộ câu theo nguồn/kịch bản thành **calibration** (chọn ngưỡng) và **holdout** (chỉ chấm một lần sau khi khóa ngưỡng). Không chia ngẫu nhiên các câu gần giống của cùng kịch bản vào hai phía. Ghi nguồn, quy tắc gán nhãn, số câu theo field, hash và các câu mơ hồ cần bỏ qua trước khi xem kết quả model. Nếu field hiếm không đủ ví dụ, báo thiếu độ phủ và tiếp tục gọi Jev cho field đó.

## 2. Định nghĩa confidence của luật

`confidence` không phải số tùy ý gán cho regex khớp mạnh. Một kết quả luật chỉ được nhận ngay nếu đồng thời có bằng chứng rằng **nhãn/giá trị đã xuất ra đúng** và **không bỏ sót nhãn cần xuất ra**. Câu chỉ bắt được một trong hai slot không đạt, dù slot đầu đúng. Kết quả rỗng cũng phải có bằng chứng là câu thực sự không chứa slot/câu hỏi/claim; không có regex khớp **không phải** bằng chứng đó.

Luật trả kèm tín hiệu kiểm được: span nằm trong đúng câu, giá trị parse được, từ khóa nằm gần giá trị, phủ định/trích dẫn, nhiều con số hoặc nhiều sản phẩm, câu đáp ngắn thiếu ngữ cảnh, và dấu hiệu thông tin chưa được luật xử lý. Từ dữ liệu calibration, tính tỷ lệ **đúng toàn bộ tập nhãn của câu** theo từng nhóm tín hiệu và một cận trên rủi ro sai có khoảng tin cậy; nhóm ít mẫu hoặc chưa thấy cách nói tương ứng luôn chuyển Jev. Có ngưỡng riêng cho slot khách, câu hỏi, claim; các claim giá/khuyến mãi/tự nhận là người thật phải kiểm chặt hơn. Chọn ngưỡng để tăng tỷ lệ dùng luật **trong ràng buộc chất lượng đã ghi trước**, không chỉnh theo holdout.

### 2.1. Công thức **chạy trực tiếp trong production**

Đầu vào của công thức chỉ gồm câu hiện tại `x`, ngữ cảnh được phép dùng `c`, kết quả luật `R_t(x,c)` và các phép kiểm code. **Không có nhãn người rà hoặc đáp án chuẩn trong đường chạy.** Tách câu agent thành các câu/đoạn; nếu một đoạn không được xác nhận an toàn thì chỉ gửi các đoạn chưa chắc sang Jev, có thể gom thành một request. `t` là một trong `customer_slots`, `agent_questions`, `agent_claims`.

Với mỗi đoạn `s`, tính sáu biến nhị phân từ dữ liệu có ngay lúc chạy:

| Biến | Bằng 1 khi |
| --- | --- |
| `G_t(s)` — grounding | Mọi span của kết quả luật nằm nguyên trong đúng đoạn nguồn. |
| `P_t(s)` — parse | Mọi giá trị được code parse hợp lệ từ span; không phải giá trị LLM/regex suy đoán. |
| `U_t(s)` — liên kết duy nhất | Mỗi nhãn gắn được với **một** giá trị và đối tượng/sản phẩm rõ ràng; nhiều số hoặc nhiều sản phẩm không gán được vai trò thì bằng 0. |
| `N_t(s)` — ngữ nghĩa an toàn | Không có phủ định, câu trích dẫn, giả định, câu hỏi về một claim, hoặc cách nói có thể đảo nghĩa mà luật chưa xử lý. |
| `K_t(s)` — phủ tín hiệu | Một bộ phát hiện tín hiệu ứng viên **tách khỏi output của rules** quét dấu hỏi, lời yêu cầu, từ khóa slot/claim và các con số; mọi tín hiệu ứng viên tìm thấy đều được kết quả luật giải thích. Có tín hiệu chưa được giải thích thì bằng 0. |
| `C_t(s,c)` — ngữ cảnh đủ | Không phải câu đáp ngắn hoặc cách nói cần câu trước để hiểu slot; với claim, biết rõ sản phẩm đang được nói tới. |

```text
CERT_t(s,c) = 1{R_t(s,c) không rỗng}
              × G_t(s) P_t(s) U_t(s) N_t(s) K_t(s) C_t(s,c)

ROUTE_t(s,c) = rules                 nếu CERT_t(s,c) = 1
             = Jev                   nếu CERT_t(s,c) = 0 và Jev đã được kiểm chứng cho t
             = hybrid hiện hành      nếu Jev chưa được kiểm chứng cho t

Kết quả toàn câu = gộp kết quả của mọi đoạn s sau khi từng đoạn đi đúng tuyến;
không chấp nhận cả câu chỉ vì một đoạn có chứng chỉ.
```

Đây là **chứng chỉ bằng điều kiện**, không phải xác suất đúng. Không đặt các trọng số kiểu `0,8` cho regex rồi gọi đó là confidence. Nếu `R_t` rỗng, đoạn không có tín hiệu, có câu yêu cầu không dấu `?`, hoặc có bất kỳ biến nào bằng 0 thì chuyển bước tiếp theo. Bộ tín hiệu `K_t` chỉ là lưới phát hiện *bất đồng rõ ràng*; nó có thể cùng bỏ sót một cách nói lạ như rules, nên `CERT=1` **không bảo đảm** đã bắt mọi nhãn. Với câu hỏi, không dùng `agent_questions()` làm cổng duy nhất trước Jev; các câu ngoài nhóm được chứng nhận phải tới Jev để tránh lặp lại lỗi sáu câu yêu cầu từng bị bỏ sót.

Các claim giá, khuyến mãi và `is_human` ban đầu đặt `CERT_agent_claims=0`, luôn chuyển bước tiếp theo vì một claim gán sai có thể làm HR tăng. Nếu Jev chưa được kiểm chứng cho claim/slot khách, “bước tiếp theo” vẫn là hybrid Qwen hiện hành. Khi Jev đã được kiểm chứng, code kiểm span, giá trị, phủ định và sản phẩm từ nhãn Jev; chỉ gọi Qwen nếu code không thể gán span/giá trị an toàn. Một nhãn Jev không có span chứng thực không tự trở thành claim trong trace.

Ví dụ: “Phòng 25m², ngân sách khoảng 5 triệu” chỉ được nhận bằng rules nếu **cả hai** tín hiệu diện tích và tiền được giải thích, hai giá trị parse đúng và không có phần mơ hồ. Bắt được diện tích nhưng bỏ ngân sách làm `K=0` nên chuyển Jev. “Chị lên địa chỉ giúp em nhé” không có `?` vẫn phải đi Jev nếu rules chưa nhận; output rỗng không được coi là câu chắc chắn không hỏi.

### 2.2. Kiểm chứng công thức production

Nhãn người rà chỉ xuất hiện **ngoài đường chạy**, để đo số câu `CERT=1` nhưng rules sai hoặc bỏ sót, tỷ lệ gọi Jev/Qwen, metric hội thoại và latency. Chọn điều kiện trên calibration rồi khóa trước khi mở holdout. Không thể suy ra một bảo đảm tỷ lệ sai chỉ từ `CERT`; nếu muốn tuyên bố cận rủi ro thống kê, vẫn cần dữ liệu kiểm độc lập có nhãn. Trước khi tích hợp Jev cho slot khách và claim, phải đo riêng Jev trên dữ liệu mới; hiện kết quả đã biết mới kiểm Jev đa nhãn cho câu hỏi.

Cách tổ chức “nhận kết quả khi đủ tin cậy, còn lại chuyển bước mạnh hơn” dựa trên ý tưởng **selective classification** và **cascade** trong [Geifman & El-Yaniv (2017)](https://arxiv.org/abs/1705.08500) và [Chen, Zaharia & Zou (2023)](https://arxiv.org/abs/2305.05176). Sáu điều kiện `G/P/U/N/K/C` là **thiết kế cho repository này**, không phải công thức được hai bài báo chứng minh cho extractor này.

## 3. Đường chạy hybrid đề xuất

```text
câu khách / câu agent
  → luật trích nhãn + giá trị/span + tín hiệu rủi ro
  → confidence đủ cao và đã kiểm tính đầy đủ? → dùng luật
  → chưa đủ → Jev phân loại các nhãn còn nghi vấn
      → code tìm span/giá trị trong chính câu, kiểm phủ định, sản phẩm, số tiền
      → chỉ khi code không gán được span/giá trị an toàn → Qwen dự phòng
      → Qwen vẫn phải trả span có thật; sai/timeout → giữ kết quả an toàn và ghi fallback
```

- **Slot khách:** luật có giá trị ngay; Jev bổ sung slot còn thiếu, luật thắng khi cùng slot. Cần ghi rõ Jev/Qwen đến trước bước lập kế hoạch hay chỉ đến sau lời đáp để cập nhật bộ nhớ. Muốn lượt hiện tại dùng slot mới thì phải chờ trước khi lập kế hoạch và đo phần tăng Total; nếu không chờ thì chỉ cải thiện lượt sau.
- **Câu hỏi lời agent:** Jev hiện đã phân loại từng câu, luật dự phòng khi Jev lỗi. Cổng confidence mới có thể bỏ Jev ở câu luật đã xác định chắc chắn. Không gộp mọi câu không có dấu hỏi thành nhãn `none`; câu yêu cầu thông tin không có dấu `?` phải có trong dữ liệu mới.
- **Claim lời agent:** cho Jev phân loại nhiều nhãn trong một câu, ưu tiên ghép với request Jev phân loại câu hỏi để không thêm request riêng nếu SDK cho phép. Với nhiều giá/số ngày trong một câu, code phải gắn đúng vai trò từng số; Qwen chỉ hỗ trợ trường hợp còn mơ hồ. Luật và Jev không được hợp mù quáng vì claim gán thừa làm HR tăng. `facts_used` vẫn do code đối chiếu lời agent và tham số tool.
- Giữ che PII trước Jev, timeout, fallback theo từng câu, metadata `backend/confidence/reason/request_count/ms`; không thay đổi định dạng trace bắt buộc của bộ chấm.

## 4. Cách chấm và điều kiện bật

So trên **cùng câu**: luật, hybrid Qwen hiện hành, Jev + luật luôn gọi, và hybrid có cổng confidence. Báo riêng TP/FP/FN, precision/recall/F1, tỷ lệ đúng toàn bộ tập nhãn, tỷ lệ luật được nhận ngay, tỷ lệ gọi Jev/Qwen, lỗi API và thời gian p50/p95 theo từng nhiệm vụ/field. Kiểm cả **những câu luật được nhận ngay nhưng sai hoặc bỏ sót**; đó là lỗi trực tiếp của confidence.

Sau khi khóa ngưỡng bằng calibration, chấm holdout mới một lần. Sau đó chạy full agent trên Kaggle với cùng model, worker, số bản trả lời ứng viên, kịch bản và môi trường; so Total, hậu xử lý, toàn lượt, Call Brief + toàn lượt, TSR/CCR/RQR/HR và số lượt lỗi. Phần trích lời agent chạy sau khi lời đáp sẵn sàng nên tối ưu nó chủ yếu ảnh hưởng **toàn lượt**, không tự giảm Total. Chỉ cân nhắc đổi mặc định khi chất lượng của câu được luật nhận ngay và metric hội thoại không giảm, đồng thời tốc độ có lợi thực đo. Giữ code dưới cờ backend riêng để chuyển lại được.
