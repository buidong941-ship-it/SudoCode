# Đề xuất 02/11/2026: đánh giá CERT và phương án CERT v2

**Trạng thái: CHỜ DUYỆT.** Chưa sửa code, test hay dữ liệu nào. Tài liệu này chỉ ghi lại đánh giá và đề xuất.

Phạm vi: `harness/rule_confidence.py` (`customer`, `empty`, `question`) và các chỗ gọi trong `harness/extractor.py` (`customer_slots`, `customer_slots_start`, `_analyze_agent_confidence`). CERT chỉ chạy khi `--extractor hybrid` và `EXTRACTOR_CONFIDENCE_GATE=1`.

## 1. Kết luận ngắn

CERT **chưa tối ưu**.

- **Nên giữ hướng thiết kế:** chứng chỉ nhị phân, kiểm được bằng mắt, không chắc thì bỏ phiếu trắng (abstain) và chuyển sang Jev/Qwen. Hướng này hợp với việc BTC rà tay extractor.
- **Code hiện tại sai cả hai phía:**
  - Có câu bị **chứng nhận sai** (CERT=1 nhưng giá trị sai), nên Jev và Qwen bị bỏ qua và slot sai được ghi vào memory.
  - Có nhiều câu đúng bị **chặn oan**, do một bug đếm số và các check quá thô.
- Con số "precision 100%" trong `NHAT-KY-2026-11-01.md` chưa đủ cơ sở thống kê.

## 2. Bằng chứng

Dưới đây là kết quả chạy `customer_slots_rules` + `rule_confidence.customer` / `empty` trên code hiện tại, ngày 02/11, chạy local, chỉ dùng hàm thuần, không gọi LLM. Cột "ctx" cho biết có truyền context hay không.

### 2.1. Chứng nhận sai: lỗi precision

| Câu khách | ctx | Luật trích | Kết quả | Vấn đề |
|---|---|---|---|---|
| "Chị không lấy màu đen đâu." | – | `color=den` | CERT ✅ | Bỏ qua phủ định |
| "Màu đen thì chị không thích." | – | `color=den` | CERT ✅ | Bỏ qua phủ định |
| "Thanh toán COD không được à?" | – | `payment=COD` | CERT ✅ | Khách đang hỏi, chưa chốt |
| "Chị ở Hà Nội." | – | `{}` | EMPTY ✅ | Thông tin địa chỉ bị bỏ, không qua Jev |

Nguyên nhân:

- `UNSAFE` chỉ có "không phải". Danh sách thiếu các từ phủ định đơn như "không", "chưa", "chẳng", "đừng", "ko".
- Không có check nào nhận ra câu hỏi.
- Chứng nhận rỗng dùng cùng họ regex với luật, nên một cách nói mà luật không bắt được thì cue cũng thường không bắt được (lỗi tương quan). Tài liệu `PLAN-HYBRID-CONFIDENCE-2026-10-29.md` đã thừa nhận điểm này.

Hậu quả: slot sai được ghi vào memory. Ví dụ khách nói không thích màu đen, nhưng sang call sau agent lại chào hàng màu đen.

### 2.2. Chặn oan: lỗi coverage

| Câu khách | ctx | Luật trích | Kết quả | Check rớt |
|---|---|---|---|---|
| "Phòng 25m²." | – | `room_area_m2=25` | CERT ✅ | — |
| "Phòng 25m²." | có | `room_area_m2=25` | ❌ | C |
| "Đúng rồi, phòng 25m2 em." | – | `room_area_m2=25` | ❌ | U, N |
| "Phòng chị dùng 25m2." | – | `room_area_m2=25` | ❌ | U, N |
| "Phòng 25m2, ngân sách tối đa 5 triệu." | – | 2 slot | ❌ | R, U |
| "Ngân sách chị tầm 5 triệu, gia đình 4 người." | – | 2 slot | ❌ | R, K |

Nguyên nhân:

