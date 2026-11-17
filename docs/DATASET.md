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

## 9. Bộ v3: holdout mới và dev bổ sung (03/11/2026, D45)

Đề xuất gốc: `docs/DE-XUAT-DATA-MOI-2026-11-03.md`. Người viết template, kịch bản và lời viết lại (naturalize): Claude (Claude Code), viết tay trong phiên, không gọi API.

### 9.1. Quy mô

| Phần | Kịch bản | Cuộc gọi | Lượt khách | Nội dung |
|---|---|---|---|---|
| **Holdout v3** | 77 | 139 | 413 | 21 template: 19 ca khó của đề (mỗi ca một "template thứ hai", khác tình huống với out_nat/BTC-like) + 2 ca đa phiên thường. 2–4 kịch bản mỗi template |
| **Dev v3** | 81 | 123 | 315 | 15 template: ca bẫy guardrail, đọc số tiền/SĐT trên hotline, slot còn thiếu, mẹ & bé, đa kênh Zalo ↔ hotline, khách hỏi nhiều không mua. 3–6 kịch bản mỗi template |
| **synth_slots đợt b3** | 113 câu | — | — | 12 slot, ~40% phản ví dụ, tăng các kiểu còn ít: teencode, viết tắt, số bằng chữ, tự sửa (`tu_sua`), hai slot một câu. Tổng ba đợt: 266 câu |

Kênh: hotline 239, Fanpage 12, Zalo 11 cuộc. Dạng đầu vào: văn bản 234, transcript ASR 25, teencode 3.

Holdout v3 khác bộ cũ ở chỗ nào (ví dụ): đơn tạo **trước 01/10** nên vẫn áp chính sách đổi trả 14 ngày (CL-01); hẹn gọi lại bằng thời gian **tương đối** ("thứ hai tuần sau" rơi vào 26/10); CCCD/STK **đọc cách quãng và đọc bằng chữ**; khách hỏi size 42 rồi **đổi sang 43 giữa cuộc** (KM loại trừ size); chung SĐT nhưng **đảo thứ tự** (cô Loan chốt trước, chị Dung gọi sau); khách quay lại sau 7 tháng qua **Zalo** (C033); ba kênh lệch giá theo thứ tự **Zalo → Fanpage → hotline**; đơn 4 món, 8 lượt khách, vượt ngân sách và hạn mức COD; đổi địa chỉ đơn đang chờ giao ở phiên 3; hỏi AI hay người và xóa dữ liệu ở **phiên giữa**, phiên sau không được nhớ.

Dev v3 thêm các loại ca mới (`hard_case`): `prompt_injection` (hotline và chat Fanpage giả dạng `[SYSTEM]`), `gia_danh_noi_bo` (tự xưng quản lý kho xin giá nhập), `asr_khong_ro` (lượt đầu là transcript rè), `cau_qua_dai` (một lượt khoảng 120 chữ), `doc_so_tien_sdt` (ngân sách "x triệu y", SĐT người nhận đọc từng số trong transcript ASR), `pii_cccd_stk` dạng chữ. Các ca thường kiểm slot hay bị chấm mà hệ thống chưa lưu: `restock_date`, `refund_vnd`, `baby_age`, `objection`.

### 9.2. Cách sinh và kiểm

```
datagen/templates_v3/common_v3.py      hàm dựng template (không có câu thoại)
datagen/templates_v3/dev_v3.py         template DEV (đọc được)
datagen/templates_v3/build_v3.py       template HOLDOUT (không đọc trước ngày đóng băng cấu hình) → 1_holdout.json, 2_dev.json
datagen/out_v3_claude_rewrites.py      lời viết lại của Claude (có cả phần holdout)
datagen/out_v3/raw|final/{dev,holdout} kịch bản; final là bộ dùng để chạy và đo
datagen/out_v3/manifest.json           seed, template, split, coverage, frozen.sha256 (158 file final)
```

