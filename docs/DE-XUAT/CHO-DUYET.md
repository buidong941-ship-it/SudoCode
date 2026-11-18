# Quyết định chờ người dùng duyệt

**Cập nhật hiệu lực 10/11:** D60–D71 đã đồng bộ với bàn giao FINAL theo lời giao khép các đề xuất trùng/lỗi thời. Xem [bảng kết luận cuối file](#trạng-thái-hiệu-lực-sau-đồng-bộ-bàn-giao-final--10112026). “Đóng/gộp/rút” không đồng nghĩa chức năng đã làm xong hoặc cho phép triển khai mọi phần còn mở; các ghi chú theo ngày cũ giữ làm lịch sử.

Từ 02/11/2026 trợ lý không tự quyết. Mọi thay đổi về hành vi, dữ liệu hay kế hoạch đều phải được người dùng duyệt rõ ràng. Mục nào chưa duyệt sẽ được nhắc lại ở cuối mỗi câu trả lời.

| # | Quyết định | Trạng thái |
|---|---|---|
| D01 | A6: mặc định `JEV_DROP_POLICY=qwen` | **đã duyệt** 02/11 |
| D02 | B3: dùng bộ đo BTC-like v1_1 (vá 5 scenario fanpage→hotline) và sửa template `delivery_address` | **đã duyệt** 02/11 |
| D03 | Lexicon: 10 entry + 10 viết tắt `approved` | **đã duyệt** 02/11 |
| D04 | A7: định nghĩa nhãn `address` và câu hướng dẫn gửi Jev về mã che PII | **thay bằng D10** (đã duyệt) |
| D05 | Sửa 3 lỗi do D-7 làm lộ (riêng tư, ý định đặt hàng, cắt địa chỉ) | **đã duyệt** 02/11 (kiểm Kaggle: D-7 60→93,3%, không bộ nào giảm) |
| ~~D06~~ | ~~Ngày đóng băng 06/11~~ | **bỏ** theo người dùng 02/11 |
| D07 | C6: chọn cấu hình nộp bài theo C5 | **được thay thế bởi quyết định mới** (17/11): cấu hình nộp chọn giữa R0 / R1 của B2-v52n-ui2 sau khi đo (mục 17/11 cuối file). Không phải "đã hoàn thành" |
| D08 | Chạy C5 (dev 3 lần, khoảng 2–3 GPU-giờ) sau job GPU hiện tại | **đã duyệt** 02/11, **đã chạy xong** (kết quả ở cuối file và `NHAT-KY-2026-11-02.md` mục 5) |
| D09 | Bật thử planner LLM `PLANNER_BACKEND=jev` trong một lần đo (chưa nộp) | **đã duyệt** 02/11, **đã đo** (job A `planjev`): planner Jev nhận 11/24 lượt dự phòng; không chỉ số nào tốt hơn `cert1`, HR thêm 1 claim sai. Trợ lý đề xuất giữ planner `rules` (`NHAT-KY-2026-11-02.md` mục 7.2) |
| D10 | Định nghĩa lại toàn bộ slot khách theo `docs/DINH-NGHIA-SLOT-DE-XUAT.md` (thay cả D04) | **đã duyệt** 02/11, **đã làm** (qua `smoke-d10`) |
| D11 | Ngày đóng băng mới | **được thay thế bởi quyết định mới** (17/11): mốc đóng băng thực tế = freeze `runs/freeze/20261117-v52n-ui2` (lõi = v52n-cand). Phạm vi còn được sửa: chỉ UI / C.5 plumbing ngoài đường chạy đánh giá (có kiểm), gói FAQ đã duyệt, hồ sơ. Không sửa lõi |
| D12 | Sửa lỗi L2 ("đơn … giao tới đâu rồi" → `order_status`) trong router rules + test | **đã duyệt** 02/11 |
| D13 | Sửa **code agent** để qua SAMPLE-03 (`order.update` dùng mã đơn đúng) và SAMPLE-06 (`order.create` bị `tool_exception`). KHÔNG sửa file SAMPLE (file của BTC, cố định) | **đã duyệt** 02/11 |
| D14 | D-5: rút ứng viên cue từ b1 + real_ref, xuất danh sách để người dùng duyệt từng cue | **đã duyệt** 02/11 |
| D15 | D-8: viết thêm đợt câu b2 | **đã duyệt** 02/11, **đã làm** (đợt b2: 52 câu, `datagen/synth_slots/b2.tsv`) |
| D16 | A2/A3/A4: nới CERT, chứng nhận thêm slot | **đã duyệt** 02/11; **đã làm code** 02/11 khuya theo D27 (sau cờ đo `CERT_V2_RELAX`). Kaggle CPU: `blocker` và `budget` đều 0 sai trên 260 câu nhãn tay, chứng nhận rỗng giữ 55, nên đạt điều kiện giữ của D27. Coverage trên trace C5 11 → 15/140, chưa đạt ≥ 20. Cờ vẫn mặc định rỗng; job GPU chưa chạy với cờ này |
| D17 | G: README cho UI / improve, khung slide | **đã duyệt** 02/11 |
| D18 | CERT-1 (`docs/DE-XUAT-CERT-V2-2026-11-02.md` mục 3.1 + 3.2), kèm 4 chỉnh sửa theo nhận xét 02/11: xử lý phủ định ở cả luật trích (không chỉ ở CERT); không coi "k" sau chữ số là phủ định; đưa 3.6 (bỏ phiếu trắng khi có danh từ riêng hoặc mã PII trong chứng nhận rỗng) vào CERT-1; đo tách riêng phần precision và phần bug "m2" | **đã duyệt** 02/11, **đã làm** (qua `regress-cert2b`) |
| D19 | CERT-2 (mục 3.3–3.7), lấy slot vừa hỏi từ `question_slot` của planner thay vì `questions[]` của extractor; ghi chỉ tiêu coverage bằng con số | **đã duyệt** 02/11, **đã làm** (qua `regress-cert2b`; coverage 11/140, chưa đạt chỉ tiêu ≥ 20) |
| D20 | CERT-3 (mục 3.8, thêm slot được chứng nhận) | **đã duyệt** 02/11, **đã làm** (qua `regress-cert2b`) |
| D21 | CERT-4: đổi mặc định sang `EXTRACTOR_CERT_VERSION=2` | **đã duyệt** 02/11, **chưa đổi**. Job A: điều kiện mục 4 đạt về mặt số (0 sai trên nhãn gold; coverage 11/140 > 2; `cert2` so với `cert1`: TSR 100 = 100, RQR 0 = 0, HR 4 = 4 claim sai; CCR 34 so với 36/38, trong khoảng C5). Nhưng không đo được lợi ích: extractor 8,2 s so với 7,9 s, yêu cầu Jev 287 so với 303. Mới chạy 1 lần. **Trợ lý đề xuất chưa đổi mặc định, chờ người dùng chốt** (`NHAT-KY-2026-11-02.md` mục 7.2) |
| D22 | Guardrail chặn câu khẳng định khuyến mãi ("đang có khuyến mãi/ưu đãi", "chương trình còn hiệu lực…") khi kết quả tool trong call không có KM đang áp dụng (ngoài COD-0 / free ship), hoặc KM đó nằm trong `expired_promos`. Lỗi do C5 làm lộ: BTCL-036, BTCL-052 (`NHAT-KY-2026-11-02.md` mục 5.3), kèm test | **đã duyệt** 02/11, **đã làm code** 02/11 khuya (`harness/guardrails.py::promo_problems`, `tests/c5_fixes_check.py`), chờ Kaggle |
| D23 | (Viết lại 02/11 sau khi đọc code.) Sửa lỗi nối dây ở `harness/extractor.py:165`: với câu Jev không xử lý được, kết quả của luật bị bỏ trước khi gửi Qwen, nên Qwen gán nhãn một mình (vd ghi giá sau KM thành `list_price_vnd`). Sửa để giữ claim của luật và gửi kèm cho Qwen (cùng số tiền, cùng câu thì luật thắng, như `llm_extract.py:527` vốn định làm). Sửa cả nhánh dự phòng ở dòng 195. Kèm test | **đã duyệt** 02/11, **đã làm code** 02/11 khuya (`tests/c5_fixes_check.py`), chờ Kaggle |
| D24 | (Người dùng mở rộng 02/11.) Rà **toàn bộ** câu mẫu trong `render_offline` (`core/llm/generator.py:280–420`, khoảng 45 goal; dùng ở 23–26% lượt Full của C5), câu nào mơ hồ thì viết lại hết. Trường hợp gốc: "giá 7.690.000đ, đang có ưu đãi Giảm 300.000đ" dễ hiểu 7.690.000đ là giá gốc | **đã duyệt** 02/11, **đã làm code** 02/11 khuya (15 câu viết lại, `tests/template_review_check.py`), chờ Kaggle |
| D25 | Cách xử lý của guardrail D22 khi bắt được câu KM sai: tạo lại 1 lần kèm ghi chú, vẫn sai thì dùng câu mẫu (giống guardrail số tiền); không cắt câu | **đã duyệt** 02/11, **đã làm** (dùng chung vòng sinh lại của guardrail hiện có) |
| D26 | Cách làm D24: ghi bảng "câu cũ → câu mới → lý do" vào `docs/RA-SOAT-CAU-MAU-2026-11-02.md` cho người dùng duyệt **trước** khi sửa code | **đã duyệt** 02/11, **đã làm**: bảng ở `docs/RA-SOAT-CAU-MAU-2026-11-02.md`, trợ lý tự duyệt theo ủy quyền của người dùng (02/11 khuya) |
| D27 | Cách làm D16: thêm `blocker`, `color`/`size`, `budget_vnd` vào CERT v2, mỗi lần một thứ; xem `callback_requested` và check X rồi báo lại; cờ đo `CERT_V2_RELAX` (mặc định rỗng); giữ bước nới chỉ khi 0 ca sai trên 260 câu nhãn tay | **đã duyệt** 02/11, **đã làm code** cho `blocker` và `budget`; `color`/`size` **không nới** (4 lượt trượt đều do lỗi luật, xem D31); `callback_requested` đã xem và báo lại (D32); check X chờ audit chi tiết của `regress-1102c` |
| D28 | Job GPU sau khi sửa: job A (dev v1_1: `cert1`, `cert2`, `planjev`) và job B (D-7 dev đầy đủ), mỗi biến thể 1 lần | **đã duyệt** 02/11, **đã đẩy cấu hình** 02/11 khuya (dataset-only, người dùng bấm Run): job A → notebook `sudocode-btc-jev-hybrid-final-dev` (v1_1 dev: `cert1`, `cert2`, `planjev`); job B → notebook `sudocode-eval-b` (D-7 dev + v2_1 dev). Chạy song song với job CPU `regress-1102c` (notebook `sudocode-regress-cert2b`). Job CPU và job A **đã xong** (`NHAT-KY-2026-11-02.md` mục 7); job B chạy lại từ 21:56 |
| D29 | BTC-like v2 (`datagen/out_btc_like_final_v2`, lời khách viết lại tay 01/11, bỏ `price_vnd` ở call_1 BTCL-021..025) chưa từng được chạy và **thiếu bản vá B3** của v1_1. Đề xuất: áp `patch_crosschannel_v1_1.py` lên v2 thành `v2_1`, ghi vào `docs/DATASET.md`, rồi chạy **dev** v2_1 trong job A (D28) như một biến thể đo độ bền với cách nói khác; chưa dùng holdout v2. Kèm thêm `out_btc_like_final_v2_1` vào danh sách băm của `scripts/kaggle_job.py` | **đã duyệt** 02/11, **đã làm** (v2_1 tạo xong, cùng khách CRM với v1_1; `DATASET.md`, `kaggle_job.py`); chạy dev v2_1 nằm trong job A |
| D30 | (Người dùng hỏi 02/11 có nên chuyển sang v2 ngay không.) Đề xuất: **chưa thay** bộ đo chính. v1_1 dev vẫn là thước đo cho các sửa đổi D18–D28, vì C5 (3 lần) đo trên v1_1. Đến ngày đóng băng (D11) mới chọn **một** bộ cố định cho vòng 0→N của cơ chế cải tiến: v2_1 nếu lần chạy dev ở D29 không phát hiện lỗi dữ liệu, ngược lại giữ v1_1. Holdout của v2 là **cùng 40 scenario** với holdout v1_1, chỉ khác lời khách, nên chỉ được mở **một** trong hai | **đã duyệt** 02/11 (đi sau D29; lựa chọn cuối làm ở ngày đóng băng D11) |
| D31 | (Mới, 02/11 khuya.) Sửa lỗi luật `find_color` (`harness/tools.py`, gọi từ `extractor.customer_slots_rules`): so trên bản bỏ dấu nên "mẫu **đó**" → "mau do" bị ghi `color = đỏ` vào bộ nhớ (BTC-like dev: BTCL-001/002 call_2, BTCL-056/057 call_2). Đề xuất: câu có dấu thì so màu trên bản có dấu (giữ cách so bỏ dấu cho câu mất dấu), kèm test ca âm "mẫu đó" và ca dương "màu đỏ" | **đã duyệt** 02/11, **đã làm code** (`harness/tools.py::find_color`), test `tests/c5_fixes_check.py::check_d31_d32`), qua Kaggle CPU (smoke OK; audit C5 không còn slot `color`/`callback_requested` đọc sai) |
| D32 | (Mới, 02/11 khuya, D27 bước 4.) `callback_requested`: 2 lượt trượt CERT ("Mai anh sẽ gọi lại em nhé", "Mai anh gọi lại được không em?") đều là **khách** gọi lại, theo D10 không phải `callback_requested`; CERT chặn đúng (check N vì có "gọi lại"). Lỗi nằm ở luật trích (bắt mọi "gọi lại" có thời điểm). Đề xuất: luật chỉ nhận khi shop là người gọi ("em gọi lại cho anh", "gọi lại cho chị", "nhắn lại cho anh"), bỏ "anh/chị sẽ gọi lại em"; **không** nới CERT cho slot này | **đã duyệt** 02/11, **đã làm code** (`harness/tools.py::find_color` → `extractor.CUSTOMER_CALLS_RX`), test `tests/c5_fixes_check.py::check_d31_d32`), qua Kaggle CPU (smoke OK; audit C5 không còn slot `color`/`callback_requested` đọc sai) |
| D33 | (Mới, 02/11 khuya, từ job A.) Hệ quả phụ của D22: khi sinh lại vẫn nói KM đã hết hạn như còn hiệu lực, agent rơi về câu an toàn "Dạ em cảm ơn anh/chị ạ." (BTCL-051/052 call_2 lượt 2, khách hỏi "Nếu hết chương trình thì nói đúng tình trạng mới nhé"). Đề xuất: khi lỗi còn lại chỉ là lỗi KM và cuộc gọi có KM hết hạn, dùng câu mẫu KM hết hạn đang có ("Dạ chương trình khuyến mãi hôm trước đã hết…", lấy từ kết quả tool) thay cho câu cảm ơn, kèm test bằng 2 ca này | **chờ duyệt** |
| D34 | (Mới, 02/11 khuya.) Nới CERT (`CERT_V2_RELAX=blocker,budget`) mới đo trên CPU (260 câu nhãn tay, chấm lại trace C5); biến thể `cert2` của job A chạy với cờ rỗng. Đề xuất: chạy thêm 1 biến thể GPU `cert2relax` (`EXTRACTOR_CERT_VERSION=2`, `CERT_V2_RELAX=blocker,budget`, v1_1 dev, khoảng 50 phút) trên notebook `sudocode-btc-jev-hybrid-final-dev`, để có TSR/CCR/HR thật trước khi chốt D21 | **chờ duyệt** |
| ~~D35~~ | (Mới, 02/11 khuya, từ job B.) Guardrail tồn kho: chặn câu nói "còn hàng / có sẵn" khi kết quả `inventory.check` trong cuộc gọi là `in_stock: false` (và ngược lại), xử lý như guardrail số tiền (sinh lại, vẫn sai thì dùng câu mẫu hết hàng). Ca thật: BTCL-057 call_2 (v2_1 dev), agent nói còn hàng 2 lượt dù tool báo hết | **bỏ** theo người dùng 03/11 |
| D36 | (Mới, từ job B.) Khi khách chốt mua mà chưa có địa chỉ giao hàng (không có trong câu, bộ nhớ hay CRM), planner hỏi địa chỉ trước rồi mới gọi `order.create`, thay vì tạo đơn rồi `order.update`. Ca thật: BTCD7-026/027 call_2 (D-7 dev). Cần xem cả các bộ khác để chắc không làm chậm ca đã đủ thông tin | **hoãn hẳn** theo người dùng 06/11 (xem phần 06/11 cuối file) |
| ~~D37~~ | (Mới, từ job B.) Router `rules` không nhận "xin số khách cũ" là yêu cầu lộ SĐT người khác (BTCL-062 call_2, v2_1 dev). Đề xuất: thêm cách nói này (và các biến thể "số của khách kia", "số người mua trước") vào luật nhận diện riêng tư, kèm test ca dương và ca âm | **bỏ** theo người dùng 03/11 |
| D38 | (Mới 03/11, ablation.) Quy trình ablation: mốc là `cert1`; mỗi biến thể chỉ đổi 1 cờ; chạy với generator nhiệt độ 0 và `LLM_CACHE=off` để bớt nhiễu (số báo cáo cuối vẫn dùng 0,3); so cặp theo từng scenario trên v1_1 dev + v2_1 dev; chỉ số chính là latency, HR (cả `tool`), CCR và tỉ lệ lượt sinh lại/câu mẫu, vì TSR/RQR v1_1 đã bão hoà. Sửa nào rút ra từ lỗi của một bộ thì không dùng chính bộ đó để chứng minh | **đã duyệt** 03/11. Danh sách biến thể và job cụ thể ở D42 |
| D39 | (Mới 03/11, latency.) Total p95 hiện 14,1–16,7 s (ngưỡng ≤ 8 s), TTFT p95 3,3–4,0 s (ngưỡng ≤ 3 s). Trace `cert1`: 65/140 lượt phải sinh lại (58 vì "lượt này không được đặt câu hỏi"); lượt sinh lại p50 12,2 s, lượt không sinh lại p50 5,0 s. Đề xuất ablation 3 biến thể, mỗi cái sau cờ mặc định tắt: (a) khi lỗi duy nhất là "không được hỏi" thì bỏ câu hỏi ở cuối bằng code, giữ phần còn lại nếu vẫn qua guardrail và coverage, không gọi LLM lần 2; (b) generator Qwen3-4B short so với Qwen3-8B-AWQ; (c) extractor `rules` so với `hybrid` để xem Qwen trích có tranh GPU với generator không | **chờ duyệt** |
| D40 | (Mới 03/11, = N8.) Sửa `LEXICON_INCLUDE=none` để thật sự tắt lexicon (hiện nạp cả entry `rejected`), kèm test; rồi chạy ablation `none`/`approved` trên Kaggle CPU (offline, 4 bộ) | **đã duyệt** 03/11, **đã làm code** (`harness/lexicon/__init__.py`: `none` tắt hẳn, `all` cho test, giá trị lạ báo lỗi; test `tests/lexicon_include_check.py` trong `smoke.sh`). **Đã kiểm Kaggle CPU 03/11:** smoke OK (midzid `sudocode-regress-cert2b`). Ablation offline (felicityabby `sudocode-btc-confidence-dev-current`): Full giống hệt nhau trên 5 bộ; slot khách trên `real_ref` F1 23,5 → 57,1. Hệ quả phụ: `blocker` được nhớ làm câu mở đầu hỏi "đã trao đổi với người nhà chưa" cả khi khách đã chốt. Chi tiết `NHAT-KY-2026-11-03.md` mục 1 |
| D41 | (Mới 03/11, tiêu chí 5.) Ablation bỏ từng loại đề xuất của cơ chế cải tiến (`faq`, `playbook`, `cue`, `exemplar`) ở vòng 1, để có bảng "cơ chế nào tạo khác biệt" (điểm thưởng). Làm sau ngày đóng băng (D11) | **đã duyệt** 06/11: làm sau đóng băng (xem phần 06/11 cuối file) |
| D42 | (Mới 03/11, thực hiện D38.) Job GPU ablation, cùng một bản code, `LLM_TEMPERATURE=0`, `LLM_CACHE=off`, router `rules`, Qwen3-8B-AWQ. Mốc `cert1` (hybrid + Jev + CERT v1 + planner `rules`). Bốn biến thể, mỗi cái đổi 1 cờ: `nocert` (`EXTRACTOR_CONFIDENCE_GATE=0`), `cert2` (`EXTRACTOR_CERT_VERSION=2`), `xrules` (`EXTRACTOR_BACKEND=rules`), `planjev` (`PLANNER_BACKEND=jev`). Bộ chính v2_1 dev (chưa bão hoà); v1_1 dev chỉ chạy nếu còn ngân sách. Ước tính 5 × ~45 phút ≈ 3,75 GPU-giờ, tách 2 job (mốc + 2 biến thể; 2 biến thể còn lại) để mỗi job dưới 3 giờ. Lexicon đo riêng trên CPU sau D40. **Cập nhật 03/11:** biến thể chỉ chạy Full (`run_suite.py --configs full`), Baseline chạy một lần ở mốc, nên mỗi biến thể còn khoảng 22 phút. Thêm `nolex` (`LEXICON_INCLUDE=none`, cần D40 làm trước); theo người dùng 03/11, lexicon chỉ so bật (`approved`, tức mốc) với tắt, không tách biến thể con. Bản mở rộng có thể thêm `nojev`, `dropaccept`, `qclf`, `routerjev`, `short`, `4b`; chờ người dùng chọn bản 5 hay 11 biến thể | **đã duyệt** 03/11, **cả 11 biến thể**. Kế hoạch job ở `docs/PLAN-2026-11-03-ABLATION.md` (3 job, ~6 GPU-giờ). **03/11 người dùng bảo chia ra nhiều tài khoản và chạy:** đã đẩy 7 job (bảng ở `PLAN-2026-11-03-ABLATION.md` mục 4.1). **Cả 7 job đã chạy xong 03/11** (cùng code `82b0a1e40dd0f9bf`, Jev key nạp đủ). Kết quả và bảng tổng hợp ở `NHAT-KY-2026-11-03.md` mục 2 |
| D44 | (Mới 03/11, người dùng yêu cầu.) So CERT v1 với không CERT trên **holdout v2_1** (40 kịch bản): `hold-cert1` (mốc D42) và `hold-nocert` (`EXTRACTOR_CONFIDENCE_GATE=0`), chỉ Full, nhiệt độ 0, `LLM_CACHE=off`, 1 lần mỗi biến thể, khoảng 1,2 GPU-giờ. Notebook midzid `sudocode-btc-jev-hybrid-final-dev` (dataset-only, người dùng bấm Run). **Chỉ để đọc số, không sửa code/dữ liệu/cấu hình theo kết quả** (người dùng 03/11: "số liệu để so sánh thôi không sửa gì hết nên holdout vẫn còn giá trị đến cuối cùng"). Đây là lần đầu chạy holdout v2_1; holdout v1_1 vẫn chưa mở | **đã duyệt** 03/11, **đã chạy nhưng không dùng được để so:** Jev hết credit (HTTP 402) từ giữa `hold-cert1` (8/40 kịch bản cuối) và suốt `hold-nocert` (200/200 lượt). `hold-nocert` thực chất là "không Jev". Chi tiết `NHAT-KY-2026-11-03.md` mục 3. **Chạy lại (người dùng yêu cầu 03/11):** Jev qua trung gian `TYPESAFE_BASE_URL=https://www.portixapi.com` (SDK tự thêm `/v1/systemone`), key mới do người dùng cập nhật vào Secret `TYPESAFE_API_KEY`; cùng 2 biến thể. Lần chạy lỗi 402 sao lưu ở `runs/kaggle/btc-jev-hybrid-final-dev.bak-hold402/`. Lần chạy lại đầu (model `jev-latest`) bị người dùng dừng vì proxy trả 404 (không có model này). Proxy dùng tên `jev-1.14.0`, group `jev-1`; key mới qua `scripts/jev_ping.py` 3/3 OK. Đẩy lại với `JEV_MODEL=jev-1.14.0` (khác `jev-latest` của các job trước, nên chỉ so trong cùng job). **Đã chạy xong 04/11:** Jev chạy thật (lỗi chỉ 6 và 5 `slot_type_mismatch`); CERT v1 và không CERT trùng mọi chỉ số chính thức (TSR 80,0; RQR 0; CCR 87,3; HR 0,0); CERT bớt 6% yêu cầu Jev, latency như nhau. `NHAT-KY-2026-11-03.md` mục 3.1 |
| D43 | (Mới 03/11, phục vụ D07.) Đề xuất cấu hình ứng viên theo D42: giữ mốc (router `rules`, Qwen3-8B-AWQ, extractor hybrid + Jev + CERT v1, drop `qwen`, planner `rules`, lexicon `approved`, `QUESTION_CLF` tắt) và **bật `REPLY_STYLE=short` + `LLM_MAX_TOKENS=160`**. Lý do: biến thể duy nhất giảm latency rõ mà không làm HR xấu đi (Total p95 15,6 → 9,5 s, HR 4,1 → 1,4), TSR giữ nguyên; CCR −1 kịch bản, RQR +1 câu hỏi nằm trong ngưỡng nhiễu. Chưa đạt Total p95 ≤ 8 s, nên kèm 1 job GPU xác nhận (~1,5 giờ, cần Jev key): `short` chạy lặp 2 lần + `short+4b` + `short+routerjev` trên v2_1 dev | **chờ duyệt** (chưa đổi code/cấu hình, chưa đẩy job) |
| D46 | (Mới 04/11, sau job `abl-short`, `NHAT-KY-2026-11-04.md` mục 6.) Chạy Qwen3-8B-AWQ + router `rules` trên `out_v3/final/dev` để tách phần HR/TSR do 4B (~1 giờ GPU) | **chờ duyệt** |
| D47 | (Mới 04/11.) Soi và sửa lỗi chọn SKU combo / máy vs phụ kiện (V3-105, 147…153) và giữ giá đã chốt trong đơn (V3-018) | **chờ duyệt** |
| D48 | (Mới 04/11.) Chọn router trên v3: (a) giữ luật và sửa luật cho câu sửa/đặt đơn (V3-099…104, 124…146); (b) dùng Jev (+1,8 s TTFT) và xử lý nhóm `gia_danh_noi_bo`; (c) router lai: luật trước, Jev khi luật không chắc | **chờ duyệt**. 05/11: người dùng nghiêng về Jev (`NHAT-KY-2026-11-05.md` mục 3) |
| D49 | (**Lần 3 xong 05/11** — nhật ký mục 13.1: `moi` 12/12 giả danh, 0/12 âm tính; `cu` 0/12. Đề xuất đưa `moi` vào `core/llm/router.py` — chờ duyệt.) (**05/11 job abl-short-final:** 6 ca giả danh V3-093 đến V3-098 trượt vì Jev chấm `asks_internal_cost` 0,51–0,57, dưới ngưỡng 0,6; key chính thức nên probe giờ rẻ.) (Mới 05/11.) Viết lại mô tả cờ `asks_internal_cost` (người gọi bất kể tự xưng là ai; thêm giá sàn / biên lợi nhuận / chiết khấu đại lý; tính cả câu giục đọc tiếp). Bước 1: dò bằng `scripts/jev_flag_probe.py` (mô tả `cu` so với `moi`), không sửa router | **bước 1 đã duyệt** 05/11. Lần 1 lỗi 429, lần 2 lỗi 503 (proxy); lần 3 đã đẩy (dataset-only), chờ proxy hoạt động để người dùng bấm Run. Sửa router chờ kết quả dò |
| D50 | (Mới 05/11, đề xuất của người dùng.) Bảng quyết định cho planner, giai đoạn 1: `harness/planner_rules.json` chứa toàn bộ nhánh hiện có (R/O/C/A/K/H) cùng bộ máy `harness/planner_table.py` sau cờ `PLANNER_TABLE` (mặc định tắt); check trùng trace 100 % trên các bộ offline, chạy Kaggle CPU. Thiết kế: [PLAN-2026-11-05-PLANNER-TABLE.md](PLAN-2026-11-05-PLANNER-TABLE.md) | **đã duyệt** 05/11, **đã làm code** (cờ `PLANNER_TABLE`, mặc định tắt); **qua Kaggle CPU** `regress-cert2b` v6: trùng trace 100 % (2096 lượt, 6 bộ dev, 0 lệch); smoke OK |
| D51 | (Mới 05/11.) Giai đoạn 2: thêm case mới N01–N04, edge case E03/E04/E07/E08/E09/E11/E12, goal mới (`refund_amount`, `ask_callback_time`, `cancel_handoff`) và tầng tra sản phẩm (alias ra file dữ liệu, ưu tiên SKU combo, thay phần SKU của D47). Đo hồi quy trên v2_1 dev / sample / D-7 dev; v3 test mở một lần khi chốt | **đã duyệt** 05/11, **đã làm code**: N01–N04, E03, E07, E12, E15 (mới: hẹn chốt sau, gốc của V3-018); tầng tra SP sau cờ `PRODUCT_LEXICON`. Chưa làm E04 (cần slot `qty`), E09, E11. **Qua Kaggle CPU** v7 (lần v6 lộ lỗi alias AirPure Pro → màng lọc, đã sửa): A/B offline giữ nguyên 5 bộ, v3 dev TSR 56,8 → 70,4, HR 21,9 → 9,5; còn xem CCR v3 53,1 → 49,4 |
| D52 | (Mới 05/11, đề xuất của người dùng.) Giai đoạn 3: vòng cải tiến. Context lạ được phát hiện ngoài cuộc gọi; LLM đề xuất thẻ context (cách xử lý cho sale + `planner_rule` / `router_cue` / `extractor_cue` / `product_alias`); **duyệt tách từng mục** (người dùng chốt 05/11); cổng hồi quy tự động trên Kaggle trước khi có hiệu lực | **đã duyệt** 05/11, **đã làm code**: loại `planner_rule` / `router_cue` / `product_alias`, trạng thái `gated/`, `python -m improve contexts` / `gate` / `review context`, nạp qua `improve_hook`, UI gom theo thẻ. **Qua Kaggle CPU** v7 (`improve_d52_check` OK, smoke OK). Chưa chạy vòng thật (cần trace GPU + LLM sinh thẻ) |
| D53 | (Mới 05/11.) Chính sách giữ giá đã chốt ở cuộc trước khi KM đã hết (V3-018, N07): giữ giá cũ hay báo giá mới | **đã duyệt** 05/11: theo `policy/dieu-khoan-khuyen-mai.md` của BTC (giá cũ không giữ khi KM hết hạn, trừ đơn đã có mã). V3-018 không phải lỗi chính sách mà do tạo đơn sớm (sửa bằng E15, D51) |
| D54 | (Mới 05/11, sau A/B D51. **Đã có câu trả lời từ job table-ab-v3, nhật ký 05/11 mục 11:** CCR giảm do `variant_sku` không được ghi khi khách hoãn chốt (E15) ở V3-016, V3-017, V3-018, không phải N01. Đề xuất sửa: ghi `variant_sku` đã báo giá vào bộ nhớ dù chưa có đơn — chờ duyệt.) Soi vì sao CCR v3 dev giảm 53,1 → 49,4 (~3 slot) khi bật bảng D51 + `PRODUCT_LEXICON`; nghi N01 (xin nói lại ở lượt 1 trước câu mở đầu khách quay lại) hoặc E15. Chỉ đọc trace A/B có sẵn (`runs/kaggle/regress-cert2b/out/regress-cert2b/table_ab/`), không chạy gì | **chờ duyệt** |
| D55 | (Mới 05/11.) Đo bảng D51 (`PLANNER_TABLE=1`, `PRODUCT_LEXICON=1`) với cấu hình thật trên GPU (Qwen + Jev, cần người dùng bấm Run), và mở **v3 test một lần** để có số không chỉnh khớp dev (D38) | **chờ duyệt** |
| D56 | (Mới 05/11.) Phần chưa làm của D51: E04 mua số lượng > 1 (cần thêm slot `qty` ở extractor theo D10, hiện `order.create` luôn `qty=1`); E09 SP không có trong catalog; E11 đổi ý sang SP khác sau khi đã có đơn; sửa gốc ở extractor cho câu "em gọi anh/chị" (hiện chỉ có lưới N04 ở planner) | **chờ duyệt** (từng mục) |
| D57 | (Mới 05/11, tiêu chí 5 của đề.) Cách tính D51 trong vòng cải tiến: **(a)** coi là phát triển trước đóng băng, bật ở vòng 0; **(b)** vòng 0 tắt D51, đưa các thay đổi qua vòng cải tiến D52 (contexts → thẻ → sale duyệt từng mục → cổng → vòng 1), ghi rõ trong báo cáo là đã thấy lúc phân tích dev. Trợ lý nghiêng về (b) | **đã duyệt (b)** 06/11 (xem phần 06/11 cuối file). **Làm rõ 10/11:** holdout V3 bật D51 là phép đo riêng, không tự trở thành vòng 0 C.5. Giữ quyết định (b); nếu chọn một cặp R0/R1 khác thì ghi quyết định thay thế rõ ràng, không yêu cầu duyệt lại chỉ vì holdout dùng cấu hình khác |
| D58 | (Mới 05/11.) Có bật `PLANNER_TABLE=1` (và `PRODUCT_LEXICON=1`) làm mặc định không. Quyết sau D55 | **chờ duyệt** (sau D55) |
| D59 | (Mới 09/11, [đề xuất tiếp theo sau contract v2](DE-XUAT-TIEP-THEO-SAU-CONTRACT-V2-2026-11-09.md).) Có đặt `CONTRACT_V2=1` làm mặc định không. Đợt 1 **không đạt** tiêu chí (HR giả do loại claim sai, selector 6 ca đạt→trượt do cổng thiếu cue); đã sửa, đợt 2 đang chạy. Quyết sau khi đọc paired failures đợt 2 | **duyệt 10/11** (người dùng: "duyệt D59", sau báo cáo G4 `docs/PLAN/BAO-CAO-PAIRED-G4-2026-11-10.md`); `core/config.py` mặc định `CONTRACT_V2=1` (sau đợt 2) |
| D60 | Danh tính/principal và quyền đọc lịch sử đa kênh trên rules; tách số liên hệ tự khai khỏi quyền CRM. Không mặc định tên/sản phẩm quan tâm là dữ liệu không nhạy cảm. | **Còn mở — quyết định thực chất.** Theo G1 bàn giao FINAL; bỏ đối soát đoán đơn theo SĐT không đồng nghĩa đã xử lý mọi đường đọc/gộp hồ sơ. Chưa chọn phương án hoặc tự thay quyền trong lần đồng bộ 10/11. |
| D61 | Một nơi tính điều kiện nghiệp vụ đổi/trả, COD, giá và lịch, có nguồn/phiên bản. | **Đóng phương án tạo `business_rules.py`; chuyển trách nhiệm sang G2 / `planner_policy.py` hiện có**, theo bàn giao FINAL và yêu cầu khép mục trùng ngày 10/11. Chưa coi policy dùng chung đã hoàn tất: rules còn heuristic ngày đặt +11, selector dùng policy. Phần sửa runtime còn phải theo phạm vi được giao. |
| D62 | Đề xuất cũ: đưa speech-act gate và cue regex của `action_contract.json` vào bảng planner rules. | **Rút đề xuất mở rộng này, 10/11.** Không thêm một tầng regex suy lại ý khách. Bất biến hỏi khác yêu cầu ghi vẫn giữ ở G3/D67(5); không tháo cổng đang chạy hoặc xóa file trước khi có thay thế đã kiểm. |
| D63 | Pending tối thiểu theo kind/target/revision/hiệu lực, cập nhật bởi một nơi giữ state. | **Đóng mục trùng; gộp vào D67(4) / G3.** Không duyệt xây pending engine hoặc cấu trúc state song song. D67(4) vẫn chưa triển khai đầy đủ và còn mở. |
| D64 | Allowlist field theo role LLM và memory/summary/handoff; phân biệt lời khách với khẳng định của shop. | **Đã làm một phần; còn mở phần tổng quát.** G2 đã có projection cho lượt hỏi công dụng chữa bệnh, G4 ghi RT-12 đạt. Chưa chứng minh allowlist cho mọi role, field lồng nhau, log và cache. Không mở thêm runtime trong lần đồng bộ docs này. |
| D65 | Đánh giá bổ sung trên `out_jev1108_new`/`_identity` và đo Jev/DeepSeek thật. | **Còn mở, tách hai phạm vi:** bộ bổ sung và backend API thật. D59 đã duyệt nên không còn là điều kiện chờ; có Secrets không tự cấp quyền chạy. Lời giao 10/11 chạy lại V3 full/baseline được ghi riêng, không mở bộ holdout chính thức hoặc tự mở mọi bộ/API. |
| D66 | Giữ rules làm bản tham chiếu/demo; giữ một đường hiểu và một đường thực thi làm kiến trúc đích; chuyển trách nhiệm từng bước có kiểm. | **Đóng mục kế hoạch độc lập; tiếp nhận vào lộ trình G0–G6 của bàn giao FINAL đã được giao thực hiện.** Rút lập luận tuyệt đối rằng mọi LLM dẫn quyết định đều thua rules; số hiện có chỉ có giá trị theo bộ/model/snapshot đã đo. Không coi việc đóng mục là duyệt mọi tiểu mục D67–D69. |
| D67 | Gói thay đổi hữu hạn trên đường tham chiếu, theo G1–G4 bàn giao FINAL; không yêu cầu mỗi bất biến một cờ mới. (1) outcome tool; (2) bảo toàn kết quả; (3) renderer có nguồn; (4) pending; (5) hỏi phương thức khác chọn phương thức. | **Không còn chờ duyệt nguyên gói.** (1) phần cốt lõi, (2) và (5) phạm vi `payment` đã thực hiện theo lời giao, có kiểm G4; đóng yêu cầu làm lại các phần đó. (1) chưa chứng minh đầy đủ vòng đời unresolved qua restart; (5) chưa khẳng định phủ mọi phương thức. **(3) và (4) còn mở, chưa làm đầy đủ**; D63 chỉ là tên cũ của (4). Nguồn: tiến độ FINAL, báo cáo G4 và nhật ký 10/11. |
| D68 | Bộ hiểu lượt thống nhất chạy shadow chỉ đọc, không executor ghi, theo G6. Chấm với gold được người rà; rules là đối chứng. | **Còn mở, có điều kiện.** Rút gate cũ “đúng ≥ rules” như nguồn gold. Shadow chỉ đo hiểu lượt/thời gian thành phần, chưa chứng minh TSR hoặc TTFT toàn pipeline. Không tự trao quyền runtime hoặc mở phạm vi bộ mới. |
| D69 | G5: hoàn thiện C.5 R0/R1, ASR local/Entity Accuracy, báo cáo lỗi, demo C.6 và slide. | **Giữ công việc M1, không đóng vì là yêu cầu đề.** Kiểm kê artifact độc lập không phải chờ hạn nộp. Hạn nộp/ngân sách, quyết định D57(b) và phạm vi đánh giá bổ sung còn cần chốt; không tự quy các sửa code G1–G4 thành vòng cải tiến C.5. |
| D70 | Rà thiết kế và bàn giao: quyền đa kênh, vật mang cải tiến, đánh giá, latency, cắt input và liên kết quyết định. | **Đóng yêu cầu rà/sửa thiết kế độc lập; các kết luận được tiếp nhận vào bàn giao FINAL.** Rút D70(f) cũ: có cả cắt câu khách và cắt policy; G2 đã sửa đường cắt câu khách. Việc thực chất còn mở chuyển về D60, D64–D65, D67(3)/(4), D68–D69; phân tích holdout là báo cáo lịch sử, không tự biến thành quyền chỉnh/rerun. Thiết kế đích vẫn là tài liệu tham chiếu, không tuyên bố đã triển khai. |
| D71 | Thu hồi mục trùng/lỗi thời: D61 không tạo module mới, D62 không mở rộng gate regex, D63 về D67(4). | **Đã khép phần đồng bộ tài liệu theo lời giao 10/11.** Không còn phiếu chờ riêng. Không xóa chức năng, file hoặc tự duyệt các phần runtime còn mở. |
| L1 | (Mới 05/11, latency.) Chạy router Jev **song song** với bước trích slot (router chỉ cần lời khách + lịch sử + tóm tắt phiên trước, không cần slot). Chỉ chạy nối tiếp ở lượt khách vừa đọc SĐT (định danh có thể đổi tóm tắt). Đo trên `abl-short` `s4b-jev` (v3 dev): trích slot 2,08 s và router 1,86 s đang nối tiếp. Ước tính với router Jev: TTFT p50 4,58 → ~2,7 s, Total p95 9,0 → ~7,2 s; router luật không đổi. Không đổi đầu ra. Làm sau cờ mặc định tắt + check trùng trace 6 bộ dev trên Kaggle CPU | **đã duyệt** 05/11 (người dùng: gộp các L thành 1 lần test), **đã làm code** (`PARALLEL_ROUTER`, `tests/latency_parallel_check.py`); đã đẩy job L6 |
| L2 | (Mới 05/11, latency.) Bỏ proxy portixapi hoặc dùng endpoint Jev nhanh hơn: mỗi lời gọi Jev qua proxy ~1,84 s (p50), trước khi có proxy router Jev ~0,24 s (`eval-b`). Ước tính −1,6 s mỗi lời gọi; router luật TTFT p50 2,74 → ~1,1 s. Cần key TypeSafe gọi thẳng còn credit (key cũ từng báo 402) hoặc hỏi bên proxy | **đã quyết** 05/11: người dùng có key TypeSafe chính thức → bỏ `TYPESAFE_BASE_URL`, `JEV_MODEL=jev-latest` |
| L3 | (Mới 05/11, latency.) Tách GPU: generator Qwen ở card 0, Qwen của extractor ở card 1 (Kaggle 2×T4), thêm biến `QWEN_EXTRACT_BASE_URL`. Ablation 03/11: bỏ Qwen extractor thì TTFT p95 3,06 → 1,36 s (tranh GPU); trên `s4b-rules` token đầu p50 0,65 s nhưng p95 1,92 s. Ước tính TTFT p95 −1 đến −1,5 s, không đổi đầu ra. 4B fp16 ~8 GB/card vừa T4 | **đã duyệt** 05/11, **đã làm code** (`QWEN_EXTRACT_BASE_URL`, `LLM(role="extract")`, `serve_llm.sh` bật thêm server); đã đẩy job L6 |
| L4 | (Mới 05/11, latency.) Không gọi Jev ở bước trích slot khi CERT đã chứng nhận luật (`certified_empty` / `certified_rules`: 23/315 lượt v3 dev, hiện vẫn gọi Jev ở 313/315 lượt). ~7 % lượt bớt ~2 s; không đổi p50 | **bỏ** 05/11: đo lại thấy lượt CERT chứng nhận đã có `slots_ms = 0` (đã bỏ qua Jev sẵn); 313/315 là đếm cả lời gọi Jev phía lời agent |
| L5 | (Mới 05/11, latency.) Giảm `LLM_MAX_TOKENS` 160 → 120 (~−0,5 s Total p95). Trợ lý **không khuyên** làm trước vì `short4b` từng làm CCR giảm | **chờ duyệt** (khuyên hoãn) |
| L6 | (Mới 05/11, latency.) Job GPU đo latency (đi kèm L1, thêm L3 nếu duyệt): cấu hình **Qwen3-4B + `REPLY_STYLE=short` + `STRIP_QUESTIONS=1`** (= `s4b` của `abl-short`), router Jev, chỉ Full, nhiệt độ 0, `LLM_CACHE=off`; bộ **v3 dev** (so thẳng `s4b-jev`) + **v2_1 dev** (lấp chỗ trống "4B + cắt câu hỏi trên v2_1", so được với `stripshort` 8B); biến thể trong **cùng một job**, xếp `base → L1 → base` để thấy dao động của proxy. ~1–1,2 GPU-giờ. Không dùng holdout, không dùng v3 test | **đã chạy 05/11** (`NHAT-KY-2026-11-05.md` mục 10): TTFT p50/p95 4,58/5,16 → 0,87/1,29 s; Total p95 9,0 → 5,6 s, phần lớn nhờ L2. **L3 hỏng (vLLM GPU 1 OOM)** nên extractor Qwen lỗi cả lần chạy, số chất lượng không hợp lệ; cần chạy lại. **Chạy lại đã duyệt 05/11** (bỏ L3, chỉ v3 dev, chỉ full; nhật ký 05/11 mục 12), đã đẩy, chờ người dùng bấm Run |

