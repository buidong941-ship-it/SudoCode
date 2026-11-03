# Các cấu hình đã chạy và số liệu (tổng hợp 03/11/2026)

File này chỉ ghi cấu hình và số liệu, không kèm nhận định.

**Cách tổng hợp:**
- **Nguồn:** mọi `report.json` có `full.config.json` đi kèm trong `runs/kaggle/`. Không tính thư mục `smoke/`, `*.bak*`, các bản tải về trùng nội dung, và các job lỗi không có số. Có tính các thư mục `<job>.bak-1103`: đó là kết quả cũ của các notebook đã dùng lại cho D42, được chuyển sang ngày 03/11; tên hiển thị bỏ hậu tố này. Tổng cộng 136 lần chạy.
- **Gộp theo cấu hình:** trong từng bộ kịch bản, các lần chạy có cùng router, generator/model, extractor (CERT, Jev, drop policy), planner và cờ khác thì gộp làm một dòng. Dòng đó lấy số của **lần chạy có ngày file gần hôm nay nhất**. Các lần cũ hơn ghi ở cột cuối.
- **✅ đã thực hiện:** cấu hình này đã chạy ít nhất một lần trên bộ đó.
- **Chấm điểm:** bằng `eval/reference_eval.py`.

**Ký hiệu:**
- **B / F:** Baseline (`baseline_no_memory`) / Full.
- **HR:** HR giá & KM chính thức, không xét SKU.
- **GV:** số vi phạm guardrail.
- **Khác:** các cờ khác mặc định đọc được từ `settings`.
- **Nhãn:** tên dùng trong nhật ký, chỉ ghi khi số khớp.

**Lưu ý:**
- **Cùng cấu hình chưa chắc cùng code.** Các file không ghi commit. Một số dòng gộp các lần chạy trên những bản code khác nhau. Ví dụ ở v1_1 dev, dòng `cert1` gộp cả lần GPU trước D05/D10 và 3 lần C5. Ở v1 dev, dòng mới nhất gộp ① và ③. Muốn xem từng lần thì xem các thư mục ở cột cuối.
- **`LEXICON_INCLUDE` không được ghi trong `settings`.** Cột Khác chỉ ghi `LEXICON_INCLUDE=none` cho các biến thể suy được từ tên (`nolex`, `lexnone`). Các dòng khác không phân biệt được giá trị lexicon.
- **Các biến thể D42 chỉ chạy Full** (`SUITE_CONFIGS=full`), nên cột B ghi "–". Riêng `base` (job 1) chạy cả hai cấu hình.
- **Ở v2_1 dev, dòng `base` gộp 5 lần `basectl` của D42 (cùng code) với Job B ngày 02/11 (code cũ hơn).** Độ lệch giữa các lần `basectl` xem `NHAT-KY-2026-11-03.md` mục 2.8.
- **"Ngày file" là ngày giải nén kết quả,** không chính xác là ngày chạy. Nhiều lần chạy có cùng ngày 02/11.
- **Dòng `offline` dùng extractor `rules`,** nên các cờ CERT/Jev không có tác dụng ở các dòng này.
- **Cờ đặt qua env mà `settings` không ghi thì không phân biệt được.** Ví dụ các biến thể `multiclass`, `jev-rules` và `w1/w2-c1/c2` ngày 29/10 bị gộp với nhau.
- **Không so chéo giữa các bộ** v1, v1_1 và v2_1, vì đáp án khác nhau.
- **Không chọn cấu hình bằng `out_nat test`.**

## BTC-like v1_1 dev (28 kịch bản) — bộ đo chính hiện nay

`datagen/out_btc_like_final_v1_1/final/dev` · 15 lần chạy, 5 cấu hình khác nhau