Lệnh tái tạo ở đầu `datagen/templates_v3/build_v3.py`. Bộ sinh dùng `generate_btc_like_benchmark.py` (thêm `--prefix V3` và `--crm-first`: template cần khách CRM có định danh kênh được sinh trước; mặc định không đổi nên các bộ cũ sinh lại vẫn như cũ). Bản ASR do template tự viết (đọc từng chữ số) không còn bị ghi đè.

- **Con số:** mọi giá, KM, tồn kho, ngày giao, mã đơn lấy từ `eval/mock_tools.py` qua resolver.
- **Viết lại lời khách:** với mỗi cuộc gọi hotline, Claude viết 3–4 cách nói (từ đệm, trật tự ý, giọng Bắc/Trung/Nam); mỗi kịch bản nhận một cách theo số thứ tự. Giá trị cụ thể không chép tay mà điền lại từ môi trường resolver của chính kịch bản đó, nên không lệch số. `naturalize.anchors_kept` kiểm lại: 583/583 lượt hotline được viết lại, **0 lượt bị trả về câu gốc**. 145 lượt chat/ASR giữ nguyên như quy ước.
- **Kiểm:** `datagen/validate.py` trên cả raw và final: **158 kịch bản, 0 lỗi, 0 cảnh báo** (`validate_raw.json`, `validate_final.json`); trace hoàn hảo PASS, trace rỗng FAIL ở mọi kịch bản có success_if.
- **Đóng băng:** `generate_btc_like_benchmark.py --out datagen/out_v3 --freeze final` (sha256 từng file trong manifest).
- **Rò rỉ dev ↔ holdout:** bộ sinh chặn trùng SĐT và trùng nguyên câu giữa hai split (0). So 8-gram (câu khách final): holdout v3 trùng `public_sample` 0/447 câu, `out_nat/test` 11/447, `out_nat/dev` 17/447, holdout v2_1 2/447; dev v3 trùng holdout v3 7/369. Các 8-gram trùng là **địa chỉ** của khách CRM dùng chung giữa các bộ (ví dụ "Ba Cu, TP Vũng Tàu, Bà Rịa - Vũng Tàu") và một cụm "xóa hết dữ liệu của chị", không phải trùng tình huống. Holdout v2_1 chỉ được so bằng số đếm, không mở câu.

### 9.3. Chạy thử trên dev v3 (03/11, chỉ kiểm pipeline)

Router `rules`, generator `offline`, extractor `rules`, transport `direct`, 1 lần. **Không chạy holdout v3.**

| Chỉ số | Baseline | Full |
|---|---|---|
| TSR | 38,3 | 56,8 (ca khó 53,8) |
| RQR | 41,9 | 0,0 |
| CCR | 1,2 | 53,1 |
| HR giá & KM | 26,3 | 23,5 |
| Vi phạm guardrail | 0 | 0 |

Dev v3 còn tạo tín hiệu (các bộ dev cũ đã 92–100% TSR với cùng cấu hình). Ca trượt toàn bộ ở cấu hình này: `asr-re-khong-ro` 6/6 (không xin khách nói lại), `cccd-doc-bang-chu` 6/6 (không gọi `order.update` trả hàng khi lời khách là transcript), `doc-so-hotline` 6/6 (không chốt đơn từ transcript có số đọc bằng chữ), `me-be-combo` 6/6 (không báo đúng giá combo), `hoi-tien-hoan` 5/6. Các ca bẫy injection, giả danh, tin nhắn dài: 0 ca trượt. Số này chỉ là kiểm luồng offline, không phải số báo cáo.

### 9.4. Chưa làm được trong đợt này

- **Audio giọng 3 miền (D45 mục 3):** container không có GPU và không vào được HuggingFace/edge-tts. Phần văn bản đã có (dev `doc-so-hotline`, holdout `chat-roi-asr`, `pii-doc-cach-quang`); cần chạy TTS vùng miền (viXTTS / F5-TTS-Vietnamese) trên Kaggle GPU.
- **Hội thoại từ customer simulator + ≥ 20 mẫu chấm tay (D45 mục 7):** cần LLM chạy được; container không có khóa API.
- **Tool lỗi giữa chừng:** định dạng kịch bản và `mock_tools` chưa có cách giả lập tool lỗi; cần thêm cơ chế vào harness trước.

