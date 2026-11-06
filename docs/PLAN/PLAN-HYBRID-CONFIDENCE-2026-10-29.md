# Kế hoạch 29/10/2026: dữ liệu mới và cổng confidence cho bộ trích hybrid

## Mục tiêu và trạng thái

Đề xuất của người dùng: luật chạy trước vì nhanh; nếu kết quả đủ tin cậy thì dùng ngay, còn không thì gọi Jev để phân loại slot lời khách, câu hỏi và claim lời agent. Chỉ dùng Qwen khi Jev phát hiện thông tin nhưng code không thể xác định đoạn chữ gốc (`span`) hoặc gán giá trị an toàn. Đây là **thiết kế thử nghiệm**, chưa phải kết quả đã chạy hay cấu hình mặc định. Không huấn luyện/fine-tune model.

Bộ nhãn hiện có `tests/extract_eval/agent.jsonl` (120 câu) và `customer.jsonl` (60 câu) lấy từ trace/dev cũ; `test_set/public_sample/` là sample BTC, còn `datagen/out_nat/{dev,test}` là synthetic nhóm đã tạo và đã dùng nhiều lần. **Nhiệm vụ dữ liệu ở plan này là tạo thêm một bộ sample mới theo phong cách BTC, độc lập với cả hai nguồn trên**, rồi chạy full agent để đo metric và latency. Không tái đóng gói/sửa vài từ trong 67 synthetic cũ rồi gọi đó là test mới.

## 1. Tạo benchmark **hội thoại đa phiên như bài thi**

**Benchmark chính là toàn hệ thống trên bộ sample kiểu BTC mới, không phải bộ câu extractor đứng riêng.** Tạo một gói dữ liệu **bổ sung** riêng theo `schemas/scenario_format.md`, không trộn với `test_set/public_sample/` hoặc `datagen/out_nat/`. Trong gói mới, tách suite phát triển để sửa cổng và suite holdout chỉ mở sau khi khóa thiết kế. Ưu tiên để **holdout có khoảng 40 kịch bản, ít nhất 100 lượt khách và nhiều ca khó**, gần quy mô 41 kịch bản/19 ca khó và yêu cầu đo latency ≥100 lượt mà BTC mô tả; suite phát triển cần đủ các họ lỗi để sửa nhưng không được lấy câu từ holdout. Nếu nguồn lực không đủ, báo quy mô thực tế và không gọi đây là phép đo có độ ổn định tương đương bộ ẩn.

### 1.1. File sinh riêng và tái sử dụng resolver hiện có

