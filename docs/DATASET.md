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

## 8. Dữ liệu cho lexicon và các bộ đo mới (01/11/2026, PLAN-2026-11-01 A-D)

### 8.1. Dữ liệu tham khảo thật: CSConDa (hcmut-ura)

- **Nguồn:** Long S. T. Nguyen và cộng sự, *A Benchmark Dataset and Evaluation Framework for Vietnamese Large Language Models in Customer Support*, nhóm URA, ĐH Bách khoa TP.HCM, arXiv [2507.22542](https://arxiv.org/abs/2507.22542), 07/2025. Bản trên Hugging Face: [`ura-hcmut/Vietnamese-Customer-Support-QA`](https://huggingface.co/datasets/ura-hcmut/Vietnamese-Customer-Support-QA).
- **Giấy phép:** CC BY-NC 4.0. Chỉ được dùng phi thương mại và phải ghi nguồn. Nếu sản phẩm dùng thương mại thì phải bỏ các cue có `source` là `ref:hcmut-ura` trong `harness/lexicon/slots.json`, hoặc xin phép nhóm tác giả.
- **Không đưa bộ dữ liệu vào repo.** `scripts/mine_lexicon.py` đọc thẳng từ thư mục ngoài (`--ref-dir` hoặc `LEXICON_REF_DIR`). Repo chỉ chứa:
  - **`tests/extract_eval/real_ref.jsonl`:** 200 câu hỏi của khách. Câu được lấy mẫu có ưu tiên theo nhóm cue (thanh toán, hẹn liên hệ lại, tự xưng tên, câu nhắc "địa chỉ"/"ship" nhưng không phải địa chỉ giao hàng, trì hoãn, có số tiền), cộng 40 câu ngẫu nhiên, seed 20261101.
  - **Che PII trước khi ghi:** SĐT, số tài khoản và CCCD (`mask_pii`), email, URL, tên sau "mình là…", cùng hai chuỗi che tay (một địa chỉ công ty, một tên). Nhãn `type` của bộ gốc không dùng.
  - **Nhãn:** Claude gán tay ngày 01/11 theo quy ước của `tests/extract_eval/customer.jsonl`. 24 câu có slot, 25 câu có `skip` vì mơ hồ. Bộ này chủ yếu đo **precision**: đây là chat CSKH phần mềm B2B, không phải telesale, nên có nhiều phản ví dụ thật, ví dụ "ck" nghĩa là *chồng*, "COD" khi nói về cài đặt phần mềm, "cân nhắc" nói về khách hàng của họ.
- **Đã dùng vào:** bộ đo câu thật `real_ref.jsonl`, nguồn của một số cue và viết tắt trong lexicon (cột `source`), và đếm thô ứng viên cue.

### 8.2. Dữ liệu tự sinh

| Bộ | Người viết | Ở đâu | Quy mô (01/11) | Dùng cho |
|---|---|---|---|---|
| Câu đơn theo slot | Claude (claude-opus-5-5, viết tay trong phiên Claude Code; không dùng Qwen) | `datagen/synth_slots/<đợt>.tsv` (commit), đặc tả `datagen/slot_specs.json`, manifest `datagen/synth_slots/manifest.json` | Đợt b1: 101 câu, 12 slot, khoảng 40% là phản ví dụ khó, 3 miền, nhiều văn phong. Mục tiêu khoảng 6.000 câu, viết dần qua nhiều phiên | Rút cue (phần `mine`), đo (phần `eval`), đo precision của CERT |
| Scenario dev D-7 | Claude (template và lời viết lại `naturalize --backend claude`) | `datagen/templates_btc_like/build_templates_d7.py`, lời viết lại trong `datagen/out_btc_like_d7_claude_rewrites.py`, đầu ra `datagen/out_btc_like_d7/` (không commit, sinh lại được) | 30 scenario dev (`BTCD7-001…030`), 60 cuộc gọi, 147 lượt khách, 5 họ lỗi × 2 diễn biến | Kiểm toàn hệ thống (planner, CCR/RQR/TSR) |
| BTC-like v1_1 | Script vá | `datagen/patch_crosschannel_v1_1.py` → `datagen/out_btc_like_final_v1_1/` | 5 scenario được vá (dev BTCL-016/017, holdout BTCL-018/019/020) | Sửa ca không thể qua của họ `delivery_address` (B3) |
| BTC-like v2 | Lời khách viết lại tay (01/11, không qua naturalize), từ v1 | `datagen/out_btc_like_final_v2/` (không commit; `manifest.json` mục `hand_edit`) | Cùng 28 dev + 40 holdout, cùng kịch bản và đáp án với v1; khác lời khách ở `final/`. Bỏ `ground_truth_facts.price_vnd` ở call_1 của BTCL-021…025 (cuộc báo giá hai sản phẩm). **Thiếu bản vá B3** → không dùng trực tiếp | Không dùng; thay bằng v2_1 |
| BTC-like v2_1 | Script vá (D29, 02/11) | `datagen/patch_crosschannel_v1_1.py --src datagen/out_btc_like_final_v2 --dst datagen/out_btc_like_final_v2_1 --date 2026-11-02` | Như v2, vá đúng 5 scenario như v1_1 và gán cùng khách CRM (dev BTCL-016 → C013, BTCL-017 → C019) | **Chỉ dev:** đo độ bền với cách nói khác (biến thể trong job A, D28). HR **không so trực tiếp** với v1_1 vì đáp án BTCL-021…025 khác. Holdout v2_1 là cùng 40 scenario với holdout v1_1 (chỉ khác lời), chỉ được mở **một** trong hai (D30) |

**Ràng buộc chất lượng:**
- **Chia 70/30 theo nhóm `prompt_id`** trong từng slot (`datagen/synth_slot_sentences.py`), nên câu rút cue và câu đo không xuất phát từ cùng một lần viết.
- **Chống trùng:** `scripts/check_overlap.py` so 8-gram sau `fold()` với lời khách của holdout BTC-like (v1, v1_1), `datagen/out_nat/test` và `test_set/public_sample`. Script chỉ in số đếm. Đợt b1 có 0 câu trùng.
- **Kiểm nhãn hai lớp:** `scripts/label_crosscheck.py` so nhãn Claude với luật hiện tại (hoặc Jev/Qwen khi đóng vai bộ kiểm). Câu lệch nhãn vào `data/lexicon_corpus/review_queue.jsonl`. Mẫu ngẫu nhiên 5% mỗi đợt nằm ở `human_sample_<đợt>.jsonl` để người duyệt đọc.
- **Không train hay fine-tune:** dữ liệu chỉ dùng để rút luật và để đo.
- **Hạn chế:** câu tự sinh đều và sạch hơn lời khách thật. Vì vậy mọi kết quả lexicon đều báo thêm số trên `real_ref.jsonl` và `tests/extract_eval`.

### 8.3. Ghi chú liêm chính dữ liệu (01/11)

Khi đọc mã nguồn `datagen/templates_btc_like/build_templates.py` để sửa template B3, trợ lý đã vô tình hiển thị các dòng template `holdout` của 5 họ (`delivery_address`, `two_items`, `change_mind`, `asr_context`, `chat_short`). Không có trace hay kết quả holdout nào bị mở, và không có thay đổi nào của agent dựa trên các dòng này. Ghi lại để minh bạch khi báo cáo số holdout.