### 9.5. Ghi chú liêm chính dữ liệu (03/11)

Holdout v3 do chính trợ lý viết trong phiên 03/11, nên phiên đó đã thấy toàn bộ câu thoại holdout v3. Phiên đó **không sửa code hệ thống** và chỉ chạy hệ thống trên phần dev. Các phiên sửa hệ thống sau này không được đọc `datagen/templates_v3/build_v3.py`, `datagen/templates_v3/1_holdout.json`, `datagen/out_v3_claude_rewrites.py`, `datagen/out_v3/*/holdout` trước ngày đóng băng cấu hình; `improve/collect.py` đã chặn mọi đường dẫn chứa `holdout`. Khi báo số holdout v3 cần nêu rõ người viết là cùng một trợ lý với người sửa hệ thống (khác phiên).

## 10. Tổ chức dataset tập trung và holdout mới H13 (13/11/2026)

Bàn giao: `docs/PLAN/BAN-GIAO-TO-CHUC-DATASET-VA-TEMPLATE-MOI-2026-11-13.md`. Đầu mối mới là **`datagen/datasets/`**
(README ở đó). Không di chuyển, xóa hay sửa file dữ liệu gốc nào. Đặt ở `datagen/datasets/` thay vì `data/datasets/`
vì `data/` bị `.gitignore` và bị loại khỏi gói Kaggle.

### 10.1. Kiểm kê (đếm bằng `scripts/dataset_registry.py index`, job Kaggle `midzid/sudocode-ds-h1113`)

| Bộ (dataset@version/phần) | File | Vai trò | Ghi chú |
|---|---:|---|---|
| btc_public_sample | 7 | btc_sample | báo riêng |
| gen@out-v1 dev/test | 45 / 22 | source_text | câu mẫu của gen@nat-v1 |
| gen@nat-v1 dev / test | 45 / 22 | dev / observed_eval | test đã chạy 25 lần |
| btcl@v1 dev/holdout (+raw) | 28 / 40 | superseded | thiếu bản vá |
| **btcl@v1_1** dev / holdout (+raw) | 28 / 40 | **dev chuẩn** / lineage_exposed | holdout chưa mở chữ nhưng đã đo qua v2_1 |
| btcl@v2 dev/holdout (+raw) | 28 / 40 | superseded | thiếu bản vá |
| btcl@v2_1 dev / holdout (+raw) | 28 / 40 | robustness_variant / observed_eval | holdout đo D44 |
| btcl_d7@v1 dev (+raw) | 30 | dev | |
| v3@v1 dev / holdout (+raw) | 81 / 77 | dev / **observed_eval** | holdout đã đo và đọc lỗi 06–12/11 |
| redteam@1c | 14 | dev | guardrail |
| jev1108@new / @identity | 12 / 1 | dev | |
| function_probe@1107 | 94 kịch bản + 251 mục | component_check | không có đáp án TSR |
| synth_slots b1/b2/b3 | 101 / 52 / 113 câu | component_check | 266 câu, khớp manifest cũ |
| extract_eval customer/agent/facts_used/real_ref | 60 / 120 / 16 / 200 | component_check | real_ref: CC BY-NC 4.0 |
| BTC asr / rag | `asr/ground_truth.json`, `rag/qa_labeled.json` (60 câu) | component_check | chấm bằng reference_eval |
| dataset/transcripts, audio | 134 / 120 mp3 (đếm bằng `ls`) | derived_artifact | không có trong gói Kaggle |
| **h13@r1 holdout** | 84 | **holdout_new (guarded)** | mục 10.3 |

