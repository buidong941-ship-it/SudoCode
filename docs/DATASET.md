# Dataset của nhóm

Bộ dữ liệu hội thoại telesale tiếng Việt, sinh hoàn toàn bằng máy (kịch bản từ template + LLM + TTS), dựng trên catalog, khuyến mãi, CRM seed và chính sách dùng chung của BTC. Không có dữ liệu khách hàng thật.

## 1. So với chỉ tiêu M1 (đề mục C.1)

| Hạng mục | Chỉ tiêu M1 | Hiện có | Đạt |
|---|---|---|---|
| Cuộc hội thoại dạng transcript hai phía | ≥ 120 | 134 cuộc, 870 lượt (435 lượt khách + 435 lượt nhân viên) | ✅ |
| Có audio | ≥ 40 cuộc / ≥ 1 giờ | 120 cuộc, 2,07 giờ (124,5 phút; mỗi cuộc 26–205 giây) | ✅ |
| Khách đa phiên (≥ 2 cuộc cùng một khách) | ≥ 30 khách | 52 khách (7 khách có ≥ 3 phiên) | ✅ |
| Khách có cả cuộc gọi và chat | ≥ 10 khách | 10 khách | ✅ (sát ngưỡng) |
| Ngành hàng | 1 ngành | 3 ngành: gia dụng 66 cuộc, thời trang 44, mẹ & bé 14 | ✅ |
| Giọng vùng miền | 2 miền | **Chưa đạt bằng audio**: edge-tts chỉ có 2 giọng chuẩn, xem mục 5 | ❌ |
| Audio có nhiễu (M2: ≥ 20%) | — | 34/120 cuộc (28%) | — |
| Catalog + chính sách | > 30 SKU | 40 sản phẩm, 96 biến thể, 14 tài liệu chính sách (của BTC) | ✅ |

Persona M1 đều có: khách do dự hỏi người nhà (32 cuộc), khách so giá (24), khách đã mua gọi lại đổi size (19). Có thêm persona M2: hỏi nhiều không mua (10), gọi lần 3 hết kiên nhẫn (12).

## 2. Cấu trúc

```
datagen/templates/*.json      27 template kịch bản (ràng buộc, không chứa con số cụ thể)
datagen/out/{dev,test}/       67 kịch bản sinh từ template (45 dev / 22 test), lượt khách là câu mẫu
datagen/out_nat/{dev,test}/   cùng 67 kịch bản, lượt khách đã viết lại cho tự nhiên  ← bộ dùng để chạy và đo
dataset/transcripts/*.json    134 cuộc gọi, hai phía (121 cuộc của nhóm + 13 cuộc từ 7 kịch bản mẫu BTC)
dataset/index.json            danh sách cuộc gọi + thống kê
dataset/audio/<id>.mp3        audio cuộc hotline, 16 kHz mono
dataset/audio/<id>.segments.json   mốc thời gian từng lượt và người nói
dataset/asr/ground_truth.json ground truth ASR, cùng định dạng asr/ground_truth.json của BTC
dataset/asr/hypotheses*.json  đầu ra ASR của nhóm (2 tập × 24 file);  report*.json: bảng WER/CER/Entity
```

Mỗi file transcript có: `scenario_id`, `call`, `persona`, `hard_case`, `channel`, `input_mode`, `call_date`, `customer` (xưng hô, giới, miền), `product_sku`, `category`, `tools_called`, `turns` (`speaker`: `C` khách / `A` nhân viên), và `source` (model, lần chạy).

## 3. Cách sinh