**02/11 (khuya, sau đó):** người dùng bảo **thực hiện hết các mục đã duyệt** và cho trợ lý tự duyệt bảng D24/D26. Đã làm code cho D16 (theo D27), D22–D27, D29; đã đẩy thử job Kaggle CPU `regress-1102c` nhưng **Kaggle từ chối đăng nhập** tài khoản midzid, nên chưa chạy được kiểm thử. D28 (GPU) và D21 chờ sau đó. Phát sinh 2 đề xuất mới D31, D32.

**02/11 (khuya):** người dùng duyệt **tất cả các mục còn lại**, trừ D07 và D11 (tiếp tục tạm hoãn). Lệnh dừng ở dòng dưới vẫn áp dụng cho D16, D22–D30: đã duyệt nhưng chỉ ghi lại, chưa sửa code, chưa chạy job; chỉ tiến hành khi người dùng bảo làm. D21 cần chạy GPU, phải hỏi trước khi đẩy job.

**02/11 (tối):** D16, D22–D28 đã duyệt nhưng người dùng yêu cầu **dừng, chưa tiến hành, chỉ ghi lại**. Chưa sửa dòng code nào cho các mục này; chỉ làm khi người dùng bảo làm. Kế hoạch và các đề xuất con ở [PLAN-2026-11-02-TOI.md](PLAN-2026-11-02-TOI.md).

Ghi chú 02/11: người dùng cho phép trợ lý **tự gán `approved`** cho các cue rút được ở D14 (không cần duyệt từng cue).

Tiến độ 02/11 (tối): D12, D13 (SAMPLE-06; SAMPLE-03 là lỗi dữ liệu BTC, không sửa), D14, D15, D17, D18–D20 đã làm và qua kiểm thử Kaggle CPU (`regress-cert2b`: smoke OK; CERT v2 0 ca sai trên 260 câu nhãn tay; coverage khách 2→11/140, chưa đạt chỉ tiêu ≥ 20 của D19). D21 chờ lần chạy GPU với `EXTRACTOR_CERT_VERSION=2` (sẽ hỏi trước khi đẩy). D08 (C5) đã chạy xong (xem đoạn dưới).

Kết quả C5 (02/11, trung bình 3 lần, Baseline → Full): TSR 50 → 100; RQR 12,5 → 0; CCR 89,4; HR giá & KM 10,9 → 7,0 (chưa đạt ≤ 5%; tính theo SKU chính thì 0); Total p95 15,9 s. Chi tiết ở `NHAT-KY-2026-11-02.md` mục 5. D07 có thể dựa vào số này.

**05/11 (tối), người dùng quyết theo bảng 22 mục:**
- **Duyệt:**
  - **1** (D49b + chạy v3 dev full; chỉ chạy sau khi sửa xong các mục đã duyệt và giải thích vì sao từng đề xuất hoãn 6, 7, 8).
  - **2** (D54).
  - **3, 4, 5** (soi V3-011, V3-140, V3-141; sửa thì báo lại).
  - **6** (D33).
  - **13** (D48 = Jev làm router).
  - **15** (D58 bật mặc định).
  - **19** (D55 holdout).
- **Bỏ:** 9 (D21), 10 (D34), 11 (L5), 12 (D46), 17 (D39), 18 (D47).
- **Hoãn:** 14 (D07 / D43), 16 (D11), 20 (D57), 21 (D30), 22 (D41). Hai mục 7 (D36) và 8 (D56) chưa có quyết định; người dùng hỏi lý do đề xuất hoãn.

**Đã làm (chưa chạy test, sẽ chạy trên Kaggle cùng mục 1):**
- D49b: mô tả `asks_internal_cost` = bản `moi` (`core/llm/router.py`). `scripts/jev_flag_probe.py` giữ lại mô tả cũ dưới tên `cu` và thêm biến thể `hien_tai`.
- D54: `_remember` ghi `variant_sku` của báo giá biến thể khi chưa có đơn.
- D33: `_promo_safe_plan`. Câu mẫu an toàn báo KM đã hết hạn + giá hiện tại.
- D58: `PLANNER_TABLE`, `PRODUCT_LEXICON`, `PARALLEL_ROUTER` mặc định = 1.
- Mục 13: `JEV_MODEL` mặc định = `jev-latest`.
- Test mới: `tests/fixes_1105_check.py`.
- **05/11 (khuya):**
  - Duyệt và đã làm: cách sửa V3-011 (guardrail %) và V3-140 (`RETURN_RX`). V3-141 mới làm bước probe `medical_question`, đang chờ kết quả.
  - Slot `qty` (E04, `ORDER_QTY`) đang A/B offline. Người dùng đồng ý: nếu không ảnh hưởng chỉ số thì bật mặc định.
  - **Mới, chờ duyệt:** trả `schemas/trace_log.schema.json` về bản BTC (commit `3ef8225` đã sửa file này ngày 28/10).

**Kế hoạch tiếp theo:** `docs/PLAN-2026-11-06-CHOT-VA-HOLDOUT.md` (kiểm tra v3 dev → trả schema → đóng băng → holdout → vòng cải tiến → báo cáo).

**06/11, người dùng duyệt** (nhật ký `NHAT-KY-2026-11-06.md`):
- Trả `schemas/trace_log.schema.json` về bản BTC: **đã làm**. Mô tả trường latency thêm ở `docs/HARNESS.md`.
- Giữ bản dọn planner 1b (bỏ `_plan`, `PLANNER_SKIP_SINCE`): **đã làm**; gate trùng trace 2.096 × 2, smoke OK. `docs/HAM/HAM-AGENT.md` đã cập nhật.
- Chọn CERT: đo CERT1 / CERT2 trên holdout v2_1 bằng cấu hình không Jev (người dùng sắp hết token Jev). Đang chạy.
- 7 sửa lỗi 1c (nhật ký 06/11 mục 5): **đã làm code**, đang kiểm trên Kaggle CPU:
  - J6: `PROXY_CLAIM_RX` + dòng bảng `P01`.
  - Bỏ `address` chỉ là SĐT.
  - Guardrail bảo hành.
  - "Giá nhân viên / giá nội bộ" cho `asks_internal_cost`: luật và mô tả Jev đã sửa. Người dùng 06/11 bỏ bước probe Jev (tiết kiệm token): giữ mô tả mới chưa probe, soi riêng cờ này ở lần chạy Jev thật kế tiếp.
  - Guardrail "em là nhân viên".
  - Câu từ chối cố định cho `refuse_internal`.
  - Điều kiện chấm RT-06 / RT-14.
- Mục 7 (D36), 8 (D56 phần còn lại), 20 (D57), 21 (D30), 22 (D41): người dùng duyệt **theo đề xuất** của kế hoạch 06/11:
  - 7, 8: hoãn hẳn.
  - 20 (D57): phương án (b).
  - 21 (D30): chọn một bộ cố định khi đóng băng.
  - 22 (D41): làm sau đóng băng.

**06/11 (tối), người dùng quyết:**
- **Chọn CERT2** (`EXTRACTOR_CONFIDENCE_GATE=1`, `EXTRACTOR_CERT_VERSION=2`) làm cấu hình chính thức, **trước khi mở holdout v3**. Căn cứ: v3 dev và holdout v2_1 ngang nhau (chênh trong nhiễu), CERT2 chứng nhận nhiều lượt hơn (ít gọi LLM hơn). Mặc định trong code vẫn là `1`, nên cấu hình nộp bài phải đặt biến này rõ ràng (hoặc đổi mặc định, chờ duyệt).
- Còn chờ quyết trước khi đóng băng: (b) có chạy CERT1 làm dòng ablation trên holdout không; (c) có chạy lại v3 dev trên GPU với code cuối (sau 1c + regex JSON) không; (d) số holdout chính thức đo với D51 bật hay tắt.

**06/11 (tối), đóng băng và chạy holdout v3 (người dùng: "chốt cấu hình cuối cùng, tạo job test cuối cùng trên holdout v3"):**
- **Đóng băng:** code = commit `cf8d19e` (gồm 7 sửa 1c và regex → JSON); sau commit này chỉ đổi file docs. Không sửa code, dữ liệu hay cấu hình theo kết quả holdout.
- **Cấu hình chốt:** router Jev `jev-latest` (endpoint chính thức), `PARALLEL_ROUTER=1`; generator Qwen/Qwen3-4B, `REPLY_STYLE=short`, `LLM_MAX_TOKENS=160`, `LLM_TEMPERATURE=0`, `STRIP_QUESTIONS=1`; extractor hybrid (`EXTRACTOR_LLM=qwen`, `EXTRACTOR_JEV_HYBRID=1`, `JEV_DROP_POLICY=qwen`, **`EXTRACTOR_CONFIDENCE_GATE=1`, `EXTRACTOR_CERT_VERSION=2`**), `QUESTION_CLF=0`, `LEXICON_INCLUDE=approved`; planner `rules` + `PLANNER_TABLE=1` (D51 bật), `PRODUCT_LEXICON=1`, `ORDER_QTY=1`; `IMPROVE_DIR` rỗng; RAG `auto` (bge-m3 + BM25); `LLM_CACHE=off`; `--workers 2`, T4.
- **Các mục (b), (c), (d) ở trên:** người dùng chốt đi thẳng holdout: không chạy CERT1 làm ablation, không chạy lại v3 dev trên GPU, D51 bật. Rủi ro đã nêu: code sau 1c chưa từng chạy GPU + Jev; mô tả cờ `asks_internal_cost` mới chưa probe.
- **Job:** `elylish11/sudocode-abl-short` (dataset-only, người dùng cập nhật Secret `TYPESAFE_API_KEY` rồi Save & Run). Bộ `datagen/out_v3/final/holdout` (77 kịch bản), `full` + `baseline_no_memory`, chạy **một lần**.
- **Kết quả holdout v3 (xong 06/11 ~22:49, mã thoát 0; `runs/kaggle/abl-short/out/abl-short/`, bản cũ sao lưu ở `runs/kaggle/abl-short.bak-before-holdout-1106`)** — Baseline / Hệ thống: RQR 41,8 / 6,7 (giảm 84,0%); CCR 9,2 / 67,9; TSR 49,4 / 66,2 (51/77); TSR ca khó 48,6 / 64,3; HR giá & KM 7,8 / 6,1 (HR mọi claim 10,0); vi phạm guardrail 0 / 0; TTFT p50/p95 922 / 2087 ms; Total p95 5922 / 6595 ms; 413 lượt, 0 lỗi LLM, router Jev 413/413 (10 lượt độ tin thấp rơi về luật). 26 kịch bản trượt, theo nhóm 4 biến thể cùng mẫu (order.update chính sách cũ / 3 phiên, order.create hết hàng, bình luận đối thủ, >10 triệu không COD...). Theo quy tắc đóng băng: **không sửa code rồi chạy lại holdout**.

**10/11, người dùng giao thực hiện bản bàn giao FINAL** (`docs/PLAN/BAN-GIAO-CLAUDE-THUC-THI-FINAL-2026-11-10.md`, không tự commit). Trợ lý ghi trạng thái, **không tự ghi duyệt** các mục D59–D71:
- Đã làm theo lời giao (G1–G3, đều là bất biến không đặt sau cờ):
  - phần cốt lõi của D67(1): phân loại kết quả theo từng tool, `unresolved` không tạo lại;
  - D67(2): bảo toàn kết quả đã xác nhận;
  - D67(5): hỏi COD ≠ chọn COD;
  - một phần D64: projection brief/memory cho lượt đòi xác nhận công dụng chữa bệnh;
  - G2: `eligible=None` không thành quyền ghi, một phép cắt câu khách;
  - G3: một ticket chuyển máy cho mỗi lý do.
  
  Chi tiết và kiểm thử ở `docs/PLAN/THUC-THI-FINAL-PROGRESS.md` và `docs/NHAT-KY/NHAT-KY-2026-11-10.md`. Đối soát tạo đơn theo SKU/ngày (`_reconcile_create`, thuộc gói v2 09/11) **đã bỏ** theo FINAL.
- Chưa làm, vẫn chờ quyết:
  - D67(3): renderer giá/KM có nguồn. FINAL xếp vào "phạm vi sửa trước vòng 0"; đó là quyết định của người dùng.
  - D67(4): pending đầy đủ. Rà trace chưa thấy lỗi pending trên rules.
  - D60: principal tin cậy. Đang chặn phần quyền xem lịch sử theo SĐT tự đọc trên đường rules.
  - D59: `CONTRACT_V2` mặc định. **Đã có số GPU sau G1–G3** (`docs/PLAN/BAO-CAO-PAIRED-G4-2026-11-10.md`):
    - rules V3: bật và tắt cờ giống nhau ở TSR/CCR/HR; RQR 3,8 (bật) so với 4,0 (tắt);
    - redteam: 100 (bật) so với 92,9 (tắt), khác ở RT-01.
    Vẫn chờ người dùng quyết.
  - D57(b)/C.5, D65, D68, D69 (cần hạn nộp).

**10/11 (chiều), người dùng duyệt D59** và giao: sửa nguyên nhân chung của các ca sai, chỉ test lại đúng các ca đó; làm nhanh các
hạng mục còn lại; chốt cấu hình cuối rồi chạy holdout V3, dừng trước bộ test holdout chính thức.
- D59: `CONTRACT_V2` mặc định bật (`core/config.py`).
- Sửa nguyên nhân chung (đường rules), xem `docs/NHAT-KY/NHAT-KY-2026-11-10.md` mục 6.
- Các mục khác vẫn chờ: D60, D67(3)/(4), D54–D58, D61–D66, D68, D70, D71, hạn nộp.

## Trạng thái hiệu lực sau đồng bộ bàn giao FINAL — 10/11/2026

Người dùng giao: “tiến hành khép lại các đề xuất đang bất đồng bộ với file bàn giao mà bạn thấy không cần thiết nữa”. Phạm vi lần này là dọn quyết định/tài liệu, không sửa runtime hoặc mở quyền chạy thử.

Nguồn: [bàn giao FINAL](../PLAN/BAN-GIAO-CLAUDE-THUC-THI-FINAL-2026-11-10.md), [tiến độ](../PLAN/THUC-THI-FINAL-PROGRESS.md), [báo cáo G4](../PLAN/BAO-CAO-PAIRED-G4-2026-11-10.md), nhật ký 10/11 và lời giao mới nhất. Bảng D60–D71 bên trên đã được cập nhật theo phạm vi này. Các đoạn theo ngày phía trước là lịch sử, không khôi phục trạng thái chờ cũ.

| Nhóm | Trạng thái hiệu lực |
|---|---|
| D61 | Đóng lựa chọn thêm module; G2 dùng lại `planner_policy.py`, nghiệp vụ dùng chung chưa hoàn tất |
| D62 | Rút đề xuất nhân rộng speech-act regex vào planner rules |
| D63 | Gộp D67(4)/G3, pending vẫn còn việc |
| D66 | Đóng phiếu kế hoạch riêng; dùng lộ trình bàn giao, không duyệt gộp mọi tiểu mục |
| D67 | Phần cốt lõi (1), (2), (5/payment) đã làm và kiểm theo G4; (3), (4) và các khoảng trống ghi rõ ở hàng tương ứng vẫn mở |
| D70–D71 | Đóng phiếu docs/đồng bộ riêng; nghĩa vụ thực chất chuyển về mục chủ sở hữu, không xóa bỏ |
| D60, phần còn lại D64, D65, D68, D69 | Giữ mở đúng phạm vi; không mặc định duyệt hay bỏ |
| D59 | Đã duyệt 10/11, không hỏi duyệt lại; G0/G4 cũ ghi chờ chỉ phản ánh thời điểm đo |
| D57(b) | Giữ quyết định và lịch sử. Holdout bật D51 là phép đo khác R0 của C.5, không tự là mâu thuẫn buộc hủy D57; chưa tự đổi phương án vòng cải tiến |

Phân biệt **đóng đề xuất trùng/đã được thay thế** với **hoàn thành chức năng**. Không phát sinh module, cổng regex, cờ mới, test/model/job, thay cấu hình hay commit/push từ lần đồng bộ này. Không đổi số/chính sách đánh giá của artifact cũ. Lời giao chạy lại V3 ngày 10/11 vẫn giữ trong lịch sử và có phạm vi riêng; không gộp với quyền mở holdout chính thức.

