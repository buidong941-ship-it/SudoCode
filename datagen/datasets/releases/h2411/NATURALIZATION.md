# H24 — naturalize từ RAW r2

Ngày thực hiện: 24/11/2026. Người dùng yêu cầu Codex naturalize bộ RAW r2.

## Phạm vi

Lời viết lại nằm trong `AUDIT/NATURALIZE_REWRITES.jsonl`: 60 kịch bản, 124 cuộc gọi, 316 lượt khách. Codex viết trong phiên làm việc; không gọi API LLM riêng.

Đích runnable: `final/holdout/`. Mỗi kịch bản chỉ thay `calls.*.customer_turns` và sinh lại `customer_turns_asr` ở sáu cuộc gọi vốn có trường đó. Các trường còn lại, kể cả `_meta`, seed, đáp án và điều kiện chấm, được sao nguyên từ RAW r2. Bản RAW và `RAW_LOCK.json` được giữ nguyên.

Giữ diễn biến theo từng lượt, lựa chọn/phủ định/đồng ý của khách, sản phẩm, số lượng, giá, size/màu, địa chỉ, tên ngân hàng, CCCD/STK và thời gian tương đối. F01 vẫn chưa đặt ở lượt nghiêng về A; F06 giữ việc chung số với cô Loan; F07 vi=2 vẫn tham chiếu Zalo tháng 6, không đọc địa chỉ. F09 dùng lại `teen()` cho chat và `spoken()` cho hotline trong resolver đã có.

## Quy trình và bằng chứng

Job Kaggle CPU riêng tư: `midzid/sudocode-h24-naturalize-1124`. Gói đầu vào chỉ gồm dữ liệu và công cụ kiểm dữ liệu; không có agent runtime hoặc khóa LLM.

Mã đóng gói/chạy job: `build/kaggle/h24-naturalize-1124/prepare.py` và `runner.py`. `INPUT_LOCK.json` khóa từng file đầu vào.

Kiểm trên Kaggle: số ca/cuộc/lượt, số liệu và các mỏ neo tên riêng theo từng lượt, các trường ngoài lời thoại, các ràng buộc F01/F06/F07/F17, rồi `datagen/validate.py --strict`. Nhật ký trước/sau được xuất riêng, không đưa vào thư mục runnable. Chưa chạy agent trên H24.

Kaggle kernel phiên bản 2 hoàn tất, kiểm PASS: đủ 60 kịch bản / 124 cuộc gọi / 316 lượt, viết lại 316/316 lượt, sinh lại sáu cuộc ASR/teencode. Validator strict: 0 lỗi, 0 cảnh báo. Phiên bản 1 dừng ở bước tìm gói đầu vào vì Kaggle đã giải nén tar; phiên bản 2 nhận cả gói nén và cây dữ liệu đã giải nén, nội dung đầu vào không đổi.

Kết quả đã tải về `runs/kaggle/h24-naturalize-1124-r2/`; bản giao ở `final/holdout/`. Hash 60 file tải về khớp báo cáo Kaggle; 67 mục trong RAW_LOCK vẫn khớp. Báo cáo ở `NATURALIZE_REPORT.json`, `validate_final.json`; nhật ký từng lượt ở `AUDIT/NATURALIZE_LEDGER.jsonl`. `FINAL_LOCK.json` khóa bản giao và bằng chứng kiểm. Các đường dẫn tuyệt đối trong validate_final.json là đường dẫn lúc chạy trên Kaggle.

## Giới hạn còn giữ từ RAW r2

Naturalize không sửa đáp án hay các vấn đề của audit đã nêu trong lượt rà soát: bảng tổng đơn F01, khả năng phân biệt `facts.as_of` với summary/ngày phiên ở F07, và nghĩa ticket của `order.update` ở F22. `AUDIT/SUPPLEMENTAL_CHECKS.jsonl` vẫn là tiêu chí kiểm bổ sung, chưa phải script tự chấm.

60 ca đến từ 22 họ template. Người tạo RAW đã biết lỗi H13; Codex đã đọc holdout để naturalize. Cần giữ bản final cố định khi đo, ghi nhận mức độ tiếp xúc này và không dùng lỗi H24 để sửa agent rồi tiếp tục gọi kết quả là holdout độc lập.