| # | Trạng thái | Router | Generator | Extractor | Planner | Khác | Lần mới nhất (ngày file) | Nhãn | Số lần chạy | TSR B → F | RQR B → F | CCR F | HR giá&KM B → F (sai/tổng F) | TTFT p95 F (s) | Total p95 F (s) | GV F | Các lần cũ hơn (cùng cấu hình) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ✅ đã thực hiện | rules | offline | rules | rules | direct, LEXICON_INCLUDE=none | `btc-confidence-dev-current / lexnone` (03/11) | D40 `none` | 1 | 50,0 → 100,0 | 25,0 → 0,0 | 89,5 | 10,4 → 6,3 (5/79) | 0,1 | 0,1 | 0 |  |
| 2 | ✅ đã thực hiện | rules | offline | rules | rules | direct | `btc-confidence-dev-current / lexappr` (03/11) | D40 `approved` | 7 | 50,0 → 100,0 | 25,0 → 0,0 | 89,5 | 10,4 → 6,3 (5/79) | 0,1 | 0,1 | 0 | `regress-1102b`; `regress-cert2 / v1`; `regress-cert2 / v2`; `regress-cert2b`; `regress-cert2b / cert1`; `regress-cert2b / cert2` |
| 3 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | hybrid (qwen, CERT v1, Jev, drop=qwen) | jev | rag=auto | `btc-jev-hybrid-final-dev / planjev` (02/11) | Job A `planjev` | 1 | 50,0 → 100,0 | 17,2 → 0,0 | 86,8 | 9,5 → 6,8 (5/74) | 3,8 | 14,1 | 0 |  |
| 4 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | hybrid (qwen, CERT v2, Jev, drop=qwen) | rules | rag=auto | `btc-jev-hybrid-final-dev / cert2` (02/11) | Job A `cert2` | 1 | 50,0 → 100,0 | 14,3 → 0,0 | 89,5 | 9,2 → 5,1 (4/78) | 3,3 | 14,3 | 0 |  |
| 5 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | hybrid (qwen, CERT v1, Jev, drop=qwen) | rules | rag=auto | `btc-jev-hybrid-final-dev / cert1` (02/11) | Job A `cert1` | 5 | 50,0 → 100,0 | 10,3 → 0,0 | 94,7 | 9,5 → 5,4 (4/74) | 3,3 | 14,7 | 0 | `btc-jev-hybrid-final-dev-1102 / btc-jev-hybrid-final-dev`; `btc-jev-hybrid-final-dev / c5r1`; `btc-jev-hybrid-final-dev / c5r2`; `btc-jev-hybrid-final-dev / c5r3` |

## BTC-like v1 dev (28 kịch bản) — trước bản vá B3

`datagen/out_btc_like_final_v1/final/dev` · 8 lần chạy, 6 cấu hình khác nhau

| # | Trạng thái | Router | Generator | Extractor | Planner | Khác | Lần mới nhất (ngày file) | Nhãn | Số lần chạy | TSR B → F | RQR B → F | CCR F | HR giá&KM B → F (sai/tổng F) | TTFT p95 F (s) | Total p95 F (s) | GV F | Các lần cũ hơn (cùng cấu hình) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | hybrid (qwen, CERT v1, Jev, drop=qwen) | rules | rag=auto | `btc-jev-hybrid-final-dev-a6 / btc-jev-hybrid-final-dev / btc-jev-hybrid-final-dev-drop-qwen` (02/11) |  | 1 | 50,0 → 92,9 | 40,0 → 14,3 | 78,9 | 18,0 → 15,8 (9/57) | 2,6 | 15,6 | 0 |  |
| 2 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | hybrid (qwen, CERT v1, Jev, drop=accept) | rules | rag=auto | `btc-jev-hybrid-final-dev-a6 / btc-jev-hybrid-final-dev / btc-jev-hybrid-final-dev-drop-accept` (02/11) |  | 1 | 50,0 → 85,7 | 46,4 → 10,5 | 78,9 | 17,6 → 14,5 (9/62) | 2,6 | 15,3 | 0 |  |
| 3 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | hybrid (qwen, CERT v1, Jev) | rules | rag=auto | `btc-jev-hybrid-final-dev-a6 / btc-jev-hybrid-final-dev / btc-jev-hybrid-final-dev-jev` (02/11) |  | 2 | 35,7 → 78,6 | 45,8 → 13,3 | 81,6 | 14,8 → 9,9 (7/71) | 2,7 | 14,1 | 0 | `btc-jev-hybrid-final-dev-a6 / btc-jev-hybrid-final-dev` |
| 4 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | hybrid (qwen, CERT v1) | rules | rag=auto | `btc-jev-hybrid-final-dev-a6 / btc-jev-hybrid-final-dev / btc-jev-hybrid-final-dev-current` (02/11) |  | 2 | 35,7 → 71,4 | 77,3 → 20,0 | 76,3 | 14,5 → 9,7 (7/72) | 3,0 | 14,8 | 0 | `btc-confidence-final-dev-paired / gate` |
| 5 | ✅ đã thực hiện | rules | offline | rules | rules | direct | `regress-b345` (01/11) |  | 1 | 50,0 → 92,9 | 25,0 → 0,0 | 78,9 | 10,8 → 6,6 (5/76) | 0,0 | 0,0 | 0 |  |
| 6 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | hybrid (qwen) | rules | rag=auto | `btc-confidence-final-dev-paired / current` (30/10) |  | 1 | 35,7 → 75,0 | 76,9 → 20,0 | 76,3 | 15,3 → 9,5 (7/74) | 3,0 | 17,6 | 0 |  |

