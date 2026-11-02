# Báo cáo đánh giá (bản nháp, 01/11/2026)

> Bản nháp cho hồ sơ nộp (PLAN-2026-11-01 mục G). Ô ghi **[chờ]** sẽ điền sau C5 (3 lần chạy dev), C4 (vòng 0 trên holdout) và vòng cải tiến 1. Số offline (router `rules`, generator `offline`) chỉ dùng để kiểm pipeline, không dùng làm số báo cáo.

## 1. Hệ thống được đánh giá

- **Agent telesale tiếng Việt có bộ nhớ khách xuyên phiên và đa kênh.** Mỗi lượt đi qua các bước: router, planner bằng code, generator, guardrails, extractor, bộ nhớ, rồi ghi trace. Tool và bộ nhớ đi qua hai MCP server; trace của `--transport direct` giống hệt trace qua MCP (`tests/mcp_parity.py`: 0/78 lượt lệch).
- **Cấu hình ứng viên nộp bài:** router `rules`, generator Qwen3-8B-AWQ trên vLLM (T4), extractor `hybrid` (luật, rồi Jev chọn nhãn, Qwen làm trọng tài) với `EXTRACTOR_CONFIDENCE_GATE=1`, `EXTRACTOR_JEV_HYBRID=1`, `JEV_DROP_POLICY=qwen`. Chốt cuối cùng ở C6 theo kết quả C5 **[chờ]**.
- **Baseline:** cấu hình `baseline_no_memory`, dùng cùng code nhưng không đọc bộ nhớ của phiên trước.

## 2. Bộ đo

| Bộ | Nguồn | Quy mô | Vai trò |
|---|---|---|---|
| `test_set/public_sample` | BTC | 7 scenario | Đối chiếu với BTC |
| `datagen/out_nat/dev` / `test` | Nhóm (template + naturalize) | xem `docs/DATASET.md` | Dev để sửa; test chỉ để đo |
| BTC-like `final_v1` dev / holdout | Nhóm, mô phỏng theo dạng đề BTC | 28 / 40 scenario | Dev để sửa; holdout chỉ chạy **một lần** sau đóng băng (vòng 0) |
| BTC-like `final_v1_1` | Như v1, đã vá 5 ca `delivery_address` không thể qua (B3) | 28 / 40 | Bộ đo chính từ 01/11 |
| D-7 dev (`BTCD7-*`) | Claude viết template và lời viết lại | 30 scenario | Kiểm thêm 5 họ lỗi |
| `tests/extract_eval/*` cùng `real_ref.jsonl` | Nhãn tay; `real_ref` là câu thật CSConDa (CC BY-NC 4.0) | 60 + 120 + 200 câu | Đo riêng extractor và lexicon |

Nguyên tắc chống rò rỉ: không mở holdout hay test trước đóng băng. Dữ liệu tự sinh được kiểm trùng n-gram với các bộ đo. Một sự cố được ghi ở `docs/DATASET.md` §8.3.

## 3. Kết quả chính

### 3.1. BTC-like dev (Kaggle T4, Qwen3-8B-AWQ, extractor hybrid)

| Lần chạy | TSR full / baseline | RQR full / baseline | CCR | HR giá & KM (chính thức) | Guardrail | Total p95 |
|---|---|---|---|---|---|---|
| ③ (31/10) | 71,4 / 35,7 | 15,4 / 42,3 | 81,6 | 14,3 | 0 | 15,4 s |
| 01/11, `JEV_DROP_POLICY=accept` | 85,7 / 50,0 | 10,5 / 46,4 | 78,9 | 14,5 | 0 | 15,3 s |
| 01/11, `JEV_DROP_POLICY=qwen` | **92,9** / 50,0 | 14,3 / 40,0 | 78,9 | 15,8 | 0 | 15,6 s |
| C5: trung bình 3 lần, cấu hình chốt | **[chờ]** | **[chờ]** | **[chờ]** | **[chờ]** | **[chờ]** | **[chờ]** |

Mức giảm RQR so với baseline: 63,6% ở lần ③, 71,0–64,2% ở hai biến thể ngày 01/11. Cả ba đều đạt ngưỡng 40% của đề. TSR đạt ngưỡng 70%.

### 3.2. HR có xét SKU (C2)

`eval/reference_eval.py` so mọi claim cùng field với ground truth của sản phẩm chính, không xét claim nói về SKU nào. Ở lần ③, 8/9 claim bị chấm sai là giá của **sản phẩm khác**, ví dụ màng lọc 690.000đ bị so với giá máy 5.200.000đ. Vì vậy báo cáo ghi ba con số, tính bằng `scripts/hr_by_sku.py` (script của nhóm, không sửa `eval/`):

| | Chính thức | Chỉ SKU chính | Đối chiếu tool theo SKU |
|---|---|---|---|
| BTC-like dev, cấu hình chốt | **[chờ]** | **[chờ]** | **[chờ]** |

### 3.3. Holdout và vòng cải tiến

| | Dev TSR / HR | Holdout TSR / HR |
|---|---|---|
| Vòng 0 (đóng băng, C4) | **[chờ]** | **[chờ]** |
| Vòng 1 (Gap Loop + Exemplar Bank, chỉ đề xuất đã duyệt) | **[chờ]** | **[chờ]** |