1. **Bug ở check U (`room_area_m2`):** `len(re.findall(r"\d+", text)) == 1` đếm cả chữ số "2" trong "m2". Kết quả là mọi câu viết "25m2" đều rớt U, kể cả câu đúng hoàn toàn. Chỉ "25m²" mới qua, vì "²" không khớp `\d`. Trong khi "m2" là cách viết phổ biến nhất, cũng là đầu ra của ASR và ITN.
2. **Check C gần như luôn chặn trong lúc chạy thật:** `harness/agent.py:246-253` luôn truyền `extraction_context` (8 lượt gần nhất cộng tóm tắt phiên trước). Do đó, từ lượt thứ hai trở đi, mọi câu ngắn hơn hoặc bằng 32 ký tự đều rớt C. Đây lại đúng là dạng câu trả lời slot hay gặp nhất ("Dạ 25m2.", "Màu xám em.").
3. **Va chạm do `fold()`:**
   - "đúng", "dùng", "đựng" đều thành `dung`, nằm trong `UNSAFE`.
   - "giá", "già", "gia đình" đều thành `gia`, bị `no_extra` chặn.
   - Hàm `empty()` đã xử lý chuyện này bằng cách khớp trên bản còn dấu, nhưng `customer()` và `question()` thì chưa.
4. **Chỉ chứng nhận được câu có đúng một slot** (`one = len(rules) == 1`). Câu có hai slot rõ ràng cũng rớt cả câu.
5. **Check trùng lặp:**
   - Trong `customer()`, P luôn bằng G (`parsed = grounded`) ở mọi nhánh.
   - Với `size`, `color`, `payment`, check G gọi lại chính `customer_slots_rules`, tức là luật tự kiểm luật.
   - Vì vậy trace nói có sáu check, nhưng số check độc lập thực tế chỉ khoảng bốn.

Audit A1 (`NHAT-KY-2026-11-01.md`, mục 1) kết luận rằng CERT đạt 2/140 chủ yếu vì luật rỗng. Kết luận đó vẫn đúng. Nhưng audit A1 chạy offline, còn bug U và check C làm hỏng luôn các lượt mà luật trích đúng.

### 2.3. Cách đo precision hiện tại

| Nguồn | Kết quả | Ý nghĩa thật |
|---|---|---|
| `tests/extract_eval/customer.jsonl` (nhãn tay) | chứng nhận rỗng 6/60, sai 0 | Không lỗi nào trên 6 mẫu: cận trên 95% (Clopper–Pearson, một phía) của tỉ lệ sai vẫn khoảng **39%** |
| Trace dev ③ | chứng nhận rỗng 38/140, trùng với Jev | So với **nhãn Jev**, không phải gold. Cận trên khoảng 7,6% chỉ khi coi Jev là đúng |
| `tests/confidence_gate_check.py` | OK | Không có phản ví dụ phủ định, câu hỏi, "m2" hay "đúng/dùng" |

Muốn khẳng định tỉ lệ sai dưới hoặc bằng 1% với độ tin cậy 95% thì cần khoảng **300 lượt có nhãn gold mà không có lỗi nào** (quy tắc 3/n).

## 3. Đề xuất: CERT v2, vẫn nhị phân

Chưa đề xuất thay bằng score xác suất có hiệu chỉnh (logistic, conformal), vì hai lý do:

- Bộ nhãn khách mới có 60 câu, không đủ để hiệu chỉnh.
- `PLAN-2026-11-01.md` đã chốt "CERT giữ dạng nhị phân".

Các mục được xếp theo thứ tự ưu tiên. Mục 3.1 lấp lỗi precision nên cần làm trước. Các mục từ 3.2 trở đi tăng coverage.

### 3.1. Thêm check độc lập NEG và QUES (precision)

- **NEG:** nếu trong khoảng ±4 từ quanh giá trị hoặc cue của slot có từ phủ định ("không", "chưa", "chẳng", "đừng", "ko", "k", "hong", "hông"), thì bỏ phiếu trắng.
- **QUES:** nếu câu kết thúc bằng "?", hoặc có mẫu nghi vấn ("... không?", "... à?", "... hả?", "được không", "có ... không"), thì bỏ phiếu trắng với các slot sở thích (`color`, `size`, `payment`, sản phẩm quan tâm). Lý do: khách đang hỏi, chưa chốt. Các slot số có đơn vị (diện tích, ngân sách) vẫn chứng nhận được nếu chỉ có một giá trị.
- Khớp trên bản còn dấu nếu câu có dấu. Câu mất dấu thì khớp trên bản fold, để abstain nhiều hơn.

### 3.2. Sửa bug check U

Bỏ các token đơn vị (`m2`, `m²`, `mét vuông`, `met vuong`) trước khi đếm số. Trường hợp "25m2" phải cho U = 1.