## BTC-like v2_1 dev (28 kịch bản, lời khách viết lại)

`datagen/out_btc_like_final_v2_1/final/dev` · 22 lần chạy, 14 cấu hình khác nhau

| # | Trạng thái | Router | Generator | Extractor | Planner | Khác | Lần mới nhất (ngày file) | Nhãn | Số lần chạy | TSR B → F | RQR B → F | CCR F | HR giá&KM B → F (sai/tổng F) | TTFT p95 F (s) | Total p95 F (s) | GV F | Các lần cũ hơn (cùng cấu hình) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | hybrid (qwen, Jev, drop=qwen) | rules | rag=auto | `btc-jev-hybrid-final-dev / nocert` (03/11) | D42 job 1 `nocert` | 1 | – → 92,9 | – → 0,0 | 92,1 | – → 4,1 (3/74) | 3,3 | 14,6 | 0 |  |
| 2 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | hybrid (qwen, CERT v2, Jev, drop=qwen) | rules | rag=auto | `btc-jev-hybrid-final-dev / cert2` (03/11) | D42 job 1 `cert2` | 1 | – → 92,9 | – → 0,0 | 92,1 | – → 4,1 (3/74) | 2,7 | 14,5 | 0 |  |
| 3 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | hybrid (qwen, CERT v1, Jev, drop=qwen) | rules | rag=auto | `btc-jev-hybrid-final-dev / base` (03/11) | D42 job 1 `base` | 7 | 46,4 → 92,9 | 21,4 → 0,0 | 92,1 | 6,5 → 4,1 (3/74) | 2,9 | 14,4 | 0 | `eval-b`; `abl-4b / basectl`; `abl-short / basectl`; `abl-routerjev / basectl`; `btc-confidence-final-dev-paired / basectl`; `eval-b / basectl` |
| 4 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | hybrid (qwen, CERT v1, Jev, drop=qwen) | jev | rag=auto | `eval-b / planjev` (03/11) | D42 job 2 `planjev` | 1 | – → 92,9 | – → 0,0 | 92,1 | – → 3,9 (3/76) | 3,7 | 14,8 | 0 |  |
| 5 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | hybrid (qwen, CERT v1, Jev, drop=qwen) | rules | rag=auto, LEXICON_INCLUDE=none | `eval-b / nolex` (03/11) | D42 job 2 `nolex` | 1 | – → 92,9 | – → 0,0 | 92,1 | – → 3,9 (3/76) | 3,5 | 15,4 | 0 |  |
| 6 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | hybrid (qwen, CERT v1, Jev, drop=qwen) | rules | QUESTION_CLF=jev, rag=auto | `btc-confidence-final-dev-paired / qclf` (03/11) | D42 job 3 `qclf` | 1 | – → 92,9 | – → 0,0 | 92,1 | – → 4,1 (3/74) | 2,7 | 12,2 | 0 |  |
| 7 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | hybrid (qwen, CERT v1, Jev, drop=accept) | rules | rag=auto | `btc-confidence-final-dev-paired / dropaccept` (03/11) | D42 job 3 `dropaccept` | 1 | – → 92,9 | – → 0,0 | 92,1 | – → 4,1 (3/74) | 2,7 | 13,1 | 0 |  |
| 8 | ✅ đã thực hiện | jev | qwen Qwen3-8B-AWQ | hybrid (qwen, CERT v1, Jev, drop=qwen) | rules | rag=auto | `abl-routerjev / routerjev` (03/11) | D42 job 4 `routerjev` | 1 | – → 96,4 | – → 0,0 | 89,5 | – → 2,6 (2/78) | 3,4 | 14,1 | 0 |  |
| 9 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ short | hybrid (qwen, CERT v1, Jev, drop=qwen) | rules | rag=auto, max_tokens=160 | `abl-short / short` (03/11) | D42 job 5 `short` | 1 | – → 92,9 | – → 5,9 | 89,5 | – → 1,4 (1/72) | 2,9 | 9,5 | 0 |  |
| 10 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | rules | rules | rag=auto | `abl-nojev / xrules` (03/11) | D42 job 7 `xrules` | 1 | – → 92,9 | – → 0,0 | 92,1 | – → 2,7 (2/75) | 1,4 | 13,7 | 0 |  |
| 11 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | hybrid (qwen, CERT v1) | rules | rag=auto | `abl-nojev / nojev` (03/11) | D42 job 7 `nojev` | 1 | – → 92,9 | – → 5,3 | 92,1 | – → 3,9 (3/76) | 3,3 | 16,9 | 0 |  |
| 12 | ✅ đã thực hiện | rules | qwen Qwen3-4B | hybrid (qwen, CERT v1, Jev, drop=qwen) | rules | rag=auto | `abl-4b / 4b` (03/11) | D42 job 6 `4b` | 1 | – → 92,9 | – → 0,0 | 84,2 | – → 1,5 (1/66) | 2,1 | 10,8 | 0 |  |
| 13 | ✅ đã thực hiện | rules | offline | rules | rules | direct, LEXICON_INCLUDE=none | `btc-confidence-dev-current / lexnone` (03/11) | D40 `none` | 1 | 46,4 → 92,9 | 45,8 → 0,0 | 89,5 | 6,0 → 1,3 (1/75) | 0,1 | 0,1 | 0 |  |
| 14 | ✅ đã thực hiện | rules | offline | rules | rules | direct | `btc-confidence-dev-current / lexappr` (03/11) | D40 `approved` | 3 | 46,4 → 92,9 | 45,8 → 0,0 | 89,5 | 6,0 → 1,3 (1/75) | 0,1 | 0,1 | 0 | `regress-cert2b / cert1`; `regress-cert2b / cert2` |

