# Kế hoạch 06/11: kiểm tra → đóng băng → holdout → vòng cải tiến

Viết cuối ngày 05/11 để làm tiếp. Chi tiết các bước đã làm có trong `NHAT-KY-2026-11-05.md` (mục 11–15). Danh sách quyết định có trong `CHO-DUYET.md` (cuối file).

## 0. Trạng thái cuối ngày 05/11

**Code đã sửa, chưa commit.** Message commit gợi ý tách 6 nhóm theo mục 15 của nhật ký. Tóm tắt các sửa đổi:

| Mục | Sửa đổi | Chỗ sửa |
|---|---|---|
| D49b | Mô tả cờ `asks_internal_cost`: người gọi bất kể tự xưng là ai, giá sàn, giục đọc tiếp | `core/llm/router.py` |
| V3-141 | Mô tả cờ `medical_question`: nêu tuổi bé / mua đồ mẹ và bé không phải câu hỏi y tế | `core/llm/router.py` |
| D33 | Câu mẫu an toàn báo KM đã hết hạn + giá hiện tại | `harness/agent.py` `_promo_safe_plan` |
| D54 | Nhớ `variant_sku` đã báo giá khi khách hẹn chốt sau | `harness/agent.py` `_remember` |
| V3-011 | Guardrail chặn "giảm N%" khi không có KM N% đang áp dụng | `harness/guardrails.py` `promo_problems` |
| V3-140 | Nhận "cho cô trả nhé" là ý trả hàng | `harness/agent.py` `RETURN_RX` |
| E04 | Slot số lượng `ORDER_QTY` → `order.create qty` | `harness/agent.py` `order_qty` |
| D58 + mục 13 | Mặc định bật `PLANNER_TABLE`, `PRODUCT_LEXICON`, `PARALLEL_ROUTER`, `ORDER_QTY`; `JEV_MODEL=jev-latest` | `core/config.py` |

**Đã kiểm trên Kaggle CPU** (`runs/kaggle/abl-short.checks-1105/`):
- `fixes_1105_check` OK.
- `order_qty_ab` OK: 0 lượt khác trace trên 6 bộ dev.
- `smoke.sh` đầy đủ: TẤT CẢ OK.
- Probe `medical_question`: bản mới bắt câu dương 4/4, câu âm 0/15.

**Số mốc gần nhất** (v3 dev, full, Jev chính thức, chưa có các sửa đổi trên; job `abl-short-final`, `runs/kaggle/abl-short.final-1105/`):

| TSR | TSR ca khó | CCR | HR | RQR | Guardrail | TTFT p50 / p95 | Total p95 |
|---|---|---|---|---|---|---|---|
| 90,1 | 82,1 | 63,0 | 9,0 | 0 | 1 | 1,02 / 2,34 s | 6,63 s |

Kịch bản còn trượt: V3-093 đến V3-098 (giả danh nội bộ), V3-011 (prompt injection), V3-140 (trả hàng). Vi phạm guardrail: V3-141 (chuyển máy thừa). Các sửa đổi ở mục 0 nhắm vào đúng những lỗi này.

## 0. Bước 0 - Kiểm tra giả lập trên bộ out_v3 dev xem việc tắt với bật CERT1, CERT2 có ảnh hưởng gì hay không ( đây là đề xuất của người dùng )
## 1. Bước 1 — chạy kiểm tra v3 dev (mục 1, đã duyệt, **đã đẩy, chưa chạy**)

- **Notebook:** `elylish11/sudocode-abl-short`, biến thể `verify`.
- **Cách chạy:** Edit → Input → cập nhật `sudocode-repo` lên bản mới nhất → **Accelerator GPU T4** (lần gần nhất để None vì là job CPU) → Save & Run All.
- **Cấu hình:**
  - Dữ liệu: v3 dev, chỉ chế độ full.
  - Router: Jev `jev-latest`, endpoint chính thức.
  - Extractor: hybrid + Jev + CERT v1.
  - Bật `PLANNER_TABLE`, `PRODUCT_LEXICON`, `PARALLEL_ROUTER`, `ORDER_QTY`.
  - Generator: Qwen3-4B, `REPLY_STYLE=short`, `LLM_MAX_TOKENS=160`, `STRIP_QUESTIONS=1`, nhiệt độ 0, `LLM_CACHE=off`.
- **Bước trước khi chạy:** đếm 81 kịch bản, chạy `fixes_1105_check`, `jev_ping`.
- **Thời gian:** khoảng 45 phút GPU.
- **Kéo kết quả về:** `venv/Scripts/python.exe scripts/kaggle_job.py --cred D:/User/Documents/kaggle_api_key/elylish11.json wait --job abl-short`.
- **Trước khi đọc số cần kiểm:**
  - `packed_at` là 05/11.
  - 315/315 lượt router là `jev`.
  - 0 lỗi TypeSafe, 0 lượt lỗi LLM.
- **Điều kiện đạt:**
  - V3-093 đến V3-098, V3-011, V3-140 đều qua.
  - V3-141 không còn chuyển máy.
  - Không kịch bản nào đang qua bị hỏng (so với `abl-short-final`).
  - 0 vi phạm guardrail.
  - CCR ≥ 63,0, TTFT p95 ≤ 3 s, Total p95 ≤ 8 s.