- Tạo **một entry point mới** `datagen/generate_btc_like_benchmark.py` và **thư mục template mới** `datagen/templates_btc_like/`. File mới chỉ nạp template ở thư mục mới; không gọi `resolver.main()` với `datagen/templates/` hoặc sinh thêm instance từ 27 template cũ. **Viết thêm template mới là bước chủ động của nhiệm vụ này**: lập bảng các họ ca cần đo, tạo đủ template mới cho từng họ; nếu sau khi sinh còn thiếu kênh, số lượt, ca khó hoặc câu hỏi/claim quan trọng thì bổ sung template khác trước khi khóa benchmark. Mỗi template mới mô tả diễn biến, lời khách và assertion mới; có thể dùng cùng cú pháp `choose`, `dates`, `let`, `require`, `scenario` mà resolver đang hiểu. Không cần chép mã chọn khách/sản phẩm và tính giá sang file mới.
- Trong file mới, import `Resolver`, `load_templates` từ `datagen/resolver.py`; gọi `Resolver.build(template, instance, split, scenario_id=...)` cho từng template. Việc tìm khách, SKU, ngày, khuyến mãi, tồn kho, ETA, địa chỉ và render các trường kỳ vọng vẫn đi qua `Resolver` và `eval/mock_tools.py`. Dùng tiền tố ID riêng, ví dụ `BTCL-001`, để trace/manifest không lẫn `GEN-*` của bộ cũ. Chỉ thay `resolver.py` nếu gặp khả năng thật sự thiếu; mọi thay đổi khi đó phải giữ CLI và đầu ra cũ tương thích.
- Template mới khai báo split `dev` hoặc `holdout` theo **template/họ tình huống**, với ít nhất hai template có lời thoại và diễn biến khác nhau cho mỗi họ quan trọng. Không dùng nhánh `plan_splits()` chia **instance của cùng một template** sang hai phía: cách đó để lộ cấu trúc và câu mẫu. File sinh mới kiểm tra trùng `scenario_id`, khách/SĐT giữa hai split, câu thoại giống hệt, và báo lỗi nếu `Resolver.build` không tìm được ràng buộc; không âm thầm bỏ ca thất bại để vẫn đạt quota.
- Đầu ra cố định: `datagen/out_btc_like_new/raw/{dev,holdout}/*.json` và `datagen/out_btc_like_new/manifest.json`. Manifest ghi seed, phiên bản generator, template nguồn, split, số call/lượt khách, nguồn dữ kiện BTC, SHA-256 từng scenario, số ca sinh thất bại và bảng coverage. **Chỉ** file mới ghi vào nhánh `out_btc_like_new`; các lệnh mặc định của `resolver.py`, `naturalize.py` và bộ `out/`, `out_nat/` cũ giữ nguyên.
- Nếu cần lời khách tự nhiên hơn, dùng tiếp `datagen/naturalize.py` với `--src datagen/out_btc_like_new/raw --out datagen/out_btc_like_new/final --splits dev holdout`; cache `rewrites.json` nằm trong nhánh mới. Rà lại từng câu viết lại, chạy validator trên **bộ final thực sự đưa vào agent**, rồi cho file sinh mới chạy chế độ `--freeze final` để ghi hash của bản final vào manifest. Không dùng bản viết lại nếu làm mất dữ kiện, đổi ý định hoặc khiến assertion không còn đúng. Nếu không chạy naturalize, dùng `raw` làm bộ đánh giá và `--freeze raw`.

Ví dụ lệnh sau khi viết file mới (tên cờ là giao diện cần hiện thực):

```bash
python datagen/generate_btc_like_benchmark.py --templates datagen/templates_btc_like --seed 20261030 --out datagen/out_btc_like_new
python datagen/validate.py datagen/out_btc_like_new/raw/dev datagen/out_btc_like_new/raw/holdout --strict --report datagen/out_btc_like_new/validate_raw.json
python datagen/naturalize.py --src datagen/out_btc_like_new/raw --out datagen/out_btc_like_new/final --splits dev holdout
python datagen/validate.py datagen/out_btc_like_new/final/dev datagen/out_btc_like_new/final/holdout --strict --report datagen/out_btc_like_new/validate_final.json
python datagen/generate_btc_like_benchmark.py --out datagen/out_btc_like_new --freeze final
```

`naturalize.py` là bước tùy chọn có API; sinh kịch bản bằng resolver và kiểm dữ kiện bằng validator chạy độc lập được. Đóng băng hash của bản dùng để chấm trước khi chạy agent; sửa câu hoặc assertion sau đó phải tạo phiên bản benchmark mới.