## D-7 dev (30 kịch bản) — bộ dò lỗi, đã sửa luật trên chính bộ này

`datagen/out_btc_like_d7/final/dev` · 9 lần chạy, 3 cấu hình khác nhau

| # | Trạng thái | Router | Generator | Extractor | Planner | Khác | Lần mới nhất (ngày file) | Nhãn | Số lần chạy | TSR B → F | RQR B → F | CCR F | HR giá&KM B → F (sai/tổng F) | TTFT p95 F (s) | Total p95 F (s) | GV F | Các lần cũ hơn (cùng cấu hình) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ✅ đã thực hiện | rules | offline | rules | rules | direct, LEXICON_INCLUDE=none | `btc-confidence-dev-current / lexnone` (03/11) | D40 `none` | 1 | 30,0 → 93,3 | 51,3 → 0,0 | 100,0 | 1,8 → 1,3 (1/77) | 0,1 | 0,1 | 0 |  |
| 2 | ✅ đã thực hiện | rules | offline | rules | rules | direct | `btc-confidence-dev-current / lexappr` (03/11) | D40 `approved` | 7 | 30,0 → 93,3 | 54,8 → 0,0 | 100,0 | 1,8 → 1,3 (1/77) | 0,1 | 0,1 | 0 | `regress-1102`; `regress-1102b`; `regress-cert2 / v1`; `regress-cert2 / v2`; `regress-cert2b / cert1`; `regress-cert2b / cert2` |
| 3 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | hybrid (qwen, CERT v1, Jev, drop=qwen) | rules | rag=auto | `eval-b` (02/11) | Job B | 1 | 30,0 → 93,3 | 59,4 → 0,0 | 100,0 | 0,0 → 0,0 (0/84) | 2,0 | 14,2 | 0 |  |

## out_nat dev (45 kịch bản)

`datagen/out_nat/dev` · 29 lần chạy, 18 cấu hình khác nhau

