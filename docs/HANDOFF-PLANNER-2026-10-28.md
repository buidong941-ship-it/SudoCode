# Bàn giao module planner — 28/10/2026

Tài liệu cho teammate nhận phần lập kế hoạch hội thoại. Đọc cùng [đề bài](../debaiSUDO.md), [điều chỉnh đề](../DIEU-CHINH-DE.md), [giải đáp mentor](../GIAI-DAP-MENTOR.md), [quy ước repo](../AGENTS.md) và [bảng tra agent](HAM-AGENT.md). Code hiện hành trong workspace là nguồn đúng khi tài liệu cũ lệch số dòng.

## 1. Phạm vi và hợp đồng của planner

Luồng một lượt trong `harness/agent.py::CallSession.turn()`:

`lời khách → perceive/ITN → extractor.customer_slots_start → router.route → _plan(text, slots, route) → plan → generator → guardrails.check + coverage → text_out → extractor.analyze_agent/facts_used → ghi bộ nhớ/trace`.

`_plan()` hiện **không gọi LLM để chọn goal hoặc tool**. Nó trả `(goals, facts)` bằng các nhánh code; đồng thời có thể cập nhật trạng thái `CallSession` và gọi tool nghiệp vụ. LLM chỉ có thể ảnh hưởng gián tiếp qua intent/cờ của router hoặc slot do extractor cung cấp. `turn()` ghép thêm `customer_said`, `intent`, `KNOWN`, `question_slot`, tên/xưng hô vào `plan` trước khi generator viết lời. `KNOWN` là các slot đã biết từ bộ nhớ (`carried`) cộng slot khách vừa nói; không phải nguyên văn toàn bộ lời khách. Nếu bộ trích bất đồng bộ trả slot muộn sau khi câu đã sẵn sàng, slot đó chỉ vào bộ nhớ cho lượt sau, không sửa câu đã chọn.

Các hợp đồng cần giữ:

| Đầu ra / trạng thái | Nơi dùng | Điều kiện |
|---|---|---|
| `goals` | `core/llm/generator.py` (`GOAL_NOTES`, `render_offline`), `harness/coverage.py` | Danh sách có thứ tự, khử trùng ở cuối `_plan()`; mỗi goal phải có dữ liệu đủ để nói đúng. |
| `facts` | Generator, guardrail, coverage | Giá, KM, tồn kho, mã đơn, ngày giao phải lấy từ tool/catalog/chính sách; không tự bịa hoặc lấy giá khách nhắc làm giá bán. |
| `question_slot` | `generator.question_slot(goals, facts)`, Coverage | Slot của goal hỏi cuối cùng, hoặc `None`; tối đa một câu hỏi mỗi lượt. Nếu thêm goal hỏi mới, cập nhật `QUESTION_GOALS`, câu mẫu và kiểm tra coverage. |
| `self.known` / `self.carried` | Planner, prompt, CCR | `carried` là fact còn hiệu lực từ phiên trước; `known` thêm fact mới. Phải xử lý đổi ý, TTL, hai người chung SĐT và yêu cầu xóa dữ liệu. |
| `self.focus`, `self.cart`, `self.quote`, `self.orders_created` | Báo giá, lên đơn, trạng thái cuộc gọi | Giữ nhất quán khi khách đổi sản phẩm/biến thể; `quote` và đơn đã tạo phải phản ánh đúng kết quả tool. |
| `tool_calls` / trace | Bộ chấm và kiểm lỗi | Không đổi tên/định dạng tool bắt buộc trong `schemas/tools.schema.json`; `eval/reference_eval.py` đọc trace. |

Planner **không xử lý lại lời agent để sửa câu gửi khách**. `coverage` và guardrail kiểm bản nháp trước khi chọn `text_out`; bộ trích `questions[]/claims[]` chạy sau đó để ghi trace và tính metric. Từ 28/10, `coverage` dùng luật nhận diện câu hỏi; Jev tùy chọn chỉ nằm trong `analyze_agent()` sau khi chọn lời agent.