**Tổng:** 1.350 file kịch bản (kể cả raw; 1.266 trước khi thêm H13 final), 806 file ở các phần chạy; **441 kịch bản độc lập** (434 của nhóm + 7 BTC),
tính theo `lineage_group` (raw/final, bản vá, viết lại lời chỉ tính một): gen 67, BTC-like 68, D7 30, v3 158,
red-team 14, JEV1108 13, H13 84. Trước H13 là 350 kịch bản độc lập của nhóm.

Trùng văn bản lời khách (chuẩn hóa) giữa các phần cũ, theo `audit.json → inventory_same_text_between_parts`:
btcl v1↔v1_1 và v2↔v2_1 trùng toàn bộ (68 + 68, bản vá chỉ đổi đáp án/khách CRM, đúng lineage); gen out↔nat 3 kịch bản
(lượt chat/ASR giữ nguyên khi naturalize); **1 kịch bản gen@out-v1/test trùng lời khách với một mẫu BTC** — cần xem lại
nếu báo số trên gen test.

### 10.2. Suite (danh sách đã giải: `datagen/datasets/suites/resolved/`)

| Suite | n | Thành phần |
|---|---:|---|
| dev | 92 | gen@nat-v1 26 (1/template), btcl@v1_1 14, d7 10, v3 dev 15 (1/template), red-team 14, JEV1108 13 |
| regression | 44 | **tập con của dev**: red-team 14, btcl 14 (1/loại ca khó), d7 5, v3 8 (6 ca khó + 2 thường), gen 2 thường, identity 1 |
| observed_v3 | 77 | V3 holdout cũ |
| observed_other | 62 | gen@nat-v1/test 22 + btcl@v2_1/holdout 40 |
| btc_sample | 7 | mẫu BTC |
| holdout_h13 | 84 | guarded: `materialize` từ chối nếu thiếu `--allow-guarded` (đã kiểm trên Kaggle) |

Runner chưa đọc suite trực tiếp: `materialize` chép file (kiểm sha256, chặn trùng `scenario_id`) vào thư mục staging rồi
chạy `run_eval.py --scenarios <dir>`. Lệnh này đã chạy trên Kaggle với suite regression (rules/offline, chỉ kiểm đường ống,
không phải số báo cáo): 44 kịch bản, 184 lượt, 0 lỗi, reference_eval xuất bảng bình thường.

### 10.3. Holdout mới H13

Người viết: Claude (claude-opus-5-5), viết tay trong phiên 13/11, không gọi API; **cùng trợ lý từng sửa hệ thống ở các
phiên khác**, phải nêu khi báo số. Template: `datagen/datasets/releases/h1113/templates/build_h1113.py` (không commit).
Seed 20261113, tiền tố `H13`.

**Bộ chạy: `datagen/datasets/releases/h1113/final/holdout/H13-001…084.json`** (đã naturalize, đóng băng). `raw/holdout`
là bản trước naturalize, cùng 84 kịch bản và đáp án, không cộng thêm.

**Naturalize (người dùng duyệt 13/11):**
- Claude viết lại tay từng cuộc gọi hotline (146 cuộc). Cách viết: từ đệm, ngập ngừng, đảo ý, giọng Bắc/Nam theo địa chỉ, nói vòng.
- Nguồn lời viết lại: `releases/h1113/naturalize/h13_claude_rewrites.py` (không commit). Áp vào bằng
  `naturalize.py --backend claude --offline --import-claude`.
- **314/338 lượt được viết lại, 0 lượt bị trả về câu gốc** vì mất mỏ neo. 24 lượt chat Fanpage/ASR giữ nguyên như quy ước.
- Ca mơ hồ có chủ ý (F10n, F11n, F17n) vẫn giữ mơ hồ. Đáp án không đổi.

**21 họ × 4 biến thể = 84 kịch bản** (trong khoảng 20–25 họ / 60–100 ca của bàn giao). Họ thứ 21 vì nhóm "ranh giới
hỏi/yêu cầu" có ba kiểu ranh giới khác nhau (điều kiện phí, số lượng giả định, chỉ hỏi giờ làm việc), đây là trục B2 yếu
nhất ở báo cáo v6. Các họ có cặp dương/âm dùng hai template cùng `family`, không bao giờ tách split.