### 3.3. Thay check C (độ dài câu) bằng ghép câu hỏi với câu trả lời

- Lấy slot mà agent vừa hỏi ở lượt trước, từ `questions[]` do chính extractor sinh lúc chạy. Đây là dữ liệu runtime, không phải answer key, nên không lộ đáp án.
- Câu khách ngắn, agent vừa hỏi slot X, luật trích đúng slot X, và giá trị có đơn vị hoặc cue riêng: **chứng nhận**. Ví dụ "Phòng rộng bao nhiêu m2?" rồi "Dạ 25m2."
- Agent vừa hỏi dạng xác nhận ("Chị lấy màu xám nhé?") mà khách chỉ đáp "Ừ", "Được em": **bỏ phiếu trắng** như hiện nay, vì giá trị nằm trong ngữ cảnh chứ không nằm trong câu.
- Giữ nguyên `CONTEXT` (tham chiếu ngược "cái đó", "hôm trước"...): có thì bỏ phiếu trắng.

### 3.4. Khớp `UNSAFE`, `no_extra` và `CONTEXT` trên bản còn dấu

Làm giống `empty()`: câu có dấu thì dùng regex có dấu, để "đúng" và "dùng" không còn rơi vào `dung`. Câu mất dấu thì giữ bản fold. Đồng thời bỏ `dung` khỏi `UNSAFE` bản có dấu, vì từ cần chặn thật là "đúng là ... nhưng", không phải mọi chữ "đúng".

### 3.5. Chứng nhận theo từng slot thay vì từng lượt

- Mỗi slot có một chứng chỉ riêng.
- Điều kiện chung:
  - Mỗi số tiền hoặc số diện tích trong câu được **đúng một** slot sử dụng.
  - Các span không chồng nhau.
  - Không còn cue thừa nào ngoài các slot đã nhận.
- Slot nào đạt thì dùng kết quả luật. Slot nào rớt, hoặc có cue thừa, thì gửi Jev/Qwen, kèm danh sách slot đã chứng nhận để phía sau không ghi đè.

### 3.6. Thêm một tín hiệu độc lập cho chứng nhận rỗng

Nếu có danh từ riêng viết hoa không đứng đầu câu (chuỗi các từ viết hoa chữ cái đầu, ví dụ "Hà Nội", "Cầu Giấy", "Dung"), thì bỏ phiếu trắng. Tín hiệu này rẻ, không phụ thuộc regex của luật, và bắt được tên riêng hoặc địa danh mà luật bỏ sót. Câu ASR viết thường sẽ không hưởng lợi, nhưng cũng không bị hại thêm.

### 3.7. Dọn các check trùng lặp

- Bỏ P ở `customer()`, vì P luôn bằng G.
- Với các slot phân loại, đổi G thành một kiểm tra độc lập: giá trị phải xuất hiện nguyên văn (sau khi chuẩn hoá) trong câu, và nằm trong danh mục hợp lệ của catalog.
- Trace chỉ ghi những check thật sự độc lập.

### 3.8. Mở rộng danh sách slot được chứng nhận (làm sau cùng, khi 3.1–3.7 đã có số đo)

Ứng viên: `address` (có số nhà và tên đường), `self_name` (có "tên là" hoặc "chị là" cộng danh từ riêng), `callback_requested` (có mốc thời gian rõ), `has_children`. Phụ thuộc vào D10 (định nghĩa slot mới, đang áp). Phải chờ D10 xong mới chốt danh sách.

## 4. Điều kiện chấp nhận CERT v2

1. **Test:** bổ sung khoảng 50 phản ví dụ vào `tests/confidence_gate_check.py` và `tests/extract_eval/customer.jsonl`, gồm:
   - phủ định;
   - câu hỏi;
   - "m2";
   - "đúng/dùng/giá/gia đình";
   - câu nhiều slot;
   - câu trả lời ngắn có hoặc không có câu hỏi trước;
   - danh từ riêng.
2. **Báo cáo bốn số, trước và sau, tách theo slot:**
   - coverage (tỉ lệ lượt và câu được chứng nhận);
   - precision so với gold, kèm cận trên 95%;
   - tỉ lệ mất slot do chứng nhận rỗng;
   - số ms tiết kiệm nhờ bỏ qua Jev/Qwen, đo thật trên Kaggle.
