# Plan: Dùng Jev phân loại câu hỏi và slot trực tiếp

## Mục tiêu

Thử để Jev phân loại **mọi câu trong lời agent** thành `none` hoặc một slot câu hỏi đã định nghĩa, đồng thời xác định `open`/`confirm`. Đường thử nghiệm không dùng regex để quyết định câu nào được gửi cho Jev. Chỉ chọn thay bộ trích hiện tại nếu chất lượng câu hỏi, metric hội thoại và latency được kiểm chứng trên dữ liệu độc lập.

Đây là kế hoạch đánh giá và tích hợp model **có sẵn**. Không huấn luyện hoặc fine-tune, theo `debaiSUDO.md` và `GIAI-DAP-MENTOR.md`.

## Cổng bắt buộc trước khi sửa code

**Không sửa bất kỳ file code, test, cấu hình hay prompt nào trong repository để tích hợp Jev đa nhãn trước khi có metric Jev đa nhãn được kiểm chứng.** Giai đoạn đầu chỉ đọc code/tài liệu, gán nhãn dữ liệu và chạy phép thử Jev độc lập bằng lệnh hoặc notebook tạm; lưu kết quả dưới `runs/` hoặc `data/`, không commit prototype. Việc đo nhị phân hiện có **không** đủ để qua cổng này.

Chỉ mở giai đoạn sửa code sau khi phép thử trên tập nhãn người rà mới báo đầy đủ TP/FP/FN, precision/recall/F1 cho phát hiện câu hỏi, đúng slot và `open`/`confirm`, cùng request count, lỗi API và p50/p95 latency. So với rules và hybrid hiện hành trên **cùng các câu**, rà các bất đồng và chốt quyết định bằng văn bản. Nếu Jev không đạt tiêu chí ở mục “Quyết định triển khai”, dừng ở báo cáo; không tạo backend hay sửa runtime.

## Vì sao cần thử

- `harness/question_classifiers/jev.py` hiện chỉ trả xác suất nhị phân `is_question`. Sau đó `harness/extractor.py::agent_questions` vẫn dùng `SLOT_KW` để gán slot.
- `harness/llm_extract.py::agent` cũng lọc câu ứng viên bằng `_is_question`, `MAYBE_ASK_RX`, `CLAIM_HINT_RX`; nhãn `ask` của LLM có thể bị bỏ nếu câu không qua cổng câu hỏi. Nhật ký 24/10 mục 5.7 ghi sáu câu yêu cầu thiếu dấu `?` từng bị bỏ trước LLM; bản sửa bắt được sáu dạng ấy nhưng cổng regex vẫn còn.
- Jev router trong `core/llm/router.py` đã dùng `Choice` nhiều nhãn. Có thể dùng cùng khả năng đó để thử `none` + các slot câu hỏi. Đây là **giả thuyết kỹ thuật**, chưa có kết quả chất lượng đa nhãn.
- Bộ 200 câu đã chấm Jev chỉ có nhãn câu hỏi nhị phân; test 40 câu cho Jev + rules P100/R80/F1 88,9. Không dùng số này để khẳng định Jev sẽ gán slot tốt hơn, và không chỉnh ngưỡng theo test cũ.

## Phạm vi và hợp đồng

1. Lấy danh sách slot từ một nguồn chung với `QUESTION_SLOTS` / `SLOT_KW` hoặc có phép kiểm bảo đảm hai danh sách khớp. Có nhãn `none` cho câu không hỏi. Không thêm nhãn theo kịch bản test.
2. Phân loại **từng câu agent**, kể cả câu không có dấu `?` hoặc từ khóa quen thuộc. Không cho `agent_questions` hay regex chọn câu đầu vào của Jev.
3. Kết quả câu hỏi gồm `slot`, `type` (`open` hoặc `confirm`) và `text` nguyên câu như trace hiện tại. `confirm` phải xét cả nội dung câu và `known_values`; không tự biến một câu hỏi mở thành xác nhận chỉ vì slot đã có trong bộ nhớ.
4. Che PII trước request Jev. API lỗi, timeout hoặc câu trả kết quả không hợp lệ thì dùng rules và ghi `fallback`/latency rõ ràng.
5. Giữ `questions[]` trong trace đầy đủ. Không bỏ câu hỏi thật để làm đẹp RQR. Không sửa `eval/`, ground truth, catalog, policy hoặc scenario để tăng điểm.
6. Tách hai vai trò: **trích `questions[]` sau khi có câu trả lời** và **coverage kiểm câu nháp trước khi gửi khách**. Nếu đưa Jev vào coverage, đo riêng chi phí response-ready và bảo đảm nhánh fallback; không bật hai thay đổi cùng lúc trong một ablation.