| Nhóm | Họ | Diễn biến mới so với bộ cũ |
|---|---|---|
| Nhiều ý cùng lượt | F01, F02 | chốt + địa chỉ + hỏi bảo hành trong một lượt; tra đơn + hỏi giá món khác + báo vắng nhà (không tạo đơn món chỉ hỏi giá) |
| Hỏi / yêu cầu | F03 ±, F04 ±, F05 ± | đổi size "nếu miễn phí" (lần 1 miễn phí → làm; lần 2 phí 30.000đ/chiều → không làm); "lấy 2 cái" và "nếu lấy 2 cái thì bao nhiêu"; hỏi giờ tổng đài rồi hẹn / không hẹn |
| Sửa / rút | F06, F07 ± | đặt hai món rồi rút một (tổng đơn đúng món giữ); đổi màu trước khi đủ thông tin (màu mới còn → đặt; hết và khách không nhận màu cũ → không đặt) |
| Giỏ, số lượng | F08, F09 | thêm phụ kiện sau đơn cũ thành đơn mới, dùng lại địa chỉ; giỏ hai món thay size một món |
| Nhiều sản phẩm / đơn | F10 ±, F11 ± | hai đơn giày: gọi tên rõ → đổi đúng đơn, mơ hồ → hỏi lại; "cái rẻ hơn" trong hai mẫu đã báo và "cái em tư vấn" |
| Điều kiện | F12 ±, F13 ± | giá trần bằng giá cũ, KM còn/hết tại ngày gọi lại; người nhà chỉ đồng ý nếu có khóa trẻ em (catalog) |
| Nhớ qua phiên | F14, F15 ± | đổi địa chỉ hồ sơ ở phiên không có đơn, phiên sau dùng địa chỉ mới; mua lại và chỉ hỏi giá giùm người khác |
| Đa kênh / danh tính | F16, F17 ± | đơn qua tổng đài → hỏi ngày giao qua Fanpage (khách CRM); khách mới chat Fanpage có/không để lại SĐT rồi gọi hotline |
| Chính sách và nguồn | F18 ±, F19 | phụ thu hàng cồng kềnh ngoài nội thành dù miễn phí ship (nối hai mệnh đề VC-02); KM 11-11 chưa bắt đầu (KM-02) rồi đang chạy |
| Khả năng trả lời | F20, F21 ± | cùng lượt một thuộc tính có nguồn (spec) và một không có nguồn; tên mẫu qua ASR khớp một mẫu / nhiều mẫu |

Mô tả "khác bộ cũ ở diễn biến nào" của từng họ nằm ở `manifest.json → templates[].diff_vs_old`.

**Coverage:** 60 kịch bản dương, 24 âm (29%); 42/84 (50%) có ít nhất một bước then chốt bị cấm ghi (`must_not_call_tools`),
4 ca bắt buộc nói "không có thông tin". Phiên: 54 ca 2 phiên, 10 ca 3 phiên, 20 ca 1 phiên (76% đa phiên). Kênh: 150 cuộc
hotline, 8 cuộc Fanpage; 4 cuộc transcript ASR. 4 khách CRM (F16), còn lại là khách tổng hợp mới.

**Kiểm lại sau naturalize (job CPU `midzid/sudocode-ds-h1113-nat`, `scripts/h1113_naturalize_job.sh`, mọi bước PASS):**
- `validate.py --strict` trên `final/holdout`: 0 lỗi, 0 cảnh báo.
- Đóng băng `--freeze final`; raw được kiểm còn nguyên byte và lưu ở `manifest.json → frozen_raw`.
- Canary: hoàn hảo PASS 84/84, rỗng FAIL 84/84, sai có chủ ý FAIL 84/84.
- Trùng lớp 1: 0 file trùng hash, 0 kịch bản trùng văn bản; 2/338 lượt trùng nguyên câu với bộ cũ (đều là "Ừ cảm ơn em nha.").
- Lớp 2: 0 SĐT khách tổng hợp trùng bộ cũ.
- 8-gram: tối đa 18/338 lượt (với V3 holdout), không đổi so với bản raw.
- Suite `holdout_h13` vẫn bị chặn khi thiếu `--allow-guarded`.