| # | Trạng thái | Router | Generator | Extractor | Planner | Khác | Lần mới nhất (ngày file) | Nhãn | Số lần chạy | TSR B → F | RQR B → F | CCR F | HR giá&KM B → F (sai/tổng F) | TTFT p95 F (s) | Total p95 F (s) | GV F | Các lần cũ hơn (cùng cấu hình) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ✅ đã thực hiện | rules | offline | rules | rules | direct, LEXICON_INCLUDE=none | `btc-confidence-dev-current / lexnone` (03/11) |  | 1 | 66,7 → 95,6 | 41,7 → 0,0 | 88,5 | 18,0 → 1,9 (2/107) | 0,1 | 0,1 | 0 |  |
| 2 | ✅ đã thực hiện | rules | offline | rules | rules | direct | `btc-confidence-dev-current / lexappr` (03/11) |  | 7 | 66,7 → 95,6 | 41,7 → 0,0 | 88,5 | 18,0 → 1,9 (2/107) | 0,1 | 0,1 | 0 | `regress-1102`; `regress-1102b`; `regress-cert2 / v1`; `regress-cert2 / v2`; `regress-cert2b / cert1`; `regress-cert2b / cert2` |
| 3 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | parallel=2, logprobs, rag=auto, max_tokens=160 | `eval-b` (28/10) |  | 1 | 68,9 → 100,0 | 16,1 → 3,8 | 76,1 | 22,1 → 2,1 (2/96) | 2,5 | 7,8 | 0 |  |
| 4 | ✅ đã thực hiện | rules | qwen Qwen3-4B short | hybrid (qwen) | rules | parallel=2, logprobs, rag=auto, max_tokens=160 | `extract-latency-28` (28/10) |  | 1 | 68,9 → 100,0 | 18,9 → 4,3 | 74,3 | 23,5 → 2,9 (3/105) | 2,8 | 7,6 | 0 |  |
| 5 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | placeholders, parallel=2, QUESTION_CLF=on, logprobs, rag=auto, max_tokens=160 | `eval-b-hyb5-ph / eval-b` (27/10) |  | 1 | 68,9 → 100,0 | 23,5 → 3,4 | 83,2 | 22,8 → 2,2 (2/91) | 2,9 | 8,3 | 0 |  |
| 6 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | parallel=2, QUESTION_CLF=on, logprobs, rag=auto, max_tokens=160 | `eval-b-hyb5 / eval-b` (27/10) |  | 1 | 68,9 → 100,0 | 22,6 → 3,6 | 81,4 | 22,6 → 2,1 (2/95) | 2,4 | 8,2 | 0 |  |
| 7 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | placeholders, QUESTION_CLF=on, rag=auto, max_tokens=160 | `eval-b-hyb4-ph / eval-b` (27/10) |  | 1 | 68,9 → 100,0 | 30,3 → 3,7 | 83,2 | 24,5 → 2,2 (2/91) | 2,1 | 7,9 | 0 |  |
| 8 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | QUESTION_CLF=on, rag=auto, max_tokens=160 | `eval-b-hyb4 / eval-b` (27/10) |  | 1 | 68,9 → 100,0 | 22,6 → 3,7 | 80,5 | 22,9 → 2,1 (2/95) | 2,1 | 6,4 | 0 |  |
| 9 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | rag=auto, max_tokens=160 | `eval-b-hyb3 / eval-b` (24/10) |  | 2 | 68,9 → 100,0 | 30,6 → 0,0 | 83,2 | 24,2 → 3,2 (3/95) | 1,3 | 3,9 | 0 | `eval-b / hyb2` |
| 10 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | rules | rules | rag=auto, max_tokens=160 | `eval-b / fix-rules` (23/10) |  | 2 | 68,9 → 100,0 | 13,9 → 2,6 | 84,1 | 23,9 → 1,1 (1/89) | 0,9 | 3,4 | 0 | `eval-b / 4b-short-w1` |
| 11 | ✅ đã thực hiện | laya | qwen Qwen3-4B short | rules | rules | rag=auto, max_tokens=160 | `laya-b / 4b-short-w1` (23/10) |  | 1 | 6,7 → 0,0 | 5,7 → 3,2 | 0,0 | 38,5 → 44,4 (4/9) | 0,8 | 7,1 | 7 |  |
| 12 | ✅ đã thực hiện | rules | qwen Qwen3-4B | rules | rules |  | `speed2-w1` (15/10) |  | 4 | – → 95,6 | – → 1,5 | 76,1 | – → 0,9 (1/108) | 0,7 | 5,4 | 0 | `speed-fp16-4b`; `speed2-rep2 / rep2`; `speed2-ngram-short / ngram` |
| 13 | ✅ đã thực hiện | rules | qwen Qwen3-4B short | rules | rules | max_tokens=160 | `speed2-ngram-short / short` (15/10) |  | 1 | – → 97,8 | – → 0,0 | 76,1 | – → 2,5 (3/118) | 1,5 | 5,6 | 0 |  |
| 14 | ✅ đã thực hiện | jev | qwen Qwen3-8B | rules | rules | rag=auto | `eval-b / 8b-tp2` (15/10) |  | 1 | 66,7 → 97,8 | 32,0 → 3,5 | 77,0 | 24,4 → 3,8 (3/78) | 1,8 | 6,9 | 0 |  |
| 15 | ✅ đã thực hiện | jev | qwen Qwen3-4B | rules | rules | rag=auto | `eval-b / 4b` (15/10) |  | 1 | 64,4 → 95,6 | 15,8 → 0,0 | 76,1 | 20,8 → 2,1 (2/94) | 1,2 | 6,6 | 0 |  |
| 16 | ✅ đã thực hiện | jev | qwen Qwen3-8B-AWQ | rules | rules | rag=auto | `eval-b-awq8 / eval-b` (15/10) |  | 1 | 68,9 → 95,6 | 24,1 → 5,9 | 77,0 | 23,5 → 3,2 (3/94) | 2,6 | 11,9 | 0 |  |
| 17 | ✅ đã thực hiện | rules | qwen Qwen3-8B-AWQ | rules | rules |  | `speed-awq8` (15/10) |  | 1 | – → 95,6 | – → 5,1 | 76,1 | – → 2,0 (2/99) | 1,9 | 9,3 | 0 |  |
| 18 | ✅ đã thực hiện | rules | qwen Qwen3-8B | rules | rules |  | `speed-fp16-8b-tp2` (15/10) |  | 1 | – → 97,8 | – → 0,0 | 75,2 | – → 4,3 (4/92) | 1,1 | 7,0 | 0 |  |