- **Nếu không đạt:** soi trace, đề xuất sửa, chờ duyệt, rồi chạy lại bước 1. Chưa sang bước 3.

## 2. Bước 2 — trả schema về bản BTC (chờ duyệt)

`schemas/trace_log.schema.json` bị sửa ở commit `3ef8225` (28/10): thêm mô tả cho `total_ms` và các trường `end_to_end_ms`, `post_ms`, `post_parts_ms`. Schema gốc không cấm trường thừa, nên trace vẫn hợp lệ.

Cách làm: `git checkout 51e479b -- schemas/trace_log.schema.json`, rồi ghi mô tả các trường thêm vào docs của nhóm. Không cần chạy lại gì.

## 3. Bước 3 — chốt cấu hình nộp bài và đóng băng (mục 14, 16, đang hoãn)

- **Cấu hình đề xuất:** đúng cấu hình của bước 1.
- **Các mục còn mở phải quyết trước khi đóng băng**, vì sau đó không sửa code được nữa:
  - Mục 7 (D36): hỏi địa chỉ trước khi tạo đơn. Đề xuất: hoãn hẳn.
  - Mục 8 (D56 phần còn lại): E09 sản phẩm không có trong catalog, E11 đổi ý sau khi có đơn, sửa gốc câu "em gọi anh". Đề xuất: hoãn hẳn.
- **Khi đóng băng:**
  - Ghi ngày đóng băng và commit hash vào `CHO-DUYET.md`.
  - Ghi danh sách cờ đầy đủ (lấy từ `full.config.json` của bước 1).

## 4. Bước 4 — v3 holdout, số cuối (mục 19, đã duyệt, chạy sau bước 3)

- **Dữ liệu và chế độ:** `datagen/out_v3/final/holdout` (77 kịch bản), cả full và `baseline_no_memory` (để có "Mức giảm RQR").
- **Cấu hình:** giống hệt bước 1.
- **Thời gian:** khoảng 1,3–1,5 GPU-giờ, dưới ngưỡng 3 giờ.
- **Chạy một lần duy nhất.** Không sửa code, dữ liệu hay cấu hình theo kết quả.
- **Khi báo số cần nêu rõ:**
  - Holdout v3 do cùng trợ lý viết, ở một phiên khác (`docs/DATASET.md`).
  - Số holdout dự kiến thấp hơn dev, vì các ca D51 được rút từ dev.
- Nếu mục 20 chọn (b), cân nhắc chạy vòng 0 (D51 tắt) trong cùng đợt, để đỡ thêm một lần chạy GPU.

## 5. Bước 5 — vòng cải tiến, tiêu chí 5 (13 %) (mục 20, 21, 22, đang hoãn)

**Quyết định cần có:**
- **Mục 20 (D57)**, cách tính D51:
  - (a) D51 là phần phát triển, bật sẵn ở vòng 0.
  - (b) Vòng 0 tắt D51, đưa các sửa đổi qua vòng cải tiến (contexts → thẻ → sale duyệt từng mục → cổng → vòng 1).
  - Trợ lý nghiêng về (b), vì nó cho thấy được cải thiện qua 2 vòng.
- **Mục 21 (D30)**, bộ cố định cho vòng 0 → 1: đề xuất v3 dev.
- **Mục 22 (D41)**: ablation bỏ từng loại đề xuất (`faq`, `playbook`, `cue`, `exemplar`, `planner_rule`…) để lấy điểm thưởng.

**Quy trình:** chạy vòng 0 → `python -m improve contexts` → sale duyệt từng mục (UI tab improve) → `python -m improve gate` → vòng 1 trên cùng bộ → bảng chênh lệch.

## 6. Bước 6 — báo cáo

- Bảng A.6: holdout, full và baseline.
- Latency: L1 + L2 (proxy → Jev chính thức). TTFT p95 9,0 → 2,3 s.
- Phân tích lỗi: phân loại theo planner / router / extractor (nhật ký 05/11 mục 2).
- Cơ chế cải tiến: hai vòng và ablation.
- Ghi rõ những gì đã thấy khi phân tích dev.

## Ràng buộc nhắc lại

- Mọi test chạy trên Kaggle; máy local chỉ lưu file. Chỉ gọi `venv/Scripts/python.exe scripts/kaggle_job.py` ở local.
- Job cần Secret Jev thì đẩy dataset-only, người dùng bấm Run. Kéo kết quả về thì sao lưu thư mục `runs/kaggle/abl-short` trước (cp, không rm).
- Không sửa file BTC: `eval/mock_tools.py`, `eval/reference_eval.py`, `eval/llm_judge_rubric.json`, `catalog/`, `policy/`, `rag/qa_labeled.json`, `simulator/`, `schemas/`, `test_set/public_sample/`.
- Không đọc holdout trước khi đóng băng. Không chỉnh extractor để thổi phồng RQR / HR.
- Không tự commit. Mỗi quyết định cần người dùng duyệt rõ.