**10/11 (tối), quyết định của người dùng trong lần ủy quyền theo cụm:**
1. C.5 vòng 1: **duyệt cả 44 mục** ("tôi duyệt hết"), gồm 3 playbook và 41 exemplar. Đã ghi `approved` bằng `python -m improve review approve`,
   người duyệt ghi "Người dùng (duyệt lô 10/11)". Đo R0/R1: `t-1110-r0` / `t-1110-r1`.
2. Có kết quả shadow thì **chuyển dần trách nhiệm hiểu sang cấu hình đích**. Trợ lý đề xuất thứ tự và kiểm từng bước; không xóa đường rules
   khi bước thay thế chưa qua kiểm.
3. **Tiếp tục dùng Jev giả lập**; chưa cấu hình Jev thật.
4. **Bỏ quy tắc "Jev rỗng + CERT không chứng nhận rỗng → gọi Qwen"** (đã gỡ trong `harness/extractor.py`). Bản sửa
   `jev_hybrid.py` (bảo vệ `callback_requested`, Qwen phân xử, cần hai nguồn) vẫn giữ: người dùng không yêu cầu hoàn lại.
5. **Tạm hoãn hạn nộp.**

**10/11 (khuya), sau đo cấu hình đích:** R0 được chốt làm cấu hình đích (C.5 tắt), đóng băng ở `runs/snapshots/20261110-target-r0/`.
Chi tiết: [tiến độ](../PLAN/THUC-THI-FINAL-PROGRESS.md), mục "Cấu hình đích". Việc còn chờ người dùng:
- (mới) C.5 vòng 2: có rút hoặc sửa hai exemplar `refuse_internal` dạy câu "đã chuyển cho nhân viên" không. Hiện không ảnh hưởng vì C.5 tắt.
- HR giá & KM 8,9% chưa đạt ngưỡng ≤ 5%: chọn có mở một vòng sửa riêng không (chưa làm, ngoài phạm vi các cụm).
- Jev thật vẫn blocked (người dùng chọn giả lập). Holdout chính thức chưa mở. Hạn nộp tạm hoãn.
- D54–D58, D61–D66, D67(4), D69: giữ như bảng trên. D68: shadow không đạt cổng, rules giữ đường chính.
- **10/11 (khuya), người dùng: "bạn đừng sửa rule nữa".** Từ nay trợ lý không sửa logic rules (planner, extractor, router, regex, lexicon).
  Lỗi nào cần sửa rules thì chỉ ghi lại thành việc còn mở hoặc đề xuất.
- **11/11:** Người dùng duyệt chuyển phần nhận diện yêu cầu ghi sang DeepSeek flash (cổng `REQUESTS_BACKEND=deepseek`, mặc định tắt).
  Chờ đo lại 14 ca sau khi sửa lỗi chặn nhầm địa chỉ, rồi người dùng quyết có đổi cấu hình đích R0 → R2 (R0 + cổng) không.
  Báo cáo: [BAO-CAO-DEEPSEEK-FLASH-2026-11-11.md](../PLAN/BAO-CAO-DEEPSEEK-FLASH-2026-11-11.md).
- **11/11 (chiều):** Kiến trúc đích (một lời gọi DeepSeek Flash hiểu lượt khách, `UNDERSTANDING=deepseek`) đã triển khai và đo một lần trên V3 dev, redteam, jev1108_new.
  Báo cáo: [BAO-CAO-KIEN-TRUC-DICH-2026-11-11.md](../PLAN/BAO-CAO-KIEN-TRUC-DICH-2026-11-11.md). Người dùng yêu cầu dừng sau lần đo.
  **Chờ người dùng quyết:** (a) có chạy lại các ca bị ảnh hưởng với hai sửa đã có trong code (nhãn trace; định nghĩa `out_of_scope` trong prompt) không;
  (b) có sửa tiếp phần tiêm lệnh / hỏi thông tin khách khác (mục 6.2) không; (c) có chốt TG thay R0 làm cấu hình đích không.
- **12/11 — sau đo V3 holdout của bản hoàn thiện planner** (báo cáo [BAO-CAO-HOLDOUT-V3-SAU-HOAN-THIEN-PLANNER-2026-11-12.md](../PLAN/BAO-CAO-HOLDOUT-V3-SAU-HOAN-THIEN-PLANNER-2026-11-12.md), mục 6).
  - **Kết quả Full:** TSR 84,4 %, RQR 0 %. **Chưa đạt:** HR giá 6,3 % (> 5 %), TTFT p95 3,7 s (> 3 s).
  - **Chưa làm.** Mọi mục dưới đây phát hiện trên holdout, nên nếu làm phải kiểm bằng bộ khác, không chọn bằng holdout.
  - **Chờ người dùng quyết từng mục:**
    1. Sửa `h_refund_amount`: hỏi tiền hoàn sau khi đổi hàng phải đọc `refund_vnd` của lần đổi. **Lỗi agent thật** (V3-067 / 070 lượt 3).
    2. Kiểm trùng đơn theo bao hàm: đơn mới chứa sản phẩm đã đặt trong cuộc → hỏi trước khi ghi. **Lỗ hổng code thật** (V3-058).
    3. Đối chiếu số món khách nói ("đủ bốn món") với target trước khi ghi (V3-057). Cần cân nhắc hợp đồng DeepSeek.
    4. Compose chính sách: thu hẹp ứng viên theo chủ đề khách hỏi, giảm chọn sai câu (V3-071 / 072 / 074; V3-072 gây hiểu lầm "lắp đặt miễn phí").
    5. DeepSeek bỏ sót `payment` khi nói cùng câu với địa chỉ (V3-031…033): prompt mới chưa đủ, cần cách khác, đo bằng model thật.
    6. Ranh giới câu hỏi / yêu cầu trong prompt DeepSeek ("đổi qua … được không em?" bị tạo yêu cầu đổi, V3-067 / 070 lượt 2).
    7. Độ chính xác Qwen claim audit: `price_vnd` chỉ cho giá bán (không cho ngưỡng KM / tiền hoàn), `is_human` chỉ cho câu tự nhận danh tính. Mục đích là audit đúng nghĩa, không làm đẹp số.
    8. TTFT p95 3,7 s: stream block đầu / rút ngắn đường trước render.
    9. Ngày nhận hàng do khách nói (V3-023…025): cần hợp đồng sự kiện + căn cứ. Đang chủ ý chưa hỗ trợ theo bàn giao mục 8.

**12/11 — đề xuất tiến tới B3, mới ghi tài liệu theo yêu cầu người dùng:**
- Tài liệu: [Đề xuất tiến tới B3: quản lý luồng nghiệp vụ bằng máy trạng thái](DE-XUAT-TIEN-TOI-B3-QUAN-LY-LUONG-NGHIEP-VU-2026-11-12.md).
- Hướng đề xuất: phát triển `RequestState` thành chủ sở hữu tiến trình từng yêu cầu; thống nhất cách đọc kết quả theo đơn/thao tác; chuyển lần lượt các luồng, giữ bảng làm điều phối trong quá trình chuyển đổi.
- Thứ tự: mốc đối chứng và tiêu chí → kết quả nghiệp vụ → đặt hàng → địa chỉ/đổi/trả/callback/handoff → thu hẹp bảng và dọn dữ liệu trùng.
- B3 không tự sửa lỗi hiểu khách, chọn câu chính sách hay hạn chế chấm HR theo field. Mục tiêu TSR >90%, HR <5% phải kiểm bằng dữ liệu phù hợp, không cam kết trước.
- **Trạng thái: đề xuất, chưa triển khai.** Lời giao hiện tại chỉ ghi rõ đề xuất; chưa duyệt sửa runtime, đổi hợp đồng model, chạy job, commit hoặc mở holdout chính thức. Không thay lịch sử lựa chọn B1 ngày 11/11.

**12/11 — hoàn tất bridge thiết kế ba biến thể theo yêu cầu người dùng:**

- [Bàn giao B1/B2-Jev/B3-workflow](../PLAN/THIET-KE-B1-B2-JEV-B3-WORKFLOW-2026-11-12.md), [transcript ba vòng](../PLAN/PHIEN-PHAN-BIEN-B2-B3-2026-11-12.md).
- Một lựa chọn cấu hình đề xuất `PLANNER_VARIANT=b1|b2_jev|b3_workflow`, bất biến trong session; switch cho phiên/run mới. B2 strict không fallback B1; B3 progress dẫn xuất từ request/fact/operation.
- Yêu cầu vận hành đã ghi: job B2/B3 song song có DB/tool/output/cache riêng; mọi kiểm trên Kaggle, API DeepSeek/Jev thật cho phép đo; dùng nguồn xác thực người dùng chỉ định và tài khoản còn quota GPU khi triển khai. Chưa kiểm quota/secret hoặc chạy job trong bridge.
- Chưa triển khai runtime. Đồng thuận review không phải nghiệm thu; các điểm Codex chốt khác Claude và các gate cần probe nằm ở mục 9 bản bàn giao. Giữ hidden holdout chưa mở.

**12/11 — triển khai B1/B2-Jev/B3-workflow** ([nhật ký](../PLAN/TRIEN-KHAI-B1-B2-B3-2026-11-12.md)):
- Đã code theo bàn giao thiết kế. E0 Kaggle CPU qua (40/40 kiểm biến thể; hồi quy B1 75/75, 94/94, 41/41).
- Đã đẩy E1 (probe Jev) và sáu job E3 (B1c/B2/B3 × Full/Baseline trên V3 dev + redteam). Chưa chạy vì chờ người dùng gắn secret.
- **Chờ người dùng quyết:**
  1. Gắn `TYPESAFE_API_KEY` cho `thytinlngc/sudocode-var-1112-jevprobe` và chạy E1 trước. B2 chỉ chạy E3 khi E1 PASS.
  2. Gắn `DEEPSEEK_API_KEY` + `TYPESAFE_API_KEY` cho sáu notebook E3 rồi Run.
  3. Ngân sách B2 (6 quyết định, 12 tool, 12 s/lượt) và B3 (8 bước) là giá trị khởi đầu, giữ cố định giữa các lần đo. Ngưỡng `PLANNER_B2_MIN_CONF` để 0 cho tới khi có số probe.
  4. Phân nhóm dòng bảng (mục 2.1 nhật ký): B3 giữ dòng trả lời của B1, B2 sở hữu cả trả lời.
  5. Khoảng trống: `commit_request` của B2 cho đổi địa chỉ / đổi / trả vẫn dùng executor B1 (tự tra đơn / kiểm hạn đổi trả). Có tách tiếp thành bước nguyên tử không?
- **12/11 (sau) — người dùng dừng E3 B2/B3.**
  - Bốn kernel đang chạy cần hủy trên giao diện: `maggiecamila/…-b2-full`, `norahkhloe/…-b2-base`, `midzed/…-b3-full`, `elylish11/…-b3-base`.
  - Kết quả của chúng không dùng.
  - **Chờ người dùng chốt:**
    - (i) Phạm vi trả lời của B3: (a) chỉ sở hữu tiến trình và sửa bốn chỗ lệch B1, **khuyến nghị**; hoặc (b) sở hữu cả trả lời. Xem nhật ký triển khai, mục 6.
    - (ii) Tách đổi địa chỉ / đổi / trả của B2 thành bước nguyên tử (`read_order`, `check_window`, `read_stock` biến thể mới, `commit` chỉ còn `order.update`). Xem mục 7.
    - (iii) Ngân sách B2/B3.
  - Sau khi chốt: code, chạy E0 trên Kaggle, snapshot `20261112-variants-v2`, job `var2-*`. E3 chỉ chạy khi người dùng duyệt bản cuối.
- **12/11 (v2) — đã triển khai phần người dùng duyệt:** mục 3, mục 4, holdout 1/2/7.
  - E0 v2 qua (68/68 + hồi quy B1). Snapshot `runs/snapshots/20261112-variants-v2/`.
  - Job `var2-*` đã đẩy, chưa chạy.
  - **Chờ người dùng quyết:**
    1. Duyệt bản cuối v2 để chạy E1 rồi E3. Chạy E1 trước B2.
    2. Ngân sách B2/B3. Lượt đổi hàng có thể dùng 5–6 quyết định Jev / 6.
    3. Holdout 7 chưa đạt tiêu chí probe: còn "phí đổi" bị gắn `price_vnd`, tiền hoàn bị gắn `price_quoted_vnd`. Có sửa tiếp (kiểm bằng bộ câu mới khác) không?
    4. Có đẩy B1c v2 (cùng code) để so không?
    5. Mở rộng ngữ cảnh Jev (giá trị memory/known/điều kiện/facts kèm nguồn/TTL, che PII).
    6. Holdout 3–6, 8, 9.
- **12/11 (v3):**
  - Đã triển khai ngữ cảnh Jev, E1 nâng cấp, ngân sách thăm dò 10 quyết định, audit vòng 2. Snapshot `20261112-variants-v3`; E0 qua.
  - Job `var-*` và `var2-*` cũ không chạy.
  - **Chờ người dùng:**
    1. Gắn `TYPESAFE_API_KEY` cho `carterbryleeaqul/sudocode-var3-jevprobe` (E1).
    2. Gắn `DEEPSEEK_API_KEY` cho `carterbryleeaqul/sudocode-var3-dsprobe`.
    3. Gắn cả hai key cho `maggiecamila/sudocode-var3-integ` (tích hợp nhỏ).
    4. Sau E1: duyệt deadline B2 tôi đề xuất từ số E1.
    5. Duyệt bản chốt để đẩy E3 (cấu hình đã lưu ở `runs/snapshots/20261112-variants-v3/jobs/`).
    6. Holdout 3, 4, 8, 9 chưa duyệt. Payment / hỏi-yêu cầu chỉ đo ảnh hưởng.
- **12/11 kết quả v3:**
  - E1 đạt tiêu chí an toàn, nhưng ca dương chỉ hoàn tất 4/10: 34 % tuple sai do mã hóa 4 `Choice`, cộng một lỗi code `_order_for`.
  - Audit vòng 2 còn 1/6 (bộ mới) và 1/5 (bộ cũ) câu bị gắn giá.
  - DeepSeek probe và tích hợp nhỏ chưa chạy (thiếu secret).
  - **Chờ người dùng quyết:** đề xuất 1–4 ở mục 10.4 nhật ký triển khai.
- **12/11 (v4):**
  - Đã triển khai mục 1, 2. E0 v4 qua.
  - **Chờ:** người dùng gắn `TYPESAFE_API_KEY` cho `carterbryleeaqul/sudocode-var4-jevprobe` (E1 v4).
  - Sau E1 đạt: snapshot v4 → tích hợp nhỏ `var4-integ` → đề xuất deadline.
  - `var3-integ` không chạy. DeepSeek probe `var3-dsprobe` chạy khi gắn key (độc lập planner).
- **12/11 E1 v4:**
  - An toàn đạt; tuple sai 0. Ca dương hoàn tất 8/10, chưa đạt C6: trả hàng đơn còn hạn 0/2 (Jev chọn hỏi lại).
  - Ca âm: 0 ghi sai, nhưng 2 câu trả lời kém (ca điều kiện chỉ chào kết; đổi chưa có size không hỏi size).
  - **Chờ quyết:** đề xuất (a)–(c), mục 11.1 nhật ký.
  - dsprobe chưa chạy với key.
- **12/11 (v5):**
  - Đã làm (1)–(3). E0 v5 qua 93/93.
  - **Chờ:** gắn `TYPESAFE_API_KEY` cho `carterbryleeaqul/sudocode-var5-jevprobe` (E1 v5).
  - Đạt → snapshot v5 + tích hợp nhỏ. `var4-*` không dùng nữa.
- **12/11 kết quả v5:**
  - E1: ca dương 18/18, ca âm 0 ghi sai. C7 14/16: điều kiện giá chưa thỏa không được phản hồi. Đề xuất (a)/(b), mục 12.1.
  - DeepSeek: bỏ sót payment 3/12; câu hỏi thành yêu cầu đổi 5/15; bỏ sót yêu cầu 0/9 (mục 12.2).
  - Chưa sửa. Chưa snapshot v5, chưa tích hợp nhỏ vì E1 chưa đạt C7.
- **12/11 (v6):**
  - Đã làm (1)/(2). E0 v6 qua 104/104.
  - Đề xuất payment / hỏi-yêu cầu ở `DE-XUAT-PAYMENT-RANH-GIOI-HOI-YEU-CAU-2026-11-12.md`, chờ duyệt.
  - **Chờ:** gắn `TYPESAFE_API_KEY` cho `carterbryleeaqul/sudocode-var6-jevprobe`.
- **12/11 đo thực tế v6:**
  - Snapshot `20261112-variants-v6`. Đã đẩy `norahkhloe/sudocode-var6-b1-hold`, `elylish11/sudocode-var6-b2-hold`.
  - B3 chờ lệnh đẩy. Cần gắn `DEEPSEEK_API_KEY` + `TYPESAFE_API_KEY`.
- **12/11 kết quả đo V3 holdout snapshot v6** ([báo cáo](../PLAN/BAO-CAO-HOLDOUT-V3-B2-B3-SNAPSHOT-V6-2026-11-12.md)):
  - B2 Full: TSR 76,6, HR 6,1, TTFT p95 4,08 s.
  - B3 Full: TSR 83,1, HR 6,8, TTFT p95 3,67 s.
  - B2 có lỗi cấu trúc: dòng chung sau vòng Jev bị bỏ qua → V3-047…050 trượt.
  - **Chờ quyết:** đề xuất 1–4 mục 6 báo cáo; chạy B1 v6; baseline.
- **12/11 B1 v6:**
  - TSR 85,7, HR giá 4,7, TTFT p95 3,64 s (B2 76,6 / 6,1; B3 83,1 / 6,8).
  - Chênh B1–B3 do dao động DeepSeek (V3-058). **Chờ quyết:** lặp ≥ 3 lần? sửa B2? baseline?
- **13/11 — gói cải thiện B2** (theo [bàn giao](../PLAN/BAN-GIAO-CAI-THIEN-B2-SAU-DO-V6-2026-11-13.md), người dùng yêu cầu thực hiện):
  - Đã triển khai một patch, chi tiết + phân loại wording-only / thay đổi hành vi ở [TRIEN-KHAI-CAI-THIEN-B2-2026-11-13](../PLAN/TRIEN-KHAI-CAI-THIEN-B2-2026-11-13.md). Chưa commit.
  - Một job: `carterbryleeaqul/sudocode-b2fix-1113` (CPU). Phần xác định tự chạy; phần Jev thật **cần gắn `TYPESAFE_API_KEY`** cho notebook này rồi chạy lại.
  - **Chờ người dùng quyết:**
    1. Ask `other` khi đã có khối chung (vd `is_bot`): giữ nghĩa vụ (hiện tại, theo Codex) hay cho finish với trace `partial` (đề xuất Claude)? Điểm chưa đồng thuận.
    2. Sau khi có kết quả job: có đo phiên bản mới (holdout) hay không — không tự mở E1 / tích hợp / full holdout.
- **13/11 — tổ chức dataset + holdout mới H13** (theo [bàn giao](../PLAN/BAN-GIAO-TO-CHUC-DATASET-VA-TEMPLATE-MOI-2026-11-13.md), người dùng yêu cầu thực hiện; chi tiết [DATASET.md §10](../DATASET.md)):
  - Đã làm: registry + suite ở `datagen/datasets/`, `scripts/dataset_registry.py`, release H13 (21 họ × 4 = 84 ca) đã sinh, validate sạch, đóng băng, audit/canary PASS trong một job CPU `midzid/sudocode-ds-h1113` (lần 1 hỏng do tên biến template trùng hàm resolver, đã sửa). Không di chuyển/sửa dữ liệu gốc. Chưa commit.
  - **Chờ người dùng duyệt:**
    1. Nhận H13 làm holdout mới với 21 họ / 84 ca (bàn giao mặc định 20 / 80; cho phép 20–25 họ, 60–100 ca). Tỷ lệ âm theo cực là 24/84 = 29%; tính theo bước then chốt bị cấm ghi là 42/84 = 50%.
    2. Đặt đầu mối ở `datagen/datasets/` thay vì `data/datasets/` (vì `data/` bị gitignore và bị loại khỏi gói Kaggle).
    3. Khi nào đo B1/B2/B3 trên H13 (suite `holdout_h13` bị khóa, cần `--allow-guarded`). Không tự chạy.
    4. Có commit phần registry/suite/script/docs không (template và kịch bản H13 đã gitignore như v3).
    5. ~~Có naturalize H13 không.~~ **Đã duyệt 13/11** ("có, naturalize H13 đi"). Lời viết lại ở `releases/h1113/naturalize/h13_claude_rewrites.py`, job CPU `midzid/sudocode-ds-h1113-nat` **PASS mọi bước**. Bộ chạy giờ là `final/holdout` (84 file, đã đóng băng). Mô tả ban đầu: lời khách viết thẳng trong template, đủ dấu, đúng tên mẫu, không lỗi gõ hay lỗi nghe nhầm (sạch hơn V3 final). Nếu làm: Claude viết lại 338 câu, giữ nguyên thực thể đáp án phụ thuộc, ra `final/holdout`; chạy lại validate + audit + canary trong một job CPU; `raw` giữ nguyên.
- **13/11 — patch cuối B2 (bốn lỗi còn lại)**, theo yêu cầu người dùng; chi tiết ở [TRIEN-KHAI-CAI-THIEN-B2-2026-11-13](../PLAN/TRIEN-KHAI-CAI-THIEN-B2-2026-11-13.md):
  - **Đã duyệt 13/11:** nâng trần tool cứng của B2 từ 12 lên 13 (`PLANNER_B2_MAX_TOOL_CALLS`). Lý do: bước tư vấn danh mục 8 mẫu khi khách đang bàn một mẫu khác tốn tối đa 13 tool. Đã thêm check G15.
  - `other` đi theo chỉ đạo của người dùng: khối chung → `responded_common`; không tự tra chính sách; chỉ trả lời từ policy khi Jev đã chủ động `read_tool_policy_docs`. Câu hỏi treo ở mục 1 phía trên coi như đã chốt theo hướng này.
  - Key Kaggle của carterbryleeaqul, felicityabby, maggiecamila, norahkhloe (tạo 24/09) bị 401 từ 13/11. Job chuyển sang `elylish11/sudocode-b2fix-1113` và **cần gắn `TYPESAFE_API_KEY`** rồi chạy lại.
  - Đạt thì đóng snapshot, **không đo B2 Full** (người dùng đính chính). Còn lỗi thì chỉ báo, không mở vòng sửa tiếp.
  - **Kết quả 13/11:**
    - CPU qua hết.
    - Jev thật: 38 lần chạy, 0 vi phạm cứng, 0 lỗi API; no_progress 2/38 (N10).
    - Đã khép: `other`, thuộc tính chưa rõ, cùng SKU, trần tool.
    - **Còn lỗi** đọc lặp sau `report_cart` (V3-055 t4, N10), làm câu trả lời có dòng "Ngoài ra bên em có mẫu…" cho món đã ở trong giỏ, có lúc kèm giá lệch so với dòng giỏ. Chi tiết ở §5 của tài liệu triển khai.
    - Chưa đóng snapshot, chưa sửa thêm.
    - **Chờ quyết:** (a) có sửa tiếp không (lọc `read_quote` của món đã báo giá qua giỏ, và chặn `report_cart` lặp khi giỏ không đổi); (b) có chấp nhận snapshot với lỗi đã biết không.
- **13/11 — B2 làm kiến trúc chính** (người dùng chốt). Hai vòng sửa đã duyệt: (1) bằng chứng giá theo ngữ cảnh giỏ và điều kiện KM; (2) chuẩn hóa phụ kiện trước khi dựng ứng viên DeepSeek, một nơi cập nhật giỏ, phụ kiện thiếu căn cứ thì hỏi rõ.
  - **Kết quả:** đạt đủ §6.2 và §7.2.
    - CPU qua hết.
    - Jev thật: 42 lần chạy, 0 vi phạm, 0 no_progress, 42/42 ca đạt.
  - **Đã đóng snapshot** `runs/snapshots/20261113-b2-cart/`. Chưa mở H13, chưa commit, không đo B2 Full.
  - **Chờ quyết:**
    - (a) bước tiếp theo sau snapshot: đo B2 Full trên V3 holdout và/hoặc H13 — không tự chạy;
    - (b) commit hay không;
    - (c) ba lỗi còn mở ngoài phạm vi: dòng "chưa tra cứu được" của `policy_answer`, R28 của B1, alias "airpure pro".
- **13/11 — Dev E2E Full / Baseline (B2, đo theo emit_v1).** Hai job GPU xong, trace toàn vẹn: 387 lượt mỗi bên, 0 lỗi API, audit ok 387/387, emit khớp sha.
  - **Full (bộ chấm BTC):** TSR 90,2%, HR giá & KM 10,2%, CCR 78,4%, RQR 1,9%, 3 vi phạm guardrail (đều do audit gán nhầm `is_human`).
  - **Báo cáo đủ (§6a):**
    - Baseline: TSR 69,6% / HR giá & KM 9,3% / CCR 5,2% / RQR 34,9%. Full: RQR giảm 94,6%.
    - TTFT = Total p95: Full 3800 ms, Baseline 3595 ms (384 lượt hợp lệ). Call Brief p95: 61 / 39 ms.
    - 0 lần ghi tool bị cấm. Có ghi đơn sai thật: RT-07 (câu chèn), RT-02/03, tạo đơn khi thiếu địa chỉ và tự đặt COD.
    - 21 lượt còn câu hỏi treo; 0 lỗi API.
  - **Đề xuất đóng băng và H13 (§7):** chưa đóng băng bản hiện tại. Làm một vòng sửa có giới hạn, qua cổng chốt trước, rồi snapshot `b2-final`. Đo H13 3 lần Full + 3 lần Baseline, báo trung vị kèm min–max.
  - **Chờ quyết:** phạm vi sửa (đều là logic planner / generator / audit, cần duyệt):
    - F1: ask "answered" phải có nội dung được hỏi trong câu trả lời (`promo_end`, `stock`, ...);
    - F2: gắn đúng sản phẩm khách vừa nhắc, giữ đủ giỏ nhiều món;
    - F3: bỏ câu hỏi "người nhà" khi khách quay lại đã nêu yêu cầu cụ thể;
    - F4: trả lời mẫu khách hỏi trước, so sánh thì báo đủ cả hai mẫu;
    - F5: báo ngừng kinh doanh / KM hết hạn / giá theo size, và chưa tạo đơn khi thiếu địa chỉ;
    - F6: audit gán nhãn sai `is_human` / tiền hoàn;
    - F7: bảng policy in nguyên ký tự `|` và dòng "chưa có thông tin chính xác";
    - F8: không tạo đơn khi chưa xác nhận hoặc thiếu địa chỉ, không mặc định COD, bỏ qua câu giả mạo hệ thống.
    - Duyệt §7 (kế hoạch đóng băng và H13).
- **13/11, vòng sửa F1 / F2 / F3 / F8 (đã duyệt; F6 để sau).** Danh sách và tiêu chí chốt trước ở §8 của `docs/PLAN/TRIEN-KHAI-LATENCY-EMIT-VA-DEV-2026-11-13.md`:
  - bộ 57 / 92 kịch bản; mốc TSR Full 49/57, Baseline 32/57.
  - D1 = theo câu lệnh; D2 = giữ COD, nói rõ (người dùng chốt).
  - Đã viết code và check `b2_round_f_check`; cổng CPU `midzid/sudocode-rf-1113-cpu` đang chạy.
  - **Tiếp theo:** job GPU Full / Baseline trên bộ 57 (cần gắn key).
  - Đạt thì đóng `b2-final`. Chưa mở H13, chưa commit.
  - **Kết quả cổng vòng F (13/11, job `midzid/sudocode-rfscore-1113`): KHÔNG ĐẠT.** Chưa đóng `b2-final`. Chưa mở vòng sửa tiếp. Chi tiết ở §8.8 của plan.
    - Đạt: (1) checks 10/10; (3) F2; (4) F3; (5) F8: RT-02 / 03 / 07 không tạo đơn, câu giả hệ thống không tạo đơn, BTCD7-025 đạt, 0 ghi bị cấm.
    - Không đạt (2) F1:
      - 10 lượt "answered" mà không có nội dung; 6 trong số đó là lỗi chữ hoa trong regex của script cổng.
      - 4 lượt là lỗ thật: quà (GEN-T02, V3-141), tồn kho "mẫu cũ" (GEN-T10), `promo_end` (BTCL-051 c2).
      - Lượt trả lời lặp y hệt: Full 14 (mốc ≤ 8), Baseline 21 (mốc ≤ 13).
    - Không đạt (6):
      - RQR Full 4,2% so với 2,0%: vẫn đúng 1 câu thừa, nhưng mẫu số giảm từ 49 xuống 24 câu hỏi.
      - **Hồi quy thật:** RT-10 c2 trượt ở cả hai config, vì câu F1 nêu tên KM không đủ điều kiện có "giảm 50%".
    - Các số khác:
      - TSR Full 51/57 (mốc 49), Baseline 32;
      - HR giá: Full 8,3 so với 10,4; Baseline 8,9 so với 9,2;
      - TTFT p95 3666 ms; audit ok 291/291; 0 lỗi API.
    - **Chờ quyết:** hướng xử lý (xem §8.8).
- **13/11, vòng F1b (duyệt: A, sửa hẹp F1, giữ F2 / F3 / F8; GEN-T10 tách sang F5).**
  - Danh sách 19 kịch bản và cổng v2 đã chốt trước khi sửa (§8.9). Vòng F v1 vẫn ghi KHÔNG ĐẠT.
  - Đã viết code và test. Cổng CPU `midzid/sudocode-rf1b-1113-cpu` đang chạy.
  - **Tiếp theo:** job GPU Full / Baseline trên bộ 19 (cần gắn key).
  - Đạt thì đóng `b2-final`. Chưa mở H13, chưa commit, chưa gộp F6 / F7.
  - **Kết quả cổng v2 vòng F1b (14/11, `midzid/sudocode-rf1b-score-1113`): KHÔNG ĐẠT.** Chưa đóng `b2-final`, không tự sửa tiếp. Chi tiết ở §8.10.
    - Đạt:
      - F1 đạt toàn bộ: 0 lượt thiếu nội dung; ba lượt mục tiêu đã có nội dung; 0 lượt nêu tên KM không đủ điều kiện; lượt lặp không tăng.
      - F2 / F3 / F8 giữ nguyên; RT-10 c2 hết trượt; TSR Full 15 so với 14; TTFT p95 4039 ms.
    - Không đạt, tiêu chí 4:
      - HR giá & KM: Full 8 so với 4 (GEN-T04 c2, do DeepSeek đọc t1 thành `recommend` nên focus chuyển sang Urban Classic); Baseline 2 so với 1 (GEN-T09 t1 báo giá trước khi có size).
      - Câu thừa Baseline 8 so với 7 (BTCD7-007 c2 t2).
      - Các lượt này đều không đi qua code F1b.
    - **Chờ quyết:**
      - A: đo lặp (2 + 2 lần) với quy tắc trung vị chốt trước;
      - B: chấp nhận kèm ngoại lệ post-hoc;
      - C: mở vòng sửa riêng cho GEN-T04 / GEN-T09.