1. Dùng `catalog/crm_seed.json` làm **trạng thái ban đầu**, không sửa file BTC. Có thể viết cuộc gọi mới cho khách sẵn có, tạo khách tổng hợp mà CRM chưa biết (đường `datagen/resolver.py` đã hỗ trợ), hoặc khai báo `seed_history` trong **kịch bản riêng** để thử lịch sử cũ. Giữ danh tính, đơn hàng và lịch sử đã có nhất quán; không trình bày lịch sử tự sinh là dữ liệu BTC phát.
2. Dùng **7 file `test_set/public_sample/` và `schemas/scenario_format.md` làm mẫu về cấu trúc và cách đặt assertion**, không dùng làm template để đổi tên/số tiền. Tạo tình huống/câu thoại mới thuộc cùng **họ năng lực** của đề: khách quay lại, đổi ý, nhiều sản phẩm, KM hết hạn/có điều kiện, tồn kho theo ngày, đơn hàng, shared phone, ASR/teencode, PII, hỏi chính sách ngoài tài liệu. Có đủ hotline/chat, khách mới/khách quay lại, câu ngắn cần ngữ cảnh, câu hỏi không dấu `?` và nhiều thông tin trong một lượt. Rà độ trùng ý/câu với cả sample BTC và `datagen/out_nat/`; loại ca chỉ diễn đạt lại tình huống cũ.
3. Mọi giá, KM, tồn kho, ETA, chính sách và expected tool result phải lấy từ `catalog/`, `policy/`, `eval/mock_tools.py` tại đúng `call_date`; không tự đặt sự thật nghiệp vụ. Mỗi call khai báo `facts_established`, `must_carry_over`, `must_not_ask`, `success_if`, `ground_truth_facts`, `memory_expectation` khi phù hợp. Chạy `datagen/validate.py` và rà thủ công các ca có đáp án/tool bất nhất trước khi đánh giá agent.
4. Tách **theo họ kịch bản/khách**, không tách lượt từ cùng một cuộc vào hai suite. Dùng đúng cây thư mục và manifest ở mục 1.1; ghi rõ đây là **sample mô phỏng do nhóm tự tạo, không phải sample/hidden test chính thức của BTC**. Không chỉnh suite holdout sau khi nhìn kết quả. Dữ liệu đầu vào cho full và baseline phải giống hệt nhau; chỉ khác việc nạp bộ nhớ như định nghĩa của bài.
5. Bộ câu có nhãn extractor chỉ là **phụ trợ**: lấy mẫu từ hội thoại mới để giải thích lỗi `CERT=1` nhưng trích sai, Jev gán sai slot hoặc claim bị bỏ sót. Không bắt buộc tạo 300+300 câu rời rồi dùng F1 riêng đó thay cho kết quả hội thoại.

## 2. Định nghĩa confidence của luật

`confidence` không phải số tùy ý gán cho regex khớp mạnh. Một kết quả luật chỉ được nhận ngay nếu đồng thời có bằng chứng rằng **nhãn/giá trị đã xuất ra đúng** và **không bỏ sót nhãn cần xuất ra**. Câu chỉ bắt được một trong hai slot không đạt, dù slot đầu đúng. Kết quả rỗng cũng phải có bằng chứng là câu thực sự không chứa slot/câu hỏi/claim; không có regex khớp **không phải** bằng chứng đó.

Luật trả kèm tín hiệu kiểm được: span nằm trong đúng câu, giá trị parse được, từ khóa nằm gần giá trị, phủ định/trích dẫn, nhiều con số hoặc nhiều sản phẩm, câu đáp ngắn thiếu ngữ cảnh, và dấu hiệu thông tin chưa được luật xử lý. Từ dữ liệu calibration, tính tỷ lệ **đúng toàn bộ tập nhãn của câu** theo từng nhóm tín hiệu và một cận trên rủi ro sai có khoảng tin cậy; nhóm ít mẫu hoặc chưa thấy cách nói tương ứng luôn chuyển Jev. Có ngưỡng riêng cho slot khách, câu hỏi, claim; các claim giá/khuyến mãi/tự nhận là người thật phải kiểm chặt hơn. Chọn ngưỡng để tăng tỷ lệ dùng luật **trong ràng buộc chất lượng đã ghi trước**, không chỉnh theo holdout.

### 2.1. Công thức **chạy trực tiếp trong production**

Đầu vào của công thức chỉ gồm câu hiện tại `x`, ngữ cảnh được phép dùng `c`, kết quả luật `R_t(x,c)` và các phép kiểm code. **Không có nhãn người rà hoặc đáp án chuẩn trong đường chạy.** Tách câu agent thành các câu/đoạn; nếu một đoạn không được xác nhận an toàn thì chỉ gửi các đoạn chưa chắc sang Jev, có thể gom thành một request. `t` là một trong `customer_slots`, `agent_questions`, `agent_claims`.