**Kiểm bản raw (một job Kaggle CPU, `scripts/h1113_dataset_job.sh`):**
- Sinh 84/84; `validate.py --strict`: 0 lỗi, 0 cảnh báo (giá/KM/tồn/ngày giao/hoàn tiền đối chiếu `mock_tools`; trace hoàn hảo PASS, trace rỗng FAIL).
- Đóng băng `--freeze raw` (sha256 từng file trong `manifest.json → frozen`).
- Canary qua `reference_eval`: hoàn hảo PASS 84/84, rỗng FAIL 84/84, sai có chủ ý (giá +1.000đ, sai action, sai giờ hẹn, gọi tool cấm, bỏ tra đơn) FAIL 84/84.
- Trùng lớp 1: 0 file trùng hash, 0 kịch bản trùng văn bản chuẩn hóa; 1/338 lượt khách trùng nguyên câu với bộ cũ ("Để chị hỏi ý chồng rồi gọi lại em nha.").
- Lớp 2: 0 scenario_id trùng; 0 SĐT khách tổng hợp trùng bộ cũ; 4 khách CRM dùng lại (không tránh được, CRM của BTC chỉ có 50 khách).
- Lớp 3: 8-gram chung tối đa 18/338 lượt (với V3 holdout), chủ yếu là địa chỉ sinh từ cùng danh sách đường phố. Khung diễn biến thô của F09 trùng T16 và của F21 âm trùng V3 `asr-re-khong-ro`; đã xem lại: F09 là thay biến thể trong giỏ (T16 là vượt hạn mức COD), F21 là tên mẫu mơ hồ (V3 là đường truyền rè).

**Hạn chế của đáp án** (theo schema BTC, không đổi evaluator):
- `must_say_any` khớp cụm từ, nên câu trả lời đúng nhưng diễn đạt khác có thể bị chấm trượt (đã thêm nhiều cụm thay thế nhưng không phủ hết).
- `reference_eval` chấp nhận mọi `order_id` do `order.create` tạo ở phiên trước; ở F10 chỉ `new_variant_sku` phân biệt đơn đúng.
- Mỗi trường `ground_truth_facts` chỉ một giá trị: các cuộc nhiều SKU (F02, F06, F09, F11) chỉ kiểm một giá, tổng đơn kiểm bằng `total_match_vnd`.
- F04 dương yêu cầu một dòng `qty=2`; tách thành hai dòng qty 1 sẽ trượt.
- F14 không so chuỗi địa chỉ trong `args_match` (định dạng có thể khác); dùng `must_carry_over`, `trace_must_not_match` địa chỉ cũ và `memory_expectation` (chỉ sàng lọc).
- F17 âm giả định agent không được nối phiên chat Fanpage (fb_id không có trong CRM, khách không để SĐT) với hotline, dù harness nạp bộ nhớ theo kịch bản.
- F18 hiểu VC-02 là phụ thu cồng kềnh 30.000đ áp dụng ngoài nội thành kể cả khi được miễn phí ship theo giá trị đơn.

**Exposure:** generated + reviewed-for-data-quality + naturalize (Claude, 13/11). Chưa chạy B1/B2/B3 hay agent nào trên H13.
Phiên/model sửa agent không đọc `releases/h1113/templates|naturalize|raw|final`, phần H13 trong `index.jsonl` hay `runs/kaggle/ds-h1113*/`.
Khi người dùng duyệt đo: `materialize --suite holdout_h13 --allow-guarded`, ghi exposure `evaluated` vào `registry.json`.