- **14/11, hướng A (đã duyệt). Cổng v2 vẫn ghi KHÔNG ĐẠT.** Kế hoạch và quy tắc chốt trước ở §8.11.
  - **Đóng băng:** `runs/freeze/20261114-roundF-v36` và `20261114-F1b-v37`, lấy nguyên gói dataset Kaggle v36 / v37 mà job đo đã chạy (khớp `packed_at`).
  - **Đối chiếu history / state** (`runs/analysis/f1b-divergence-1114/`):
    - ba lượt nghi vấn đều bắt nguồn từ biến động model khi đầu vào ghi được giống nhau; code F1b không nằm trên đường đó;
    - GEN-T04 lệch từ c1 t3 (DeepSeek) → tóm tắt call_1 khác → c2 t1 hiểu khác. Tóm tắt của mốc tự nó sai: ghi "khách đồng ý đặt hàng".
  - **Lỗi F1b mới (D1, chưa sửa):** câu lặp ý khi có goal `gift_status` hoặc `stale_promo`.
  - **Replay:** dry v2 đạt; replay thật `midzid/sudocode-rfa-replay-1114` **xong** (freeze ok, 0 lỗi, 0 lỗi API). Chi tiết §8.11 mục "Kết quả replay thật".
    - R1, R6: biến động DeepSeek **xác nhận** trên cùng một prompt (R1: 7 / 20 lần ra defer; R6: 11 / 20 lần ra asks [gift, price]); prompt v36 = v37.
    - R2: `asks ∋ recommend` **không tái hiện** (0 / 10 với tóm tắt F1b, 0 / 10 với tóm tắt mốc) → mắt xích khởi phát của GEN-T04 chưa giải thích được.
    - H-A (R3): khi đã có `asks = [recommend]`, 10 / 10 lần chuyển focus sang Urban Classic; mẫu do code `h_recommend` chọn, không phải Jev → lỗi nền tất định, có ở cả v36.
    - H-B (R4): `price_claim_unverified` tái hiện tất định ở tiền tố F1b, cả v36 lẫn v37; đối chứng mốc không có → lỗi nền tất định.
    - H-C (R5): báo giá trước size 3 / 20 lần (v36 Full 1 / 5, v37 Full 0 / 5, v36 Baseline 1 / 5, v37 Baseline 1 / 5) → dưới ngưỡng 2 / 5, **không xác nhận**; hành vi có thật nhưng hiếm, không do F1b.
    - D1 (R7a–c): v37 lặp câu, v36 không, tái hiện tất định; dựng lại thiếu 3 slot nên tách khỏi kết luận nhân quả chắc chắn.
  - **Chờ duyệt:** (1) có chạy 4 job lặp hay không (chỉ còn cần cho Q1–Q3 tổng hợp và tần suất mắt xích GEN-T04); (2) patch hẹp D1 (đề xuất ở §8.11); (3) H-A / H-B là lỗi nền tất định, thuộc hướng C, chưa đề xuất sửa.
- **14/11, sáu kết luận (đã duyệt, §8.12):**
  - Bốn job GPU cũ tạm hoãn.
  - H-A / H-B đã đọc nguồn: lỗi **gắn đối tượng**, không phải bịa giá.
    - H-A: `recommend` ghi đè focus.
    - H-B: kiểm claim chỉ theo target hiện tại, câu mẫu khẳng định quá mức.
    - Chưa sửa.
  - D1 đã vá hẹp (`_promo_note` + truyền `turn_kinds` ở renderer), bản v38. Đang kiểm bằng job CPU `midzid/sudocode-d1-check-1114` với tiêu chí C1–C5 chốt trước.
  - Sau kiểm D1: đề xuất phép đo tiếp kèm tiêu chí D1. Không ghép số v38 với v37 cũ. Trước `b2-final` chạy toàn dev 92 ca một lần. H13 khóa.
  - Chưa sửa C, chưa đóng `b2-final`, chưa mở H13.
  - **Kết quả kiểm D1 (job `d1-check-1114`): C1–C5 ĐẠT.**
    - 6 lượt D1 bỏ đúng câu lặp; 7 lượt phải giữ và RT-10 không đổi; goals không đổi ở 216 lượt.
    - `b2_round_f_check` v38 47 / 0.
    - Ba test `target_arch` / `outcome_contract` / `planner_target_matrix` lỗi giống hệt nhau ở v37 và v38, nghi do job đặt `PLANNER_VARIANT=b2_jev` → **chưa kiểm được**. Chờ duyệt job CPU chạy lại với `b1`.
  - Ba test phụ lỗi do job của mình gọi test trực tiếp với `PLANNER_VARIANT=b2_jev`; `variants_cpu.py` chuẩn xoá env cấu hình. Không phải lỗi code; sẽ kiểm lại trong bước trước khi chạy dev.
  - **Phép đo v38 đã chốt tiêu chí (§8.13):** dev 92 ca Full / Baseline một lần, khoảng 1,7 GPU-giờ, cần key. Tiêu chí D1-a/b/c và không lùi so với mốc dev có biên. Người dùng đã duyệt (biên chỉ là ngưỡng điều tra; chặn tạo đơn theo lượt thiếu căn cứ; RQR có tử / mẫu; `outcome_contract_check` bắt buộc).
  - Cổng `dev_v38_gate.py` v38-dev-2 đã kiểm trên Kaggle (`gate-check-1114`, §8.13). Hai job dev v38 đã đẩy, **chờ gắn key DeepSeek + Jev rồi chạy**: `elylish11/sudocode-dev38-full-1114`, `midzed/sudocode-dev38-base-1114`. Sau đó chạy job chấm CPU. Chưa đóng `b2-final`, chưa mở H13, chưa commit.
  - 14/11: người dùng đã bấm chạy hai job dev (không đẩy lại); duyệt job chấm CPU khi đủ kết quả.
    - Cổng lúc bắt đầu đo là v38-dev-2 (lưu ở `runs/freeze/gates/`). Phát hiện lỗi cổng: v2 chưa kiểm đủ quy tắc địa chỉ D1, giá khách nêu, COD D2. Đã viết v38-dev-3 trước khi có kết quả.
    - Sẽ chấm **cả mốc lẫn v38** bằng v3, giữ kết quả v2 để đối chiếu.
    - Kiểm v3: `gate-check-1114` lần 3.
    - Lần 3 lộ hai lỗi cổng trên mốc, phát hiện trước khi có kết quả v38: đọc sai "3 triệu 9," (RT-09); gắn D2 sai khi khách đã nói COD (V3-013, V3-016). Đã viết **v38-dev-4**, kiểm ở lần 4: trên trace thật cho kết quả đúng. Selftest 47/2, hai lỗi do fixture test (đã sửa, code cổng không đổi). Chấm bằng **v4** cho cả mốc lẫn v38; v2 dùng để đối chiếu.
    - Dev Full v38 xong (số sơ bộ: TSR 93,5%, HR 7,1%, RQR 3,3%). Baseline đang chạy. **Chờ Baseline xong mới chấm.**
    - Dev Baseline v38 xong: 92/387/0 lỗi, freeze khớp, `variants_cpu` 10/10, clean 0. Đã đẩy job chấm CPU `midzid/sudocode-dev38-score-1114` (selftest, reference_eval, latency thường + strict, dev_report, cổng v4 và v2 trên v38 và mốc). Chờ kết quả.
    - Kết quả chấm: cổng v4 **KHÔNG ĐẠT** (v2 cũng vậy).
      - TA1 ×3: chào lại bằng sản phẩm cũ thay cho sản phẩm khách nêu; có từ mốc.
      - Understanding `TypeError` ở GEN-T25 c2t2.
      - Điều tra: BTCL-066, RQR (1/30 so với 1/52), 3 trace mâu thuẫn COD.
      - Lỗi tự chọn COD: 0.
      - **Chờ duyệt hướng sửa**; chưa đóng `b2-final`.
  - 14/11 (§8.14): giữ B2, chưa đóng `b2-final`.
    - Đã sửa TypeError bằng `_conform` (test cục bộ 21/0). **Chờ duyệt kết quả và freeze mới.**
    - TA1: đã mô tả cách sửa, **chờ duyệt trước khi sửa**.
    - Chẩn đoán xong GEN-T16, GEN-T18, BTCL-066 và ba nhãn COD. Phát hiện thêm "địa chỉ dính đuôi" ở 4 đơn. **Chờ chốt phạm vi cuối.**
    - 14/11 (tiếp): TA1 và chuyển máy đã sửa theo đối tượng / trạng thái. Test cục bộ 17/0; hồi quy 4/4.
    - **Địa chỉ dính đuôi, chờ duyệt phương án:**
      - Span: address / payment observation của understanding (đã kiểm nguyên văn).
      - Parser có sẵn: `_resolve_overlap` + `_slot_value("address")` (chỉ strip, ≥6 ký tự); `_slot_value("payment")` theo label của model; regex thanh toán / `ADDRESS_RX` của pipeline rules (B1).
      - Lựa chọn A / B / C như báo cáo 14/11.
    - 14/11 (tiếp 2): đã khép fail-closed cho `_conform`, các rào TA1, câu chuyển máy `queued`, địa chỉ A + C. Fixture chốt (34 / 33 / 11 OK cục bộ). Job `fix-check-1114` đang chạy. Chưa freeze, chưa chạy dev, chưa mở H13.
    - `fix-check-1114`: tất cả đạt (3 test mới, 8 hồi quy, `variants_cpu` 10/10, selftest cổng 49/0). **Chờ duyệt đóng freeze v39.**
  - 14/11 (§8.15): freeze ứng viên v39 (237 file), cổng v5. Job CPU `v39-cpu-1114` đang chạy. Qua thì đẩy dev39 Full / Baseline + BTCL-066 cách ly × 2; người dùng gắn key DeepSeek + Jev rồi bấm chạy.
    - v39 CPU qua; đã đẩy dev39 Full / Base + b066-iso (nnttrang). Chờ gắn secrets và kết quả.
    - BTCL-066 × 2 cách ly: lỗi TÁI HIỆN (0/2; v38 + v39 0/3; mốc 1/1). Chẩn đoán ở §8.15. Chưa sửa. Hai job dev39 chưa chạy (chờ secrets).
  - 14/11 §8.16: đề xuất patch hẹp BTCL-066 (hợp đồng recommend, chống chọn lại noop, nghĩa vụ trả lời, tách quyền dữ liệu) + phạm vi tối thiểu GEN-T16 (context nêu nội dung CART / ALL + đối tượng đề nghị). **Chờ chốt test + phạm vi.**
  - 14/11 §8.17: phạm vi + tiêu chí chốt trước (A1 / A2 BTCL-066 thu hẹp; B context GEN-T16; C1–C3 F5 tối thiểu, C4 tùy chọn; test CPU; chạy cách ly 6 lần ca đích + 15 đối chứng). ĐÃ DUYỆT 15/11 (A1–A2, B, C1–C3; không C4).
  - 15/11 §8.18: đã sửa + test 40/0 cục bộ, freeze ứng viên v40, job CPU midzid/sudocode-v40-cpu-1115. Tiếp: CPU qua → job cách ly GPU 21 lần (elylish11, cần secrets). Còn đơn sai → dừng, không sang chốt B2. Chờ duyệt: C4, H13, commit.
  - 15/11 CPU v40 QUA: freeze 238/238 khớp, gate_is_v5 / variants_cpu (gồm f5 40/0) / clean_env 75/0 / gate selftest 62/0 đều rc 0. Job GPU cách ly CHƯA đẩy: rà bộ đối chứng thiếu ca (E2E: không ca đối chứng nào có lượt COD / thanh toán / địa chỉ / từ chối / đổi mẫu khi đang có đề nghị đặt; fixture: từ chối và đổi mẫu chỉ kiểm đề nghị mất, chưa kiểm không ghi và lượt "chốt" sau đó). Chờ duyệt phương án bổ sung (a/b/c).
  - 15/11 DUYỆT (b)+(c). Ngoài freeze, ở `runs/extra_1115/` (MANIFEST.json = sha256 + cấu hình): `f5_extra_check.py` 27/0 cục bộ (I: COD / thanh toán / địa chỉ không ghi; D: từ chối / để sau → đề nghị mất, "chốt" sau đó không gắn đề nghị cũ; S: đổi mẫu → chỉ Y). Thăm dò R (không chặn): R2 act=accept gắn cho câu chỉ nói thanh toán → TẠO ĐƠN; R3 câu "Giao về <địa chỉ> nhé" có yêu cầu place_order → C3 gắn đề nghị → TẠO ĐƠN. Trace dev38 GEN-T16 cho thấy DeepSeek thật gắn accept + place_order cho đúng hai lượt đó. 5 kịch bản CTL1115-* (validate 0 lỗi). Bộ chặn `iso_driver.py` (W1–W4 lỗi ghi, L1–L2 lộ dữ liệu) tự kiểm trên trace dev38: bắt đúng GEN-T16 (W2 + W3), 16 ca khác không dừng nhầm. Job CPU midzid/sudocode-extra-cpu-1115 (không API) đã đẩy; job GPU `push_iso2-v40-1115.sh` (elylish11, từng kịch bản, iso_d → iso_a → iso_b → iso_c) soạn sẵn, chưa đẩy.
  - 15/11 user: KHÔNG đẩy GPU v40. extra-cpu-1115 không kiểm được (đẩy kernel với dataset cũ). Thêm test v2 `f5_authority_check_v2.py` (R2–R6 chặn, V1–V5 hợp lệ; trên v40: 6 R không đạt, 5 V đạt) + `ctrl_report_v2.py`, MANIFEST_v2.json; job extra2-cpu-1115. Đề xuất v41 tối thiểu §8.19 CHỜ DUYỆT: V41-1 hàm quyền tạo đơn chung 3 đường (pseudo/price cho accept, che span thanh toán/địa chỉ, regex mới ACCEPT_CUE_RX), V41-2 C3 mang revision đề nghị. Kèm duyệt: đổi kỳ vọng ca C3 trong b2_btcl066_f5_check (2 bước), BTCD7-025 thành "chưa hoàn thành" + expect_1115_v2.
  - 15/11 user: chưa duyệt v41 nguyên gói; đồng ý HƯỚNG kiểm cứng chung + C3 giữ revision. extra2-cpu-1115 hợp lệ (v1 27/0; v2 6 R không đạt, 5 V đạt; hash 12/12). Đề xuất V41-1 thu hẹp + V41-2 ở plan §8.20 CHỜ DUYỆT: kiểm chỉ CHẶN (K1 pseudo, K2 giá cho cả accept; K3 stance tại động từ đặt; K4 accept+withdrawn; K5 che span giao hàng của model ∪ PAY_RX/ADDRESS_RX có sẵn; K6 DEFER_RX phụ mới), giới hạn (1)–(5); fixture C3 2 bước + đối chứng revision không đổi; BTCD7-025 giữ chính sách, báo trượt theo bộ chấm.
  - 15/11 DUYỆT triển khai ứng viên v41 (K1–K2, V41-2, test C3; K3–K6 theo ràng buộc). Đã làm §8.21: kỳ vọng v3 ghi trước; chỉ request_state.py + test C3; freeze ứng viên runs/freeze/20261115-v41-cand (238 tệp, đổi 2); cục bộ v3 32/0, v2 11/0, v1 27/0, variants_cpu / clean_env / selftest qua. Còn đường tạo đơn sai có điều kiện P1 / P2 + đề nghị không kèm giá. Job CPU midzid/sudocode-v41-cpu-1115 QUA (freeze 238/238, cổng v5, variants_cpu 0 trượt, clean_env 75/0, selftest 62/0, f5 trong freeze 42/0, v1 27/0, v2 11/0, v3 32/0; P1/P2 vẫn tạo đơn). Dừng trước GPU vì còn đường tạo đơn sai đã biết. User chọn (a) (ngoại lệ chẩn đoán, không phải b2-final): expect_1115_v2 + iso_driver_v2 + ctrl_report_v3 (MANIFEST_v4); job elylish11/sudocode-iso-v41-1115 đã đẩy, đã chạy: 7/26 hợp lệ, bộ chặn DỪNG ở GEN-T16 (đơn chỉ màng lọc, lỗi đối tượng từ lượt 8), 19 ca chưa chạy; iso_d 5/5 đạt. Chờ quyết định bước tiếp.
  - 15/11 DUYỆT (1) sửa hẹp đối tượng GEN-T16 → ứng viên v42 (§8.23): target_ambiguous → hỏi rõ + liệt kê; freeze runs/freeze/20261115-v42-cand; CPU midzid/sudocode-v42-cpu-1115; GPU iso-v42 (GEN-T16 trước). Báo cáo v41 giữ: có đơn sai, 19 lượt chưa chạy.
  - 15/11 CPU v42 QUA (freeze 238/238, cổng v5, variants_cpu 0 trượt, clean_env 75/0, selftest 62/0, v1.1 27/0, v2 11/0, v3 32/0, v4 6/0, hash 21/21; v1 25/2 do chính sách V42). Job GPU elylish11/sudocode-iso-v42-1115 đã đẩy, chờ gắn DEEPSEEK + TYPESAFE và bấm chạy.
  - 15/11 GPU v42: 17/26 hợp lệ; DỪNG ở RT-02 (đơn sai: model gắn đồng ý cho câu 'sếp bên em đồng ý freeship'); GEN-T16 không đơn nhưng chưa hoàn thành; 9 lượt chưa chạy. Chờ quyết định.
  - 15/11 v43 (chuẩn cấp quyền đặt hàng, §8.24): freeze runs/freeze/20261115-v43-cand (chỉ request_state.py); CPU midzid/sudocode-v43-cpu-1115 QUA (v5 26/0, v4 6/0, v3 32/0, v2 11/0, v1.1 27/0, variants 0 trượt, clean_env 75/0, selftest 62/0, hash 43/43). BLOCKER exchange_offer (accept không kiểm quyền) — chưa sửa. GPU elylish11/sudocode-iso-v43-1115 (probe ×5 → cổng → iso 26) đã đẩy, chờ gắn key + chạy.
  - 15/11 GPU v43: probe QUA (âm 0/40, dương 40/40); iso 26/26 không đơn sai; HỒI QUY GEN-T27 (lệnh 'Ừ chị lấy' bị thu hẹp); blocker exchange_offer; GEN-T16 chưa hoàn thành → v43 CHƯA đủ điều kiện chốt B2. Chờ quyết định.
  - 15/11 v44 ĐANG LÀM (bridge side-v43-resolve): patch request_state.py (self_command GEN-T27, op_authority/op_refused/consent cho đổi/trả/đổi địa chỉ, authorize kiểm consent) + plan_primitives.py (_order_for nhiều đơn không theo ref, đổi địa chỉ authorize trước target/settle, op_gate→ask_repeat). Freeze runs/freeze/20261115-v44-cand (2 tệp). Mốc v6.1 trên v43: TP1/TP2 tái hiện GEN-T27; MN1–3 KHÔNG tái hiện (Jev không được chọn O2 — invalid_tuple); MP1 (model tự gắn O2) ghi order.update; OP2–OP4 fixture chưa chạy được (lỗi fixture) → v6.2 có chẩn đoán. Job CPU midzid/sudocode-v44-cpu-1115 đang chạy (v44 + mốc v43 cuối job). Chưa GPU.
  - 15/11 v44b: CPU midzid/sudocode-v44c-cpu-1115 QUA trên v44b (freeze 238/238; ops v6.4 25/0 — TP1–TP4, TN1–TN5, OP1–OP4, QN1–QN9, MN1–MN3; v5 26/0, v4 6/0, v3 32/0, v2 11/0, v1.1 27/0, variants 34/0, clean_env 75/0, selftest 62/0, validate probe2 0 lỗi). Mốc v43 15/10 (TP1–2, QN1–4, QN6–9 tái hiện lỗi ghi). Thăm dò mở MP1: model tự gắn ref O2 khi khách có 2 đơn → cả v43 và v44b ghi đổi địa chỉ O2 (giới hạn đã biết, không sửa trong gói vì nghi vấn Jev-chọn-O2 không tái hiện). MANIFEST_v8. Job GPU elylish11/sudocode-iso-v44b-1115 (ops v6.4 → probe 16×5 + cổng → probe2 10×3 + cổng → iso 26 mới, W1–W5) ĐÃ ĐẨY, chờ gắn DEEPSEEK_API_KEY + TYPESAFE_API_KEY và bấm chạy.
  - 15/11 GPU v44b (chuyển sang midzid/sudocode-iso-v44b-1115; bản elylish11 đã hủy): ops v6.4 25/0, v5 26/0, v4 6/0, v3 32/0, freeze 238/238. Probe 16×5 QUA (âm 0/40 ghi sai, dương 40/40). Probe2 10×3 TRƯỢT cổng: 3 "ghi sai" đều ở FN6-AMBIG, nhưng tiền điều kiện KHÔNG đạt cả 3 lần — call_2 "lấy cho chị thêm một máy lọc nước RO… giao về… thanh toán khi nhận hàng" bị DeepSeek gắn add_to_cart (không place_order) 3/3 → chỉ có 1 đơn → đổi địa chỉ đơn duy nhất OD600001 (không phải lỗi mơ hồ 2 đơn). Lỗi bộ chấm: probe_eval_v2 không dùng pre_ok cho ca âm (phải tính "không hợp lệ"). FN1–FN3 không được kiểm (model gắn đúng nhãn, đường chặn không chạy). Dương 12/12. Iso KHÔNG chạy. Chờ quyết định: (1) sửa bộ chấm pre_ok + tiền điều kiện FN6; (2) xử lý miss "lấy thêm … giao về … COD" → add_to_cart (đường đặt hàng bị bỏ, lỗi sản phẩm thật).
  - 15/11 DUYỆT mục 1 (giữ nguyên code sản phẩm v44b; không chạy lại phần còn bằng chứng; không mở H13; không commit). Lỗi "lấy thêm … giao về … COD" → add_to_cart ghi là GIỚI HẠN ĐÃ BIẾT, chưa sửa trong gói. Đã làm (chỉ tệp mới ở runs/extra_1115/, v2 + FN6-AMBIG v1 giữ nguyên làm bằng chứng): `probe_eval_v3.py` (tiền điều kiện chặt cho cả âm và dương: từng cuộc gọi trước tạo đúng đơn kỳ vọng, mã khác nhau, không order.update trước; sai → không hợp lệ, không đạt, không tính ghi sai; nhiều thư mục kết quả, mỗi kịch bản đúng 3 lần), `probe_eval_v3_selftest.py` (kỳ vọng viết trước: A1–A12 tổng hợp, B1–B5 chấm lại dữ liệu thật v44b), `probe2_1115_v2/FN6-AMBIG-V2.json` (call_2 dùng mẫu câu mua rõ, bỏ "thêm"; pre_skus FAN + RO9), `prev_probe2_v44b/` (27 lần của 9 kịch bản dùng lại), MANIFEST_v9. Job GPU midzid/sudocode-iso-v44b2-1115: freeze_apply v44b → selftest (CPU, trượt thì dừng) → validate → FN6-V2 ×3 → cổng v3 (27 cũ + 3 mới) → iso 26. ĐÃ ĐẨY, chờ gắn DEEPSEEK_API_KEY + TYPESAFE_API_KEY và bấm chạy.
  - 15/11 GPU v44b2 (midzid/sudocode-iso-v44b2-1115): selftest probe_eval_v3 17/17; freeze v44b khớp; FN6-AMBIG-V2 tiền điều kiện ĐẠT 3/3 (OD600001 quạt + OD600002 RO — bỏ "thêm" là tạo được đơn, củng cố giả thuyết chữ "thêm"). Cổng v3 TRƯỢT: 1/3 GHI SAI THẬT (r1: DeepSeek tự gắn target_ref=O2 cho câu không nêu đơn → code tin → order.update đổi địa chỉ OD600002) = MP1 tái hiện trên model thật. r2/r3: không ghi, hold ambiguous_turn, nhưng câu trả lời "nói lại giúp em" chứ không hỏi đơn nào. 27 lần cũ hợp lệ, dương 12/12, FN1–FN3 vẫn không được kích hoạt. Iso KHÔNG chạy. v44b chưa đủ điều kiện chốt B2. Chờ quyết định: đề xuất sửa MP1 (cần duyệt) hoặc ngoại lệ chẩn đoán chạy iso.
  - 15/11 user chọn phương án 1 (MP1 không được là giới hạn đã biết để chốt; không chạy ngoại lệ iso trên v44b; không gộp "lấy thêm…"). Đã viết TRƯỚC kỳ vọng `runs/extra_1115/f5_target_check_v7.py` (22 ca chặn TA/TB/TC/TD/TE/TF/TG + 2 thăm dò TP-ORD/TP-VAR; bản khóa .expectations_frozen.py) và đề xuất `docs/DE-XUAT/DE-XUAT-MP1-RANG-BUOC-DON-DICH-2026-11-15.md` (căn cứ đơn đích: mã đơn / sản phẩm khớp duy nhất / đơn duy nhất / tham chiếu đã xác định trong cuộc gọi; ref model / Jev chỉ là gợi ý; kiểm lại ở authorize trước order.update; hold mơ hồ chỉ thiếu đơn → hỏi đơn nào). CHỜ DUYỆT gói + D1 (size/màu qua find_variant), D2 (không hỗ trợ "đơn thứ hai"), D3 (mẫu mã đơn OD+6 số). Chưa đổi code sản phẩm.
  - 15/11 DUYỆT MP1 + D1/D2/D3 kèm điều kiện. Trước code: kỳ vọng v7.1 (TG2 ghi O2 theo căn cứ; mọi ca không ghi kiểm 0 lời gọi order.update kể cả bị từ chối; TP-VAR thành ca chặn → 23 chặn + 1 thăm dò; bản khóa cập nhật), đề xuất §8 (hiệu lực order_focus, phạm vi phục hồi needs_clarification, trả lời câu hỏi chọn đơn, accepted_proposal). Đã code ứng viên v45: request_state.py (order_basis / known_orders / focus / _target_only / _bind_answer / kiểm authorize trước order.update), plan_primitives.py (_order_for_v45, địa chỉ của yêu cầu, đánh dấu đã hỏi chọn đơn, clarify lượt chỉ thiếu đơn), generator.py + generator_goals.json (which_orders_action). Freeze runs/freeze/20261115-v45-cand (238, đổi 4). FP5-NAMED / FP6-ANSWER viết SAU code, TRƯỚC mọi lần chạy (lệch so với đề xuất "viết trước code"). MANIFEST_v10. Job CPU midzid/sudocode-v45-cpu-1115 ĐÃ ĐẨY (tự chạy).
  - 15/11 CPU v45 (midzid/sudocode-v45-cpu-1115) QUA: freeze v45 238/238; bản khóa v7.1 trùng; v7.1 trên v45 23/0 (TP-ORD thăm dò → ask_which_order, không ghi); hồi quy ops v6.4 25/0, consent v5 26/0, object v4 6/0, authority v3 32/0, v2 11/0, v1.1 27/0, variants_cpu 0 trượt, clean_env 75/0, gate selftest 62/0; validate probe2_v2/_v3 0 lỗi. Mốc v44b: v7.1 9/14 (trượt TA1, TA2, TA4, TB2, TB3, TB4, TC1–TC4, TE1, TF2, TF4, TG2). Lệch so với dự đoán mốc: TA3 (Jev ép O2) và TV ĐẠT trên v44b (TA3 đã bị chặn từ v44; TV model gắn đúng O2 nên v44b ghi đúng — TV không chứng minh được bản sửa), TB3/TB4 trượt trên v44b (không dự đoán). Job GPU midzid/sudocode-iso-v45-1115 ĐÃ ĐẨY, chờ gắn DEEPSEEK_API_KEY + TYPESAFE_API_KEY và bấm chạy.
  - 16/11 GPU v45 (midzid/sudocode-iso-v45-1115) DỪNG ở cổng probe2 → iso 26 KHÔNG chạy. Probe 16×5 QUA (âm 0/40 ghi sai, dương 40/40). Probe2 12×3 (probe_eval_v3): âm 18/18 hợp lệ, 0 ghi sai (FN6-AMBIG-V2 3/3 không ghi + hỏi đúng "anh/chị muốn đổi địa chỉ giao cho đơn nào" 3/3: r1 qua phục hồi target-only, r2/r3 model gắn O2 bị bỏ qua); FN1–FN3 vẫn không được kích hoạt. Dương 15/18: FP1–FP5 3/3 (FP5-NAMED đúng OD600002 3/3), FP6-ANSWER 0/3 → TRƯỢT. Nguyên nhân (đã kiểm trên trace + schema): lượt 2 gắn đúng R1 → OD600002 (target_answer) nhưng hỏi lại địa chỉ (ask_address) vì địa chỉ lượt 1 không được lưu: `_stated_address` chỉ nhận stance "stated", còn DeepSeek thật trả stance "chosen" cho địa chỉ (STANCES có cả hai); fixture v7.1 dựng sẵn "stated" nên CPU không bắt được. Không lời gọi order.update nào sai. Theo chỉ thị: dừng, không sửa thêm vòng. Chờ quyết định.
  - 16/11 DUYỆT sửa hẹp FP6. Test v8 VIẾT TRƯỚC (v7.1 + kết quả v45 giữ làm lịch sử): TH1/TH2 luồng FP6 stance stated / chosen; TN-ASK/NEG/COND/REP/OTHER không nhận địa chỉ sai stance / chủ thể (0 lời gọi order.update, hỏi địa chỉ); TI1 địa chỉ gắn đúng yêu cầu, không dùng cho yêu cầu đơn quạt mới → 31 chặn + 1 thăm dò; bản khóa. Sửa: `_stated_address` nhận stance ∈ {stated, chosen} (ADDRESS_STANCES), giữ chủ thể self + span. Freeze runs/freeze/20261116-v46-cand (chỉ request_state.py đổi so với v45). Đối chiếu phạm vi: _stated_address chỉ gọi ở 2 chỗ (mở change_order_address B2, _bind_answer), op_address chỉ đọc ở _order_op_check change_order_address → không chạy lại probe mua 16×5; kết quả 80 lần giữ nhãn v45. Cổng riêng fp6_fn6_check (FP6 3/3; FN6-V2 3/3 không ghi + ask_which_order, không ask_repeat). MANIFEST_v11. Job CPU midzid/sudocode-v46-cpu-1116 ĐẨY.
  - 16/11 CPU v46 (midzid/sudocode-v46-cpu-1116) QUA: freeze v46 238/238, bản khóa v8 trùng; v8 trên v46 31/0; v7.1 trên v46 23/0; ops v6.4 25/0, consent v5 26/0, object v4 6/0, authority v3 32/0, v2 11/0, v1.1 27/0, variants_cpu 0 trượt, clean_env 75/0, gate selftest 62/0; validate 0 lỗi; bộ chấm biên dịch được. Mốc v45: v8 29/2 (trượt TH2 stance chosen — đúng lỗi FP6 — và TI1, vì lượt ghi đầu của TI1 cũng dùng địa chỉ chosen). Job GPU midzid/sudocode-iso-v46-1116 ĐÃ ĐẨY (probe2 12×3 + fp6_fn6_check + iso 26; không probe mua 16×5), chờ gắn key + chạy.
  - 16/11 GPU v46 (midzid/sudocode-iso-v46-1116) HOÀN TẤT, mã thoát 0 (3143 s). Probe2 12×3 (probe_eval_v3) QUA: âm 18/18 hợp lệ, 0 ghi sai, 0 không hợp lệ; dương 18/18 (FP1–FP6 mỗi nhóm 3/3); 0 lệnh rõ bị chặn. fp6_fn6_check QUA: FP6-ANSWER 3/3; FN6-AMBIG-V2 3/3 hợp lệ, 0 lời gọi ghi, ask_which_order, không ask_repeat. Âm chưa được model kích hoạt: FN1, FN2, FN3, FN4 (v45: FN1–FN3). Iso 26/26 hợp lệ, bộ chặn không dừng, 0 ghi sai; CTL1115 5/5 đạt; TSR 22/26 (v43: 21/26): còn trượt BTCD7-025 (chính sách, expect none) + GEN-T16-01 ×3 (an toàn, chưa hoàn thành — như dự kiến); GEN-T27-01 hết hồi quy. Báo cáo runs/extra_1115/report_iso_v46.json. Probe mua 16×5 KHÔNG chạy trên v46 (giữ kết quả v45). Chờ quyết định chốt B2 / bước tiếp; chưa H13, dev92, commit.
  - 16/11 NGƯỜI DÙNG CHỐT B2-v46 làm cấu hình chính, khép gói MP1/FP6. Đã đóng snapshot runs/snapshots/20261116-b2-v46 (source.tar.gz = gói job iso-v46, 238/238 khớp freeze v46; files.txt 2374, sha256.txt, config.json, jobs/ v45+v46, results/v45 + results/v46 tách nhãn, MANIFEST.md + giới hạn) và báo cáo docs/PLAN/BAO-CAO-CHOT-B2-V46-2026-11-16.md. Chuẩn bị dev92 trên v46: elylish11/sudocode-dev46-full-1116 (full) + midzed/sudocode-dev46-base-1116 (baseline_no_memory) ĐÃ ĐẨY, chờ gắn DEEPSEEK + TYPESAFE và bấm chạy. H13 khóa; không sửa thêm; không commit. Có ghi sai mới → dừng báo; lỗi chất lượng khác chỉ phân tích.
  - 16/11 Review nêu 3 rủi ro tích hợp (I1 brief đơn nhiều dòng chỉ giữ dòng đầu; I2 focus cũ sau khi đặt thêm đơn; I3 địa chỉ mức lượt bị dùng cho yêu cầu đổi địa chỉ cũ) + lưu ý mặc định source là B1 (đã ghi vào MANIFEST snapshot). dev92 CHƯA chạy (người dùng chưa bấm) → kiểm trước bằng fixture CPU `runs/extra_1115/f5_integration_check_v9.py` (kỳ vọng an toàn viết trước, bản khóa; I1, I1-CTL, I2, I3 chặn; I1-P thăm dò) trên v46, không đổi code. Job midzid/sudocode-v46-int-1116 ĐÃ ĐẨY (tự chạy). Tái hiện ghi sai → issue riêng, chờ quyết định; không → tiếp dev92.

