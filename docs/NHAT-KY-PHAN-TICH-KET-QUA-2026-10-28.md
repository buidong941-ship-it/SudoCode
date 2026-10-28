# Nhật ký phân tích kết quả Kaggle — 28/10/2026

## 1. Phạm vi và nguồn số liệu

Hôm nay chạy bốn kernel trên Kaggle tài khoản `midzid` để thực hiện `PLAN_EXTRACTOR_METRIC_LATENCY.md`. Tất cả dùng code trong dataset riêng `midzid/sudocode-repo`; không huấn luyện hoặc fine-tune model. Kết quả chi tiết và lệnh chạy được lưu tại `NHAT-KY-EXTRACTOR-LATENCY-2026-10-28.md`.

| Kernel | Vai trò | Cấu hình chính | Output |
| --- | --- | --- | --- |
| `sudocode-extractor-metrics-28` | Chấm rules và xác suất Jev lịch sử | CPU, checkpoint Jev 27/10, không gọi API mới | `runs/kaggle/extractor-metrics-28/out/extractor-metrics-28/` |
| `sudocode-extract-latency-28` | Đối chứng hội thoại và latency | Router rules, Qwen3-4B, hybrid, 2 suite workers, 2 generation candidates | `runs/kaggle/extract-latency-28/out/extract-latency-28/` |
| `sudocode-eval-b` | Jev mới + hội thoại đầy đủ | Router Jev, Qwen3-4B, hybrid, cùng số workers/candidates, `QUESTION_CLF=0` | `runs/kaggle/eval-b/out/eval-b/` |
| `sudocode-extractor-fix-28` | Kiểm ba sửa lỗi hybrid | Router rules, Qwen3-4B, hybrid, sample + extractor dev | `runs/kaggle/extractor-fix-28/out/extractor-fix-28/` |

Hai job hội thoại đầy đủ dùng sample 39, dev 267 và test 129 lượt ở mỗi cấu hình `full` và `baseline_no_memory`. `eval-b` đã nạp Kaggle Secret `TYPESAFE_API_KEY`; benchmark gọi Jev mới 200/200 câu, không lỗi. Cả ba suite GPU có `failed=false`, smoke rc=0, 0 lỗi LLM. Job `extractor-fix-28` chỉ chạy sample hội thoại, nên không có metric hội thoại dev/test sau ba sửa mới nhất.

## 2. Chất lượng phát hiện câu hỏi bằng Jev

`P/R/F1` trong bảng dưới là precision/recall/F1 của nhãn *câu hỏi trong lời agent*, không phải metric hội thoại RQR. Chấm ở ngưỡng Jev 0,75, hợp Jev với rules theo phép OR. TP/FP/FN là số câu.

| Split | Rules TP/FP/FN | Rules P/R/F1 | Jev + rules TP/FP/FN | Jev + rules P/R/F1 |
| --- | ---: | ---: | ---: | ---: |
| Dev, 120 câu | 31/1/15 | 96,9/67,4/79,5% | 41/2/5 | 95,3/89,1/92,1% |
| Tune, 40 câu | 12/0/3 | 100/80/88,9% | 15/1/0 | 93,8/100/96,8% |
| Test, 40 câu | 10/0/5 | 100/66,7/80% | 12/0/3 | 100/80/88,9% |

Trên cả 200 câu, Jev + rules đạt TP/FP/FN **68/3/8**, P **95,8%**, R **89,5%**, F1 **92,5%**; Jev API p50/p95 **118/173 ms**. Jev cải thiện recall so với rules trên cả ba split, nhưng test còn **3 false negative trong 15 câu dương**, nên recall test **80%**. Mốc 85% là **tiêu chí nội bộ để xem xét bật Jev** ở Nhiệm vụ 6 của `HUONG-DAN-THUC-THI-2026-10-25.md`, không phải yêu cầu của đề thi. Chưa bật `QUESTION_CLF` mặc định theo tiêu chí nội bộ này. `QUESTION_CLF` ở đây chỉ ảnh hưởng phép trích `questions[]` sau khi agent đã tạo câu trả lời, khác với Jev router đang dùng trong hội thoại.