## out_nat test (22 kịch bản) — KHÔNG dùng để chọn cấu hình

`datagen/out_nat/test` · 25 lần chạy, 14 cấu hình khác nhau

| # | Trạng thái | Router | Generator | Extractor | Planner | Khác | Lần mới nhất (ngày file) | Nhãn | Số lần chạy | TSR B → F | RQR B → F | CCR F | HR giá&KM B → F (sai/tổng F) | TTFT p95 F (s) | Total p95 F (s) | GV F | Các lần cũ hơn (cùng cấu hình) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | parallel=2, logprobs, rag=auto, max_tokens=160 | `gen-adaptive-29 / eval-b / w1-c2` (29/10) |  | 8 | – → 95,5 | – → 0,0 | 68,4 | – → 0,0 (0/45) | 1,9 | 5,2 | 0 | `eval-b`; `jev-slots-total-29 / eval-b / current`; `jev-slots-total-29 / eval-b / multiclass`; `jev-no-agent-qwen-29 / eval-b / current`; `jev-no-agent-qwen-29 / eval-b / jev-rules`; `gen-latency-ablation-29 / eval-b / gen-latency-29-w1-c2`; `gen-latency-ablation-29 / eval-b / gen-latency-29-w2-c2` |
| 2 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | logprobs, rag=auto, max_tokens=160 | `gen-adaptive-29 / eval-b / w1-c1` (29/10) |  | 3 | – → 95,5 | – → 0,0 | 71,1 | – → 0,0 (0/49) | 1,3 | 5,4 | 0 | `gen-latency-ablation-29 / eval-b / gen-latency-29-w1-c1`; `gen-latency-ablation-29 / eval-b / gen-latency-29-w2-c1` |
| 3 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | parallel=2, adaptive, logprobs, rag=auto, max_tokens=160 | `gen-adaptive-29 / eval-b / adaptive` (29/10) |  | 1 | – → 95,5 | – → 10,0 | 71,1 | – → 0,0 (0/46) | 1,3 | 5,7 | 0 |  |
| 4 | ✅ đã thực hiện | rules | qwen Qwen3-4B short | hybrid (qwen) | rules | parallel=2, logprobs, rag=auto, max_tokens=160 | `extract-latency-28` (28/10) |  | 1 | 81,8 → 95,5 | 0,0 → 16,7 | 63,2 | 8,3 → 0,0 (0/48) | 2,9 | 7,8 | 0 |  |
| 5 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | placeholders, parallel=2, QUESTION_CLF=on, logprobs, rag=auto, max_tokens=160 | `eval-b-hyb5-ph / eval-b` (27/10) |  | 1 | 77,3 → 90,9 | 0,0 → 11,1 | 68,4 | 12,8 → 2,0 (1/49) | 2,9 | 8,6 | 0 |  |
| 6 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | parallel=2, QUESTION_CLF=on, logprobs, rag=auto, max_tokens=160 | `eval-b-hyb5 / eval-b` (27/10) |  | 1 | 81,8 → 95,5 | 0,0 → 7,7 | 71,1 | 8,5 → 0,0 (0/45) | 3,0 | 8,2 | 0 |  |
| 7 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | placeholders, QUESTION_CLF=on, rag=auto, max_tokens=160 | `eval-b-hyb4-ph / eval-b` (27/10) |  | 1 | 77,3 → 95,5 | 0,0 → 11,1 | 68,4 | 8,7 → 0,0 (0/50) | 2,3 | 7,6 | 0 |  |
| 8 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | QUESTION_CLF=on, rag=auto, max_tokens=160 | `eval-b-hyb4 / eval-b` (27/10) |  | 1 | 81,8 → 95,5 | 0,0 → 10,0 | 71,1 | 10,2 → 2,1 (1/47) | 2,0 | 6,9 | 0 |  |
| 9 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | rag=auto, max_tokens=160 | `eval-b-hyb3 / eval-b` (24/10) |  | 2 | 81,8 → 95,5 | 20,0 → 0,0 | 73,7 | 10,9 → 4,1 (2/49) | 1,3 | 4,2 | 0 | `eval-b / hyb2` |
| 10 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | rules | rules | rag=auto, max_tokens=160 | `eval-b / fix-rules` (23/10) |  | 2 | 81,8 → 95,5 | 14,3 → 0,0 | 68,4 | 8,9 → 2,0 (1/50) | 0,9 | 3,5 | 0 | `eval-b / 4b-short-w1` |
| 11 | ✅ đã thực hiện | laya | qwen Qwen3-4B short | rules | rules | rag=auto, max_tokens=160 | `laya-b / 4b-short-w1` (23/10) |  | 1 | 0,0 → 0,0 | 0,0 → 10,0 | 0,0 | 0,0 → 0,0 (0/5) | 0,7 | 6,2 | 1 |  |
| 12 | ✅ đã thực hiện | jev | qwen Qwen3-8B | rules | rules | rag=auto | `eval-b / 8b-tp2` (15/10) |  | 1 | 72,7 → 90,9 | 0,0 → 0,0 | 65,8 | 6,1 → 0,0 (0/48) | 1,9 | 10,8 | 0 |  |
| 13 | ✅ đã thực hiện | jev | qwen Qwen3-4B | rules | rules | rag=auto | `eval-b / 4b` (15/10) |  | 1 | 77,3 → 90,9 | 0,0 → 0,0 | 68,4 | 6,0 → 0,0 (0/49) | 1,2 | 9,3 | 0 |  |
| 14 | ✅ đã thực hiện | jev | qwen Qwen3-8B-AWQ | rules | rules | rag=auto | `eval-b-awq8 / eval-b` (15/10) |  | 1 | 77,3 → 86,4 | 5,9 → 0,0 | 68,4 | 8,3 → 0,0 (0/45) | 3,2 | 15,6 | 0 |  |