Với mỗi đoạn `s`, tính sáu biến nhị phân từ dữ liệu có ngay lúc chạy:

| Biến | Bằng 1 khi |
| --- | --- |
| `G_t(s)` — grounding | Mọi span của kết quả luật nằm nguyên trong đúng đoạn nguồn. |
| `P_t(s)` — parse | Mọi giá trị được code parse hợp lệ từ span; không phải giá trị LLM/regex suy đoán. |
| `U_t(s)` — liên kết duy nhất | Mỗi nhãn gắn được với **một** giá trị và đối tượng/sản phẩm rõ ràng; nhiều số hoặc nhiều sản phẩm không gán được vai trò thì bằng 0. |
| `N_t(s)` — ngữ nghĩa an toàn | Không có phủ định, câu trích dẫn, giả định, câu hỏi về một claim, hoặc cách nói có thể đảo nghĩa mà luật chưa xử lý. |
| `K_t(s)` — phủ tín hiệu | Một bộ phát hiện tín hiệu ứng viên **tách khỏi output của rules** quét dấu hỏi, lời yêu cầu, từ khóa slot/claim và các con số; mọi tín hiệu ứng viên tìm thấy đều được kết quả luật giải thích. Có tín hiệu chưa được giải thích thì bằng 0. |
| `C_t(s,c)` — ngữ cảnh đủ | Không phải câu đáp ngắn hoặc cách nói cần câu trước để hiểu slot; với claim, biết rõ sản phẩm đang được nói tới. |

```text
CERT_t(s,c) = 1{R_t(s,c) không rỗng}
              × G_t(s) P_t(s) U_t(s) N_t(s) K_t(s) C_t(s,c)

ROUTE_t(s,c) = rules                 nếu CERT_t(s,c) = 1
             = Jev                   nếu CERT_t(s,c) = 0 và Jev đã được kiểm chứng cho t
             = hybrid hiện hành      nếu Jev chưa được kiểm chứng cho t

Kết quả toàn câu = gộp kết quả của mọi đoạn s sau khi từng đoạn đi đúng tuyến;
không chấp nhận cả câu chỉ vì một đoạn có chứng chỉ.
```

Đây là **chứng chỉ bằng điều kiện**, không phải xác suất đúng. Không đặt các trọng số kiểu `0,8` cho regex rồi gọi đó là confidence. Nếu `R_t` rỗng, đoạn không có tín hiệu, có câu yêu cầu không dấu `?`, hoặc có bất kỳ biến nào bằng 0 thì chuyển bước tiếp theo. Bộ tín hiệu `K_t` chỉ là lưới phát hiện *bất đồng rõ ràng*; nó có thể cùng bỏ sót một cách nói lạ như rules, nên `CERT=1` **không bảo đảm** đã bắt mọi nhãn. Với câu hỏi, không dùng `agent_questions()` làm cổng duy nhất trước Jev; các câu ngoài nhóm được chứng nhận phải tới Jev để tránh lặp lại lỗi sáu câu yêu cầu từng bị bỏ sót.

Các claim giá, khuyến mãi và `is_human` ban đầu đặt `CERT_agent_claims=0`, luôn chuyển bước tiếp theo vì một claim gán sai có thể làm HR tăng. Nếu Jev chưa được kiểm chứng cho claim/slot khách, “bước tiếp theo” vẫn là hybrid Qwen hiện hành. Khi Jev đã được kiểm chứng, code kiểm span, giá trị, phủ định và sản phẩm từ nhãn Jev; chỉ gọi Qwen nếu code không thể gán span/giá trị an toàn. Một nhãn Jev không có span chứng thực không tự trở thành claim trong trace.