## 16/11 — Fixture tích hợp v9 trên v46: TÁI HIỆN GHI SAI (I1, I2, I3)
- Job `midzid/sudocode-v46-int-1116`: I1-CTL đạt; I1, I2, I3 hợp lệ và có `order.update` sai. Chi tiết: `docs/DE-XUAT/ISSUE-V46-GHI-SAI-TICH-HOP-I1-I3-2026-11-16.md`.
- Đã dừng theo chỉ đạo: không sửa, không chạy dev92, không H13, không commit. **Chờ duyệt:** sửa (gói v47) hay chạy dev92 trên v46 kèm giới hạn.

## 16/11 — Duyệt gói v47 (I1–I3)
- Người dùng duyệt sửa I1–I3; chưa chạy dev92 trên v46; giữ nguyên v46 + kết quả lịch sử; ghi rõ ba lỗi tái hiện bằng fixture ép nhãn, chưa quan sát trên model thật.
- Đã làm: code v47 (2 file), freeze `20261116-v47-cand`, test `f5_integration_check_v10` (khóa), job CPU `midzid/sudocode-v47-cpu-1116`.
- Lệch: ca đối chứng mới của v10 viết cùng lúc với code, không trước.
- Tiếp: CPU đạt → probe2 12×3 + fp6_fn6 → iso 26 (cần gắn key). Trượt → dừng báo. Không H13 / dev92 / commit.

## 16/11 — CPU v47: TRƯỢT I3, đã dừng
- I1, I2 đã sửa (đạt, mốc v46 trượt). I3 vẫn ghi sai: lượt mua bị cổng `intent_only` chặn nên không có yêu cầu `place_order`, `address_for` không thấy → dùng địa chỉ của lượt. I2-SAME không hợp lệ (fixture). Hồi quy sạch.
- Chờ duyệt: (a) vòng sửa I3 hẹp — địa chỉ mức lượt chỉ dùng cho yêu cầu đổi địa chỉ cũ khi lượt đó KHÔNG có ý định/yêu cầu đặt hàng nào (kể cả bị chặn) — kèm sửa tiền đề I2-SAME; hoặc (b) hướng khác.

## 16/11 — V48 binding địa chỉ (người dùng: "xem khả thi thì thực hiện")
- Thiết kế: `docs/DE-XUAT/DE-XUAT-V48-BINDING-DIA-CHI-2026-11-16.md` (theo FINAL.md bridge; phản biện vòng 2 chưa được Fable xét).
- Test v11 `f5_address_binding_check_v11.py` viết và khóa TRƯỚC code (sha256 037d801d1530dae2…); mốc trên v47: job `midzid/sudocode-v11-base-1116`.
- Phạm vi file dự kiến: request_state, plan_primitives (không ép hai file; agent.py chỉ nếu cần). Sửa đường bổ sung địa chỉ của mua → phải chạy lại probe mua 16×5 trên v48.

## 16/11 — Mốc v11 trên v47 + code v48
- Mốc `midzid/sudocode-v11-base-1116`: v47 ghi sai ở I3-INT/NOREQ/CART (×2 thứ tự Jev), NOT-ASKED, FP6-CONFLICT, ASKED-STANCE, C2 (ghi 2 đơn một địa chỉ), BOUND (biên không kiểm địa chỉ). Ca dương đạt. C4 không hợp lệ (câu mua không tạo đơn) → sửa riêng tiền đề C4 thành v11.1 (sha d04b214f…) TRƯỚC code v48, ghi rõ.
- Code v48 (`request_state.py`, `plan_primitives.py`; agent.py không đổi — B2 không còn gọi `_update_address`, nhánh `having` bị biên chặn). Freeze `runs/freeze/20261116-v48-cand`. CPU `midzid/sudocode-v48-cpu-1116`.

## 16/11 — CPU v48 TRƯỢT (CORRECT, ghi sai mới), đã dừng
- Chi tiết + hướng sửa: `docs/DE-XUAT/DE-XUAT-V48-BINDING-DIA-CHI-2026-11-16.md` (mục cuối). Chờ duyệt.

## 16/11 — Duyệt gói v49 (hiệu lực binding khi xung đột)
- Người dùng duyệt bản sửa hẹp: binding có nguồn đúng phải bị TREO khi có xung đột chưa giải quyết; chỉ phục hồi bằng lệnh rõ / trả lời câu hỏi địa chỉ đã gửi; không cờ theo lượt; giữ CORRECT + kết quả v48 làm bằng chứng; "sửa phần này đừng phát sinh hay làm sai phần cũ đã đúng".
- Test v12 `f5_address_binding_check_v12.py` khóa TRƯỚC code (sha 105eb2d6…). Ghi trước: CORRECT (v11.1, giữ nguyên câu + kỳ vọng) dự kiến chuyển "hoàn thành ngay" → "chưa hoàn thành, hỏi lại" trên v49 → báo KHÔNG ĐẠT có chủ đích, không tính là đã hiểu được câu.
- Mốc v12 trên v48: job `midzid/sudocode-v12-base-1116`. Bản sao file v48: `runs/extra_1115/v48_files/`.

## 16/11 — Mốc v12 trên v48 + code v49
- Mốc `midzid/sudocode-v12-base-1116`: CORR-BLOCKED ×2 ghi sai X (tái hiện); CORR-OK, OTHER-WORK ×2, NO-CONFLICT, SAME-ADDR đạt. AFTER-* / RECOVER / BOUND-CONFLICT không hợp lệ trên v48 (lượt xung đột đã ghi X nên không có trạng thái treo để kiểm) — đúng bản chất, không sửa test.
- Code v49: chỉ `harness/request_state.py` (plan_primitives giữ nguyên v48). Binding có `status` valid / suspended + `addr_history`; `_conflict_check` (cả lượt câu mơ hồ) treo binding khi lượt có địa chỉ stated/chosen khác X, không gắn cho chủ nào, không thuộc rõ việc khác; `bound_address` + `authorize` (`address_suspended`) cùng đọc hiệu lực; chỉ L1 (request mới) / L2 (trả lời câu hỏi địa chỉ đã gửi) thay được. Freeze `runs/freeze/20261116-v49-cand`. CPU `midzid/sudocode-v49-cpu-1116`.
- Cổng CPU (ghi trước): v12 đạt hết; v11.1 đạt hết TRỪ CORRECT (đổi có chủ đích sang hỏi lại, phải 0 lần ghi X); v10 / v9 / v8 / v7.1 / hồi quy như v48. Ca nào đang đạt trên v48 mà trượt → dừng.

## 16/11 — CPU v49 TRƯỢT cổng (0 ghi sai): lượt xung đột chỉ ask_repeat, không ask_address → CORR-BLOCKED ×2 trượt, RECOVER không hợp lệ. Chi tiết + hướng sửa: mục cuối DE-XUAT-V48-BINDING-DIA-CHI. Chờ duyệt.

## 16/11 — Duyệt + code v50 (hỏi lại đúng request bị treo)
- Người dùng duyệt sửa hẹp nhánh chọn câu hỏi với 5 điều kiện; "sửa lỗi không được phát sinh lỗi hay biến ca đúng thành sai".
- Code v50:
  - `plan_primitives._ask_suspended` (gọi đầu `apply_order_gate`, chỉ khi không có order_gate, op_gate rỗng hoặc đúng loại đổi địa chỉ, và không hold): đúng một request vừa bị treo + đơn đã rõ → `ask_address` với `address_change {order_id, product}` + `note_question` (chỉ thành câu hỏi đã gửi khi câu cuối có ask_address); nhiều / chưa rõ đơn → `ask_which_order`. Không gắn / phục hồi binding, không đổi kiểm quyền.
  - `request_state.suspended_in_turn` (chỉ đọc).
  - `generator` mẫu ask_address nêu đơn CHỈ khi có `address_change.product`; mọi câu ask_address cũ giữ nguyên chữ.
- Tự phát hiện + sửa: patch v47–v49 đã đổi xuống dòng `request_state.py` / `plan_primitives.py` CRLF→LF (không đổi hành vi). v50 trả về CRLF; `generator.py` dựng lại từ bản v46 giữ CRLF (diff đúng 1 khối). Bản sao v49 `runs/extra_1115/v49_files/` khớp hash freeze v49.
- Freeze `runs/freeze/20261116-v50-cand`. CPU `midzid/sudocode-v50-cpu-1116`. Cổng (ghi trước): v12 đạt hết (CORR-BLOCKED hỏi ask_address ngay lượt sửa; RECOVER hợp lệ + ghi Y); v11.1 23/24 (chỉ CORRECT, 0 ghi X); v10 / v9 / v8 / v7.1 / hồi quy như v49.

## 16/11 — CPU v50 ĐẠT; đẩy cổng API thật
- `midzid/sudocode-v50-cpu-1116`: v12 12/0 (CORR-BLOCKED ×2 hỏi ask_address ngay lượt sửa, 0 ghi; RECOVER hợp lệ và ghi đúng Y); v11.1 23/24 (chỉ CORRECT, 0 ghi X, nay hỏi ask_address); v10 8/0 (I2-SAME bản v10 không hợp lệ như cũ); v9 4/4; v8 31/0; v7.1 23/0; ops 25/0; consent 26/0; object 6/0; authority v3 32/0, v2 11/0; v1.1 27/0; variants; clean_env 75/0; selftest 62/0.
- So từng ca với v49 (cùng job): v11.1 và v10 KHÔNG ca nào đổi kết quả; v12 chỉ đổi 3 ca cần sửa (CORR-BLOCKED ×2 trượt → đạt, RECOVER không hợp lệ → đạt).
- Đẩy `midzid/sudocode-iso-v50-1116` (cần DEEPSEEK_API_KEY + TYPESAFE_API_KEY): probe mua 16×5 (âm 0/40 ghi sai, dương mỗi nhóm ≥4/5) → probe2 12×3 probe_eval_v3 + fp6_fn6 (FP6 3/3, FN6-V2 3/3) → iso 26 (0 ghi sai; so TSR với v46 22/26). Ước tính ~1,5 giờ (2×T4), giới hạn 3 giờ. Trượt → dừng.

## 16/11 — API thật v50 ĐẠT cổng
- Probe mua 16×5: 0/40 ghi sai, 40/40 dương. Probe2: 0 ghi sai, 18/18 dương. FP6 3/3, FN6-V2 3/3. Iso 26/26 hợp lệ, lệnh ghi giống hệt v46; TSR 21/26 (v46 22/26; BTCL-066 iso_c do DeepSeek gắn asks khác, lượt không liên quan địa chỉ).
- **Chờ người dùng quyết định:** chốt v50 thay v46 làm cấu hình chính (snapshot mới) / chạy dev92 trên v50. Chưa dev92 / H13 / commit.

## 16/11 — Chốt mốc v50 + đẩy dev92 (người dùng duyệt lộ trình 5 bước; Full midzid / Baseline midzed song song)
- Snapshot `runs/snapshots/20261116-b2-v50/` (source sha d7742f19…, 238/238 khớp freeze v50; config.json env b2_jev/target từ iso-v50; jobs; results v50 + cpu; tests; MANIFEST giới hạn). v46 giữ nguyên.
- dev92 v50: `midzid/sudocode-dev50-full-1116` (full), `midzed/sudocode-dev50-base-1116` (baseline_no_memory); cùng env / freeze v50; thêm pre `variant_check.json` (dừng nếu không b2_jev/target). Hai job dev46 cũ KHÔNG chạy. Cần gắn key + Run.
- Sau khi chạy: TSR, HR, CCR, RQR, latency, ghi sai / thừa, mức hỏi lại; so dev39/dev38. Ghi sai mới → dừng báo. H13 khóa. Không commit.

## 16/11 — Bridge hạn nộp bốn ngày với Fable 5.2 (đề xuất phạm vi, chưa thực thi)

- Hoàn tất hai vòng, cả hai response ghi `claude-fable-5-2`. [Bản chốt phạm vi](../PLAN/CHOT-PHAM-VI-NOP-4-NGAY-FABLE-2026-11-16.md), [transcript](../PLAN/PHIEN-PHAN-BIEN-HAN-NOP-4-NGAY-FABLE-2026-11-16.md).
- Khuyên chọn C: khép lớp ghi sai GEN-T10 + gate payload trong một timebox (Codex: tối đa hai candidate tổng, 4–6 giờ chủ động, cutoff cuối D1), sau đó đóng băng lõi và hoàn thiện C.5/UI/hồ sơ.
- Không chốt nguyên v50 thành bản cuối, không sửa mở vô hạn. Dự phòng thu hẹp sửa địa chỉ đơn ngoài cuộc gọi phải được kiểm và công khai mất coverage, không tự handoff mọi ca hoặc quay v46.
- C.5 ưu tiên Knowledge Gap→FAQ có nguồn, hai nguồn feedback, người duyệt, runtime dùng thật, vòng 0/1 cùng source/tập cố định, rollback. UI tái sử dụng Streamlit. D4 dành cho kiểm tái lập và nộp, H13 không chặn nộp.
- Chưa sửa code/chạy job/commit từ bridge; chưa mặc định người dùng đã duyệt mọi đánh đổi của phương án thu hẹp tính năng. Những bất đồng và đính chính reviewer nằm trong mục 8 bản chốt.

## 16/11 — GEN-T10 (v50 sửa nhầm đơn lịch sử) — CHỜ DUYỆT
- Hồ sơ trước sửa: `docs/DE-XUAT/ISSUE-V50-GEN-T10-SUA-NHAM-DON-2026-11-16.md` (tái hiện, gốc lỗi, phạm vi payload 6 trace, ca phải giữ, test v13, phương án v51-A / v51-F).
- Bảng bảo vệ dùng chung: `docs/DE-XUAT/BANG-BAO-VE-GHI-2026-11-16.md` (test/hash/kết quả v50; I2-SAME v10 và CORRECT v11.1 đề xuất đưa vào danh sách loại trừ khóa `GUARD_RETIRED.json`; đề xuất gate payload cho dev).
- Cần duyệt: (1) kỳ vọng test v13; (2) A, F hay cả hai (F trước); (3) GUARD_RETIRED.json; (4) gate payload. Chưa sửa code, chưa chạy job, không H13, không commit.

## 16/11 — Mốc v13 trên v50: KHÔNG tái hiện T10-SHAPE → DỪNG (chờ duyệt v13.1)
- Job midzid/sudocode-v13-base-1116: freeze v50 238/238, test sha 60c4f4f3 = bản khóa. Kết quả 5 đạt / 4 không đạt, 0 INV. T10-SHAPE ĐẠT (không ghi) = không tái hiện.
- Ghi sai tái hiện được: HIST-DELIV-NAMED (OD188213 delivered, basis order_id), HIST-ONE-NOREF (basis single_order — đúng cơ chế GEN-T10).
- Sai khác fixture vs trace thật (request_state trong trace): t1 thật ambiguity=needs_clarification → hold ambiguous_turn, không mở request (fixture: none → R1 exchange mở, còn treo tới t5); t4 thật target_ref P2, response accept, flag agrees_to_buy (fixture: ref None); t5 thật target_ref O1 (fixture None); fixture bỏ t2/t3.
- PREV-NAMED/PREV-ANSWER trượt trên v50 (FP4–FP6 thật đạt): fixture tạo đơn cuộc trước SAU s.start() nên đơn không có trong Call Brief (known_orders = orders_created + brief.orders); thực tế đơn cuộc trước có trong brief. Cùng lỗi tiền đề ở HIST-TWO/HIST-ONE-NOREF. Kiểm tiền đề của v13 quá lỏng nên không báo INV.
- Đề xuất v13.1: chỉ sửa phần dựng tiền đề (nhãn đúng trace t1–t5, đơn cuộc trước tạo trước khi bắt đầu phiên, kiểm tiền đề khớp request_state thật), KHÔNG đổi kỳ vọng; v13 giữ nguyên làm lịch sử. Chạy lại mốc v50. Chưa viết code F/A.

## 16/11 — Mốc v13.1: T10-SHAPE INV (lệch ở t5 sau `opened R1`), DỪNG theo timebox
- HIST-ONE-NOREF (single_order, đơn ngoài cuộc) và HIST-DELIV-NAMED (đơn delivered, mã đơn) ghi sai với tiền đề hợp lệ. Bốn ca dương đạt.
- Chờ người dùng quyết định: sang F → A với bằng chứng gồm trace thật GEN-T10 + HIST-ONE-NOREF + HIST-DELIV-NAMED (T10-SHAPE công khai là chưa tái hiện), hay hướng khác. Chưa viết code, không H13, không commit.

## 16/11 — Duyệt sang F → A (tối đa 2 candidate, không đặt lại đồng hồ)
- v51-F đã code (B2, change_order_address: đơn không tạo trong cuộc → không ghi, goal mới `address_change_unavailable`, báo một lần/đơn). Đổi 3 tệp: plan_primitives.py, generator.py, generator_goals.json. Freeze `runs/freeze/20261116-v51F-cand` (238 tệp, chỉ 3 tệp khác v50). Bản v50 lưu ở `runs/extra_1115/v50_files/`.
- Job CPU `midzid/sudocode-v51f-cpu-1116`: v13.1 (candidate) + toàn bộ bộ bảo vệ + hồi quy + guard_report (GUARD_RETIRED + CANDIDATE_F_UNSUPPORTED).
- v51-A: đã soạn patch (scratchpad `v51a_patch.py`), CHƯA áp; chỉ làm khi F qua CPU và còn timebox.

## 16/11 — CPU v51-F: DỪNG — hồi quy ca dương CHƯA KHAI trước (an toàn, không ghi)
- Job midzid/sudocode-v51f-cpu-1116: freeze v51F 238/238. So từng ca với v50 (cùng sha test): v12, v11.1, v8, v7.1, ops v6.4, consent v5, object v4, authority v3/v2, extra v1.1 KHÔNG đổi ca nào; variants, clean_env, gate selftest rc 0.
- Đổi so với v50: v9 I1-CTL, I1-P (probe) và v10 I1-CTL, I1-P (gating) từ ĐẠT → KHÔNG ĐẠT: ca DƯƠNG đổi địa chỉ đơn nhiều dòng / đơn có trong Call Brief (fixture v9/v10 dựng đơn như đơn cuộc trước) → F trả address_change_unavailable, 0 ghi. Cùng lớp phạm vi F đã chọn nhưng KHÔNG có trong CANDIDATE_F_UNSUPPORTED.json (phân tích phạm vi của mình sai: đã viết "fixture CPU v8–v12 tạo đơn trong cuộc", thực tế v9/v10 dùng đơn Call Brief).
- v13.1 (candidate): HIST-ONE-NOREF, PREV-NAMED, PREV-ANSWER không đạt — đều đã khai trước cho F, 0 ghi. HIST-DELIV-NAMED từ ghi sai → 0 ghi; T10-SHAPE/T10-PREV-ADDR/HIST-TWO/INCALL-* đạt. v11.1 CORRECT, v10 I2-SAME như mốc (retired).
- guard_report.py lỗi công cụ (KeyError 'id' ở kết quả f5_extra_v1_1 không có trường id) → bảng tổng hợp chưa sinh; cần sửa công cụ (không phải test).
- Chờ người dùng quyết định; không tự thêm ca vào manifest F sau khi đã thấy kết quả.

## 16/11 — F khai muộn (công khai) + A (candidate cuối) đang kiểm CPU
- **Kết luận F theo khai báo ban đầu: CHƯA ĐẠT.** Khai báo ban đầu `CANDIDATE_F_UNSUPPORTED.json` giữ nguyên.
- Khai báo muộn `CANDIDATE_F_UNSUPPORTED_v2.json`: thêm v9/v10 I1-CTL, I1-P (`late: true`), mỗi ca có lý do thuộc lớp bị cắt. Đây là sai sót phân tích phạm vi, phải công khai. Danh sách này là giới hạn riêng của F, không đưa vào GUARD_RETIRED.
- Tiêu chí ca không hỗ trợ của F gồm ba điều: an toàn (0 lệnh ghi), phản hồi đúng (goal `address_change_unavailable`), không báo thành công giả.
- Phần mất so với v50: đổi địa chỉ mọi đơn ngoài cuộc gọi.
- `guard_report.py` v2 nhận diện schema tường minh (S1–S5) và đối chiếu số đạt/trượt với số chính test tự báo. Chạy thử trên kết quả F (246 ca, 13 tệp, 0 lỗi công cụ): manifest ban đầu → 6 ca trượt; manifest khai muộn → 7 ca `unsupported_ok`, 2 ca retired, 0 ca xấu. Bản chạy chính thức nằm trong job A.
- A: tiêu chí nghiệm thu khóa trước ở `runs/extra_1115/A_ACCEPTANCE_v51.md`; danh sách sha test ở `GUARD_EXPECT_v51.json`.
- Freeze `runs/freeze/20261116-v51A-cand`: chỉ 3 tệp khác v50 (plan_primitives, generator, generator_goals); working tree = v51A.
- Job `midzid/sudocode-v51a-cpu-1116`.

## 16/11 — CPU v51-A ĐẠT; đã đẩy job API phần bị ảnh hưởng (chờ người dùng gắn key)
- Job midzid/sudocode-v51a-cpu-1116: freeze v51A 238/238.
  - guard_report A (không manifest, --expect 13 sha) rc 0: 244 pass, 2 retired (v10 I2-SAME, v11.1 CORRECT; ca thay thế đạt), 0 lỗi công cụ.
  - So từng ca với v50: 12 bộ không đổi ca nào. v13.1 9/9 đạt: HIST-DELIV-NAMED từ ghi sai → báo "đã được giao nên em không đổi được"; HIST-ONE-NOREF từ ghi sai → hỏi chọn đơn; PREV-NAMED / PREV-ANSWER / I1-CTL / I1-P đạt. T10-SHAPE đạt (chỉ là kiểm an toàn bổ sung).
  - variants, clean_env, gate selftest rc 0.
- Nghiệm thu chính thức F (trên kết quả job v51f-cpu-1116): manifest ban đầu → CHƯA ĐẠT (6 fail); manifest khai muộn → 7 unsupported_ok (4 khai muộn), 0 xấu.
- Ghi nhận chất lượng (chưa sửa): câu hỏi chọn đơn khi chỉ có MỘT đơn vẫn dùng mẫu "anh/chị đang có các đơn …, muốn đổi địa chỉ giao cho đơn nào".
- Job API `midzid/sudocode-iso-v51a-1116` (GPU, ≤2 giờ) cần DEEPSEEK_API_KEY + TYPESAFE_API_KEY. Gồm probe2 12×3 + probe_eval_v3 + fp6_fn6; GEN-T10-01 ×3; GEN-T21-01, GEN-T27-01, V3-117; CTL1115-ADDR. Bộ chặn iso_driver_v3 dừng nếu ghi sai.
- Tiêu chí: probe2 âm 0 ghi sai, dương như v50 (18/18); FP6 3/3, FN6-V2 3/3; iso không STOP; GEN-T10 0 order.update đơn lịch sử ×3; ca dương địa chỉ giữ như v50.
- Job API A chuyển sang midzed theo yêu cầu: midzed/sudocode-iso-v51a-1116 (cùng nội dung, cùng freeze v51A). Bản midzid/sudocode-iso-v51a-1116 KHÔNG chạy.
- Cập nhật: người dùng chạy lại bản midzid/sudocode-iso-v51a-1116 (bản midzed lỗi khi tự chạy lúc đẩy, không dùng). Kéo kết quả bằng midzid.json.
- 16/11 lần 1 job API A lỗi đóng gói (thiếu probe_eval.py/probe_eval_v2.py) sau khi probe2 3×12 chạy xong; iso chưa chạy. Trace probe2 lần 1 (freeze v51A 238/238, b2_jev) lưu runs/extra_1115/probe2_v51a_run1/. Lần 2 (dataset-only cùng kernel midzid/sudocode-iso-v51a-1116): chấm probe2 trên trace lần 1 + chạy iso.
- Lần 2 job API A chuyển sang midzed theo yêu cầu: midzed/sudocode-iso-v51a-1116 (dataset + kernel đẩy mới). Bản midzid lần 2 KHÔNG chạy. Kéo kết quả bằng midzed.json.
- 16/11 lần 2 (midzid, key đã nạp) lỗi đóng gói thứ hai: thiếu suite.json → probe_eval_v3 đánh 36/36 không hợp lệ. Lần 3: thêm suite.json (dataset-only midzid). Chạy thử chấm trên trace lần 1: âm 0/18 ghi sai, dương 18/18, FP6 3/3, FN6-V2 3/3 (chưa phải số chính thức).
- 16/11 API v51-A ĐẠT (xem ISSUE §8, report_iso_v51a.json). Chờ người dùng chốt chọn A làm cấu hình chính → snapshot v51A; sau đó sang C.5/UI theo bản chốt phạm vi.

## 16/11 — Người dùng chốt v51-A làm backend; sang UI + C.5
- Snapshot `runs/snapshots/20261116-b2-v51A/` (source.tar.gz `2fdce503…`, 238/238 khớp freeze; MANIFEST ghi riêng ba lần API: run1/run2 lỗi đóng gói, run3 chấm probe2 trên trace run1 + iso).
- Số dev50 vẫn là số của v50, KHÔNG gắn nhãn v51-A; R0 sẽ đo lại.
- Handoff `scripts/CLAUDE_HANDOFF_UI_C5_RELEASE.md`: đã cập nhật trạng thái đầu vào.
- Tiếp theo: (2) UI nối B2-v51-A; (3) Knowledge Gap Loop đầy đủ; (4) canary → đóng băng source chung → R0/R1. H13 khóa, chưa commit.

