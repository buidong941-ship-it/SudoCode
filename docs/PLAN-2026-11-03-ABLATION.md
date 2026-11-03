# Kế hoạch job ablation D42 (03/11/2026)

Thực hiện D38 (quy trình đo) và D42 (danh sách biến thể), cả hai đã được người dùng duyệt 03/11. Trạng thái duyệt ở [CHO-DUYET.md](CHO-DUYET.md). **Chưa đẩy job nào.** Tổng ước tính vượt 3 GPU-giờ nên phải hỏi lại trước khi đẩy.

## 1. Việc phải xong trước khi đẩy GPU

| Việc | Trạng thái |
|---|---|
| D40: `LEXICON_INCLUDE=none` tắt hẳn lexicon; giá trị lạ báo `ValueError`; thêm chế độ `all` cho `tests/lexicon_check.py` | Xong code (`harness/lexicon/__init__.py`), test `tests/lexicon_include_check.py` (đã thêm vào `smoke.sh`) |
| `scripts/run_suite.py`: biến môi trường `SUITE_CONFIGS=full` để biến thể chỉ chạy Full | Xong code |
| Job Kaggle CPU: `smoke.sh` | **Xong 03/11, OK** (midzid `sudocode-regress-cert2b`). Ablation lexicon offline của D40 cũng xong (`NHAT-KY-2026-11-03.md` mục 1) |

Không sửa `kaggle/runner.py`: notebook chạy bản runner nhúng sẵn, đẩy dataset-only không cập nhật được runner.

## 2. Thiết lập chung (env cấp job)

| Thành phần | Giá trị |
|---|---|
| Bộ đo | BTC-like v2_1 dev (`datagen/out_btc_like_final_v2_1/final/dev`, 28 kịch bản), như job B |
| Router | `rules` |
| Generator | `qwen`, Qwen3-8B-AWQ, `LLM_TEMPERATURE=0` |
| Cache | `LLM_CACHE=off` |
| Extractor | `hybrid`, `EXTRACTOR_CONFIDENCE_GATE=1`, `EXTRACTOR_CERT_VERSION=1`, `EXTRACTOR_JEV_HYBRID=1`, `JEV_DROP_POLICY=qwen` |
| Planner | `PLANNER_BACKEND=rules` |
| Lexicon | `LEXICON_INCLUDE=approved` |
| Cải tiến | `IMPROVE_DIR` rỗng |
| Code | **cùng một version dataset `sudocode-repo` cho cả 3 job** |

## 3. Biến thể

Mỗi biến thể đổi đúng 1 yếu tố so với `base`. Biến thể chỉ chạy Full (`SUITE_CONFIGS=full`). Router và extractor phải đổi qua `SUITE_ROUTER` / `SUITE_EXTRACTOR`, vì `run_suite.py` nhận hai giá trị này qua dòng lệnh, nên `ROUTER_BACKEND` / `EXTRACTOR_BACKEND` không có tác dụng.

| # | Tag | Env của biến thể | So cái gì |
|---|---|---|---|
| 0 | `base` | (không) — chạy Full + Baseline | mốc |
| 1 | `nocert` | `EXTRACTOR_CONFIDENCE_GATE=0` | không CERT / CERT v1 |
| 2 | `cert2` | `EXTRACTOR_CERT_VERSION=2` | CERT v1 / v2 |
| 3 | `xrules` | `SUITE_EXTRACTOR=rules` | hybrid / rules thuần |
| 4 | `planjev` | `PLANNER_BACKEND=jev` | planner rules / Jev |
| 5 | `nolex` | `LEXICON_INCLUDE=none` | lexicon bật / tắt |
| 6 | `nojev` | `EXTRACTOR_JEV_HYBRID=0` | hybrid có / không Jev |
| 7 | `dropaccept` | `JEV_DROP_POLICY=accept` | xử lý khi Jev bỏ slot |
| 8 | `qclf` | `QUESTION_CLF=1` | bộ phân loại câu hỏi |
| 9 | `routerjev` | `SUITE_ROUTER=jev` | router rules / Jev |
| 10 | `short` | `REPLY_STYLE=short`, `LLM_MAX_TOKENS=160` | độ dài câu trả lời |
| 11 | `4b` | `QWEN_MODEL=Qwen/Qwen3-4B` | model generator |