## 2. Những gì đã làm

- `_plan()` là planner bằng code, dùng intent/cờ của router cộng regex và trạng thái phiên. Nhánh ưu tiên gồm: nhận diện khách, mở đầu khách quay lại, hỏi AI/người, xóa dữ liệu, chuyển máy y tế/ngoài phạm vi, đổi/trả và trạng thái đơn, chính sách/no-info, tư vấn sản phẩm, báo giá/KM, giỏ hàng/COD, mặc cả, chốt đơn, hẹn gọi lại, fallback. Xem `harness/agent.py` từ `_plan()` tới `_plan_callback()`.
- `question_slot()` đã tách quyết định **hỏi gì** khỏi generator **nói thế nào**. Prompt cấm hỏi khi slot là `None`; `coverage` bắt thiếu nội dung, nhiều câu hỏi, hỏi mở slot đã biết và nhánh hỏi sai. Bản nháp không đạt được sinh lại một lần, rồi dùng câu mẫu khi cần. Chi tiết ở [nhật ký 25/10](NHAT-KY-2026-10-25.md) mục 2–3.
- Giá dùng `_quote()` và tool `pricing.get_quote`; biến thể/size, KM có điều kiện, mẫu ngừng bán, hàng hết, COD > 10 triệu và giỏ nhiều món đã có nhánh xử lý. `order.create` dùng giá tool, xử lý `price_mismatch`; `order.update`, `order.status`, `schedule.callback`, `handoff.transfer` có đường riêng.
- Bộ nhớ khách đa phiên được nạp ở `_bind()`/`_build_brief()`. Lượt đầu khách quay lại dùng `opening_returning`, cảnh báo KM/giá cũ; thông tin đã hết hạn không tiếp tục nằm trong `known`.
- Hai biến thể `hyb4` và `hyb5` đã chạy trên Kaggle, mỗi biến thể có full/baseline trên sample, dev, test. [Nhật ký 27/10](NHAT-KY-2026-10-27.md) chứa trace, lỗi và số chi tiết. Kết quả `hyb5` (`GEN_PLACEHOLDERS=0`, 2 worker): TSR sample/dev/test **85,7 / 100 / 95,5%**, TSR ca khó test **94,7%**, HR test **0%**. Đây là số của phiên bản trước thay đổi classifier ngày 28/10, không phải lần chạy xác nhận code hiện tại.
- Ngày 28/10 đã loại đường huấn luyện classifier để tuân thủ đề. `QUESTION_CLF=0` mặc định; không fine-tune, LoRA, SFT hoặc train classifier trong phần planner. Xem [nhật ký 28/10](NHAT-KY-2026-10-28.md).

## 3. Ranh giới khi teammate sửa

1. Chỉ dùng `datagen/out_nat/dev`, `test_set/public_sample`, catalog/chính sách và ví dụ tự viết để phát triển. Không xem câu trong `datagen/out/test/` hoặc trace test để viết luật/prompt. Chạy test để **đo** sau khi sửa, giữ nguyên test. Không sửa `eval/`, `catalog/`, `policy/`, `test_set/`, `schemas/`, `rag/` để cải thiện điểm; nếu thấy dữ liệu BTC bất nhất, ghi vấn đề và bằng chứng.
2. Đề cấm huấn luyện lại/fine-tune model. Cải tiến planner bằng logic, dữ liệu, prompt, điều phối và tool có sẵn. Giữ baseline và hệ thống cùng model/tham số; khác biệt baseline chính là không nạp bộ nhớ cũ.
3. Không đưa giá/khuyến mãi/ngày giao từ suy đoán vào `facts`. Dựa vào kết quả tool hiện hành theo ngày cuộc gọi. Giữ PII được che khi gửi model ngoài và khi ghi log.
4. Khi thêm/sửa goal, rà đồng thời `_plan`, `question_slot`, `GOAL_NOTES`, `render_offline`, `coverage` và trace. Nếu goal thiếu facts, generator có thể nói sai hoặc rơi về câu mẫu dù planner chọn đúng nhánh.
5. Mọi thay đổi ảnh hưởng hành vi phải có kiểm tra tập trung dưới `tests/`, chạy smoke/integration tương ứng. Trên máy Windows hiện tại `bash tests/smoke.sh` báo WSL `E_ACCESSDENIED`; các kiểm tra Python có thể chạy bằng `venv/Scripts/python.exe -X utf8`. Các lượt đánh giá LLM/tốn RAM nên chạy trên Kaggle như người dùng yêu cầu; dùng `--workers 2` đã giảm thời gian nhưng số latency này không thay cho đo 1 worker.