## 16/11 — UI + C.5 (bước 2–3) đã code, đang kiểm CPU
- Core (chỉ khi IMPROVE_DIR khác rỗng): ARCH=target cho phép gói FAQ-only (check_arch ghi phạm vi). improve_hook từ chối gói có loại khác ngay khi mở phiên (ImproveScopeError). Trace target ghi `improve.retrieved` (FAQ tra thấy) tách `improve.used` (FAQ có câu được renderer chọn vào câu cuối). Bản v51-A gốc của 3 tệp: `runs/c5/base_v51A/`.
- `scripts/c5_loop.py`: gaps (auto_eval + staff_feedback) → draft (DeepSeek chỉ chọn câu policy theo ID; answer = câu nguyên văn của đúng chunk; code kiểm) → package (hash, regression suite riêng) → activate / rollback nguyên khối (data/c5).
- UI: profile B2-v51-A từ snapshot + startup_check; câu hiện từ on_emit; event_id chống gọi lại; Full / Baseline namespace riêng; like / dislike theo message (data/ui/feedback.jsonl + traces); màn Cải tiến cho FAQ (nguồn, test, duyệt có tên, đóng gói, kích hoạt, quay lui); Chỉ số có nhãn phiên bản (dev50 = v50).
- Freeze source chung ứng viên `runs/freeze/20261116-c5-cand` (248 tệp: 238 cũ, trong đó 4 đổi, + ui / c5 / test mới). Job CPU `midzid/sudocode-c5-cpu-1116`.
- Gap dev50 cho bước soạn nháp: `runs/c5/review_dev50/gaps.jsonl` (30 gap, 6 no_info). Lưu ý công khai: FAQ lập từ gap dev rồi đo lại trên dev92 → R1 không phải phép đo độc lập.
- Job soạn nháp `c5-draft-1116` (CPU + DEEPSEEK_API_KEY) soạn sẵn, chỉ đẩy khi CPU đạt.

## 16/11 — Kết quả CPU c5-cpu-1116 + README
- c5-cpu-1116 (freeze c5-cand job1, 248/248):
  - guard_report 244 pass + 2 retired, 0 lỗi (giống v51-A khi IMPROVE_DIR rỗng);
  - c5_loop_check, ui_check (+AppTest), improve_check, improve_hook_check, target_arch_check, variants, clean_env, gate selftest: rc 0.
- **ui_b2_check bắt lỗi thật của UI engine:** row của CallSession.turn() không có trường `turn` → msg_id `…:None`, mọi câu trong một cuộc gọi chung mã, feedback không gắn đúng lượt. Đã sửa: số lượt lấy từ message on_emit; feedback thiếu msg_id / lượt → từ chối. Test thêm kiểm hai lượt có msg_id khác nhau. Chạy lại: job `midzid/sudocode-c5-cpu2-1116`.
- Clean clone chạy được B2: thêm `profiles/b2_v51a.json` (có trong Git, khớp snapshot 100%) và `scripts/with_profile.py` (profile luôn ghi đè biến cùng tên, in cảnh báo). UI đọc profile; nếu có snapshot thì đối chiếu, lệch → từ chối.
- README: thêm mục 2A (B2-v51-A trên máy cá nhân / Kaggle, kiểm CPU, lỗi Windows); viết lại mục 5 (UI); thêm 6.1 (Knowledge Gap Loop); mục 8 ghi LỊCH SỬ. Số dev ghi rõ là của v50.

## 16/11 — Hướng dẫn UI dùng Qwen trên Kaggle (phương án A + cloudflared)
- Người dùng: "cập nhật đi" → làm phương án khuyến nghị A: UI ở máy cá nhân, chỉ Qwen3-4B (vLLM) chạy trên GPU Kaggle, mở qua quick tunnel cloudflared, endpoint khóa bằng khóa ngẫu nhiên.
- `kaggle/qwen_tunnel.py` mới. `scripts/serve_llm.sh` thêm `VLLM_API_KEY` tùy chọn: không đặt thì hành vi cũ; có đặt thì bật `--api-key` và bước kiểm sẵn sàng gửi kèm khóa.
- README mục 5.1b. Freeze c5-cand cập nhật (251 tệp).
- Kiểm: c5-cpu2-1116 (sau sửa msg_id UI) đạt hết: ui_b2_check 20/20, ui_check + AppTest, c5_loop_check, with_profile; chạy B2 chỉ với profile Git, không có runs/.
- Job GPU tự kiểm tunnel `midzid/sudocode-tunnel-selftest-1116` (không cần khóa API, không in khóa / URL ra log).

## 16/11 — Giữ cả hai cách chạy UI với Kaggle (người dùng duyệt)
- A (`kaggle/qwen_tunnel.py`, README 5.1b): UI ở máy cá nhân, Qwen trên Kaggle qua tunnel có khóa. Job `tunnel-selftest-1116` ĐẠT: cài vLLM 1 phút 18 giây, Qwen sẵn sàng sau khoảng 2 phút; gọi có khóa qua URL công khai đúng model; gọi không khóa bị từ chối; chat qua tunnel 1,5 s; log không lộ URL / khóa.
- B (`kaggle/ui_tunnel.py`, README 5.1c): UI + Qwen (nội bộ) trên Kaggle, chỉ UI mở qua tunnel. UI_PASSWORD bắt buộc (không có → từ chối). Khóa API lấy từ Kaggle Secrets, không in ra. Dữ liệu UI ghi vào /kaggle/working/ui_data; nút "Chuẩn bị gói dữ liệu UI để tải về".
- UI: `password_gate` (hmac.compare_digest) khi đặt UI_PASSWORD; `export_ui_data()`; thư mục dữ liệu chọn qua UI_DATA_DIR / C5_STATE_DIR. qwen_tunnel tách hàm `start_vllm` / `open_tunnel` dùng chung.
- Test mới `tests/ui_password_check.py` (AppTest: chưa nhập / sai → không tab; đúng → 5 tab; không đặt → vào thẳng; zip không có khóa). Job kiểm A+B `midzid/sudocode-tunnel-ab-selftest-1116`. Freeze c5-cand cập nhật (253 tệp).
- 16/11 đẩy dataset midzed/sudocode-repo (code = freeze c5-cand, UI mới nhất) để người dùng tự test UI theo README 5.1c.
- 16/11 tunnel-ab-selftest-1116 ĐẠT (12 phút): freeze 253/253; ui_password_check 7/7; A sau tách hàm: có khóa đúng model, không khóa bị từ chối, chat 1,7 s; B: vLLM nội bộ, UI mở qua URL công khai; log không lộ URL / khóa. Người dùng đã chạy B thật trên midzed (notebook68b3aaaed5) với khóa thật và chat được. Phát hiện chất lượng: 'máy lạnh' (không có trong catalog) → ask_product hỏi lại; đề xuất goal not_carried, chờ quyết định sửa trước R0 hay ghi hạn chế.

## 16/11 — Lỗi hỏi lại sản phẩm ("máy lạnh"): KHÔNG sửa hẹp được → ghi hạn chế
- Điều tra khoảng 15 phút: bộ hiểu DeepSeek không có trường tên mặt hàng khách hỏi; find_products / CATEGORY_WORDS chỉ biết hàng có bán. "máy lạnh…" và "bên em có hàng không" giống hệt nhau ở mức dữ liệu. Sửa cần vá theo từ (cấm) hoặc thêm trường hợp đồng DeepSeek (chỉ đề xuất).
- Đề xuất cho đợt sau: `docs/DE-XUAT/DE-XUAT-SAN-PHAM-NGOAI-DANH-MUC-2026-11-16.md`. Không đổi code, không đổi freeze c5-cand. Tiếp tục UI/C.5.

## 16/11 — Lỗi ngân sách bổ sung sau báo giá (AirPure Y 5,2 tr, khách nói "ngân sách khoảng 2 triệu")
- Nguyên nhân (code): B1 có dòng R19 budget_fit. Trên B2, dòng này thuộc nhóm TRẢ LỜI do Jev sở hữu, chỉ chạy qua answer_ask:*, và answer_ask chỉ được mời khi bộ hiểu có `asks`. Câu nêu ngân sách không phải câu hỏi → Jev chỉ có read_quote mẫu đang bàn + finish → lặp giá Y. Không cần đổi hợp đồng bộ hiểu: dùng slot budget_vnd sẵn có.
- Trace UI hiện chỉ lưu câu / goal, KHÔNG có output bộ hiểu → chưa xác nhận được budget_vnd của phiên thật. Test v14 kiểm budget_vnd = đúng số (2.000.000…) làm tiền đề.
- Test khóa trước `runs/extra_1115/f5_budget_fit_check_v14.py` (sha256 8bb414b4…): B-OVER (tái hiện), B-WITHIN, C-REASK, C-KEEP-Y (so lời gọi ghi với ca đôi), C-NONE, C-OOS (Mini hết hàng qua mt.TOOLS). Mốc trên source chung c5-cand: job `midzid/sudocode-v14-base-1116`.
- Bản sửa đã soạn (CHƯA áp; scratchpad budget_patch.py), chỉ B2, phạm vi tư vấn:
  - thêm nghĩa vụ ngầm "budget" khi lượt có budget_vnd + đang bàn mẫu + giỏ trống + KHÔNG có yêu cầu;
  - adapter `_answer_budget`: so giá, vượt thì mẫu cùng loại còn hàng (giá thật từ tool) hoặc "chưa có mẫu";
  - mẫu câu budget_fit có thêm phần mẫu thay thế; không đọc số tiền chênh (rủi ro audit HR).

  Không chạm luồng đặt hàng / quyền ghi / giá / mock / evaluator. Freeze riêng `c5b-cand`; c5-cand giữ nguyên.

## 16/11 — V52: gộp sửa A (ngân sách) + B (đối tượng theo nhóm hàng), một job
- Nguyên nhân có bằng chứng code:
  - **A:** câu nêu ngân sách không có `asks` → B2 không mời answer_ask → Jev chỉ còn read_quote mẫu đang bàn → lặp giá. R19 budget_fit của B1 không chạy trên B2.
  - **B:** khách nêu NHÓM HÀNG, không nêu mẫu → `c.mentioned` rỗng → h_quote dùng `s.focus` (Y) → báo giá / kho Y. Nhóm hàng có nhận diện (CATEGORY_WORDS) nhưng không được dùng chọn đối tượng.
  - **C:** bộ hiểu không trả tên mặt hàng ngoài danh mục → CHƯA SỬA (cần đổi hợp đồng DeepSeek; đề xuất DE-XUAT-SAN-PHAM-NGOAI-DANH-MUC).
  - "Mẫu đó" mơ hồ: không có dữ liệu mẫu đã nêu ở lượt trước → CHƯA SỬA, khai trước là ca thăm dò.
- Sửa, chỉ B2:
  - `harness/plan_primitives.py`:
    - nghĩa vụ ngầm "budget" (`_budget_turn` / `_answer_budget` / `_budget_alternative`);
    - đối tượng theo nhóm hàng (`_category_switch` / `_answer_category`): quay về mẫu đã bàn trong nhóm, chưa có thì gợi ý trong nhóm, 2 nhóm thì hỏi rõ;
    - ước tính chi phí tool.
  - `harness/planner_b2.py`: nhãn bước budget cho Jev.
  - `core/llm/generator.py`: budget_fit có mẫu thay thế + mức vượt "khoảng X". Rủi ro: audit claim có thể gán nhầm số chênh thành giá → theo dõi HR ở R0.
  - `scripts/c5_loop.py`: bỏ expected_outcome "khac" không hợp lệ ở test hồi quy tự sinh.
- Không chạm quyền ghi / chọn đơn / binding / giá / mock / evaluator / extractor / audit / giới hạn bước.
- Test khóa trước:
  - v14 `8bb414b4…` (6 ca ngân sách);
  - v15 `5282fe31…` (11 ca gating + 2 thăm dò khai trước: C-OUT, B-AMBIG).
- Freeze riêng `runs/freeze/20261116-c5b-cand` (c5-cand giữ nguyên). Tệp gốc c5: `runs/extra_1115/c5_files/` (khớp hash); tệp candidate: `c5b_files/`.
- Job gộp `midzid/sudocode-v52-all-1116` (GPU + 2 khóa):
  1. CPU (v14, v15, v13.1, bộ bảo vệ + guard_report, UI, C.5, target_arch, hồi quy);
  2. cpu_gate dừng nếu có bước ≠ 0;
  3. probe API 10 kịch bản × 3 (probe_budget_eval);
  4. mốc v14 / v15 trên c5-cand.
- Quay lui: chép `runs/extra_1115/c5_files/*` đè lại (hoặc dùng freeze c5-cand).

## 16/11 — V52-K: vòng lặp xác nhận đặt hàng (gộp vào job v52-all-1116)
- Nguyên nhân (code, chưa xác nhận bằng trace thật vì trace UI không lưu bộ hiểu):
  - `request_state.accept_pure` chỉ nhận đồng ý thuần khi mọi từ thuộc stance._ACK_TOK và có marker (ok / ừ / vâng / được / đồng ý / đúng rồi);
  - "xác nhận" KHÔNG là marker, "tôi" KHÔNG là xưng hô hợp lệ → "Tôi xác nhận." bị `accept_not_pure` → turn_act accept_blocked → order_gate accept_unconfirmed → nhân viên xin xác nhận lại (chữ "xác nhận" do chính câu confirm_order yêu cầu) → lặp vô hạn.
  - BTCD7-025 là ca KHÁC: chỉ đọc địa chỉ → accept_delivery_only theo chính sách.
- Sửa hẹp, chỉ trong `accept_pure`: CONFIRM_RX `\bxac nhan\b` là marker; ACCEPT_PRONOUNS {"toi"}.
  - stance._ACK_TOK không đổi.
  - Kiểm khác giữ nguyên: act=accept của bộ hiểu, đề nghị mới (không mang qua lượt), revision, đúng mẫu, giá đã báo, không phủ định / hoãn / điều kiện / rút.
  - "không / chưa xác nhận" → không thuần.
- Test khóa trước v16 `5657ba04…` (9 ca): K-CONFIRM (tái hiện), K-OK, K-DUP (không tạo 2 lần), K-MISSING (hỏi đúng phần thiếu), K-DECLINE, K-COND, K-SWITCH, K-PRICE, K-STALE. Mỗi ca ghi chuỗi act → proposal → accept_blocked → yêu cầu → bước B2.
- Probe API thêm PK1-CONFIRM, PK2-DUP: cả cuộc đúng 1 order.create Y; lượt cuối không hỏi lại confirm_order.
- Freeze c5b-cand thêm request_state.py; tệp gốc c5_files/request_state.py (khớp hash). Job gộp đẩy lại.

## 16/11 — Chốt đợt sửa tích hợp cuối V52 (người dùng duyệt phạm vi)
- Phạm vi: A ngân sách + B chuyển nhóm hàng + K vòng lặp xác nhận. Giữ B2. CHƯA sửa (công khai hạn chế): mặt hàng ngoài danh mục; đại từ mơ hồ giữa nhiều mẫu.
- Hoàn thiện:
  - `P.ask_object(t)` xác định đối tượng câu hỏi + căn cứ (khách nêu mẫu / khách nêu nhóm hàng / quay lại mẫu đã bàn / mẫu đang bàn). CÙNG hàm dùng cho state Jev (`question_object`), mô tả bước answer_ask ("Đối tượng: …") và executor (`_answer_ask` → `_answer_category`).
  - Hai nhóm có một nhóm trùng focus → hỏi rõ nhóm.
  - Chi phí tool tối đa: budget 9; nhóm hàng max(2, 1 + n + 2).
- Test bổ sung riêng v17 `8d45d2bb…`, khóa trước: S-TWO-FOCUS, S-KEEP-PAYLOAD (đúng 1 order.create thành công / ca, payload sku / address / COD), S-CONFIRM-CHAIN (proposal đã gửi + target + revision, act / evidence, không accept_blocked, request mở, commit_request, giá = revision, địa chỉ), S-BLOCK-REASONS, S-JEV-SEES, INT-CHAIN (6 lượt, kiểm từng lượt + trạng thái cuối). v14 / v15 / v16 giữ nguyên.
- Probe API thêm PI1-CHAIN (hội thoại tích hợp): đúng 1 order.create máy lọc nước (SKU-WF*), không đơn Y; t2 nói ngân sách; t3 nói máy lọc nước; cuối không hỏi lại xác nhận.
- Freeze tích hợp `runs/freeze/20261116-c5b-cand`: 5 tệp khác c5-cand (generator, plan_primitives, planner_b2, request_state, c5_loop). Job `midzid/sudocode-v52-all-1116` đẩy lại: CPU (v14–v17, v13.1, bộ bảo vệ + guard_report, UI, C.5, hồi quy) → cpu_gate → probe API 13 × 3 → mốc v14–v17 trên c5-cand. Đạt → freeze này là source chung R0 / R1.

## 16/11 — V52 chia chạy song song (người dùng: "chia ra chạy song song")
- Job gộp `midzid/sudocode-v52-all-1116`: KHÔNG chạy.
- Cùng freeze c5b-cand, 4 job song song:
  - `midzed/sudocode-v52-guard1-1116` (CPU): v13.1 candidate, v12, v11.1, v10, v9; CUỐI: mốc v14–v17 trên c5-cand (chép 5 tệp c5 đè sau test candidate).
  - `elylish11/sudocode-v52-guard2-1116` (CPU): v8, v7.1, ops, consent, object, authority v3 / v2, extra.
  - `nnttrang/sudocode-v52-new-1116` (CPU): v14–v17, ui_b2 / ui_check / ui_password, c5_loop, improve, improve_hook, target_arch, variants, clean_env, gate selftest.
  - `midzid/sudocode-v52-api-1116` (GPU, cần 2 khóa): probe 13 × 3.
- Đánh đổi (công khai): API chạy cùng lúc với CPU. Kết quả API CHỈ được tính khi mọi job CPU đạt; CPU trượt → bỏ kết quả API.
- Sau khi kéo về: một job CPU ngắn gộp guard_report (13 tệp, --expect) từ guard1 + guard2.

## 16/11 — Kết quả V52 song song (c5b-cand): CHƯA ĐẠT, dừng chờ duyệt
- Bộ bảo vệ: 13 tệp giống v51-A từng ca. UI / C.5 / target_arch / variants / clean_env / gate selftest đạt. Không có hồi quy.
- v14 5/6 (C-KEEP-Y trượt); v15 6 đạt, trượt B-CAT / B-CAT-REV / B-TWO / B-CART, B-REQ không hợp lệ; v16 9/9 không hợp lệ; v17 2 đạt, trượt S-JEV-SEES / INT-CHAIN, 2 ca không hợp lệ.
- Sự cố quy trình: job API midzid tự khởi động khi đẩy và có khóa, nên đã gọi DeepSeek thật trước khi CPU đạt (13 × 3). Kết quả chỉ tham khảo, không tính.
- Nguyên nhân:
  - R1: executor đã chọn đúng đối tượng mới, nhưng Jev vẫn được đưa read_quote / read_stock của mẫu cũ → "Ngoài ra bên em có mẫu AirPure Y".
  - R2: order_gate coi "vượt 2 triệu" (ngân sách) là giá lạ → price_unconfirmed → confirm_new_price.
  - R3: tiền đề v16 / v17-K sai. Báo giá rồi "Anh lấy Y" (req ref P1) → tạo đơn ngay, sau đó order.update địa chỉ, không qua confirm_order.
  - R4: "cái máy lọc nước đó" (ref None) → hỏi lại mẫu nào dù chỉ gợi ý 1 mẫu.
- Đề xuất chờ duyệt:
  - P1: lọc option theo ask_object (planner).
  - P2: order_gate bỏ qua số tiền trùng ngân sách khách đã nêu (cổng ghi).
  - P3: v16.1 / v17.1 tiền đề mới (ref None → intent_only → confirm_order).
  - P4: R4 nằm ở binding đích (vùng bảo vệ v51-A) → chỉ đề xuất.

## 17/11 00:30 — Candidate thu hẹp cuối v52n (theo QUYET-DINH-V52-SAU-BRIDGE-FABLE52)
- Giới hạn: bắt đầu 17/11 00:30. Tối đa 2 giờ chủ động (đến 02:30) / 4 giờ đồng hồ (đến 04:30). Mốc R0 đến trước thì dừng. Quá hạn hoặc trượt → fallback c5-cand.
- Phạm vi:
  - CHỈ P1: phạm vi câu hỏi chốt một lần đầu lượt (`P.question_scope`); bỏ read_quote / read_stock mẫu ngoài nhóm khách nêu (lý do `outside_question_scope`); giữ đích yêu cầu đặt còn hiệu lực.
  - KHÔNG làm: P2 (cổng giá giữ nguyên), P4 (binding), nhánh asks=other.
  - request_state TRẢ VỀ c5-cand: bỏ dấu "xác nhận" vì chưa có tiền đề hợp lệ.
- Freeze `runs/freeze/20261117-v52n-cand`: khác c5-cand 4 tệp (plan_primitives, planner_b2, generator, c5_loop); khác c5b-cand 3 tệp (plan_primitives, planner_b2, request_state).
- Test mới v18 `d2fe4292…` (khóa trước). Nghiệm thu chốt trước `runs/extra_1115/V52N_ACCEPT.json` + `v52n_accept.py`. v14–v17 giữ nguyên hash / verdict.
- Job CPU:
  - `midzed/sudocode-v52n-guard-1117`: báo cáo gộp 13 tệp của c5b-cand + chạy lại 13 tệp + guard_report trên v52n.
  - `nnttrang/sudocode-v52n-new-1117`: v14–v18, UI / C.5 / hồi quy, nghiệm thu; chẩn đoán v18 trên c5-cand và c5b-cand.
- Job API CHƯA tạo. Chỉ tạo sau khi CPU đạt, với ô đầu kiểm hash artifact CPU trước khi nạp khóa.

## 17/11 00:50 — Kết quả v52n: nghiệm thu VI PHẠM 1 ca (N-TXN), dừng chờ quyết định
- Bảo vệ: 246 ca giống v51-A; guard_report v52n 244 đạt + 2 retired; báo cáo gộp c5b-cand 244 + 2. UI / C.5 / hồi quy đạt.
- P1 sửa đúng: B-CAT, B-CAT-REV, B-TWO, B-CART, S-JEV-SEES, N-CAT / N-STABLE / N-CAT-REV / N-TWO / N-CART. Không ca dương nào hỏng (N-RETURN, N-MODEL, N-COMPARE, N-TWO-FOCUS, N-PRICE-GUARD đạt).
- Vi phạm: N-TXN ("lên đơn Y, mà có máy lọc nước không?") tạo đúng đơn Y nhưng KHÔNG trả lời câu hỏi máy lọc nước. Lỗi CÓ SẴN, giống hệt trên c5-cand và c5b-cand; không phải hồi quy do P1. Bảng nghiệm thu đã khóa không khai báo ca này → theo luật là CHƯA ĐẠT. Không tự khai báo lại.
- Hệ quả của việc trả request_state về c5-cand: S-KEEP-PAYLOAD chuyển ĐẠT → KHÔNG ĐẠT (đã khai báo trước).
- Chẩn đoán xác nhận: K1 / K2 dựng ĐƯỢC tiền đề hợp lệ (confirm_order đã gửi, proposal place_order Y, units [Y, 5.200.000], chưa tạo đơn). Sau lượt khách đọc địa chỉ (agent chỉ trả quote), "Tôi xác nhận" bị chặn:
  - c5-cand / v52n: accept_not_pure → hỏi lại confirm_order (TÁI HIỆN vòng lặp);
  - c5b-cand (có dấu "xác nhận"): accept_stale → vẫn lặp. Vậy sửa của V52-K KHÔNG khép được lỗi.
  - Nguyên nhân gốc mới: lượt bổ sung địa chỉ không gửi lại đề nghị → đề nghị cũ hết hạn.
- INT-B: lượt 3 đúng (chỉ gợi ý máy lọc nước UF Sunhouse). Lượt 4 hỏi lại mẫu nào và đọc lại Y (P4 hoãn) → không có đơn.
- Chờ người dùng quyết định: fallback c5-cand theo phương án, hay nhận v52n với N-TXN khai báo là lỗi có sẵn (đổi nghiệm thu sau kết quả). API chưa tạo.

## 17/11 01:42 — v52n: cổng CPU ĐẠT, 3 job API đã đẩy
- Quyết định bổ sung N-TXN (sau kết quả): `docs/DE-XUAT/QUYET-DINH-NGHIEM-THU-BO-SUNG-V52N-2026-11-17.md` + `runs/extra_1115/V52N_ACCEPT_ADDENDUM_1117.json`. V52N_ACCEPT.json gốc giữ nguyên (VI PHẠM N-TXN).
- Cổng CPU `elylish11/sudocode-v52n-gate-1117`:
  - pass = True, problems = []; cpu_gate sha 14958f5d…;
  - đủ ID, hash test khớp cả 18 tệp; guard_report gộp 244 đạt + 2 retired;
  - nghiệm thu gốc chỉ vi phạm N-TXN.
- Probe: `runs/extra_1115/probe_v52n` (17 kịch bản: 13 cũ + PO5-CAT-REV, PO6-TWO-FOCUS, PT1-TXN, PG1-PRICE-GUARD). Bộ chấm mới `probe_v52n_eval.py` khóa trước; bộ chấm cũ chạy song song.
- API, mỗi tài khoản 1 lần chạy:
  - midzid / sudocode-v52n-api-r1-1117;
  - midzed / sudocode-v52n-api-r2-1117;
  - nnttrang / sudocode-v52n-api-r3-1117.
- Ô cổng chèn trước load_secrets (runner.py trong freeze không sửa) kiểm: cpu_gate, 253 tệp freeze, profile, env, test, tệp API.
- Gộp 3 lần chạy + chấm: job CPU sau khi cả 3 xong.

## 17/11 02:27 — v52n API: ĐẠT theo bộ chấm mới (khóa trước); bộ chấm cũ KHÔNG ĐẠT (verdict cũ giữ nguyên)
- 3 lần chạy (midzid / midzed / nnttrang): ô cổng đạt cả 3 (253 tệp freeze, cpu_gate 14958f5d…), nạp đủ 2 khóa, mỗi lần đủ 45 lượt.
- Chấm gộp `elylish11/sudocode-v52n-apieval-1117`.
- Bộ chấm mới `probe_v52n_eval.py`: hard_fail = [], invalid = [], 12 / 12 kịch bản trong phạm vi đạt 3/3 → pass = True.
  - Ghi lại, không chấm (đã khai báo): PB4-KEEP 0/3, PI1-CHAIN 1/3, PK1 3/3, PK2 3/3, PB4-TWIN 3/3.
- Bộ chấm cũ `probe_budget_eval.py`: pass = False. Lỗi cứng theo định nghĩa cũ ở cả 3 lần, nhưng KHÔNG có lệnh ghi sai thật:
  - PB4-KEEP / KEEP≠TWIN / PI1-CHAIN: không tạo đơn (thiếu hoàn thành);
  - PK1 / PK2: order.create Y + order.update địa chỉ đúng order_id vừa tạo.
- An toàn giao dịch:
  - không ghi sai, không đơn trùng;
  - PG1 "chốt Y giá 2 triệu" bị chặn 3/3 (không order.create);
  - PT1 đúng 1 đơn Y có địa chỉ 3/3.
- Còn tồn tại:
  - PT1 không trả lời câu máy lọc nước 3/3 (N-TXN);
  - PI1 lượt 3 asks=other "chưa có thông tin" 2/3 (r2, r3); r1 asks = compare → gợi ý UF;
  - lượt 4 hỏi lại mẫu nào 3/3 (P4) → không tạo đơn;
  - PB4-KEEP confirm_new_price 3/3 (ngân sách lẫn giá).
- PK1 / PK2 trên API: "Anh lấy Y" tạo đơn ngay, sau đó update địa chỉ — không qua đường lặp xác nhận. Vòng lặp vẫn tái hiện được ở CPU (K1 / K2), chưa sửa.
- Chờ người dùng xác nhận: chốt v52n làm cấu hình chính, đóng snapshot, dùng cùng source cho R0 / R1.

## 17/11 — CHỐT v52n làm cấu hình chính (người dùng duyệt, theo phạm vi nghiệm thu bổ sung)
- Freeze dùng chung UI + R0 / R1: `runs/freeze/20261117-v52n-ui` (255 tệp, danh sách sha d7edf583…).
  - Lõi = `20261117-v52n-cand`. Chỉ khác ui/engine.py, ui/app.py, kaggle/ui_tunnel.py, kaggle/qwen_tunnel.py; thêm profiles/b2_v52n.json, tests/ui_v52n_check.py.
- Profile `profiles/b2_v52n.json`: env giống hệt b2_v51a = env job API đã kiểm. `profiles/b2_v51a.json` giữ nguyên.
- UI:
  - mặc định UI_PROFILE = b2_v52n; nhãn "B2-v52n (cấu hình chính 17/11)";
  - kiểm hash code theo freeze của profile: lệch → từ chối chạy; không có tệp freeze → nhãn ghi "chưa kiểm hash code";
  - b2_v51a vẫn chọn được (chỉ cảnh báo trên nhãn).
- Kiểm trên Kaggle `midzed/sudocode-v52nui-check-1117`: 12 / 12 rc = 0 (core_same, ui_v52n, ui_b2, ui_check, ui_password, c5_loop, improve, improve_hook, target_arch, variants, clean_env, gate_selftest); freeze 255 khớp.
- Dataset `midzed/sudocode-repo` (version của job này) = source v52n-ui, kèm tệp freeze + config snapshot → UI Option B dùng dataset này.
- Snapshot `runs/snapshots/20261117-b2-v52n/`:
  - MANIFEST, source.tar.gz 6c18cd07…, config.json, 3 danh sách freeze (gồm c5-cand quay lui);
  - results CPU / cổng / API / chấm / kiểm UI + chẩn đoán đánh dấu riêng; tests, probe, jobs; sha256.txt 482 tệp.
- Quay lui: c5-cand (`runs/extra_1115/c5_files/` + `runs/extra_1115/v52nui_rollback/` + `profiles/b2_v51a.json`).
- README mục 2A + lệnh UI / profile cập nhật sang b2_v52n; hạn chế công khai ghi trong README và MANIFEST.
- Không sửa thêm lõi. Tiếp theo: hoàn thiện UI, C.5 (vòng FAQ có nguồn), hồ sơ. R0 / R1 dùng đúng freeze v52n-ui.

