# Nhật ký thực hiện plan extractor và latency trên Kaggle (28/10/2026)

## Phạm vi và cấu hình

- Plan: `docs/PLAN_EXTRACTOR_METRIC_LATENCY.md`. Đã đọc `AGENTS.md`, nhật ký 27–28/10, code và kiểm tra liên quan. `git status`/diff báo unsafe repository ownership; không đổi Git configuration.
- GPU job `midzid/sudocode-extract-latency-28`: Kaggle T4, Qwen3-4B fp16, router `rules`, generator `qwen`, extractor `hybrid`, 2 suite workers, `GEN_PARALLEL_N=2`, `QUESTION_CLF=0`, `GEN_PLACEHOLDERS=0`, `EXTRACTOR_ASYNC=1`, `EXTRACT_LOGPROBS=1`, sample/dev/test, full và baseline, smoke suite + extractor eval. Job này không cần secret. Output: `runs/kaggle/extract-latency-28/`.
- CPU job `midzid/sudocode-extractor-metrics-28`: chấm rules và xác suất Jev **đã cache từ Kaggle ngày 27/10**, tách dev/tune/test theo split cũ; kiểm gate và rules extractor. Không gọi Jev mới, không huấn luyện model. Output: `runs/kaggle/extractor-metrics-28/`.
- Theo phản hồi của người dùng, phép đo Jev mới là bắt buộc. Đã chạy cấu hình `eval-b` từ version mới của dataset `midzid/sudocode-repo`: router `jev`, Qwen3-4B, hybrid extractor, 2 workers, 2 generation candidates, pre-step gọi Jev mới trên 200 câu có nhãn theo split dev/tune/test, sau đó suite sample/dev/test. Kernel `midzid/sudocode-eval-b` đã gắn secret từ trước; người dùng cập nhật input và chọn Save & Run All để giữ secret vì `kernels push` qua CLI từng làm mất liên kết. Log và `machine.json` xác nhận `TYPESAFE_API_KEY` được nạp. Output: `runs/kaggle/eval-b/out/eval-b/`.
- CPU job hoàn tất mã 0, output đã kéo về `runs/kaggle/extractor-metrics-28/`. GPU job đối chứng hoàn tất mã 0, output ở `runs/kaggle/extract-latency-28/`; job Jev hoàn tất mã 0, output ở `runs/kaggle/eval-b/out/eval-b/`. Job kiểm ba sửa lỗi hybrid hoàn tất mã 0, output ở `runs/kaggle/extractor-fix-28/`.

## Mốc so sánh cũ

Trace `runs/kaggle/eval-b-hyb5/out/eval-b/test/full.jsonl`: 129 lượt, Qwen3-4B, Jev router, hybrid extractor, 2 suite workers, 2 generation candidates. `scripts/latency_report.py` cho reply-ready p50/p95 = 4.638/8.155 s; post p50/p95 = 8.067/12.996 s; end-to-end **ước tính** p50/p95 = 12.788/19.727 s vì cả 129 lượt chưa có `end_to_end_ms`. Mốc này khác router và `QUESTION_CLF` với GPU job mới, nên không dùng để khẳng định cải thiện tốc độ theo quan hệ nhân quả.

## Kiểm tra trước khi đẩy

- `venv/Scripts/python.exe -X utf8 tests/llm_extract_check.py`, `tests/extractor_quality_check.py`, `tests/question_detection_check.py`, `tests/coverage_check.py`: qua.
- `venv/Scripts/python.exe -X utf8 -m py_compile harness/extractor.py harness/llm_extract.py harness/agent.py scripts/extract_eval.py scripts/latency_report.py`: qua.
- `scripts/extract_eval.py --modes rules`: dev agent 120 câu, khách 60 câu; questions 15/0/0, claims 52/0/0, customer slots 40/0/0, facts_used 14/0/0 TP/FP/FN. Đây là bộ dev/regression đã được sử dụng để sửa code, không phải holdout mới.
- `scripts/customer_gate_report.py`: gate bỏ 12/60 lời gọi LLM (60 → 48), không mất gold slot ngoài rules trong tập 60 câu này. Chưa đo chênh lệch chất lượng hybrid trước/sau gate trên một lần chạy cặp độc lập.
- Không thêm rule khi điểm dev đang đạt trần; tránh mở rộng regex theo test.

## Thay đổi phục vụ đo lường

- `scripts/latency_report.py`: nêu số lượt end-to-end đo thật và số lượt chỉ ước tính.
- `scripts/customer_gate_report.py`: xuất số lời gọi LLM dự kiến tiết kiệm và kiểm gold-slot gate.
- `scripts/evaluate_question_detection.py`: hỗ trợ split rõ ràng và scoring checkpoint lịch sử không gọi API.
- `docs/question_detection_splits_2026-10-27.json` và `kaggle/ref/jev_question_predictions_2026-10-27.jsonl`: chỉ chứa ID/split và xác suất Jev + hash câu từ lần Kaggle trước; không có nội dung câu hoặc khóa.