## Bước 1 — Chuẩn bị nhãn và baseline

1. Đọc `docs/NHAT-KY-2026-10-24.md` mục 5.7, `docs/NHAT-KY-2026-10-28.md`, `docs/HANDOFF-PLANNER-2026-10-28.md`, `harness/question_classifiers/jev.py`, `harness/extractor.py`, `harness/llm_extract.py`, `harness/coverage.py`, `core/llm/router.py`.
2. Tạo bộ nhãn người rà mới từ **dev/sample và câu mới độc lập**: mỗi câu có `is_question`, `slot` hoặc `none`, `type` nếu là câu hỏi, ghi chú trường hợp mơ hồ. Bao gồm câu hỏi không có `?`, lời đề nghị, câu dặn dò, câu xác nhận, câu có nhiều slot, phủ định và câu có số/khuyến mãi. Khử trùng câu giữa các split. Giữ một holdout chưa xem kết quả khi thiết kế prompt/tiêu chí.
3. Chốt cách gán nhãn khi một câu hỏi chứa nhiều slot hoặc khi tên slot không có trong danh sách. Ghi hướng dẫn trước khi chấm; nếu cần, dùng nhãn `other` đúng hợp đồng trace hiện có.
4. Chạy baseline rules và hybrid Qwen hiện hành trên cùng bộ nhãn; đo Jev nhị phân hiện hành riêng cho phát hiện câu hỏi. Lưu TP/FP/FN, precision/recall/F1 theo các nhãn mà từng phương pháp thực sự trả, cùng latency/request count và lỗi API. Không gán metric slot cho Jev nhị phân và không so lẫn số liệu lịch sử từ môi trường khác.

## Bước 1b — Kiểm chứng Jev đa nhãn độc lập, chưa sửa repo

1. Dùng request `TypeSafeClient.system_one` tạm thời ngoài runtime hiện hành để thử `Choice` gồm `none` và các slot; thử thêm `open`/`confirm` nếu API hỗ trợ. Gửi **mọi câu** trong tập nhãn, không qua regex ứng viên. Không tạo backend, đổi cấu hình hoặc sửa file source/test trong repo ở bước này.
2. Chấm trên dev/tune, chốt prompt và cách đọc output; sau đó đo một lần trên holdout mới chưa dùng để điều chỉnh. Báo số theo từng slot và loại câu hỏi, lỗi/timeout, request count và latency. Đối chiếu thủ công false positive/false negative, đặc biệt các câu yêu cầu không có `?`.
3. So kết quả Jev đa nhãn với baseline trên cùng tập. Chỉ khi đạt tiêu chí mục “Quyết định triển khai” mới chuyển sang Bước 2. Nếu không đạt, kết thúc bằng báo cáo metric và nguyên nhân; không sửa code.

## Bước 2 — Tích hợp Jev đa nhãn, chỉ sau khi qua cổng metric