## public_sample của BTC (7 kịch bản)

`test_set/public_sample` · 25 lần chạy, 14 cấu hình khác nhau

| # | Trạng thái | Router | Generator | Extractor | Planner | Khác | Lần mới nhất (ngày file) | Nhãn | Số lần chạy | TSR B → F | RQR B → F | CCR F | HR giá&KM B → F (sai/tổng F) | TTFT p95 F (s) | Total p95 F (s) | GV F | Các lần cũ hơn (cùng cấu hình) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ✅ đã thực hiện | rules | offline | rules | rules | direct, LEXICON_INCLUDE=none | `btc-confidence-dev-current / lexnone` (03/11) | D40 `none` | 1 | 57,1 → 85,7 | 44,4 → 0,0 | 66,7 | 29,4 → 5,6 (1/18) | 0,1 | 0,1 | 0 |  |
| 2 | ✅ đã thực hiện | rules | offline | rules | rules | direct | `btc-confidence-dev-current / lexappr` (03/11) | D40 `approved` | 8 | 57,1 → 85,7 | 44,4 → 0,0 | 66,7 | 29,4 → 5,6 (1/18) | 0,1 | 0,1 | 0 | `regress-b345`; `regress-1102`; `regress-1102b`; `regress-cert2 / v1`; `regress-cert2 / v2`; `regress-cert2b / cert1`; `regress-cert2b / cert2` |
| 3 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | parallel=2, logprobs, rag=auto, max_tokens=160 | `eval-b` (28/10) |  | 1 | 57,1 → 85,7 | 40,0 → 0,0 | 71,4 | 36,4 → 7,1 (1/14) | 3,7 | 8,2 | 0 |  |
| 4 | ✅ đã thực hiện | rules | qwen Qwen3-4B short | hybrid (qwen) | rules | parallel=2, logprobs, rag=auto, max_tokens=160 | `extractor-fix-28` (28/10) |  | 2 | – → 85,7 | – → 0,0 | 61,9 | – → 6,2 (1/16) | 3,5 | 10,0 | 0 | `extract-latency-28` |
| 5 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | placeholders, parallel=2, QUESTION_CLF=on, logprobs, rag=auto, max_tokens=160 | `eval-b-hyb5-ph / eval-b` (27/10) |  | 1 | 57,1 → 85,7 | 16,7 → 0,0 | 71,4 | 35,7 → 8,3 (1/12) | 2,7 | 9,2 | 0 |  |
| 6 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | parallel=2, QUESTION_CLF=on, logprobs, rag=auto, max_tokens=160 | `eval-b-hyb5 / eval-b` (27/10) |  | 1 | 57,1 → 85,7 | 20,0 → 0,0 | 66,7 | 33,3 → 7,7 (1/13) | 3,1 | 9,8 | 0 |  |
| 7 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | placeholders, QUESTION_CLF=on, rag=auto, max_tokens=160 | `eval-b-hyb4-ph / eval-b` (27/10) |  | 1 | 57,1 → 85,7 | 25,0 → 0,0 | 76,2 | 33,3 → 0,0 (0/11) | 2,1 | 9,1 | 0 |  |
| 8 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | QUESTION_CLF=on, rag=auto, max_tokens=160 | `eval-b-hyb4 / eval-b` (27/10) |  | 1 | 57,1 → 85,7 | 28,6 → 0,0 | 66,7 | 33,3 → 0,0 (0/12) | 3,4 | 8,5 | 0 |  |
| 9 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | hybrid (qwen) | rules | rag=auto, max_tokens=160 | `eval-b-hyb3 / eval-b` (24/10) |  | 3 | 57,1 → 85,7 | 28,6 → 0,0 | 76,2 | 40,0 → 7,7 (1/13) | 2,0 | 5,8 | 0 | `eval-b / fix-hybrid`; `eval-b / hyb2` |
| 10 | ✅ đã thực hiện | jev | qwen Qwen3-4B short | rules | rules | rag=auto, max_tokens=160 | `eval-b / fix-rules` (23/10) |  | 2 | 57,1 → 85,7 | 40,0 → 0,0 | 76,2 | 36,4 → 0,0 (0/10) | 0,8 | 6,3 | 0 | `eval-b / 4b-short-w1` |
| 11 | ✅ đã thực hiện | laya | qwen Qwen3-4B short | rules | rules | rag=auto, max_tokens=160 | `laya-b / 4b-short-w1` (23/10) |  | 1 | 14,3 → 14,3 | 16,7 → 14,3 | 0,0 | 50,0 → 50,0 (1/2) | 0,8 | 4,5 | 0 |  |
| 12 | ✅ đã thực hiện | jev | qwen Qwen3-8B | rules | rules | rag=auto | `eval-b / 8b-tp2` (15/10) |  | 1 | 57,1 → 85,7 | 33,3 → 0,0 | 61,9 | 45,5 → 0,0 (0/6) | 4,6 | 8,8 | 0 |  |
| 13 | ✅ đã thực hiện | jev | qwen Qwen3-4B | rules | rules | rag=auto | `eval-b / 4b` (15/10) |  | 1 | 57,1 → 85,7 | 25,0 → 12,5 | 66,7 | 40,0 → 7,1 (1/14) | 5,0 | 10,7 | 0 |  |
| 14 | ✅ đã thực hiện | jev | qwen Qwen3-8B-AWQ | rules | rules | rag=auto | `eval-b-awq8 / eval-b` (15/10) |  | 1 | 57,1 → 85,7 | 25,0 → 0,0 | 61,9 | 27,3 → 7,1 (1/14) | 7,6 | 12,8 | 0 |  |