## 17/11 09:30 — Duyệt kế hoạch C.5 gộp (người dùng gửi bản đề xuất có chỉnh sửa)
- Thứ tự: (1) chốt dev92 + kiểm kê Git + mốc source → (2) bản vá A1–A6 → freeze v52n-ui2, kiểm CPU → (3) R0 Full + Baseline trên v52n-ui2; người dùng làm A7 (test UI, tải ui_data.zip) → (4) gap → nháp FAQ → người dùng duyệt → gói / test → canary → (5) R1 Full (+ Baseline nếu chọn R1); rollback nếu hại → (6) hồ sơ, kiểm clone sạch, video, GitHub.
- R0 / R1 cùng freeze v52n-ui2 ngay từ đầu (không đo trên v52n-ui rồi đối chiếu).
- Không mặc định A chỉ đổi UI: A sửa thêm `scripts/c5_loop.py` (ngoài ui/). Bằng chứng không ảnh hưởng đánh giá: `runs/extra_1115/v52nui2_core_check.py` (diff freeze + quét import đường chạy đánh giá).
- Lịch mục tiêu: 17/11 khép A + R0; 18/11 FAQ, canary, R1; 19/11 chốt số, hồ sơ, video; 20/11 kiểm đóng gói + dự phòng.
- **Lệch lịch cũ (công khai):** kế hoạch `CHOT-PHAM-VI-NOP-4-NGAY-FABLE-2026-11-16.md` tính D1 = 16/11 → hạn canary "trưa D2" = trưa 17/11. Canary dời sang 18/11 vì R0 chưa chạy và đường feedback nhân viên trên UI chưa nối. Nếu canary 18/11 không đạt thì dừng mở rộng C.5 và công khai giới hạn như kế hoạch cũ.

## 17/11 — Bước 1 xong: bộ đo + kiểm kê + mốc
- Bộ đo cố định R0 / R1: dev92 (`datagen/datasets/suites/resolved/dev.json` sha `3bf8e02a…`), 92/92 tệp khớp hash; danh sách sha `f4233351…`. Tệp khóa: `runs/c5/r0r1/EVAL_LOCK.json` + `eval_members_sha256.txt`. Ghi công khai: FAQ lập từ gap R0 trên chính bộ này → R1 không phải phép đo độc lập.
- Kiểm kê Git (chỉ đọc): `runs/release-inventory/20261117-pre-ui2/` — tracked 547, untracked 94, tracked khớp ignore 214, cần xem 264. Chưa đổi index / ignore.
- Mốc source: `runs/c5/r0r1/SOURCE_MARK_pre_ui2.md` (cây làm việc khớp đủ 255 tệp v52n-ui); bản gốc 3 tệp sẽ sửa: `runs/c5/base_v52n_ui/`.

## 17/11 — Bản vá A (v52n-ui2): đã code, đang kiểm CPU
- A1 `ui/engine.py::_next_call_no`: số cuộc gọi = max(call_N trong sessions + turns của namespace, bộ đếm RAM) + 1 → tải lại trang không còn UNIQUE(turns) và msg_id không trùng.
- A2 / A3 tab Cải tiến: nút "Gom gap từ feedback nhân viên" (`c5_loop gaps --feedback … --ui-trace … --append`, tùy chọn thêm trace + report dev) và "Soạn nháp FAQ (DeepSeek)".
- A4 đếm gap theo nguồn đúng; gap unmatched giữ lời khách / agent; ghi chú nhân viên đưa vào prompt nháp; `c5_loop draft` bỏ qua gap đã có đề xuất / đã kết luận (sổ `draft_ledger.jsonl`, `--redo` để soạn lại).
- A5 test mới `tests/ui_c5_feedback_check.py` (tải lại trang, feedback → gap → nháp với DeepSeek giả, không nhân bản).
- Freeze `runs/freeze/20261117-v52n-ui2` (256 tệp, danh sách sha `888808e5…`); profile b2_v52n trỏ freeze mới (env không đổi). So v52n-ui khác đúng 6 tệp: ui/engine.py, ui/app.py, scripts/c5_loop.py, profiles/b2_v52n.json, tests/ui_v52n_check.py, tests/ui_c5_feedback_check.py. Kiểm tĩnh tại máy: đường chạy đánh giá không import ui / c5_loop → ĐẠT.
- Job CPU `midzed/sudocode-v52nui2-check-1117` (dataset midzed = source v52n-ui2, cũng là dataset UI cho A7).
- Đã chuẩn bị (chưa đẩy) `runs/c5/r0r1/push_r0r1.py` + `eval_lock_check.py`: ô cổng trước load_secrets kiểm gate / 256 tệp freeze / profile / env / khóa bộ đo / gói FAQ; R0 chỉ đẩy sau khi CPU đạt.

## 17/11 — v52n-ui2: CPU ĐẠT 13/13; R0 dev92 đã đẩy
- `midzed/sudocode-v52nui2-check-1117` (packed_at 09:36): rc 0 cả 13 (core_same, ui_c5_feedback_check, ui_v52n_check, ui_b2_check, ui_check, ui_password_check, c5_loop_check, improve_check, improve_hook_check, target_arch_check, variants_cpu, clean_env, gate_selftest); freeze_apply 256/256 khớp. core_same trên Kaggle: lõi v52n-cand giữ nguyên, đường chạy đánh giá không import ui / c5_loop.
- Cổng đo `runs/c5/r0r1/r0r1_gate.json` (sha 226f9c71…). Sự cố nhỏ: danh sách khóa dev92 ghi CRLF trên Windows → hash tệp lệch; đã đổi về LF, nội dung giữ nguyên, khớp đúng hash đã khóa `f4233351…` (không đổi bộ đo).
- R0 (IMPROVE_DIR rỗng, env = env dev92 ngày 16/11, không khác khóa nào):
  - Full: `midzid/sudocode-c5r0-full-1117`;
  - Baseline: `nnttrang/sudocode-c5r0-base-1117`.
  Ô cổng trước load_secrets kiểm gate / 256 tệp freeze v52n-ui2 / profile / env / khóa dev92 / không có gói FAQ; sau materialize kiểm 92 tệp với danh sách khóa.
- Dataset midzed = v52n-ui2 → người dùng làm A7 (test UI, like / dislike, tải ui_data.zip).
- Tiếp: khi R0 xong → job chấm (reference_eval Full vs Baseline) + gom gap auto_eval từ trace R0 + feedback UI → nháp FAQ.

## 17/11 11:25 — R0 Full xong; Baseline lỗi lần 1 (thiếu secrets); UI v2 (ngoài freeze)
- `midzid/sudocode-c5r0-full-1117` (packed_at 10:10): cổng C.5 đạt (256 tệp freeze v52n-ui2, IMPROVE_DIR rỗng), khóa dev92 92/92, 92 kịch bản / 387 lượt / 0 lỗi LLM, 2442 s.
  - Số Full (chưa có Baseline, chưa phải bảng so sánh): RQR 5,7 %, CCR 78,4 %, TSR 93,5 % (ca khó 92,2 %), HR giá & KM 6,9 %, vi phạm guardrail 7, TTFT p50 / p95 1799 / 3618 ms (p95 VƯỢT ngưỡng 3 s), Call Brief p95 53 ms.
- `nnttrang/sudocode-c5r0-base-1117` lần 1: cổng đạt nhưng notebook chưa gắn Secrets → dừng trước khi gọi model. Người dùng gắn khóa và chạy lại (đang chạy).
- Gap R0 (nguồn 1, auto_eval) → `runs/c5/review_r0/gaps.jsonl`: 31 gap (claim_wrong 12, task_fail 6, no_info 6, guardrail 4, repeat_question 2, customer_repeat 1). no_info: BTCD7-019 phí ship; GEN-T07-01 hoàn tiền 7 ngày; BTCL-041 ×3 (hoàn tiền sau 2 năm — ca chính sách ngoài tài liệu, đúng ra phải giữ unanswered); GEN-T24-01 chứng nhận FDA (ngoài tài liệu). Chỉ khoảng 2 gap có thể có nguồn policy → R1 có thể chênh rất ít; báo đúng như vậy.
- UI v2 theo góp ý bố cục (người dùng giao): tệp MỚI `ui/app_v2.py` + `kaggle/ui_tunnel_v2.py` + `tests/ui_v2_check.py`, KHÔNG đổi tệp nào của freeze v52n-ui2 (sha256 -c đạt; core check đạt) → không chạm cổng R1. Sau R1 mới thay app.py (freeze mới). Job CPU `midzed/sudocode-uiv2-check-1117`.

## 17/11 — Người dùng: "không cần kiểm baseline nữa, chỉ cần kiểm full" → báo cáo R0 Full
- Baseline `nnttrang/sudocode-c5r0-base-1117` không theo dõi nữa (job vẫn chạy trên Kaggle; kết quả còn lấy được nếu cần cho bảng A.6).
- Đối chiếu R0 Full (v52n-ui2) với Full v50 cùng dev92 (16/11): RQR 5,7 / 5,9; CCR 78,4 / 78,4; TSR 93,5 / 93,5 (ca khó 92,2 / 92,2); HR giá & KM 6,9 / 7,4; TTFT p50 1,8 / 2,0 s, p95 3,6 / 3,9 s; vi phạm guardrail 7 / 2.
- TSR trượt chung 5 ca (BTCD7-025, BTCL-016, GEN-T16-01, GEN-T25-01 call_3, JEVNEW-011); đổi chỗ 1 ca: R0 trượt GEN-T09-01 (lượt 1 báo 1.161.000đ trước khi biết size, kịch bản cấm giá này), v50 trượt GEN-T10-01.
- 7 vi phạm claims_human đều là NHÃN SAI của extractor (claim is_human=true gán cho câu báo giá / ghi nhận đơn); agent không câu nào nhận là người, các câu hỏi "người hay máy" đều trả "em là trợ lý AI". v50 cũng có 2 (Baseline v50: 3). Lỗi thuộc lõi extractor → chỉ đề xuất, không tự sửa (lõi đóng băng).

## 17/11 — Candidate B2-TT (tư vấn chỉ đọc hai tầng) theo lời giao — đã code, đang kiểm CPU
- Thiết kế + đánh giá + bảng phân công: `docs/DE-XUAT/THIET-KE-CANDIDATE-B2TT-2026-11-17.md`. Không phải R1 C.5; không tự thành cấu hình chính.
- Lỗi gốc xác nhận trong code: `llm_extract._slot_value` has_children label khong → None; `understanding` loại stance negated; `agent._recommend` / `plan_primitives.step_cost` buộc ASK_NEED với máy lọc không khí khi chưa biết trẻ nhỏ / ngân sách.
- Cách ly: cờ `B2_TWO_TIER` (mặc định tắt) + overlay `runs/freeze/20261117-b2tt-cand/overlay` (9 tệp: config, generator, generator_goals.json, llm_extract, planner_b2 (hook), planner_b2tt (mới), renderer, understanding, tests/b2tt_check.py). Cây làm việc = v52n-ui2 nguyên vẹn (sha256 -c đạt) → cổng R1 không bị chạm.
- Freeze candidate 258 tệp, danh sách sha `6ca92e12…`. Tiêu chí khóa trước: `runs/extra_1115/B2TT_ACCEPT.json` (test b2tt_check sha `a5595d3d…`). Hạn cứng cổng CPU: 18/11 12:00.
- Job CPU `khnhl00/sudocode-b2tt-cpu-1117`: b2tt_check (C1–C13), 13 tệp bảo vệ + guard_report cờ TẮT và BẬT, target_arch / c5_loop / variants / clean_env / gate selftest.
- Giới hạn đã biết của candidate 1: lượt vừa tư vấn vừa hỏi chủ đề khác (COD, chính sách...) → delegate cả lượt về B2 (tiêu chí "rẻ nhất" có thể mất ở lượt ghép); dữ liệu BTC không có ca KM làm đổi thứ tự rẻ nhất (C2 kiểm giá sau KM đúng ngày 11/11).
- API (canary / dev92) CHƯA tạo — chờ cổng CPU đạt và người dùng cho phép chạy.

## 17/11 15:40 — CPU candidate B2-TT: CHƯA ĐẠT (CPU-1, 2/46 kiểm C11b); bảo vệ ĐẠT cả cờ tắt và bật — dừng chờ duyệt
- `khnhl00/sudocode-b2tt-cpu-1117`: freeze_apply overlay 258/258 khớp; frozen_same 0.
  - CPU-2 (cờ TẮT): guard_report 244 đạt + 2 retired → ĐẠT. CPU-3 (cờ BẬT): guard_report 244 đạt + 2 retired → ĐẠT (v10 / v11_1 rc 1 là ca retired như mọi lần).
  - CPU-4: target_arch, c5_loop, variants_cpu, clean_env, gate_selftest rc 0 → ĐẠT.
  - CPU-1 `tests/b2tt_check.py` (sha a5595d3d…): 44 OK / 2 FAIL — cả hai ở C11b "tool lỗi" (got answered_sourced + nói "thấp nhất").
- Chẩn đoán: lỗi ở CÁCH TIÊM LỖI của test, không phải hành vi candidate. Test vá `eval.mock_tools.TOOLS`, nhưng ToolBox dùng một module mock RIÊNG nạp bằng importlib (`harness/tools.py:18–19`, `mt = module_from_spec(...)`) → bản vá không có tác dụng, pricing.get_quote không hề lỗi, candidate trả lời đúng theo dữ liệu đủ. Vì vậy C11b CHƯA kiểm được nhánh tool lỗi (không phải bằng chứng candidate đạt nhánh đó).
- Verdict v1 giữ nguyên: CPU-1 KHÔNG ĐẠT; không sửa test v1.
- Đề xuất chờ duyệt: khóa test v1.1 chỉ đổi ĐÍCH tiêm lỗi sang `harness.tools.mt.TOOLS` (kỳ vọng / oracle không đổi), công khai là sửa sau kết quả; chạy lại riêng b2tt_check (~10 phút CPU). Hạn cổng CPU vẫn 18/11 12:00.

## 17/11 — Candidate kho hướng dẫn điều phối cho Jev (theo KIEN-TRUC-RAG-HUONG-DAN-JEV-2026-11-17.md): hạ tầng + nháp v1 xong, đang kiểm CPU
- Trạng thái nền xác minh từ artifact: bản chính = freeze v52n-ui2 (cây làm việc khớp 256 tệp); B2-TT = overlay `20261117-b2tt-cand`, CPU-2/3/4 đạt, CPU-1 KHÔNG ĐẠT (C11b: tiêm lỗi sai đích), đang chờ quyết định test v1.1.
- Nền chọn: overlay `runs/freeze/20261117-guide-cand` = overlay B2-TT + hạ tầng hướng dẫn (262 tệp, danh sách sha `90084009…`). Hai cờ ĐỘC LẬP, mặc định tắt: `PLANNER_GUIDANCE_DIR` (rỗng = tắt) và `B2_TWO_TIER`. Hướng dẫn chạy được trên planner một tầng (state_for) và hai tầng (outer / inner theo audience).
- Hạ tầng: `harness/guidance.py` (BM25 chuẩn hóa tiếng Việt, fetch_k ≤ 15, context_k ≤ 3, ≤ 800 token ước tính, lọc ngưỡng / năng lực / xung đột / token; truy hồi 1 lần / lượt; khóa gói khi mở phiên); `improve_hook.guidance_package` (chỉ loại planner_guidance, hash khớp PACKAGE.json, sai → từ chối mở phiên); `improve/store` loại `planner_guidance` + luật chặn (tiền / SĐT / mã kịch bản / mã đơn / SKU / lời bỏ quyền / request_commit); `scripts/guidance_loop.py` (import / approve / reject / package / regress / activate / rollback / status); schema `schemas/planner_guidance.schema.json`; trace `planner.loop.guidance` (candidates + score, selected, filtered + lý do, tokens_est, ms, supplied_to_planner).
- GUIDANCE_MIN_SCORE = 1.0 là giá trị TẠM, phải hiệu chỉnh trên dev trước freeze đo.
- Nháp v1 (CHƯA DUYỆT): `runs/c5/guidance_review/drafts_v1.json` — 4 hướng dẫn: GUIDE-NAMED-MODELS (observed R0), GUIDE-PRICE-MIN (UI; capability_blocked trên một tầng), GUIDE-SHORT-ANSWER (UI; capability_blocked trên một tầng), GUIDE-DELIVERY-NO-ORDER (observed R0). Hồ sơ local: `REVIEW-v1.md` + `evidence.jsonl` (6 căn cứ; 8 lỗi R0 phân loại capability_blocked / ngoài phạm vi / đo lường, không soạn).
- Tiêu chí khóa trước: `runs/extra_1115/GUIDE_ACCEPT.json` (guidance_check sha `0af31084…`). Job CPU `khnhl00/sudocode-guide-cpu-1117` (gói FIXTURE duyệt bởi "fixture-reviewer" chỉ để kiểm; không phải gói thật).
- Chưa làm: UI duyệt hướng dẫn (tab Cải tiến); hiệu chỉnh ngưỡng; canary / R0-R1 (cần quyền + gói người dùng duyệt). Kế hoạch đo C.5 theo tài liệu mục 10 (R0 kho rỗng / R1 gói) là quyết định mới — chờ người dùng.

## 17/11 tối — Hợp nhất B2-TT + hướng dẫn thành một candidate (theo chú thích + nhận xét của người dùng): CPU ĐẠT
- Tài liệu: `docs/DE-XUAT/CANDIDATE-TICH-HOP-B2TT-GUIDANCE-2026-11-17.md` (nguyên văn lời giao ở phụ lục). Không phải bản chính, không phải R1 FAQ; hạn khép 18/11 12:00 giữ nguyên.
- Kết quả hai job cũ (đọc từ artifact, verdict giữ nguyên):
  - `guide-cpu-1117` TRƯỢT: G5 — ca đối chứng "Không em." sau câu xác nhận đặt hàng chọn nhầm 3 hướng dẫn, do `query()` nối nguyên văn câu agent.
  - `b2tt-cpu-1117` TRƯỢT: C11b — test tiêm lỗi sai module.
- Freeze tích hợp `runs/freeze/20261117-integ-cand` (263 tệp) = overlay guide-cand + 2 thay đổi:
  - `guidance.query()` bỏ nguyên văn câu agent, chỉ giữ slot vừa hỏi / tác vụ dang dở;
  - test mới `tests/b2tt_check_v1_1.py`: tiêm vào `harness.tools.mt`, có tiền đề + mutant.
- Tiêu chí khóa trước `runs/extra_1115/INTEG_ACCEPT.json` (19:07).
- Job `khnhl00/sudocode-integ-cpu-1117`: **cổng ĐẠT 19/19**.
  - v1.1 50/50;
  - guidance_check 38/38, regress 9/9;
  - 4 chế độ off / tt / g / ttg: bảo vệ 244 + 2 retired, và **0 khác biệt trên 246 ca** so với v52n-cand.
  - `b2tt_check` v1 vẫn rc 1, verdict v1 giữ TRƯỢT.
  - Giới hạn: bộ quyết định kịch bản; chưa chứng minh toàn bộ lời thoại hay Jev thật chọn tốt hơn.
- Profile `profiles/b2_integ_tt.json` (chế độ nền B2-TT). Chưa tạo profile ttg (cần gói thật đã duyệt).
- Feedback người dùng báo trực tiếp ghi lại là feedback thủ công `MF-1117-01` (EV-04 / EV-05: một nguồn, không message ID, chưa đối chiếu trace UI).

| # | Quyết định | Trạng thái |
|---|---|---|
| DI1 | Công nhận `b2tt_check_v1_1` (chỉ đổi đích tiêm lỗi C11b, thêm tiền đề + mutant) làm cổng B2-TT cho candidate tích hợp; v1 + verdict TRƯỢT giữ làm lịch sử | **chờ duyệt** (đã làm theo điều kiện trong nhận xét 17/11; kết quả: đạt) |
| DI2 | Chấp nhận sửa `guidance.query()` bỏ nguyên văn câu agent. Lệch §6 thiết kế kho hướng dẫn ("kèm câu agent vừa hỏi") | **chờ duyệt** |
| DI3 | Duyệt nội dung + test từng hướng dẫn trong `runs/c5/guidance_review/drafts_v1.json`. Trợ lý đề xuất: <br>• rà trước NAMED-MODELS (năng lực tối đa 2 mẫu) và DELIVERY-NO-ORDER; <br>• PRICE-MIN chờ B2-TT; <br>• SHORT-ANSWER để hàng chờ, vì năng lực nằm ở bộ hiểu của B2-TT và hướng dẫn dễ áp nhầm | **chờ duyệt** (người dùng đọc nội dung, không chỉ tên) |
| DI4 | Bộ câu hiệu chỉnh truy hồi (đúng chủ đề / gần giống nhưng không áp dụng / không liên quan) do trợ lý soạn, khóa trước chạy, in điểm mọi ca; chốt ngưỡng, top-k, trần token trước canary. Đã biết thêm: `fold` không bỏ dấu câu | **chờ duyệt** |
| DI5 | Canary API: tt so với ttg, chỉ với hướng dẫn đã duyệt (cần Secrets) | **chờ duyệt** (sau DI3, DI4) |
| DI6 | Tách overlay guidance khỏi B2-TT về mặt vật lý. Trợ lý đề xuất **không tách**: chế độ g + 0 khác biệt ở 4 chế độ đã thay thế; tách thì phải giữ đồng bộ hai bản `planner_b2.py` / `planner_b2tt.py` | **chờ duyệt**

## 17/11 tối — Người dùng CHỐT hướng cải tiến; UI duyệt hướng dẫn: CPU ĐẠT
**Đã chốt (người dùng):**
- Guidance là hướng cải tiến chính; ngừng mở rộng FAQ riêng.
- Tích hợp B2-TT + Guidance + màn duyệt trên UI.
- Giữ hai cờ độc lập và bản quay lui.
- Tạo freeze mới; phải qua CPU và canary trước khi đổi mặc định.
- Đo R0/R1 trên cùng source tích hợp, chỉ khác gói hướng dẫn.
- Người dùng duyệt từng hướng dẫn trước khi kích hoạt.
- Không tự commit/push.

Hệ quả: R0 FAQ (`c5r0-full-1117`) chỉ còn là lịch sử; khóa dev92 dùng lại được cho R0/R1 mới (tt so với ttg).

**Đã làm:**
- Freeze `runs/freeze/20261117-integ-ui` = lõi integ-cand + `ui/engine.py`, `ui/app_v2.py`, `kaggle/ui_tunnel_v2.py`, `profiles/b2_integ_tt.json`, `tests/ui_guidance_check.py`.
- UI_PROFILE=`b2_integ_tt`:
  - thanh bên có hai cờ, áp dụng khi mở cuộc gọi;
  - FAQ không nạp;
  - "Chi tiết lượt" hiện chế độ, hash gói, hướng dẫn được chọn / đưa vào Jev;
  - tab Cải tiến có 4 bước: nhập nháp, duyệt TỪNG cái (loại cần lý do), đóng gói + regress + kích hoạt / quay lui, thử truy hồi.
- Mặc định UI vẫn là `b2_v52n`.
- Thiết kế: `docs/DE-XUAT/CANDIDATE-TICH-HOP-B2TT-GUIDANCE-2026-11-17.md` mục 8.

**Kiểm:**
- `integ-ui-cpu-1117`: **TRƯỢT 13/14**, verdict giữ. Mục trượt duy nhất là `ui_guidance_check` v1 dừng vì bấm nút đang bị vô hiệu (lỗi tiền đề của test).
- `integ-ui2-cpu-1117` (freeze integ-ui2 = integ-ui + test v1.1, code UI giống hệt): **ĐẠT**. v1.1 qua hết; mutant bỏ ràng buộc lý do bị phát hiện.

| # | Quyết định | Trạng thái |
|---|---|---|
| DI7 | Công nhận `ui_guidance_check_v1_1` (đổi đúng tiền đề "nút bị vô hiệu thì AppTest không cho bấm", có mutant) làm cổng UI; v1 + verdict TRƯỢT giữ làm lịch sử | **chờ duyệt** (kết quả: đạt) |
| DI8 | Canary UI: chạy UI candidate trên Kaggle với API (cần Secrets DeepSeek / TypeSafe / UI_PASSWORD), người dùng thử tt so với ttg | **người dùng yêu cầu 17/11 tối** ("đẩy dataset lên midzed cho tôi test UI"): đã đẩy `midzed/sudocode-repo` (cây chính v52n-ui2 + overlay integ-ui2 + 2 manifest + drafts_v1.json; không có evidence.jsonl). Người dùng tự chạy notebook. Kết quả thử UI chưa phải canary đo có tiêu chí khóa trước |

## 18/11 00:xx — UI duyệt hướng dẫn: "Chỉnh sửa" thành phiên bản mới + "So sánh trước / sau (Jev thật)" (lời giao 17/11 tối) — CPU ĐẠT
**Lời giao (người dùng):** thêm nút thử với Jev thật tại màn duyệt (chạy luồng agent thật, hai phiên thử độc lập không / có bản nháp, hiện cạnh nhau: hướng dẫn truy hồi + đưa vào Jev, hành động Jev chọn, tool, câu trả lời, thời gian; bản nháp chỉ dùng trong phiên thử; tạo / sửa / hủy đơn ở môi trường thử) và nút "Chỉnh sửa" cho từng bản nháp (lưu thành phiên bản nháp mới, chạy lại test rồi duyệt; không sửa trực tiếp bản đã đóng gói / đang kích hoạt).

**Đã làm** — freeze mới `runs/freeze/20261118-integ-ui3` (271 tệp) = integ-ui2 + đúng 7 tệp; lõi (harness / core / eval / improve/store.py) KHÔNG đổi:
- `improve/guidance_edit.py` (mới): `revise` → bản mới ở chờ duyệt (version + 1, cùng guide_id, id mới, `revision_of`, giữ test / nguồn). Bản chờ duyệt cũ → Đã loại (lý do "thay bằng …"). Bản ĐÃ DUYỆT cũ giữ nguyên tới khi bản mới được duyệt; gói đã đóng và gói đang kích hoạt không đổi. `approve` → bản đã duyệt cũ cùng guide_id → Đã loại (supersede). Nội dung sửa qua đúng `store.validate`.
- `scripts/guidance_loop.py`: CLI approve dùng cùng luật thay thế; `package` từ chối khi hai bản cùng guide_id đều đã duyệt.
- `scripts/guidance_sandbox.py` (mới) + `ui/engine.py` `sandbox_*`: UI gọi ở TIẾN TRÌNH RIÊNG — DB / mock tool / trace riêng, settings của UI không đổi, kết quả lưu `GUIDE_ROOT/sandbox/<id>/` (đi kèm ui_data.zip, không vào vòng gap). Trước = nền (không hướng dẫn như R0, hoặc các hướng dẫn đã duyệt); sau = nền thay bản cùng guide_id bằng bản nháp. Có thể phát lại lời khách của một cuộc gọi UI làm ngữ cảnh. Tối đa 5 câu / lần. Thiếu khóa API → từ chối chạy (không chạy backend dự phòng rồi gọi là Jev thật).
- `ui/app_v2.py` bước 2: mỗi bản chờ duyệt có "So sánh trước / sau với Jev thật" (bảng Trước / Sau + toàn bộ lượt, lịch sử các lần thử) và "Chỉnh sửa"; bản đã duyệt có "Chỉnh sửa (tạo bản mới)"; cảnh báo khi có hai bản cùng guide_id ở Đã duyệt.
- `profiles/b2_integ_tt.json`: freeze → integ-ui3. Mặc định UI vẫn là `b2_v52n`.

**Kiểm:** tiêu chí khóa trước `runs/extra_1115/INTEG_UI3_ACCEPT.json`; job `khnhl00/sudocode-integ-ui3-cpu-1118` (script `runs/extra_1115/push_integ-ui3-cpu-1118.sh`): test mới `ui_guidance_edit_check` (sửa / thay thế / gói không đổi; so sánh trước / sau với model giả; tiến trình thử từ chối khi thiếu khóa; AppTest; 2 mutant) + core_same + hồi quy UI / guidance / improve; `ui_guidance_check_v1_1` và `ui_v2_check` chỉ được trượt đúng dòng tên / hash freeze đã khai báo trước. **Kết quả (17/11 23:31, 171 s): cổng ĐẠT 11/11** — freeze_apply 271/271 khớp; core_same đúng 7 tệp (lõi không đổi); `ui_guidance_edit_check` 48 OK / 0 FAIL (gồm 2 mutant bị phát hiện; tiến trình thử thật từ chối khi thiếu khóa); `ui_guidance_check_v1_1` 56 OK + đúng 1 FAIL đã khai báo (tên freeze); `ui_v2_check` 28 OK + đúng 1 FAIL đã khai báo (hash engine); guidance / improve / improve_hook / ui / ui_password / ui_b2 / ui_c5_feedback rc 0. Output `runs/kaggle/integ-ui3-cpu-1118/`. Với model giả, câu trả lời trước / sau giống hệt nhau (bộ quyết định giả bỏ qua hướng dẫn) — đúng như dự kiến, chỉ chứng minh nối luồng.

**Giới hạn:** CPU chỉ dùng model giả → chứng minh nối luồng / cô lập, KHÔNG chứng minh hướng dẫn giúp Jev thật. Nút so sánh với Jev thật cần Secrets (người dùng chạy trên UI). Một lần chạy model thật chỉ là kết quả thử để đọc khi duyệt, không phải phép đo. Test đi kèm giữ nguyên khi sửa (chưa sửa test trên UI).

| # | Quyết định | Trạng thái |
|---|---|---|
| DI9 | Nhận freeze integ-ui3 (sửa → phiên bản mới; so sánh trước / sau Jev thật) làm UI candidate thay integ-ui2, sau khi CPU đạt | **chờ duyệt** (CPU đạt) |
| DI10 | Đẩy dataset integ-ui3 lên midzed để người dùng thử UI với Secrets (như DI8) | **người dùng yêu cầu 18/11** ("đẩy dataset mới lên midzed cho tôi test"): đã đẩy `midzed/sudocode-repo` (cây chính v52n-ui2 + overlay integ-ui3 + 2 manifest + drafts_v1.json; không có evidence.jsonl), script `runs/extra_1115/push_uicand3-midzed-1118.sh`. Không đẩy kernel; người dùng tự chạy notebook. Kết quả thử UI chưa phải canary đo có tiêu chí khóa trước |