## 4. Chia job

Mỗi job dưới 3 giờ. Job 2 và 3 có thêm `basectl` (`base` chỉ chạy Full) làm đối chứng trong cùng job: latency so được trong cùng máy, và kiểm luôn nhiệt độ 0 có cho kết quả lặp lại không.

| Job | Notebook | Biến thể | Ước tính |
|---|---|---|---|
| 1 | `sudocode-btc-jev-hybrid-final-dev` | `base`, `nocert`, `cert2`, `xrules`, `nolex` | ~2,3 giờ |
| 2 | `sudocode-eval-b` | `basectl`, `planjev`, `nojev`, `dropaccept`, `qclf` | ~2,0 giờ |
| 3 | (notebook GPU còn lại) | `basectl`, `routerjev`, `short`, `4b` | ~1,7 giờ |

Tổng khoảng 6 GPU-giờ. Ước tính tính 45 phút cho `base`, 22 phút cho mỗi biến thể Full, cộng vài phút khởi động lại vLLM mỗi biến thể (`run_suite.py` tắt vLLM khi xong mỗi lần, nên `4b` tự khởi động đúng model).

### 4.1 Cách chia thực tế (03/11, người dùng bảo chia ra nhiều tài khoản)

Thay cho bảng trên: 7 job song song, mỗi job ≤ ~1,6 giờ. Mọi job dùng cùng code (gói lúc 11:2x 03/11) và cùng env chung mục 2. Script đẩy: `push_d42.sh` (scratchpad của phiên).

| Job | Tài khoản / notebook | Biến thể | Jev key |
|---|---|---|---|
| 1 | midzid `sudocode-btc-jev-hybrid-final-dev` | `base` (Full + Baseline), `nocert`, `cert2` | có sẵn, người dùng bấm Run |
| 2 | midzid `sudocode-eval-b` | `basectl`, `nolex`, `planjev` | có sẵn, người dùng bấm Run |
| 3 | felicityabby `sudocode-btc-confidence-final-dev-paired` | `basectl`, `dropaccept`, `qclf` | cần gắn |
| 4 | midzed `sudocode-abl-routerjev` (mới) | `basectl`, `routerjev` | cần gắn |
| 5 | elylish11 `sudocode-abl-short` (mới) | `basectl`, `short` | cần gắn |
| 6 | maggiecamila `sudocode-abl-4b` (mới) | `basectl`, `4b` | cần gắn |
| 7 | carterbryleeaqul `sudocode-abl-nojev` (mới) | `nojev`, `xrules` (job env `EXTRACTOR_JEV_HYBRID=0`) | không cần, tự chạy |

Job 7 không có `basectl` vì `basectl` cần Jev; latency của `nojev`/`xrules` so với `base` khác máy, nên chỉ coi là tham khảo. Tổng khoảng 7,5 GPU-giờ.

## 5. Cách đọc kết quả

- So từng biến thể với `base` (job 1) và với `basectl` của chính job đó.
- Chỉ số: CCR, HR giá & KM (chính thức và `hr_by_sku.py`), RQR, TSR, Total/TTFT p95, tỉ lệ lượt sinh lại / câu mẫu, số lần gọi Jev/Qwen của extractor.
- RQR giảm (%) của biến thể tính bằng Baseline của `base`.
- Mỗi biến thể chạy 1 lần: chênh lệch dưới 1 kịch bản TSR (3,6 điểm) coi là nhiễu. Nếu `basectl` lệch `base` thì nhiệt độ 0 vẫn chưa tất định, và ngưỡng nhiễu lấy theo độ lệch đó.
- Không kết luận khả năng tổng quát từ v2_1 dev; việc đó chờ holdout (D11).
