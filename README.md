# Harness Agent Call Center | SUDO CODE 2026

Agent telesale tiếng Việt có bộ nhớ xuyên phiên và đa kênh. Khi khách quay lại, agent nạp Call Brief để tiếp tục hội thoại. Bộ nhớ và công cụ nghiệp vụ được cung cấp qua MCP. Repo có web demo, xử lý ghi âm bằng ASR local và script đánh giá Full so với Baseline không đọc bộ nhớ phiên trước.

## Cấu trúc repo

```text
SudoCode/
├── run_eval.py     # Chạy kịch bản và xuất trace
├── core/           # Cấu hình và client gọi model
├── harness/        # Vòng lặp agent, Call Brief, bộ nhớ và guardrails
├── mcp_servers/    # Công cụ thương mại và bộ nhớ qua MCP
├── ui/             # Web demo và kịch bản hai cuộc gọi
├── asr/            # Nhận dạng ghi âm tiếng Việt trên máy
├── improve/        # Thu feedback, duyệt và đóng gói cải tiến
├── scripts/        # Chạy đánh giá, khởi tạo môi trường và điều phối C.5
├── kaggle/         # Launcher đánh giá và web demo trên Kaggle
├── profiles/       # Cấu hình chạy theo môi trường
├── eval/           # Công cụ giả lập và bộ chấm BTC
├── catalog/        # Sản phẩm, tồn kho, khuyến mãi và CRM seed
├── policy/         # Chính sách dùng để trả lời và kiểm tra
├── schemas/        # Định dạng tool, Call Brief và trace
├── rag/            # Dữ liệu chấm truy hồi chính sách
├── test_set/       # Kịch bản mẫu của BTC
├── datagen/        # Script và template tạo dữ liệu của nhóm
└── docs/           # Kiến trúc, mô tả dữ liệu và báo cáo
```

## Cấu hình bản nộp

| Hạng mục | Giá trị |
| --- | --- |
| Commit hoặc tag | [Điền sau khi chốt bản nộp] |
| Profile đánh giá và profile demo | [Điền tên và lệnh nạp từng profile] |
| Model và phần cứng | [Điền provider, model và yêu cầu máy cho từng thành phần trong `.env.example`] |

## Chạy trên máy cá nhân

Tại thư mục gốc repo, tạo môi trường Python và cài `requirements.txt`. Nếu mở web demo, cài `requirements-ui.txt`. Sao chép `.env.example` thành `.env` rồi điền khóa cho cấu hình đã chọn. Trên Windows, đặt `$env:PYTHONIOENCODING = 'utf-8'` trước khi chạy.

[Điền cách nạp profile và endpoint model cần dùng trên máy cá nhân.]

Chạy web bằng `python -m streamlit run ui/dashboard.py` và mở tab **Demo C.6**. Kịch bản có hai cuộc gọi của cùng một khách. Cuộc đầu tư vấn, báo giá và ưu đãi rồi hẹn khách hỏi người nhà. Cuộc sau hiển thị Call Brief, tiếp tục tư vấn và chốt đơn.

Xem [hướng dẫn ASR local](docs/HARNESS.md#asr) để chạy nhận dạng ghi âm và xuất kết quả đo.

## Chạy trên Kaggle

Mở [điền link notebook đánh giá] và dùng đúng commit hoặc tag ghi ở trên. Gắn khóa vào Kaggle Secrets theo tên trong `.env.example`.

[Điền loại GPU, lệnh chạy hai cấu hình và đường dẫn lấy trace/báo cáo từ notebook.]

Nếu chạy web trên Kaggle, gắn thêm `UI_PASSWORD`, nạp profile demo rồi chạy `python -u kaggle/ui_dashboard.py`.

## Chạy bộ chấm

Nạp cấu hình đánh giá ở trên rồi chạy từ gốc repo. Dùng cùng model và tham số cho hai lần chạy. Thay `test_set/public_sample` bằng thư mục kịch bản cần chấm.

```bash
python run_eval.py --scenarios test_set/public_sample --config full --out runs/submission/full.jsonl
python run_eval.py --scenarios test_set/public_sample --config baseline_no_memory --out runs/submission/baseline.jsonl
python eval/reference_eval.py --scenarios test_set/public_sample --trace runs/submission/full.jsonl --baseline runs/submission/baseline.jsonl
```

## Dataset, báo cáo và demo

| Tài liệu | Đường dẫn |
| --- | --- |
| Kiến trúc hệ thống | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Dataset và script khởi tạo | [Mô tả dataset](docs/DATASET.md) · [Hướng dẫn sinh dữ liệu](datagen/README.md) |
| Gói transcript, audio và bộ kịch bản dùng trong báo cáo | [Điền link và đường dẫn giải nén] |
| Báo cáo đánh giá | [Điền link bản cuối có bảng A.6, số đo ASR, kết quả trước/sau cải tiến và phân tích ít nhất 10 ca sai] |
| Video demo và slide | [Điền link khi có] |