## Tiêu chí kiểm tra

Đã kéo output, kiểm `suite.json`, `extract_eval.json`, `question_detection_report.json`, trace JSONL và schema; báo riêng TP/FP/FN, P/R/F1, p50/p95 response-ready/post/end-to-end/từng post-part; xác minh `end_to_end_ms >= total_ms`, `post_ms >= 0`, không có lỗi LLM. Giữ `QUESTION_CLF=0` mặc định vì Jev trên test 40 câu vẫn chỉ R=80%, thấp hơn mốc **nội bộ** 85% để xem xét bật Jev; đề thi không yêu cầu ngưỡng recall này.

## Kết quả CPU Kaggle

Nguồn: `runs/kaggle/extractor-metrics-28/out/extractor-metrics-28/`. Log kernel ghi mã thoát 0 sau 126 giây.

| Tập | Phương pháp | TP/FP/FN | P | R | F1 |
| --- | --- | ---: | ---: | ---: | ---: |
| Tune 40 câu | Rules | 12/0/3 | 100% | 80% | 88,9% |
| Tune 40 câu | Jev + rules (cache cũ) | 15/0/0 | 100% | 100% | 100% |
| Test 40 câu | Rules | 10/0/5 | 100% | 66,7% | 80% |
| Test 40 câu | Jev + rules (cache cũ) | 12/0/3 | 100% | 80% | 88,9% |

Jev chỉ có checkpoint trên tune/test, nên hàng `dev` của báo cáo Jev có `n=0`; **không** diễn giải thành P/R/F1 bằng 0. Có 80/80 dự đoán cache hợp lệ, 0 lỗi, p50/p95 latency API lịch sử 219/275 ms. Đây là kết quả trên split đã dùng để chọn ngưỡng 0,75, không phải holdout mới. `question_detection_report.json` ghi `prediction_source=historical_cache`, `new_jev_calls=0`.

Rules dev trên Kaggle: questions 15/0/0, claims 52/0/0, customer slots 40/0/0, facts_used 14/0/0 TP/FP/FN. Gate 60 → 48 lời gọi dự kiến, tiết kiệm 12, không mất slot gold trong kiểm tra này.

## Kết quả GPU đối chứng và sửa lỗi hybrid

`extract-latency-28` (router rules, Qwen generator, hybrid extractor) hoàn tất 5.987 giây, `failed=false`, smoke rc=0, 0 lỗi LLM ở cả 435 lượt full và 435 lượt baseline. Test full: TSR 95,5%, CCR 63,2%, RQR 16,7%, HR giá 0%, 0 vi phạm guardrail. Mốc cũ `hyb5` dùng Jev router và `QUESTION_CLF=1`, vì thế không thể coi chênh lệch latency là tốc độ cải thiện do code mới.

Trên 129 lượt test full, p50/p95 (s): reply-ready 4,361/7,789; post 7,642/12,210; end-to-end đo thật 12,003/19,181. Post-part p50/p95: agent extraction wall 7,589/12,107; customer slot wait (106 lượt) 0/2,733; memory write 0,035/0,083; turn log 0,012/0,014. 435/435 lượt full sample/dev/test có `end_to_end_ms`; validate schema thành công, 0 lượt `end_to_end_ms < total_ms` hoặc `post_ms < 0`. Trace cũ 129/129 lượt vẫn parse được, `end_to_end` của nó là ước tính.

Extractor dev của GPU đối chứng: rules questions 15/0/0, claims 52/0/0, customer 40/0/0, facts_used 14/0/0; hybrid questions 15/0/0 (slot accuracy 93,3%), claims 52/1/0, customer 40/1/0, facts_used 14/0/0. Xem lỗi hybrid: A101 `promo_active=true` trên câu “chưa có thông tin giảm thêm”, A109 gán `product_advised` cho lời đề nghị tư vấn, C008 gán COD từ câu chỉ nói số điện thoại. Ba lỗi được sửa theo cue hẹp ở `harness/llm_extract.py` và có ca hồi quy trong `tests/llm_extract_check.py`; focused checks qua. Đã chạy `midzid/sudocode-extractor-fix-28` trên Kaggle để kiểm code sau sửa. Kết quả `eval-b` được tạo từ bản trước ba sửa này, nên không được gộp với số liệu của bản sửa.

`extractor-fix-28` đã hoàn tất trên Kaggle: smoke rc=0, `extract_eval` rc=0, sample full 39 lượt/0 lỗi LLM, TSR 85,7%, CCR 61,9%, RQR 0%, 0 vi phạm. Hybrid dev sau sửa: questions 15/0/0, claims 52/0/0, customer 40/0/0, facts_used 14/0/0 TP/FP/FN; question slot accuracy 100%. So với trước sửa: claim FP 1→0, customer FP 1→0, sai slot câu hỏi 1→0. 39/39 trace sample qua schema và kiểm latency. Đây là cải thiện trên bộ dev đã biết, chưa có xác nhận held-out cho ba sửa này.

