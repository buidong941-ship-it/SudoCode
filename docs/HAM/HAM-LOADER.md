# Bảng tra hàm của `harness/loader.py`

[harness/loader.py](../harness/loader.py) đọc file kịch bản (định dạng `test_set/public_sample`, mô tả ở `schemas/scenario_format.md`) và **chỉ đưa cho agent phần agent được biết**. Đây là lá chắn chống rò đáp án: các trường dùng để chấm không bao giờ tới agent.

Agent nhận: lượt khách (`customer_turns_asr` nếu có, không thì `customer_turns`), kênh, định danh kênh, ngày gọi, SĐT, `seed_history`. Bị ẩn: `facts_established`, `must_not_ask`, `must_carry_over`, `success_if`, `ground_truth_facts`, `memory_expectation`, `expected_outcome`, `notes`, `customer_name`, `_meta`. Số dòng ứng với code ngày 17/10/2026.

**Ai dùng file này:** `run_eval.py` (`load_scenarios`, `agent_view`), `datagen/export_transcripts.py` (`agent_view`).

## 1. Hằng số

| Tên | Ý nghĩa |
|---|---|
| `REF_DATE` [:12](../harness/loader.py#L12) | Ngày quy ước "hôm nay" của bộ dữ liệu BTC: `2026-10-15` |

## 2. Hàm

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `load_scenarios(path)` [:15](../harness/loader.py#L15) | Đọc mọi file `.json` trong thư mục (đệ quy) hoặc một file. Bỏ file bắt đầu bằng `_`, `manifest*`, `validate_report.json`, `report.json`, và file không có cả `calls` lẫn `scenario_id` | thư mục hoặc đường dẫn file | list kịch bản (dict nguyên bản, còn đáp án) | |
| `agent_view(s)` [:28](../harness/loader.py#L28) | Biến một kịch bản thành danh sách cuộc gọi chỉ chứa thông tin agent được biết. Sắp cuộc gọi theo số (`call_1`, `call_2`…). Ngày mỗi cuộc: `call_date` nếu có; không thì cuộc đầu = `REF_DATE` + `days_later`, cuộc sau = ngày cuộc trước + `days_later`. `input_mode` lấy từ kịch bản, hoặc `asr_transcript` khi có `customer_turns_asr` | dict kịch bản | `{scenario_id, phone, calls: [{call, date, channel, channel_identity, input_mode, turns, seed_history}]}` | |

## 3. Ghi chú khi đọc code

- **`seed_history` đi vào bộ nhớ, không vào prompt.** `run_eval.py` gọi `CallSession.import_old_session` cho từng phiên cũ, như dữ liệu CRM có trước cuộc gọi.
- **Script chấm BTC đọc kịch bản theo cách riêng** (`eval/reference_eval.py`, chỉ thư mục phẳng `*.json`), nên hai bên không phụ thuộc nhau.