Bộ 200 câu đã có nhãn và ngưỡng 0,75 từng được dùng trong thử nghiệm trước. Lần này xác nhận API Jev hiện tại và số liệu theo split cũ; **không phải holdout mới**. Kết quả cache 80 câu từ kernel CPU cho test cũng là P100/R80/F1 88,9%; số này nhất quán với 200 lời gọi mới ở test, nhưng cache không thay thế được phép đo API mới.

## 3. Chất lượng hybrid extractor

Trên bộ dev extractor gồm 120 lời agent, 60 lời khách và 16 ca `facts_used`, bản trước sửa có các lỗi sau:

| Trường | Trước sửa TP/FP/FN | Sau sửa TP/FP/FN | Phân tích |
| --- | ---: | ---: | --- |
| Questions, phát hiện | 15/0/0 | 15/0/0 | Phát hiện câu hỏi giữ nguyên; độ đúng *slot* tăng 93,3% → 100% |
| Claims | 52/1/0 | 52/0/0 | Bỏ FP `promo_active=true` khi agent nói chưa có thông tin giảm thêm |
| Customer slots | 40/1/0 | 40/0/0 | Bỏ FP `payment=COD` từ câu khách chỉ nêu số điện thoại |
| `facts_used` | 14/0/0 | 14/0/0 | Không đổi; đây là bộ hồi quy nhỏ, tự soạn |

Lỗi slot câu hỏi còn lại là agent đề nghị “Em có thể tư vấn thêm ... không ạ?” nhưng LLM gán `product_advised`; bộ sửa giữ nhãn `other`. Mỗi lỗi đã có ca hồi quy trong `tests/llm_extract_check.py`. `extractor-fix-28` chạy lại smoke và `extract_eval` trên Kaggle: hybrid dev hết ba lỗi, 0 lỗi LLM, sample TSR 85,7% và 0 vi phạm guardrail. Đây là **cải thiện trên dev đã biết**; chưa chứng minh tổng quát hóa lên câu mới. `eval-b` hoàn tất bằng snapshot trước ba sửa này, nên không gán metric hội thoại test của `eval-b` cho bản sửa mới.

Gate customer-slot bỏ qua dự kiến **12/60 lời gọi LLM** (20%) ở bộ dev khi không có tín hiệu slot và không làm mất slot gold mà rules chưa có. Đây là kiểm coverage/call-count theo code; chưa có phép chạy cặp gate bật/tắt cùng workload để đo số request thực tế và metric đầu cuối.

## 4. Metric hội thoại

Bảng dùng hệ thống `full`, không lấy số baseline làm số của hệ thống. `extract-latency-28` khác `eval-b` ở router (rules/Jev), nên chênh lệch chỉ là quan sát giữa hai phiên chạy.

| Metric | Rules router: sample/dev/test | Jev router: sample/dev/test | Nhận xét |
| --- | ---: | ---: | --- |
| TSR | 85,7 / 100 / 95,5% | 85,7 / 100 / 95,5% | Thành công tác vụ bằng nhau trong ba split |
| CCR | 61,9 / 74,3 / 63,2% | 71,4 / 76,1 / 68,4% | Jev cao hơn ở cả ba, test +5,2 điểm phần trăm; chưa là chứng cứ nhân quả |
| RQR, thấp hơn tốt hơn | 0 / 4,3 / 16,7% | 0 / 3,8 / 11,1% | Jev thấp hơn ở dev/test, nhưng vẫn còn 11,1% test |
| HR giá/khuyến mãi, thấp hơn tốt hơn | 6,7 / 2,9 / 0% | 7,1 / 2,1 / 0% | Test đều 0%; sample/dev dao động nhỏ |
| Vi phạm guardrail | 0 / 0 / 0 | 0 / 0 / 0 | Không phát hiện vi phạm trong các run này |

Test TSR ca khó đều **94,7%**. Baseline `baseline_no_memory` test TSR **81,8%** ở cả hai suite; hệ thống cao hơn **13,7 điểm phần trăm**. Test CCR baseline 5,3% so với hệ thống rules 63,2% và Jev 68,4%. RQR baseline test bằng 0 trong cả hai suite, nên không tính phần trăm “giảm RQR” tại test; hệ thống test vẫn có RQR dương.

## 5. Độ trễ và nút thắt