Ví dụ: “Phòng 25m², ngân sách khoảng 5 triệu” chỉ được nhận bằng rules nếu **cả hai** tín hiệu diện tích và tiền được giải thích, hai giá trị parse đúng và không có phần mơ hồ. Bắt được diện tích nhưng bỏ ngân sách làm `K=0` nên chuyển Jev. “Chị lên địa chỉ giúp em nhé” không có `?` vẫn phải đi Jev nếu rules chưa nhận; output rỗng không được coi là câu chắc chắn không hỏi.

### 2.2. Kiểm chứng công thức production

Nhãn người rà chỉ xuất hiện **ngoài đường chạy** và chỉ để phân tích lỗi trích trên mẫu lấy từ suite hội thoại. Kết luận chính dựa trên metric và latency của **toàn lượt hội thoại**. Chọn điều kiện trên suite phát triển rồi khóa trước khi mở holdout. Không thể suy ra một bảo đảm tỷ lệ sai chỉ từ `CERT`; nếu muốn tuyên bố cận rủi ro thống kê vẫn cần dữ liệu kiểm độc lập có nhãn. Trước khi tích hợp Jev cho slot khách và claim, phải đo riêng Jev trên dữ liệu mới; hiện kết quả đã biết mới kiểm Jev đa nhãn cho câu hỏi.