3. **Ngưỡng chấp nhận:**
   - không có ca chứng nhận sai nào trên bộ nhãn gold;
   - coverage phía khách trên trace dev ③ tính lại bằng `scripts/confidence_audit.py` phải cao hơn hẳn 2/140;
   - TSR, RQR và HR hội thoại trên dev không giảm.
4. **Kiểm tra:** mọi phép kiểm chạy trên Kaggle CPU (`scripts/kaggle_job.py --accelerator none`). Không mở holdout.
5. **Cờ:** đặt sau cờ `EXTRACTOR_CERT_VERSION=1|2`, mặc định là `1` (hành vi cũ) cho tới khi được duyệt đổi.

## 5. Không làm trong đề xuất này

- Không chuyển CERT sang score xác suất hay ngưỡng mềm. Chỉ cân nhắc lại khi bộ câu tổng hợp (các mục D-*) có từ 300 câu gold trở lên, lúc đó mới đủ dữ liệu để hiệu chỉnh và đặt cận sai.
- Không chứng nhận claim giá, khuyến mãi hay `is_human`, vì claim sai làm tăng HR (giữ quyết định của `PLAN-HYBRID-CONFIDENCE-2026-10-29.md`).
- Không chỉnh CERT theo hướng làm đẹp RQR hoặc HR.

## 6. Quyết định cần người dùng duyệt

| Mục | Nội dung | Khuyến nghị |
|---|---|---|
| CERT-1 | Làm 3.1 + 3.2 (sửa lỗi precision và bug "m2") | Nên làm trước |
| CERT-2 | Làm 3.3–3.7 (tăng coverage) | Làm sau CERT-1, sau cờ, mặc định tắt |
| CERT-3 | Làm 3.8 (thêm slot) | Chờ D10 xong |
| CERT-4 | Đổi mặc định sang CERT v2 | Chỉ khi đạt mục 4 |

## 7. Đã làm (02/11, sau khi người dùng duyệt D18–D21)

- **Code:** `harness/rule_confidence.py` (`customer_v2`, `empty_v2`, `negated`, `is_question`, `_slot_cert`) chạy sau cờ `EXTRACTOR_CERT_VERSION=2`; mặc định vẫn là `1`.
- **CERT-1 (D18):**
  - Thêm NEG và QUES (mục 3.1) và sửa bug "m2" ở check U (3.2).
  - **Phủ định được xử lý ngay trong luật trích:** khi bật v2, `customer_slots_rules` bỏ `color`/`size`/`payment` nếu bị phủ định.
  - "k" hoặc "kg" đứng sau chữ số không bị coi là phủ định.
  - Mục 3.6 (danh từ riêng hoặc mã PII làm chứng nhận rỗng bỏ phiếu trắng) đã đưa vào `empty_v2`.
- **CERT-2 (D19):**
  - **3.3:** slot vừa hỏi lấy từ `question_slot` của **planner** ở lượt trước (`CallSession.last_q_slot`), truyền vào bằng tham số `asked`.
  - **3.4:** `UNSAFE`, `CONTEXT` và `no_extra` khớp trên bản còn dấu khi câu có dấu.
  - **3.5:** chứng nhận theo từng slot. Slot đã chứng nhận bị khóa, Jev/Qwen không ghi đè được (`extractor._lock`, `cert_locked`).
  - **3.7:** bỏ check P; check G của slot phân loại kiểm giá trị có trong catalog và có trong câu.
- **CERT-3 (D20):** thêm `address`, `self_name`, `callback_requested`, `has_children` vào `CERT_V2_SLOTS`.
- **Test:** `tests/cert_v2_check.py` (đã đưa vào `smoke.sh`) gồm các phản ví dụ và kiểm precision trên `customer.jsonl` cộng `real_ref.jsonl` (không được có ca sai). `scripts/confidence_audit.py --trace` tính lại theo cờ và truyền `asked` lấy từ trace.

**Chỉ tiêu coverage (D19, ghi trước khi đo):**
- Phía khách trên trace BTC-like dev (140 lượt), v2 phải chứng nhận **≥ 20 lượt** (khoảng 14%), so với 2/140 của v1.
- Chứng nhận rỗng v2 không được giảm quá 25% so với v1.
- Bộ nhãn tay: 0 ca chứng nhận sai.

**D21 (đổi mặc định sang v2):** chỉ làm khi đạt đủ mục 4 **và** một lần chạy dev trên GPU (cấu hình thật) cho thấy TSR, RQR, HR không giảm.