1. Sau khi đã ghi nhận kết quả đạt cổng ở Bước 1b, thêm backend thử nghiệm riêng trong `harness/question_classifiers/` hoặc module tương đương; chưa đổi `QUESTION_CLF=0` mặc định. Dùng `TypeSafeClient.system_one` với `Choice` cho `none` + slot. Dùng cách phân loại `open`/`confirm` đã được kiểm chứng ở Bước 1b; nếu cần thay cách này, đo lại trước khi tích hợp.
2. Gửi mọi câu trong một lời agent. Kiểm khả năng gom các câu vào **một request**; nếu SDK không hỗ trợ an toàn thì đo số request theo số câu. Không giả định latency của phân loại nhị phân (~118/173 ms p50/p95 trên phiên 28/10) sẽ giữ nguyên với đa nhãn hoặc nhiều câu.
3. Chuẩn hóa output về schema trace hiện tại. Từ chối nhãn lạ, câu thiếu kết quả hoặc output không khớp index; fallback rules cho phần thất bại. Ghi `backend`, `ms`, request count và fallback ở metadata.
4. Viết kiểm tra tập trung cho câu thiếu `?`, câu dặn dò có từ khóa slot, xác nhận slot đã biết, nhiều câu trong một lượt, lỗi/timeout Jev và PII. Không dùng câu test để viết luật hoặc prompt.

## Bước 3 — Đánh giá chất lượng và latency

1. Sau tích hợp, chạy lại trên dev/tune và holdout bằng prompt/cách xử lý output đã chốt ở Bước 1b để xác nhận code runtime giữ đúng metric Jev độc lập. Báo bảng riêng cho phát hiện câu hỏi, gán slot và `open`/`confirm`; không chỉ báo một F1 tổng.
2. So ba biến thể trên cùng câu: rules, hybrid Qwen hiện hành, Jev đa nhãn. Đếm lỗi do Jev bỏ sót, sai slot, sai `confirm`, câu kể bị gán thành câu hỏi và lỗi API. Rà thủ công các bất đồng; không coi nhãn của một model là ground truth.
3. Chạy replay trên dev/sample để xem `questions[]` đổi thế nào và ảnh hưởng RQR/TSR/HR. Sau đó chạy cặp Qwen + Jev trên cùng scenario, model, worker, `GEN_PARALLEL_N`, cache/môi trường. Báo `total_ms` (reply-ready), `post_ms`, `end_to_end_ms`, p50/p95 và request count. Jev dùng sau khi có câu đáp có thể giảm chi phí post nhưng **không tự giảm reply-ready**.
4. Nếu Jev được dùng cho coverage, chạy ablation thứ hai riêng: rules coverage hiện tại so với Jev coverage. Đo số lần sinh lại/câu mẫu, câu hỏi thừa còn lọt, TTFT và reply-ready p95. Giữ luật an toàn và fallback khi Jev không trả đúng hạn.
5. Test hiện có chỉ dùng để báo kết quả cuối; theo `docs/HANDOFF-PLANNER-2026-10-28.md`, không xem nội dung test để thiết kế prompt/luật.

## Quyết định triển khai

Chỉ thay phân loại câu hỏi hiện hành khi Jev đa nhãn trên **holdout mới** đạt đồng thời:

- Recall phát hiện câu hỏi và độ đúng slot ít nhất ngang hybrid hiện hành, không tăng false positive gây RQR/TSR sai.
- `open`/`confirm` đủ tin cậy để không đánh dấu sai câu hỏi thừa.
- Tỷ lệ lỗi/timeout có fallback rõ và không làm xấu latency mục tiêu. Nếu dùng trong coverage, TTFT p95 vẫn ≤ 3 s và reply-ready p95 vẫn ≤ 8 s theo mục tiêu đề.
- Không làm xấu TSR, CCR, HR và guardrail trong suite hội thoại tương đương. Báo cả trường hợp xấu đi.

Nếu chưa đạt, giữ Jev đa nhãn ở chế độ shadow để thu nhãn/bất đồng và tiếp tục dùng rules + hybrid hiện hành. Không bật chỉ vì F1 trên bộ 200 câu cũ tăng.

## Bàn giao cho phiên code

Ghi các file sửa, định nghĩa nhãn, split và hash dữ liệu, prompt/Choice schema, cấu hình model, request count, TP/FP/FN theo từng slot, kết quả kiểm tra, latency trước/sau và quyết định bật/tắt. Giữ output chạy dưới `runs/` hoặc `data/`; không đưa credential hay PII vào repo.