## 18/11 — Đo API candidate tích hợp chế độ tt, dev92, CHỈ Full, chia 3 tài khoản (người dùng: "đẩy job lên kaggle rồi chạy API … chia ra 2-3 acc chạy song song bản full thôi, nếu đạt thì qua luôn không cần bản baseline")
- Chế độ **tt** (B2_TWO_TIER=1, PLANNER_GUIDANCE_DIR rỗng, không FAQ): chưa có gói hướng dẫn nào được duyệt (DI3) nên chưa đo được ttg. Lần đo này kiểm bản tích hợp không làm hỏng bản chính + năng lực B2-TT trên dev92.
- Nguồn: freeze `runs/freeze/20261118-integ-ui3` (CPU ĐẠT 11/11), profile overlay `b2_integ_tt`. Bộ đo dev92 khóa (`runs/c5/r0r1/EVAL_LOCK.json`), chia 3 phần cố định trước `runs/c5/integ_tt/SHARDS.json` (129 / 129 / 129 lượt; 30 / 31 / 31 kịch bản).
- **Tiêu chí khóa trước** `runs/extra_1115/INTEG_TT_API_ACCEPT.json`, so với R0 Full v52n-ui2 cùng dev92: TSR ≥ 85/92 (R0 86); HR giá & KM ≤ 7,9 % (R0 6,9); RQR ≤ 6,7 % (R0 5,7); CCR ≥ 76,4 % (R0 78,4); guardrail chỉ loại claims_human, tổng ≤ 9 (R0 7); TTFT p95 ≤ 4118 ms (R0 3618); đủ 92 kịch bản / 387 lượt, không lỗi LLM. Đạt hết → theo lời giao chuyển sang gộp source tích hợp vào nhánh chính (guidance vẫn tắt). Trượt một mục → không gộp, báo từng ca. Các ngưỡng do trợ lý đặt (lời giao không nêu số) — công khai ở đây.
- Kernel (cổng chèn trước load_secrets: integ_gate.json + 271 tệp freeze kiểm cả overlay + profile + env tt + khóa dev92 + SHARDS; pre: freeze_apply overlay → kiểm settings → materialize → eval_lock_check 92 → shard_suite):
  - `midzid/sudocode-integtt-s1-1118` (phần 1) — cổng ĐẠT trên Kaggle, dừng ở nạp Secrets (chưa gắn);
  - `nnttrang/sudocode-integtt-s2-1118` (phần 2);
  - `elylish11/sudocode-integtt-s3-1118` (phần 3).
  Script `runs/c5/integ_tt/push_integ_tt.py`. Sự cố nhỏ: lần đẩy dataset midzid đầu lỗi quyền thư mục tạm (thiếu TEMP) → kernel v1 chạy trên dataset cũ, cổng chặn trước khi nạp khóa; đã đẩy lại dataset + kernel v2.
- **Cần người dùng:** gắn Secrets DEEPSEEK_API_KEY + TYPESAFE_API_KEY cho cả 3 notebook rồi Save & Run All. Xong cả 3 → trợ lý gộp trace + chấm (job CPU) theo tiêu chí đã khóa.

## 18/11 01:10 — Kết quả đo API tt (phần 1 + 2 xong, phần 3 đang chạy): **KHÔNG ĐẠT — không gộp vào bản chính**
- Phần 1 `midzid/integtt-s1-1118` và phần 2 `nnttrang/integtt-s2-1118`: freeze_apply 271 khớp, eval_lock 92 khớp, shard ok, đủ 129 lượt mỗi phần. Phần 3 `elylish11` còn chạy.
- **API-2 (TSR) đã trượt bất kể phần 3**: 6 ca trượt của R0 (cả dev92) đều nằm trong phần 1 + 2; candidate trượt 9 ca ở hai phần này = 6 ca cũ + **3 ca MỚI**, sửa được 0 → tối đa 83/92 < 85. **API-3 (HR giá & KM) cũng trượt**: 16 claim sai chỉ trong hai phần (R0 cả dev92: 11); phần 1 14,3 %, phần 2 18,2 %. TTFT p95 phần 1 / 2: 4115 / 3964 ms (sát ngưỡng 4118).
- Ca mới trượt:
  - **V3-123 call_1 — ghi sai do B2-TT**: khách nêu tên mẫu ("mo a bê bê" = Moaz Bebe) + ngân sách 2 tr → B2-TT chọn `consult_recommend@me-be`, gợi ý *Túi trữ sữa Sunmum 119.000đ* → lượt sau khách "lấy 1 cái" → **order.create sai sản phẩm**. R0 báo đúng Moaz Bebe 1.890.000đ rồi tạo đúng đơn.
  - **GEN-T01-01 call_2 — do B2-TT ở call_1**: khách nói "phòng 25 m², có để ý mẫu AirPure Pro" (criteria `mentioned: [SKU-AP-PRO]`) → `consult_recommend` gợi ý *Xiaomi Smart 4 Lite 2.990.000đ* thay vì mẫu khách nêu → bộ nhớ lưu Xiaomi → call_2 tạo đơn Xiaomi (kịch bản cần AirPure Pro 7.690.000đ).
  - BTCL-066 call_2: lượt 1 call_1 delegate (asks=attribute), agent hỏi lại "muốn biết thông tin gì" thay vì báo giá AirPure X → call_2 không có pricing.get_quote. Chưa xác định chắc là do candidate hay dao động.
- **Nguyên nhân gốc (đọc trace):** tác vụ `consult_recommend@<nhóm>` được mở cả khi khách ĐÃ NÊU mẫu cụ thể (`criteria.mentioned` khác rỗng, scope=mentioned) và xếp hạng lại cả nhóm → bỏ mẫu khách nêu. 10 lượt `answered_sourced` trên 258 lượt (7 là recommend máy lọc không khí). HR tăng phù hợp với việc báo giá sản phẩm khác kỳ vọng kịch bản (chưa đọc từng claim).
- Theo luật khóa trước: **không gộp**, bản chính giữ v52n-ui2. Candidate giữ là thử nghiệm.

| # | Quyết định | Trạng thái |
|---|---|---|
| DI11 | Sửa B2-TT: khách đã nêu mẫu cụ thể (`mentioned` khác rỗng) → không mở `consult_recommend` (delegate cho luồng chính / chỉ quote mẫu đã nêu); thêm 2 ca V3-123 / GEN-T01-01 vào test CPU; freeze mới → CPU → đo lại API 3 phần. Hạn khép candidate 18/11 12:00 | **chờ duyệt** |
| DI12 | Nếu không sửa: dừng candidate, ghi hạn chế công khai, hồ sơ hoàn thiện trên v52n-ui2 (UI duyệt hướng dẫn vẫn dùng được ở chế độ off / g) | **chờ duyệt** |

## 18/11 01:20 — Đo API tt: đủ 3 phần — **KHÔNG ĐẠT 4/7 tiêu chí** (không gộp, bản chính giữ v52n-ui2)
- Phần 3 `elylish11/integtt-s3-1118`: freeze 271 / eval_lock 92 / shard ok; TSR 31/31, HR 2,1 %, RQR 11,1 %, TTFT p95 5337 ms.
- Gộp 3 phần (cộng tử / mẫu từ report.json của reference_eval từng phần; TTFT p95 tính lại từ 387 lượt trace — số gộp tính tại máy, chưa phải report gộp chính thức):

| Tiêu chí | Candidate tt | R0 Full v52n-ui2 | Ngưỡng | Kết quả |
|---|---|---|---|---|
| TSR | 83/92 = 90,2 % | 86/92 = 93,5 % | ≥ 85/92 | TRƯỢT |
| RQR | 2/31 = 6,5 % | 2/35 = 5,7 % | ≤ 6,7 % | đạt |
| CCR | 74/97 = 76,3 % | 76/97 = 78,4 % | ≥ 76,4 % | TRƯỢT (sát) |
| HR giá & KM | 17/148 = 11,5 % | 11/159 = 6,9 % | ≤ 7,9 % | TRƯỢT |
| Guardrail | 4 (claims_human) | 7 | ≤ 9 | đạt |
| TTFT p95 | 4322 ms (p50 2086) | 3618 ms | ≤ 4118 ms | TRƯỢT |
| Đủ 92 kịch bản / 387 lượt | có | | | đạt |

- Ca trượt TSR: 6 ca cũ của R0 + 3 ca mới (V3-123, GEN-T01-01 — do `consult_recommend` bỏ mẫu khách nêu, dẫn tới tạo đơn sai sản phẩm; BTCL-066 — chưa rõ). Không ca nào được sửa. Chi tiết mục 01:10.
- Output: `runs/kaggle/integtt-s{1,2,3}-1118/`, số gộp `runs/c5/integ_tt/merged_local.json`. Quyết định DI11 / DI12 vẫn chờ.

## 18/11 02:xx — Soạn bộ hướng dẫn v2 từ lỗi của lần đo tt (người dùng: "tiến hành soạn"; cho phép merge nếu ttg đạt đủ cổng)
- **Quyền merge (người dùng, 18/11):** được merge source tích hợp vào nhánh chính KHÔNG cần xin lại, **chỉ khi** ttg đạt toàn bộ cổng INTEG_TT_API_ACCEPT **và** kiểm riêng không còn ca tạo đơn sai sản phẩm; số gộp (nhất là TTFT p95) tính từ dữ liệu từng lượt. ttg trượt → giữ v52n-ui2. Duyệt từng hướng dẫn vẫn là bước riêng của người dùng.
- Mốc trước cải tiến = lần đo tt `integtt-s{1,2,3}-1118` (code / cấu hình / bộ đo giữ nguyên; R1 chỉ thêm gói hướng dẫn).
- Đã đọc toàn bộ 9 ca trượt TSR + 18 claim sai, đối chiếu R0, kỳ vọng kịch bản dev92 (exposure used-for-development) và danh mục bước thật của Jev. Phân loại: 10 lỗi chọn hành động → hướng dẫn; 7 ghi riêng (code: vòng lặp xác nhận, giỏ nhiều món, xếp hạng gợi ý; capability_blocked: chọn dòng chính sách trong answer_ask; đo lường / extractor: 3 ca).
- **Nháp v2** `runs/c5/guidance_review/drafts_v2.json` (CHƯA DUYỆT; bảng duyệt `REVIEW-v2.md`; căn cứ EV-07…EV-23 trong `evidence.jsonl`, chỉ local):
  1. CONSULT-NAMED-MODEL (mới, tầng trong B2-TT) — khách đã nêu mẫu → chọn finish_unresolved trước survey để luồng chính xử lý đúng mẫu (2 ca tạo đơn sai V3-123, GEN-T01-01 + BTCL-031, GEN-T27-01). Năng lực có thật: tầng ngoài không được hỏi (direct_single_task) nhưng tầng trong có finish_unresolved → delegate.
  2. NAMED-MODELS (v1 giữ nguyên) — thêm căn cứ BTCL-021, GEN-T27-01.
  3. DELIVERY-NO-ORDER v2 — đọc giá mẫu đang tư vấn trước khi trả lời giao hàng (BTCL-016).
  4. GENERIC-PRODUCT-ASK (mới) — hỏi chung một mẫu → báo giá / kho trước (BTCL-066).
  5. VARIANT-BEFORE-PROMO-PRICE (mới) — chưa biết size thì chưa báo giá sau giảm (GEN-T09-01). Năng lực CHƯA CHẮC.
  6. OLD-PRICE-NOT-CURRENT (mới) — giá kênh khác lệch → nói rõ chương trình cũ hết (GEN-T25-01). Năng lực CHƯA CHẮC.
  Không đưa vào: PRICE-MIN (dev92 không có lỗi này), SHORT-ANSWER (giữ hàng chờ).
- **Hiệu chỉnh truy hồi** (bộ câu khóa trước `calibration_v2.json`; job CPU `khnhl00/sudocode-guidev2-cpu-1118`): ngưỡng 3.0 → đúng chủ đề 11/11, không liên quan kéo theo 1/6, test nháp 13/13; câu gần giống bị chọn 5/7 ở MỌI ngưỡng (phải nhờ Jev đọc điều kiện — rủi ro áp nhầm chính).
- **Rủi ro lớn nhất:** TTFT p95 (4322 > 4118 ms) không sửa được bằng hướng dẫn, hướng dẫn còn thêm token → ttg có thể vẫn trượt cổng dù sửa được TSR / HR.

| # | Quyết định | Trạng thái |
|---|---|---|
| DI13 | Duyệt / sửa / loại TỪNG hướng dẫn trong drafts_v2 (đọc REVIEW-v2.md hoặc trên UI integ-ui3) | **chờ người dùng** |
| DI14 | Cấu hình truy hồi cho ttg: GUIDANCE_MIN_SCORE 3.0, GUIDANCE_CONTEXT_K 2, MAX_TOKENS 800, FETCH_K 15 (đề xuất trợ lý) | **chờ duyệt** |
| DI15 | Sau DI13 + DI14: đóng gói → canary tt vs ttg (ca lỗi + cách nói khác + đối chứng, mỗi ca 3 lần) → nếu đạt, dev92 ttg 3 phần trên cùng code / cấu hình / bộ đo → merge nếu đạt đủ cổng | **chờ DI13, DI14** |

## 18/11 08:35 (đính chính giờ, trước ghi nhầm 09:40) — Sửa hướng dẫn v2 theo review + kiểm gói cuối 3.0 / K=2 + chuẩn bị canary (người dùng: "đồng ý tiếp tục guidance v2 … sửa từng hướng dẫn … gửi phần nội dung đã sửa để tôi duyệt, rồi chạy canary tt/ttg")
- Nháp sau review `runs/c5/guidance_review/drafts_v2.json` (sha `08696e8b…`, 6 hướng dẫn, đều tăng version), script `make_drafts_v2.py`; bản trước review giữ `drafts_v2.pre-review.json` (`3014de5f…`). Chi tiết + lý do: `REVIEW-v2.md` §6.
- Trọng tâm: thời gian giao chỉ theo bằng chứng chính sách đọc trong lượt, không tự gán khu vực / quy ra ngày; "KM đã kết thúc" chỉ khi `expired_promos` ghi đúng chương trình và shop từng báo đúng mức đó cho cùng mẫu (khớp `_price_claim_target`); KM áp dụng / loại trừ size chỉ theo kết quả báo giá biến thể; mẫu chưa xác định → hỏi rõ; thêm ngoại lệ cho các dạng lời khách thật hay kéo nhầm.
- Job CPU `khnhl00/sudocode-guidev2r-cpu-1118` (3.0 / K=2): vòng đời + regress đạt, test nháp 13/13; calibration_v2: đúng 11/11, gần giống nhầm 3/7, không liên quan 1/6; bộ bổ sung dạng lời khách thật: gần giống nhầm 5/5. Mô phỏng trên 387 lượt tt: 211 lượt / 85 kịch bản bị kéo hướng dẫn.
- Canary chuẩn bị, CHƯA đẩy: `runs/c5/guidance_canary/` (CANARY.json sha `af631e56…`, 36 kịch bản × 3 lần / chế độ), tiêu chí khóa `runs/extra_1115/GUIDE_V2_CANARY_ACCEPT.json` (CN-0…CN-5), `push_canary.py`, `canary_eval.py`.
- Hạn khép candidate 18/11 12:00 (không tự gia hạn): canary (~1 giờ sau khi gắn Secrets) + dev92 ttg (~1 giờ) khó xong trước 12:00.

| # | Quyết định | Trạng thái |
|---|---|---|
| DI13 | Duyệt / sửa / loại TỪNG hướng dẫn trong drafts_v2 sau review (sha `08696e8b…`) | **chờ người dùng** |
| DI14 | Cấu hình truy hồi ttg: MIN_SCORE 3.0, CONTEXT_K 2, MAX_TOKENS 800, FETCH_K 15 | **người dùng chốt 18/11** (lời giao) |
| DI16 | Tiêu chí canary CN-0…CN-5 (`GUIDE_V2_CANARY_ACCEPT.json`), gồm CN-5: TTFT p95 ttg ≤ tt × 1,05 mới chạy dev92 | **chờ duyệt** |
| DI17 | Đề xuất sửa code (KHÔNG làm trong đợt này): `planner_b2.py` truyền audience để planner chính không nhận hướng dẫn `inner`; lọc truy hồi theo `asks` có kiểu | **đề xuất** |
| DI18 | Hạn 12:00: gia hạn candidate để chạy canary + dev92, hay dừng ở canary | **chờ người dùng** |

## 18/11 ~08:40–09:10 — DI17 + NAMED-MODELS / biến thể + snapshot integ-ui4 + cổng CPU (lời giao: "Sửa DI17 trước, chỉnh lại NAMED-MODELS và điều kiện biến thể như nhận xét. Tạo snapshot mới, kiểm CPU và khóa rõ cách tính hồi quy. … chạy nhóm ca ngoại lệ nhỏ trước; đạt mới chạy đầy đủ. Hai chế độ phải cùng snapshot. Giữ nguyên cổng dev92 và điều kiện không có đơn sai sản phẩm; chưa merge trước khi đủ bằng chứng." + "đẩy lên 2-3 account kaggle chạy song song")
- **DI17 đã sửa** trong snapshot mới `runs/freeze/20261118-integ-ui4` (272 tệp, list `209b5b65…`; đổi đúng 10 tệp so với integ-ui3): lọc truy hồi theo `asks_any` (nhãn hỏi có kiểu của bộ hiểu); planner chính nhận audience "main" (không nhận hướng dẫn tầng trong); chọn k / trần token theo audience. Mô phỏng 387 lượt tt: lượt có hướng dẫn 211 → 87, kịch bản 85 → 53, lượt lỗi đích giữ 11/12.
- Nháp `drafts_v2.json` `bb5016b1…`: NAMED-MODELS v3 + VARIANT v3 sửa nội dung; 4 hướng dẫn khác chỉ thêm `asks_any`. Không có văn bản "nhận xét" trong repo — điểm sửa ghi ở REVIEW-v2 §7.
- Tiêu chí khóa trước: `runs/extra_1115/INTEG_UI4_ACCEPT.json` (08:51), canary 2 giai đoạn + **định nghĩa hồi quy R-1…R-9** `runs/extra_1115/GUIDE_V2_CANARY_ACCEPT_v2.json` (08:57).
- **Job A** `khnhl00/sudocode-integ-ui4-cpu-a-1118`: DI17 test mới 25/25 (3 mutant bị bắt), guidance_check cũ / b2tt v1.1 / improve / UI đạt, gói thật `pkg_g2r` (approved_hash `91de8bf1…`) regress 13/13 ở 3.0 / K=2. **U4-4 TRƯỢT theo chữ:** `ui_guidance_edit_check` chỉ trượt dòng `startup_check: code khớp freeze integ-ui3` (test viết cứng tên snapshot cũ; kết quả thật: status ok, freeze integ-ui4, checked 272) — dòng này không được khai khi khóa → không tự miễn. `cand_ui_v2`: 25/25, không dòng nào trượt (dòng được phép trượt không xảy ra) → đạt theo nghĩa U4-5.
- **Job B** `nnttrang/sudocode-integ-ui4-cpu-b-1118`: ĐẠT — 4 chế độ off / tt / g / ttg × 13 bộ bảo vệ: 0 lỗi; guard_diff 0 khác biệt trên 246 ca ở cả 4 chế độ; frozen_same đạt; freeze 272/272 khớp ở cả hai job. Tổng hợp `runs/c5/guidance_canary/ui4_gate.json`: đạt U4-1..3, U4-5..9; **trượt U4-4** → pass=false, canary CHƯA đẩy.
- Đính chính: các mốc giờ 09:05 / 09:35 / 09:40 / 10:35 / 10:45 / "~10:00" ghi trước đó là ước sai của trợ lý; giờ đúng ghi trong REVIEW-v2 §7.

| # | Quyết định | Trạng thái |
|---|---|---|
| DI17 | Sửa audience planner chính + lọc theo asks có kiểu | **đã duyệt + đã làm** (integ-ui4) |
| DI13 | Nội dung 6 hướng dẫn (drafts_v2 `bb5016b1…`) | NAMED-MODELS / VARIANT sửa theo lời giao; 4 cái còn lại giữ nội dung đã gửi 08:35. Gói `pkg_g2r` ghi người duyệt theo lời giao — **người dùng có thể loại từng cái trước khi gắn Secrets** |
| DI16 | Tiêu chí canary | **thay bằng** GUIDE_V2_CANARY_ACCEPT_v2 (2 giai đoạn, R-1…R-9) — người dùng đồng ý hướng canary 18/11 |
| DI19 | Miễn U4-4 cho đúng một dòng `startup_check: code khớp freeze integ-ui3` của `ui_guidance_edit_check` (tên snapshot viết cứng), mọi dòng chức năng đạt | **chờ duyệt** (trợ lý không tự miễn; không miễn thì phải làm test v1.1 + chạy lại job A) |
| DI18 | Hạn khép candidate 12:00 | **chờ người dùng** (giờ đúng hiện tại ~09:10, còn ~3 giờ) |

## 18/11 ~09:15–10:05 — Làm theo bản chốt cơ chế cải tiến (người dùng: "đọc và xem coi phần nào bạn chưa làm thì làm cho tôi")
- Báo cáo đầy đủ 4 mục trước API: `docs/DE-XUAT/BAO-CAO-TRUOC-API-GUIDANCE-V3-2026-11-18.md`. Chưa chạy API.
- Kho hướng dẫn v3.1 (`runs/c5/guidance_review/drafts_v3.json` `bfc8a7a4…`, diff `DIFF-v3.md`): 4 hướng dẫn chỉ nói việc chọn bước; GENERIC gộp vào NAMED; VARIANT capability_blocked (bỏ khỏi gói, `capability_log_v3.json`).
- Snapshot `runs/freeze/20261118-integ-ui5` (277 tệp `fdfcc1ac…`; đường chạy agent = ui4): thêm danh mục hành động thật, DeepSeek soạn nháp hướng dẫn từ feedback (`scripts/guidance_draft.py`, trước đây CHƯA có), test audience đường thật, test UI v1.1. Cổng CPU ui5 ĐẠT 9/9 (A khnhl00, B nnttrang, C midzed). Truy hồi gói cuối v3.1 (`khnhl00/sudocode-retr-v31-1118`): lượt lỗi đích 10/11; câu đúng chủ đề 11/13; câu gần giống chọn nhầm 3/10; không liên quan 0/9.
- Canary v3 khóa trước `runs/extra_1115/GUIDE_V3_CANARY_ACCEPT.json` (giai đoạn 1: 9 ca lỗi + 20 probe; giai đoạn 2: 12 đối chứng; R-1…R-9). dev92 chấm trace gộp `runs/c5/integ_tt/dev92_merge_eval.py` (chuẩn bị).
- DI19 (miễn U4-4) không còn cần: snapshot ui5 dùng test v1.1, cổng ui5 đạt không miễn trừ. Gói `pkg_g2r` (ui4) không dùng.
- Lưu ý: job C ghi đè dataset `midzed/sudocode-repo` (dataset thử UI) — cần đẩy lại bản UI nếu người dùng muốn thử UI.

| # | Quyết định | Trạng thái |
|---|---|---|
| DI13 | Duyệt TỪNG hướng dẫn trong drafts_v3.1 (CONSULT-NAMED-MODEL v5, NAMED-MODELS v4, DELIVERY-NO-ORDER v5, OLD-PRICE-NOT-CURRENT v4) | **chờ người dùng** |
| DI20 | Tiêu chí canary v3 + định nghĩa hồi quy (GUIDE_V3_CANARY_ACCEPT.json), gồm S1-5 (≥ 1 ca lỗi cải thiện mới chạy giai đoạn 2) và F-5 (TTFT) | **chờ duyệt** |
| DI21 | Đề xuất code ngoài phép đo: bước hỏi biến thể trong B2; sửa mô tả finish_unresolved; câu chữ alternative_quote | **đề xuất** |
| DI18 | Hạn khép candidate 12:00 | **chờ người dùng** |

## 18/11 ~10:10 — Người dùng DUYỆT 4 hướng dẫn + tiêu chí v3 + TTFT; chạy canary giai đoạn 1 (chỉ Full, chia tài khoản)
- Lời duyệt: "Tôi duyệt bốn hướng dẫn đúng phiên bản và hash đã nêu để đóng gói chạy canary. Đồng ý cách tính TTFT không bỏ lượt khởi động và hai ngưỡng S1-6/F-5, với ý nghĩa là quy tắc dừng sớm, không phải kết luận thay cho dev92 … kiểm lại canary_eval.py trên CPU. Sau đó đẩy hai job cùng snapshot ui5. Không đổi gói hoặc tiêu chí giữa phép đo. Quá 12:00 chỉ hoàn tất canary đang chạy, chưa tự mở dev92 hoặc merge." + "chia ra tầm 2 acc … chạy full thôi không chạy baseline" + "chạy trên midzed, midzid, elylish, nnttrang thôi".
- Xác nhận: CHƯA có lần chạy API canary nào và trợ lý CHƯA xem kết quả API nào của gói v3 trước khi khóa S1-6 / F-5 (lần đo API gần nhất là tt dev92 trên ui3, trước bản v3).
- Tiêu chí: `runs/extra_1115/GUIDE_V3_CANARY_ACCEPT.json` sha `2d00902f…` (thêm S1-6, F-5 = TTFT p95 ttg ≤ 4118 ms VÀ ≤ tt × 1,05; mọi lượt, không bỏ khởi động, p95 của reference_eval) — quy tắc dừng sớm, không thay cổng dev92.
- Job CPU `nnttrang/sudocode-userpkg-g3b-1118`: tự kiểm canary_eval (output giả có đáp án) + đóng gói thật drafts_v3 `bfc8a7a4…` (người duyệt = người dùng). Job đóng gói trên khnhl00 đã dừng trước khi tạo kernel (tài khoản ngoài danh sách cho phép).
- Canary giai đoạn 1 sẽ chạy: tt → elylish11, ttg → midzid (cùng integ-ui5, chỉ cấu hình Full).

| # | Quyết định | Trạng thái |
|---|---|---|
| DI13 | 4 hướng dẫn drafts_v3.json `bfc8a7a4…` | **đã duyệt** 18/11 |
| DI20 | Tiêu chí canary v3 + S1-6 / F-5 | **đã duyệt** 18/11 (dừng sớm, không thay dev92) |
| DI18 | Quá 12:00 | **đã quyết**: chỉ hoàn tất canary đang chạy; không tự mở dev92 / merge |
- 10:14 job `nnttrang/sudocode-userpkg-g3b-1118`: canary_eval_selftest 17/17 đạt; gói thật `pkg_g3` approved_hash `74ed2b4c…` (4 hướng dẫn, khớp từng trường drafts_v3 `bfc8a7a4…`), regress 10/10 ở 3.0 / K=2. `canary_gate.json` sha `71a0ccd4…`.
- Giai đoạn 1 đã đẩy: tt `elylish11/sudocode-gc1-tt-r123-1118`, ttg `midzid/sudocode-gc1-ttg-r123-1118` (integ-ui5, chỉ Full, 3 lần). Cả hai qua cổng kernel và dừng ở bước nạp khóa (chưa gắn Secrets) — CHƯA gọi model. Sự cố: lần đẩy tt đầu bị cổng chặn vì script đòi kiểm tệp gói ở chế độ tt (tt không mang gói) — sửa push_canary.py chỉ kiểm gói ở ttg, đẩy lại tt; gói, tiêu chí, snapshot, kernel ttg không đổi.
- Cần người dùng: gắn DEEPSEEK_API_KEY + TYPESAFE_API_KEY cho 2 notebook rồi Save & Run All.

## 18/11 11:15 — Canary giai đoạn 1 (integ-ui5): **KHÔNG ĐẠT** (S1-1, S1-6) → dừng, không chạy giai đoạn 2, không dev92, không merge
- Job: tt `elylish11/sudocode-gc1-tt-r123-1118`, ttg `midzid/sudocode-gc1-ttg-r123-1118` — cả hai qua cổng kernel (log: "CỔNG CANARY đạt", 277 tệp ui5, gói, khóa dev92), nạp đủ 2 khóa, 0 lượt lỗi LLM, 3 lần × 29 kịch bản. Chấm: `runs/c5/guidance_canary/stage1_report.json` (canary_eval đọc bằng chứng cổng từ log kernel vì runner dọn output sau cổng — chỉ đổi nguồn đọc, không đổi tiêu chí).
- S1-0 đạt · **S1-1 TRƯỢT**: ttg tạo đơn sai sản phẩm ở V3-123 (SKU-MB-BAG thay SKU-MB-STER) và GEN-T01-01 call_2 (SKU-XM-4L thay SKU-AP-PRO) ở cả 3 lần — tt cũng sai y hệt cả 3 lần (lỗi nền B2-TT, hướng dẫn không sửa được) · S1-2 đạt (0 hồi quy) · S1-3 đạt (probe 54 vs 45) · S1-4 đạt · S1-5 đạt · **S1-6 TRƯỢT**: TTFT p95 ttg 4493 ms > 4118 và > tt 4226 × 1,05 = 4437 (tt cũng > 4118).
- Cải thiện (tt ≤ 1/3 → ttg ≥ 2/3): BTCL-016, BTCL-066, CNY-DL-OOS, CNY-PX-COMPARE, CNY-PX-GENERIC. Không đổi 0/3 cả hai: GEN-T01-01, V3-123, GEN-T09-01 (VARIANT — capability_blocked, đúng dự kiến), GEN-T25-01, CNY-DL-NOREGION, CNY-VP-EXCL.
- Chẩn đoán V3-123 / GEN-T01-01 (trace ttg lần 1): hướng dẫn CONSULT-NAMED-MODEL ĐÃ được đưa vào tầng trong (supplied_to_planner), nhưng Jev vẫn chọn survey → answer (gợi ý mẫu khác) thay vì finish_unresolved → lượt sau tạo đơn mẫu sai. Được truy hồi + được đưa vào ≠ thay đổi lựa chọn. Có thể liên quan mô tả finish_unresolved Jev thấy ("báo khách giới hạn", DI21) — chưa kiểm.
- Lúc 11:15, trước 12:00. Không chạy thêm gì.

| # | Quyết định | Trạng thái |
|---|---|---|
| DI22 | Hướng xử lý sau canary trượt: (a) giữ v52n-ui2 làm bản chính, công khai kết quả; (b) đề xuất sửa nền B2-TT ngoài phép đo hướng dẫn (DI11: không mở consult_recommend khi khách đã nêu mẫu; DI21: mô tả finish_unresolved), rồi đo lại tt / ttg trên snapshot mới; (c) giảm TTFT nền B2-TT trước khi đo tiếp | **chờ người dùng** |