Cơ chế cải tiến (`improve/`, mục D/E): gom gap từ dev, đề xuất FAQ / playbook / exemplar / cue, người duyệt, nạp qua `harness/improve_hook.py`, so vòng bằng `scripts/compare_rounds.py`, quay lui khi TSR tụt quá 3 điểm hoặc HR tăng. Feedback chỉ lấy từ dev. Phần sửa tay trước vòng 0 là công việc phát triển, **không** tính là cải tiến.

## 4. Phân tích lỗi (≥ 10 ca)

| # | Ca | Nhóm | Nguyên nhân gốc | Xử lý |
|---|---|---|---|---|
| 1 | BTCL-041/042 | Sai ý định | Câu hỏi hoàn tiền sau 2 năm rơi vào nhánh xác nhận đơn | B1: so thời hạn khách hỏi với mọi thời hạn trong tài liệu, vượt thì nói `no_info` |
| 2 | BTCL-061/062 | Riêng tư | Không có nhánh từ chối khi khách xin SĐT của khách khác | B2: goal `refuse_other_customer`, guardrail bắt buộc câu từ chối |
| 3 | BTCL-046/047 | Mất địa chỉ | Regex cắt địa chỉ dính chữ "không"; Jev bỏ nhãn vì địa chỉ đã bị che thành `[ĐỊA_CHỈ_1]` | A5 sửa regex; A6 `JEV_DROP_POLICY=qwen`; A7 sửa định nghĩa nhãn và hướng dẫn gửi Jev |
| 4 | BTCL-016/017 | "Mất ngữ cảnh" | **Lỗi bộ dữ liệu:** khách tổng hợp chat fanpage rồi gọi hotline, không có cách hợp lệ nối hai kênh | B3: vá thành v1_1 (khách CRM có `fb_id`); agent xin thông tin để tra lịch sử thay vì hỏi lại sản phẩm |
| 5 | BTCL-031 | Sai giá | "Tầm 5 triệu rưỡi có vừa không" rơi vào `closing`; Qwen đọc ngân sách thành giá; guardrail cho qua vì số do khách nói | B5: goal `budget_fit`; guardrail chặn số tiền khách nêu khi bị đọc như giá bán |
| 6 | BTCL-051/052 | Lệch câu hỏi quà | "Có tặng màng lọc không" được hiểu thành hỏi giá phụ kiện | B4: `gift_status` theo KM của sản phẩm chính; trả lời được câu hỏi hạn KM |
| 7 | BTCL-021/022/057 | HR do evaluator | Giá sản phẩm phụ bị so với ground truth sản phẩm chính | C2: báo kèm HR theo SKU |
| 8 | SAMPLE-02 | HR do evaluator | Ground truth `promo_active: false` trong khi `mock_tools` áp GIFT-FILTER ngày 18/10 | Ghi nhận; HR đối chiếu tool theo SKU |
| 9 | Demo C.6, cuộc 2 | Sai fact | "Giao về số 12 Nguyễn Trãi" → `size = 12` | L1: lexicon `size.neg.so_nha` |
| 10 | Demo C.6, cuộc 3 | Sai ý định | "Đơn … giao tới đâu rồi" không khớp luật `order_status` | L2: chưa sửa luật; planner LLM có thể chọn `order_status` |
| 11 | 15/28 lượt fallback dev | Trì hoãn không nhận ra | "so thêm rồi phản hồi", "chờ đối chiếu", "xem rồi nhắn lại" không khớp cờ defer | B-H planner LLM (`defer_ack`) cùng lexicon |
| 12 | SAMPLE-03 / SAMPLE-06 | Đơn hàng | `order.update` dùng mã đơn mới tạo thay vì mã trong CRM; `order.create` báo `tool_exception` | L3/L4, chưa sửa |

## 5. Chi phí và latency

- Total p95 khoảng 15,3–15,6 s trên T4 với 8B-AWQ. Khoảng 81% latency là thời gian Qwen sinh chữ.
- Chứng nhận rỗng giúp bỏ qua Jev và Qwen ở khoảng 14–27% lượt khách trên dev.
- Chi phí mỗi cuộc gọi tính bằng `scripts/cost_report.py` từ `llm_usage` và số lần gọi Jev/LLM, với đơn giá ghi rõ: **[chờ]**.

## 6. Tác động kinh doanh (ước lượng)

**[chờ số C5]** Gồm: tỷ lệ chốt ở cuộc gọi thứ hai khi có bộ nhớ so với baseline (TSR full so với baseline), số câu hỏi lặp tránh được (RQR), rủi ro báo sai giá (HR theo SKU), và chi phí mỗi cuộc so với chi phí nhân viên.

## 7. Hạn chế

- Bộ BTC-like và D-7 là dữ liệu mô phỏng của nhóm. Câu tự sinh đều và sạch hơn lời khách thật.
- Bộ câu thật duy nhất (`real_ref.jsonl`) là CSKH phần mềm B2B, không phải telesale.
- Evaluator không xét SKU khi chấm HR.
- Jev là API ngoài, nên cấu hình có Jev không đạt điểm thưởng "chạy local toàn bộ".
- Planner LLM (B-H) mặc định tắt cho tới khi đạt tiêu chí nhận.