1. **Kịch bản** (`datagen/resolver.py`): template khai báo ràng buộc; resolver tìm khách, sản phẩm, ngày gọi thỏa ràng buộc. Mọi con số (giá sau KM, tồn kho, ngày giao) lấy từ `eval/mock_tools.py` của BTC, không lấy từ LLM. `datagen/validate.py` kiểm tra lại từng kịch bản (0 lỗi trên 67 kịch bản).
2. **Lượt khách tự nhiên** (`datagen/naturalize.py`): DeepSeek viết lại câu mẫu theo persona. Một lượt viết lại chỉ được nhận khi giữ đủ mọi con số, sản phẩm, số tiền và tên riêng của câu gốc; nếu thiếu thì giữ câu gốc. Kết quả: 351/396 lượt được viết lại, 45 lượt giữ nguyên có chủ ý (bản ASR lỗi, teencode, kênh chat), 0 lượt bị loại vì mất thông tin. Đáp án của kịch bản không đổi.
3. **Lời nhân viên**: chạy chính hệ thống của nhóm (`run_eval.py --config full`, router Jev, generator `deepseek-v4-flash`) trên các kịch bản trên; `agent_text` trong trace là lời nhân viên. `datagen/export_transcripts.py` ghép hai phía.
4. **Audio** (`datagen/make_audio.py`): edge-tts đọc từng lượt của các cuộc hotline. Trước khi đọc, lời thoại được đổi sang dạng nói ("5.200.000đ" → "năm triệu hai trăm nghìn") để ground truth khớp đúng với audio. Khách và nhân viên dùng hai giọng khác giới; giọng khách đổi tốc độ và cao độ theo từng kịch bản.
5. **Nhiễu**: khoảng 25% số cuộc được lọc băng thông điện thoại (300–3400 Hz, hạ xuống 8 kHz) và trộn nhiễu nền với SNR 8–15 dB. Tập được chọn theo băm của id nên chạy lại ra cùng kết quả.

Lệnh tái tạo: xem `docs/HARNESS.md`, mục "Dataset của nhóm".

## 4. Phân bố

| Chiều | Phân bố (số cuộc) |
|---|---|
| Kênh | hotline 120, chat Fanpage 8, Zalo OA 6 |
| Miền của khách | Nam 48, Trung 46, Bắc 40 |
| Ngành hàng | máy lọc không khí 44, giày 40, mẹ & bé 14, máy lọc nước 12, nồi chiên 5, quạt 5, áo khoác 4, không gắn sản phẩm 10 |
| Dạng đầu vào | văn bản sạch 124, teencode 6, transcript ASR lỗi 4 |
| Tập | dev 83, test 38, mẫu BTC 13 |
| Ca khó | 75 cuộc thuộc 19 loại ca khó (KM hết hạn, hết hàng lúc chốt, chung SĐT, PII, ép giá, ngoài tài liệu…) |

Độ dài trung bình: 6,5 lượt mỗi cuộc, khoảng 30 từ mỗi lượt.

## 5. Chất lượng ASR trên audio của nhóm

ASR chạy local: faster-whisper `small` (int8, CPU 4 nhân), tên sản phẩm trong catalog làm `initial_prompt`. Chấm bằng `wer_cer` của `eval/reference_eval.py`; transcript được đưa về dạng chữ trước khi tính WER/CER (`asr/itn.py: to_spoken`).

Đo trên 48 file (46,8 phút audio), chia hai tập 24 file, mỗi tập 17 file sạch và 7 file nhiễu:

| Tập | WER | CER | WER sạch | WER nhiễu | Entity Accuracy | Số tiền |
|---|---|---|---|---|---|---|
| A: dùng để sửa luật hậu xử lý | 15,7% | 9,7% | 12,4% | 24,6% | 92,3% (12/13) | 91,7% (11/12) |
| **B: chưa dùng khi sửa luật** | **13,5%** | **8,8%** | **11,1%** | **19,6%** | **42,9% (6/14)** | **46,2% (6/13)** |

**Con số nên báo cáo là tập B.** Entity Accuracy của tập A cao vì luật được sửa trên chính 24 file đó (trước khi sửa: 15,4%).

Nhận xét:

- **WER/CER:** lỗi chủ yếu ở tên riêng và từ ngoại lai ("AirPure" → "EOCT", "RO" → "do", "9 lõi" → "chính lỗi") và từ đệm cuối câu ("ạ" → "à", "nè"). Nhiễu điện thoại làm WER tăng khoảng 8–12 điểm.
- **Số tiền là điểm yếu chính.** Whisper viết số theo nhiều kiểu: "7,690.000", "7,690,000", "1 triệu 590.000". Hai kiểu đầu đã được chuẩn hóa (`norm_separators`); kiểu "1 triệu 590.000" chưa xử lý, nên giá bị mất phần triệu (1.590.000 → 590.000). Đây là nguyên nhân của phần lớn lỗi ở tập B.
- **Phân loại số tiền theo ngữ cảnh** (giá shop, giá bên khác, ngân sách) hỏng khi từ khóa ngữ cảnh bị nhận dạng sai ("bên kia" → "bên chiên").
- **Số điện thoại:** cả bộ chỉ có 1 cuộc khách đọc SĐT thành tiếng và cuộc đó không nằm trong 48 file đã đo, nên **chưa có số Entity Accuracy riêng cho SĐT**. Cần thêm kịch bản khách đọc SĐT trên hotline.
- **Tốc độ:** RTF khoảng 1,0 trên CPU 4 nhân (1 phút audio mất 1 phút xử lý).

Chi tiết từng file: `dataset/asr/report.json` (tập A), `dataset/asr/report_heldout.json` (tập B), `dataset/asr/report_before_fix.json` (tập A trước khi sửa luật).

## 6. Hạn chế

- **Giọng nói:** edge-tts tiếng Việt chỉ có hai giọng (HoaiMy nữ, NamMinh nam). Không chọn được giọng vùng miền, nên chỉ tiêu "2 miền" chưa đạt về mặt âm thanh. Trường miền trong dữ liệu là miền của khách trong CRM, không phải giọng đọc. Muốn đạt cần TTS có giọng vùng miền (viXTTS, F5-TTS-Vietnamese) hoặc thu âm thật.
- **Audio là giọng tổng hợp, đọc rõ, không ngắt lời, không nói chồng.** WER đo trên bộ này thấp hơn thực tế cuộc gọi thật. Nhiễu là nhiễu tổng hợp (nhiễu hồng + lọc băng), chưa có tiếng đường phố hay tiếng người khác.
- **Lời nhân viên do chính hệ thống sinh**, nên transcript mang theo cả lỗi của hệ thống: có lượt dùng ký hiệu markdown, có lượt gọi "anh/chị" dù khách đã xưng "chị", có lượt bị cắt cụt. Các lỗi này được giữ nguyên để phân tích, không sửa tay.
- **Lượt khách viết sẵn, không phản ứng theo nhân viên.** Khách nói đúng câu đã định dù nhân viên trả lời gì, nên một số cuộc nghe không liền mạch.
- **Lượt khách còn gần với câu mẫu.** Phép kiểm "giữ đủ thông tin" khiến LLM viết lại khá thận trọng; đa dạng cách nói thấp hơn hội thoại thật.
- **Đa kênh sát ngưỡng** (10 khách) và ngành mẹ & bé ít dữ liệu (14 cuộc).
- **Chưa có audio của BTC** trong gói dữ liệu, nên chưa đo WER/CER trên 4 hội thoại mẫu D01–D04.

## 7. Thông tin cá nhân

- Không có dữ liệu người thật. Tên, SĐT, định danh Zalo/Facebook lấy từ CRM seed của BTC; địa chỉ do resolver sinh.
- CCCD và số tài khoản khách đọc trong hội thoại được che ngay khi nhận câu nói (`harness/textnorm.mask_pii`), nên không xuất hiện trong transcript và không được đọc thành audio.
- SĐT và địa chỉ được thay bằng mã (`[SĐT_1]`, `[ĐỊA_CHỈ_1]`) trước khi gửi DeepSeek/Jev và ghép lại sau (`core/pii.py`); bước viết lại lượt khách cũng dùng cơ chế này.
- `dataset/index.json` chỉ lưu băm của SĐT để gom các cuộc của cùng một khách.