## Kết quả Jev API mới trên Kaggle

`eval-b` nạp `TYPESAFE_API_KEY` theo `machine.json`, cấu hình từ dataset mới theo kernel log. Pre-step `evaluate_question_detection.py` gọi Jev mới 200/200 câu, 0 lỗi, không train model; xác suất phản hồi p50/p95 118/173 ms. Điểm tách theo split cũ:

| Split | Phương pháp | TP/FP/FN | Precision | Recall | F1 |
| --- | --- | ---: | ---: | ---: | ---: |
| Dev 120 | Rules | 31/1/15 | 96,9% | 67,4% | 79,5% |
| Dev 120 | Jev + rules | 41/2/5 | 95,3% | 89,1% | 92,1% |
| Tune 40 | Rules | 12/0/3 | 100% | 80% | 88,9% |
| Tune 40 | Jev + rules | 15/1/0 | 93,8% | 100% | 96,8% |
| Test 40 | Rules | 10/0/5 | 100% | 66,7% | 80% |
| Test 40 | Jev + rules | 12/0/3 | 100% | 80% | 88,9% |

Tổng 200 câu Jev + rules: TP/FP/FN 68/3/8, P=95,8%, R=89,5%, F1=92,5%. Test 40 câu không đạt mốc **nội bộ** R≥85% trong hướng dẫn thực thi; không bật `QUESTION_CLF` mặc định. Đề thi không đặt mốc này. Bộ 200 câu và ngưỡng 0,75 đã từng được dùng trong thử nghiệm trước; kết quả này là lần gọi API mới trên nhãn cũ, không phải holdout độc lập mới.

Suite Jev + Qwen + hybrid chạy sample/dev/test full và baseline, smoke rc=0, `failed=false`, 0 lỗi LLM. Full test 129 lượt: TSR 95,5%, TSR khó 94,7%, CCR 68,4%, RQR 11,1%, HR giá 0%, guardrail 0. Test reply-ready p50/p95 4,278/7,443 s; post 7,070/11,847 s; end-to-end **đo thật** 11,474/17,819 s. Post-part p50/p95: agent extraction wall 7,016/11,798 s; customer slot wait (102 lượt) 0/3,383 s; memory write 0,032/0,076 s; turn log 0,011/0,013 s. 435/435 full trace qua schema, đủ `end_to_end_ms`, 0 giá trị âm hoặc nhỏ hơn reply-ready. Độ trễ post chủ yếu ở agent extraction, không phải router Jev (router p95 0,329 s) hay ghi memory.

So với `hyb5` lịch sử, p95 reply-ready 8,155→7,443 s và end-to-end ước tính 19,727→đo thật 17,819 s, nhưng hai lần chạy khác code, `QUESTION_CLF`, trạng thái máy/cache và phương pháp đo end-to-end. Đây là chênh lệch quan sát, **chưa chứng minh cải thiện tốc độ do thay đổi extractor**. Cần chạy cặp trước/sau trong cùng điều kiện nếu muốn kết luận nhân quả; cũng chưa có ablation gọi LLM với gate bật/tắt trên cùng workload để đo chất lượng và số request thực tế.

## Lệnh kiểm chứng và file thay đổi

- Kaggle: `scripts/kaggle_job.py push` cho `extract-latency-28`, `extractor-metrics-28`, `extractor-fix-28`; `push --job eval-b --dataset-only` rồi Save & Run All trên notebook gắn secret. Tất cả bằng credential `midzid.json`, không chép khóa vào repo. Xem `out/job.json`, `out/eval-b/suite.json`, `out/extractor-fix-28/suite.json` để lấy tham số chính xác.
- Local focused checks: `venv/Scripts/python.exe -X utf8 tests/llm_extract_check.py`, `tests/extractor_quality_check.py`, `tests/question_detection_check.py`, `tests/coverage_check.py`, `-m py_compile` các module sửa. Kaggle smoke suite rc=0 cho cả ba job GPU.
- Trace: `venv/Scripts/python.exe -X utf8 scripts/latency_report.py <full.jsonl>` và `scripts/validate_trace_latency.py <sample/full.jsonl> <dev/full.jsonl> <test/full.jsonl>`.
- File sửa/thêm: `harness/llm_extract.py`, `tests/llm_extract_check.py`, `scripts/latency_report.py`, `scripts/evaluate_question_detection.py`, `scripts/customer_gate_report.py`, `scripts/validate_trace_latency.py`, `docs/question_detection_splits_2026-10-27.json`, `kaggle/ref/jev_question_predictions_2026-10-27.jsonl`, nhật ký này. Không có fine-tune hoặc model artifact.