Các con số dưới đây là p50/p95 theo **129 lượt test full**, đơn vị giây. `total_ms` là lúc lời đáp sẵn sàng; `post_ms` là xử lý sau đó; `end_to_end_ms` là khi toàn bộ lượt hoàn tất. Percentile của từng phần không cộng trực tiếp với nhau.

| Thành phần | Rules router p50/p95 | Jev router p50/p95 |
| --- | ---: | ---: |
| Reply-ready | 4,361 / 7,789 | 4,278 / 7,443 |
| Post-processing | 7,642 / 12,210 | 7,070 / 11,847 |
| End-to-end, đo thật | 12,003 / 19,181 | 11,474 / 17,819 |
| Agent extraction wall | 7,589 / 12,107 | 7,016 / 11,798 |
| Customer-slot wait | 0 / 2,733 (106 lượt) | 0 / 3,383 (102 lượt) |
| Memory write | 0,035 / 0,083 | 0,032 / 0,076 |
| Turn log | 0,012 / 0,014 | 0,011 / 0,013 |

**Nút thắt đo được là agent extraction sau khi câu trả lời sẵn sàng.** Trong run Jev, p95 `agent_extraction_wall_ms` 11,798 s gần p95 post 11,847 s; router Jev p95 chỉ 0,329 s. Customer extraction đã được khởi chạy sớm và có overlap; vẫn có 102 lượt ghi `customer_slot_wait_ms`, p95 3,383 s trên các lượt đó. Việc hai bước chồng thời gian đã được xác nhận bằng code và post timing, nhưng bảng percentile chưa cho phép quy toàn bộ latency từng lượt cho một thành phần duy nhất.

Trace `hyb5` cũ có test reply-ready p95 8,155 s và end-to-end **ước tính** p95 19,727 s từ `total_ms + post_ms`. Hai run mới ghi `end_to_end_ms` đo thật cho **435/435 lượt full** mỗi suite. Schema trace qua kiểm tra; 0 lượt end-to-end nhỏ hơn reply-ready hoặc post âm. So sánh p95 cũ 19,727 s với Jev mới 17,819 s chỉ là chênh lệch quan sát: code, `QUESTION_CLF`, cache/môi trường và cách đo end-to-end khác nhau. **Chưa đủ bằng chứng để tuyên bố đã tăng tốc độ do sửa extractor.**

## 6. Quyết định và việc còn lại

1. Giữ `QUESTION_CLF=0` theo quyết định kỹ thuật hiện tại: recall Jev + rules trên test 40 câu mới gọi lại là 80%, chưa đạt mốc nội bộ 85% trong hướng dẫn thực thi. Đề thi không đặt mốc recall này. Không chỉnh ngưỡng theo test.
2. Giữ ba bộ lọc hybrid vừa sửa cùng regression tests. Cần đánh giá trên nhãn/câu mới trước khi coi mức dev 100% là chất lượng tổng quát.
3. Muốn kết luận tác động latency của gate hoặc agent extraction: chạy cặp trước/sau với cùng scenario, model, router, worker, candidate count, môi trường và cache; báo cả metric lẫn request count. Ưu tiên điều tra vì post p95 vẫn gần 12 s.
4. Muốn xác nhận metric hội thoại sau ba sửa: chạy lại suite Jev + Qwen trên snapshot code mới nhất. Run Jev hôm nay dùng snapshot trước sửa; không tái sử dụng số đó như kết quả sau sửa.
5. Giữ nguyên cấm fine-tune/training theo đề thi. Toàn bộ thay đổi hôm nay là luật kiểm chứng, phép đo và dùng model có sẵn.

Nguồn trực tiếp: `runs/kaggle/eval-b/out/eval-b/{summary.md,suite.json,question-detection-current/question_detection_report.json,test/full.jsonl}`, `runs/kaggle/extract-latency-28/out/extract-latency-28/{summary.md,extract_eval.json,test/full.jsonl}`, `runs/kaggle/extractor-fix-28/out/extractor-fix-28/{summary.md,extract_eval.json}`. Lệnh và các trường cấu hình đầy đủ nằm trong `NHAT-KY-EXTRACTOR-LATENCY-2026-10-28.md` và `out/job.json` của từng kernel.
