# Khung slide (≤ 15 trang) — hồ sơ nộp vòng 1 (D17, bản nháp 02/11/2026)

Số liệu điền sau C5 / vòng 0 / vòng 1 (ô **[chờ]**), lấy từ `docs/BAO-CAO-DANH-GIA.md`. Mỗi trang một ý chính, ≤ 40 chữ trên slide.

| # | Tiêu đề | Nội dung chính | Hình / số |
|---|---|---|---|
| 1 | Telesale AI nhớ khách | Tên nhóm, một câu giá trị: "gọi lại không hỏi lại, không báo sai giá" | — |
| 2 | Bài toán | Khách gọi nhiều lần, nhiều kênh; nhân viên quên ngữ cảnh → hỏi lại, báo giá cũ, hứa sai | 3 chỉ số đề: RQR, TSR, HR |
| 3 | Kiến trúc một lượt | router → planner bằng code → generator → guardrails → extractor → bộ nhớ → trace; 2 MCP server | sơ đồ `docs/ARCHITECTURE.md` |
| 4 | Bộ nhớ & Call Brief | Fact có hạn dùng, fact bị thay thế vẫn lưu nguồn; Call Brief dựng < 100 ms | ảnh UI tab Bộ nhớ |
| 5 | Giá chỉ từ tool | Guardrail chặn số tiền không có trong kết quả tool; chặn đọc ngân sách khách như giá bán (B5) | ví dụ BTCL-031 trước/sau |
| 6 | Extractor lai có chứng chỉ | Luật → CERT (nhị phân, kiểm bằng mắt) → Jev chọn nhãn → Qwen trọng tài; định nghĩa slot D10 | tỉ lệ lượt bỏ qua LLM **[chờ]** |
| 7 | Dữ liệu đánh giá | public_sample, out_nat dev/test, BTC-like v1_1 dev/holdout, D-7, real_ref (câu thật CC BY-NC) | bảng `docs/DATASET.md` |
| 8 | Kết quả chính | full vs baseline trên dev (trung bình 3 lần C5) | TSR / RQR / CCR / HR **[chờ]** |
| 9 | HR có xét SKU | evaluator so giá phụ kiện với giá máy → báo 3 con số | `scripts/hr_by_sku.py` **[chờ]** |
| 10 | Cơ chế cải tiến | gap → đề xuất → người duyệt → nạp → đo → quay lui; chỉ feedback từ dev | sơ đồ `docs/HAM-IMPROVE.md` |
| 11 | Vòng 0 → vòng 1 | dev và **holdout chưa từng nhìn** | bảng `scripts/compare_rounds.py` **[chờ]** |
| 12 | Phân tích lỗi | 12 ca (bảng mục 4 báo cáo): nguyên nhân gốc, cách sửa, ca còn mở | — |
| 13 | Chi phí & latency | p95 ~15 s trên T4 8B-AWQ; chi phí mỗi cuộc gọi | `scripts/cost_report.py` **[chờ]** |
| 14 | Demo C.6 | 3 cuộc gọi: tư vấn → chốt đơn không hỏi lại → hỏi vận đơn | ảnh UI tab Demo |
| 15 | Hạn chế & bước tiếp | dữ liệu mô phỏng, bộ câu thật khác lĩnh vực, Jev là API ngoài, SAMPLE-03 chờ BTC | — |

Video demo 5–8 phút (đề C.6): quay tab Demo C.6 của UI (`streamlit run ui/app.py`, generator Qwen hoặc DeepSeek), sau đó chạy `eval/reference_eval.py` trực tiếp để cho thấy số so với baseline.