## 4. Điểm cần theo dõi khi cải tiến

| Vấn đề | Phân loại / hướng xử lý |
|---|---|
| `SAMPLE-02` yêu cầu `promo_active=false` khi tool cho KM còn hiệu lực; `SAMPLE-03` kỳ vọng mã đơn khác mã tool tạo | Bất nhất giữa đáp án và tool trong [PLAN](PLAN.md), không ép planner bịa để khớp. Ghi riêng khi báo cáo. |
| `GEN-T21-02`: đổi địa chỉ sang vùng khác nhưng `order.update` không trả ngày giao mới | Thiếu dữ liệu tool; không tự tính ETA trong planner. Cần làm rõ đầu ra tool hoặc chấp nhận báo chưa có ngày mới. |
| `GEN-T10-01`: câu giá mẫu thay thế đúng nhưng bộ chấm đối chiếu với giá mẫu chốt sau đó | Giới hạn evaluator đã ghi trong [PLAN](PLAN.md); không dùng test để chỉnh luật. |
| `hyb5-ph` test TSR 90,9% thấp hơn `hyb5` 95,5%; placeholder làm tăng câu mẫu ở một số lượt | Chưa chứng minh quan hệ nhân quả vì mỗi cấu hình chạy một lần. So trace theo nguyên nhân trước khi đổi planner. |
| RQR test ở vài lần chạy cao dù dev thấp; mẫu câu hỏi ít | Xem trace và nhãn trích `questions[]` trước khi quy trách nhiệm cho planner. Không bỏ câu hỏi thật khỏi trace để đẹp metric. |
| Total p95 test `hyb5` 8,155 s ở 2 worker | Vượt nhẹ ngưỡng 8 s; tối ưu không được làm mất facts hoặc tăng HR/vi phạm. Đo lại theo cấu hình chấm nếu cần kết luận SLA. |

## 5. Cách bắt đầu và tiêu chí bàn giao lại

1. Đọc `harness/agent.py` các phần `turn`, `_plan`, `_quote`, `_plan_order`, `_plan_order_change`, `_plan_callback`; đối chiếu `core/llm/generator.py::question_slot`, `GOAL_NOTES` và `harness/coverage.py`.
2. Chọn một lỗi planner trên **dev/sample** có trace và kỳ vọng rõ; ghi trước/sau: `goals`, `facts`, `question_slot`, tool_calls, câu cuối, action guardrail/coverage. Ưu tiên lỗi làm giảm TSR/CCR hoặc tăng HR/RQR, không tối ưu theo một metric riêng.
3. Chạy `python tests/coverage_check.py`, các kiểm tra liên quan và `bash tests/smoke.sh` trong môi trường Bash dùng được. Chạy full + baseline trên cùng tập bằng `run_eval.py`, chấm `eval/reference_eval.py`; các lượt Jev/Qwen thực hiện trên Kaggle, lưu output riêng trong `runs/kaggle/` và ghi rõ workers/seed/cấu hình.
4. Bàn giao PR hoặc bản sửa gồm: lỗi gốc, nhánh planner đổi, test thêm, trace trước/sau, bảng TSR/CCR/RQR/HR và latency, các ca xấu đi, giới hạn còn lại. Không thay đổi ground truth để đạt điểm.

Tài liệu này mô tả trạng thái hiện hành và các hợp đồng cần giữ khi teammate tiếp tục phần planner.