Cách tổ chức “nhận kết quả khi đủ tin cậy, còn lại chuyển bước mạnh hơn” dựa trên ý tưởng **selective classification** và **cascade** trong [Geifman & El-Yaniv (2017)](https://arxiv.org/abs/1705.08500) và [Chen, Zaharia & Zou (2023)](https://arxiv.org/abs/2305.05176). Sáu điều kiện `G/P/U/N/K/C` là **thiết kế cho repository này**, không phải công thức được hai bài báo chứng minh cho extractor này.

## 3. Đường chạy hybrid đề xuất

```text
câu khách / câu agent
  → luật trích nhãn + giá trị/span + tín hiệu rủi ro
  → confidence đủ cao và đã kiểm tính đầy đủ? → dùng luật
  → chưa đủ → Jev phân loại các nhãn còn nghi vấn
      → code tìm span/giá trị trong chính câu, kiểm phủ định, sản phẩm, số tiền
      → chỉ khi code không gán được span/giá trị an toàn → Qwen dự phòng
      → Qwen vẫn phải trả span có thật; sai/timeout → giữ kết quả an toàn và ghi fallback
```

- **Slot khách:** luật có giá trị ngay; Jev bổ sung slot còn thiếu, luật thắng khi cùng slot. Cần ghi rõ Jev/Qwen đến trước bước lập kế hoạch hay chỉ đến sau lời đáp để cập nhật bộ nhớ. Muốn lượt hiện tại dùng slot mới thì phải chờ trước khi lập kế hoạch và đo phần tăng Total; nếu không chờ thì chỉ cải thiện lượt sau.
- **Câu hỏi lời agent:** Jev hiện đã phân loại từng câu, luật dự phòng khi Jev lỗi. Cổng confidence mới có thể bỏ Jev ở câu luật đã xác định chắc chắn. Không gộp mọi câu không có dấu hỏi thành nhãn `none`; câu yêu cầu thông tin không có dấu `?` phải có trong dữ liệu mới.
- **Claim lời agent:** cho Jev phân loại nhiều nhãn trong một câu, ưu tiên ghép với request Jev phân loại câu hỏi để không thêm request riêng nếu SDK cho phép. Với nhiều giá/số ngày trong một câu, code phải gắn đúng vai trò từng số; Qwen chỉ hỗ trợ trường hợp còn mơ hồ. Luật và Jev không được hợp mù quáng vì claim gán thừa làm HR tăng. `facts_used` vẫn do code đối chiếu lời agent và tham số tool.
- Giữ che PII trước Jev, timeout, fallback theo từng câu, metadata `backend/confidence/reason/request_count/ms`; không thay đổi định dạng trace bắt buộc của bộ chấm.

## 4. Cách chấm và điều kiện bật

Trên **cùng suite phát triển**, chạy `full` và `baseline_no_memory` bằng `run_eval.py`, chấm `eval/reference_eval.py`. So cấu hình hybrid hiện hành, Jev + luật luôn gọi và hybrid có cổng confidence; dùng cùng model sinh lời, router, số worker, số bản trả lời ứng viên, RAG, mock tools và máy. Để tách riêng chi phí extractor khỏi biến động câu Qwen, bổ sung phép **replay cùng lời khách/lời agent cố định** từ trace; replay chỉ phục vụ phân tích, không thay kết quả full agent. Báo rõ khi các lần full sinh lời khác nhau.

Quy trình đo cụ thể: chọn `raw` hoặc `final` theo `manifest.json` đã đóng băng; giữ nguyên cùng đường dẫn scenario và cùng hash qua mọi cấu hình. Trước hết chạy cấu hình **hybrid hiện hành** làm mốc (lệnh dưới dùng `final/dev` làm ví dụ):

```bash
python run_eval.py --scenarios datagen/out_btc_like_new/final/dev --config full --extractor hybrid --out runs/btc_like_new/current_dev_full.jsonl
python run_eval.py --scenarios datagen/out_btc_like_new/final/dev --config baseline_no_memory --extractor hybrid --out runs/btc_like_new/current_dev_baseline.jsonl
python eval/reference_eval.py --scenarios datagen/out_btc_like_new/final/dev --trace runs/btc_like_new/current_dev_full.jsonl --baseline runs/btc_like_new/current_dev_baseline.jsonl --out runs/btc_like_new/current_dev_score.json
python scripts/latency_report.py runs/btc_like_new/current_dev_full.jsonl
```

Sau khi **Jev đã được đo riêng cho slot khách và claim** và các biến thể extractor được hiện thực dưới cờ cấu hình riêng, chạy lại đúng bốn bước trên cho từng biến thể, đổi tên trace/report và cờ extractor tương ứng. Khóa lựa chọn bằng `dev`, rồi thay `dev` bằng `holdout` và chấm **một lượt** trên bộ đã đóng băng. Đối chiếu hash và số scenario/call/lượt trong manifest với trace trước khi so điểm; nếu thiếu trace hoặc lỗi hệ thống, báo riêng và không coi đó là metric hợp lệ. Lưu mỗi trace, report, cấu hình chạy và báo cáo latency dưới `runs/btc_like_new/`.

**Bảng kết quả chính** cho mỗi cấu hình và split: số kịch bản/cuộc/lượt; TSR và TSR ca khó; CCR; RQR; HR mọi claim và HR giá/KM; guardrail; TTFT, Total (`total_ms`), hậu xử lý (`post_ms`), toàn lượt (`end_to_end_ms`) và Call Brief + toàn lượt, đều p50/p95; thời gian cả suite. Báo thêm số request Jev/Qwen theo nhiệm vụ, tỷ lệ rules đi thẳng, số lần Qwen fallback, lỗi/timeout và số lượt slot khách tới sau `_plan()`. Không cộng các p95 riêng để ra p95 toàn lượt.

Sau khi khóa cổng bằng suite phát triển, chạy **suite holdout mới một lần** với đúng các cấu hình và cách đo trên. Kèm một bảng lỗi trích từ những lượt full: rules được `CERT=1` nhưng thiếu slot/claim/câu hỏi, Jev gán sai, và ảnh hưởng thực tế tới câu đáp, bộ nhớ hoặc metric. F1 extractor trên các câu được rà chỉ là phép chẩn đoán phụ. Chỉ cân nhắc đổi mặc định khi metric hội thoại không giảm và latency có lợi thực đo. Phần trích lời agent chạy sau khi lời đáp sẵn sàng nên tối ưu nó chủ yếu ảnh hưởng **toàn lượt**, không tự giảm Total. Giữ code dưới cờ backend riêng để chuyển lại được.
