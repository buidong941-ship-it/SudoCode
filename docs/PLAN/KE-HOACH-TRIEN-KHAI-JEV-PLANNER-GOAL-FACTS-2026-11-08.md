# Bàn giao triển khai: Jev planner, extractor và hợp đồng goals/facts

Ngày lập: 08/11/2026. Nơi thực hiện: luồng chính.

**Trạng thái: NGƯỜI DÙNG ĐÃ DUYỆT TRIỂN KHAI các đề xuất mới trong phạm vi dưới đây.** File này được tạo ở cuộc trò chuyện nhánh để bàn giao; chưa triển khai runtime, chưa đẩy job Kaggle từ cuộc trò chuyện nhánh. Không coi trạng thái “đề xuất chưa triển khai” trong tài liệu cũ là yêu cầu xin duyệt lại phạm vi đã được duyệt ở đây.

## 1. Yêu cầu đã duyệt và ranh giới thực thi

Người dùng yêu cầu:

> “tôi duyệt hết. test ở chế độ hệ thống full thôi. ... mới đầu thì dùng qwen trước đi còn đến cuối cùng thì chọn deepseek. tiến hành lần lượt hết tất cả đề xuất mới rồi đẩy job lên kaggle ở path D:\User\Documents\kaggle_api_key để test đi (nếu có nhiều job thì chia ra nhiều account mà chạy song song) nhưng lưu ý là giả lập jev để tiết kiệm token trước rồi sau khi thống nhất mới chạy bản có jev cuối.”

Diễn giải thực thi:

- Triển khai tuần tự các thay đổi; không chỉ viết kế hoạch rồi dừng.
- Chạy đánh giá hệ thống **chỉ `full`**. Không chạy `baseline_no_memory`, kể cả runner suite có mặc định chạy cả hai. Các test hàm/hợp đồng/schema không phải một config đánh giá hệ thống; vẫn chạy những kiểm tra cần thiết trên Kaggle, không tự chạy một suite có baseline trái yêu cầu.
- Giai đoạn đầu dùng Qwen; chuẩn bị và đo cấu hình DeepSeek ở giai đoạn cuối. Kết quả cuối với Jev thật chỉ chạy **sau khi người dùng thống nhất** dựa trên kết quả giả lập. Không suy ra chấp thuận lượt Jev thật từ việc job giả lập hoàn tất.
- Trong toàn bộ giai đoạn giả lập, không tiêu thụ token Jev ở bất kỳ đường nào: selector, router cũ, flags, slot khách, claim, question, classifier phụ hay fallback.
- Giữ cơ chế agent question hiện tại về hành vi/phân tầng; dùng adapter Qwen giả lập phần Jev khi đo tiết kiệm token, trả cùng hợp đồng mà code đang cần.
- Tất cả kiểm thử/đánh giá chạy trên Kaggle; máy người dùng chỉ để đọc, sửa, đóng gói, đẩy/kéo kết quả và phân tích nhẹ. Không khởi động model hay chạy suite local.
- Thông tin xác thực Kaggle được người dùng chỉ định ở `D:\User\Documents\kaggle_api_key`. Kiểm tra đây là file hay thư mục và dùng cách nạp phù hợp với tooling hiện có. Không in nội dung khóa, không đưa khóa vào source, dataset, job metadata, log hay commit.
- Nếu có nhiều job độc lập, phân phối qua các tài khoản Kaggle sẵn có và chạy song song. Không chạy song song các bước phụ thuộc đầu ra của nhau; không suy ra mọi tài khoản đều có Secrets hoặc quota.
- Không tự commit/push Git. Không sửa file BTC, đáp án hay dữ liệu đánh giá để làm hệ thống qua test.

## 2. Đọc trước và kiểm hiện trạng trong luồng chính

- `docs/CLAUDE.md`, các `AGENTS.md` thực sự áp dụng, các hướng dẫn Kaggle hiện có.
- [Đề xuất tổng hợp](../DE-XUAT/DE-XUAT-JEV-PLANNER-VA-HOP-DONG-GOAL-FACTS-2026-11-08.md).
- [Phân tích thành phần planner](../PHAN-TICH-CAU-TRUC-PLANNER.md).
- [Vấn đề planner](../DE-XUAT/VAN-DE-PLANNER-2026-11-7.md).
- [Nhật ký 07/11](../NHAT-KY/NHAT-KY-2026-11-7.md), cấu hình chốt và ràng buộc holdout trong `docs/DE-XUAT/CHO-DUYET.md`.

Đọc source hiện tại trước khi sửa: code có thể đã được luồng chính thay đổi sau lúc bàn giao. Kiểm Git status/diff, giữ nguyên công việc chưa commit của người dùng hoặc agent khác. Dùng checkout/worktree riêng trong luồng chính nếu cần để tránh ghi đè. Theo hướng dẫn graphify của repo: query trước khi tìm source nếu công cụ có sẵn; nếu không có, ghi rõ và dùng đọc source có phạm vi. Cập nhật graph theo quy trình khi sửa code.

Không coi tài liệu là bằng chứng tuyệt đối về code hiện tại. Các điểm nối được quan sát ở cuộc trao đổi:

- `harness/planner_table.py`: Ctx, prepare, PREDS, HANDLERS, `_semantic_plan`, `plan`, `_finish`.
- `harness/planner_selector.py`, `planner_actions.json`, `planner_state.py`, `planner_policy.py`.
- `harness/planner_llm.py`: fallback giới hạn, không phải selector nghiệp vụ chính.
- `harness/agent.py`: Call Brief, state, executor nghiệp vụ, plan, guardrail, ghi nhớ và trace.
- `harness/extractor.py`, `jev_hybrid.py`, `llm_extract.py`, `rule_confidence.py`, `question_classifiers/jev_slots.py`.
- `core/llm/generator.py`, `core/llm/summarizer.py`, `harness/coverage.py`, `core/config.py`.

## 3. Kiến trúc đích và cấu hình

| Thành phần | Đích triển khai |
|---|---|
| Call Brief | Giữ dựng ngữ cảnh đầu cuộc gọi bằng code; dùng dữ liệu runtime/bộ nhớ |
| Working memory | Giữ trong session; snapshot cung cấp trạng thái cho selector; tách quan sát khỏi quyết định nghiệp vụ |
| Slot khách | Rules/CERT → Qwen ban đầu, DeepSeek ở cấu hình cuối; có dẫn chứng, kiểm span, chuẩn hóa và khóa slot đã chứng nhận |
| Prepare planner | Giữ chuẩn bị sản phẩm/slot/trạng thái; không tự thay đổi giỏ bằng regex trước quyết định selector |
| Router nghiệp vụ | Gộp hiểu ý nghiệp vụ vào selector; chỉ bỏ đường intent riêng sau khi rà đủ các phụ thuộc |
| Selector | Hợp đồng đa hành động đóng, Jev thật ở bản cuối; adapter Qwen mô phỏng trong các lần đo trước |
| Safety flags | Giữ chức năng phát hiện; có thể chung request selector nếu phù hợp; giai đoạn giả lập dùng Qwen/code, không gọi Jev |
| Điều kiện và quyền | Code kiểm danh tính, quyền, slot bắt buộc, trạng thái và luật nghiệp vụ |
| Executor/handler | Tái sử dụng; nhận action rõ ràng, thực hiện đủ nhiều ý theo thứ tự hợp lệ, không thực thi lặp |
| Goals/facts | Registry định nghĩa chung, validator trước generator, coverage/fallback đồng bộ |
| Generator | Qwen3-4B làm mốc giai đoạn đầu; DeepSeek ở cấu hình cuối; giữ facts là nguồn nội dung |
| Agent claim | Rules + Qwen ban đầu, DeepSeek ở cấu hình cuối; bỏ Jev chọn nhãn; bảo toàn claim và dẫn chứng theo chính sách đã kiểm |
| Agent question | Giữ hành vi rules/CERT/Jev/fallback hiện tại; Qwen giả lập phần Jev trước khi bật Jev thật cuối |
| CERT claim | Chưa thêm trong đợt này |
| Tool/guardrail/memory | Giữ MCP, kiểm quyền, phản hồi an toàn, provenance, TTL, supersede, ghi nhớ và trace |

### Các phần còn lại giữ làm mốc

- Generator giai đoạn đầu: Qwen/Qwen3-4B, `REPLY_STYLE=short`, `LLM_TEMPERATURE=0`, `LLM_MAX_TOKENS=160`, `STRIP_QUESTIONS=1` theo cấu hình chốt trước. Khi đổi model, rà tham số tương thích; không tự đổi đồng thời nhiều tùy chọn sinh câu.
- Giữ một ứng viên sinh câu (`GEN_PARALLEL_N=1`); không tự bật placeholder hay sinh nhiều ứng viên trong đợt đổi kiến trúc này.
- CERT khách: bật gate, dùng CERT2 theo cấu hình chốt; không nới `CERT_V2_RELAX` tùy tiện.
- `PRODUCT_LEXICON=1`, `ORDER_QTY=1`, `LEXICON_INCLUDE=approved`. `ORDER_QTY=1` là bật tính năng nhận số lượng, không ép qty mọi đơn bằng 1.
- SQLite/memory namespace, profile, episodic, TTL, supersede giữ nguyên; `MEM_ABLATE` rỗng.
- RAG auto, ưu tiên bge-m3 + BM25 theo code, ghi rõ backend thực tế nếu fallback; không tự bật reranker hoặc đổi kho vector.
- Transport MCP; guard mode enforce; coverage và fallback bật.
- Summary/handoff giữ chính sách hiện tại. Nếu `auto` khiến model tóm tắt đổi theo generator khi chuyển DeepSeek, ghi rõ trong manifest/kết quả, không coi hai cấu hình chỉ khác câu chữ generator.
- `IMPROVE_DIR` rỗng cho vòng mốc. Không tự bật playbook/example mới cùng lúc để tránh trộn tác động. Các vòng cải tiến riêng chỉ bổ sung khi thuộc phạm vi được thống nhất tiếp.
- Đánh giá `full`, workers 2/T4 làm mốc nếu tài khoản có tài nguyên phù hợp; `LLM_CACHE=off` khi so sánh thật. Hạ workers khi cần ổn định tài nguyên và ghi rõ, không âm thầm so latency khác cấu hình.

Giá trị mặc định trong `core/config.py` không nhất thiết là cấu hình chốt. Luôn ghi rõ cấu hình hiệu lực từng job. `PLANNER_BACKEND=jev` hiện không đủ để bật selector chính; không giả định tên cờ mới đã tồn tại.

## 4. Dữ liệu và cách sử dụng

| Bộ | Vai trò |
|---|---|
| `datagen/out_v3/final/dev` — hiện có 81 kịch bản | Bộ chính để chạy full và so sánh theo giai đoạn với cấu hình mốc |
| `datagen/out_redteam/dev` | Riêng tư, giả danh, xóa dữ liệu, memory poisoning, hành động sai quyền |
| `test_set/public_sample` — hiện có 7 kịch bản | Tương thích dữ liệu/tool/evaluator BTC; ghi nhận vấn đề mẫu đã biết thay vì sửa đáp án |
| `datagen/function_probe/` | Chẩn đoán action, đa ý và lỗi selector; số probe không phải TSR |
| Bộ dev mới viết và đóng băng trước lần đo tương ứng | Kiểm cách diễn đạt mới, giảm phụ thuộc v3 dev đã được xem và sửa nhiều lần |

Bộ câu mới cần ghi seed/nguồn sinh, nhãn được rà, manifest/hash và phân chia rõ phần phát triển với phần đánh giá cuối. Giữ quy mô vừa đủ cho các nhóm hành động, câu đa ý, phủ định/sửa ý, an toàn và trạng thái; chọn số lượng cụ thể theo ngân sách hiện có rồi ghi vào manifest trước chạy. Không dùng output hệ thống làm gold mà không rà độc lập. Không cho answer key (`success_if`, `ground_truth_facts`, nhãn probe...) vào prompt, adapter hay state runtime.

Không dùng holdout v3 đã mở để chọn cấu hình hoặc thay số đã chốt. Muốn có đánh giá cuối khách quan, tạo tập mới và đóng băng trước khi xem kết quả. Chọn cấu hình trên dev trước khi mở tập cuối.

Theo yêu cầu mới, không chạy baseline không bộ nhớ. Vì vậy báo cáo đợt này là so sánh các biến thể **full**; không tự tuyên bố đã có lại bảng baseline/full chính thức cho kiến trúc mới.

## 5. Giả lập Jev: yêu cầu bắt buộc

- Viết adapter Qwen trả cùng hợp đồng mà Jev thật dự kiến trả: actions, flags và các trường bắt buộc khác; question giữ slot/type tương ứng đường hiện tại.
- Giả lập bằng suy luận từ câu khách/agent và ngữ cảnh runtime. Không replay đáp án scenario, nhãn gold hay output từ test để quyết định hành động.
- Có thể dùng fixture định trước cho test hàm cô lập; không dùng nó làm kết quả đánh giá toàn agent.
- Cấu hình dry-run phải chặn mọi lời gọi TypeSafe/Jev thật thay vì chỉ hy vọng không đi vào đường đó. Rà `_client()`, selector, router, extractor, classifier và fallback. Nếu rơi vào đường bị chặn, ghi lỗi/fallback rõ và không gọi API Jev.
- Trace và tên biến thể phải ghi `simulated`/backend thực tế, tách `selected_actions`, `executed_actions`, flags, điều kiện bị chặn và lỗi mô hình.
- Đối chiếu log/count để xác nhận số request Jev thật bằng 0. Không ghi bí mật vào log để chứng minh điều này.
- Số đo giả lập chỉ đánh giá pipeline và cấu hình Qwen. Không suy ra độ chính xác, confidence, latency hoặc chi phí Jev thật từ Qwen. Không dùng confidence Qwen giả làm xác suất Jev đã hiệu chỉnh.

## 6. Hợp đồng action và executor

- Tận dụng `planner_actions.json`: action, mô tả, requires, handler, instruction.
- Lập bảng đủ action → executor → tool có thể dùng → goal đầu ra → điều kiện. Những action chưa có đường thực thi đầy đủ phải được xử lý, không âm thầm rơi về nhãn không làm gì.
- Kiểm đủ requires bằng code: có đơn thuộc khách, có sản phẩm/biến thể, địa chỉ, thanh toán và các yêu cầu riêng.
- Không để mô hình tự cấp quyền hay tự sinh giá/SKU/mã đơn làm nguồn sự thật. Tham số lấy từ slot đã kiểm, memory, catalog/tool và phép tính xác định.
- Tách `focus` đang nhắc khỏi sản phẩm đã chọn; chuyển cập nhật giỏ mang ý nghĩa cam kết ra khỏi prepare regex.
- Đa action cần thứ tự và xử lý xung đột rõ: thêm giỏ trước tính tổng; không để chào/cảm ơn lấn át nghiệp vụ; không coi hỏi chính sách là yêu cầu đổi/trả.
- Không `return` sau action đầu nếu còn ý hợp lệ chưa xử lý. Có kết quả một phần và trạng thái lỗi; ngăn tạo/sửa lặp khi retry hoặc action trùng.
- Giữ kiểm danh tính/người gọi, người nhà/proxy, xóa dữ liệu, giới hạn COD, tồn kho, biến thể, hiệu lực chính sách và ngày nghỉ. Rà các nhánh đang chỉ bật khi backend selector là `qwen`.
- Khi mô hình lỗi/abstain: fallback hữu hạn, rõ ràng, không thực hiện hành động ghi dữ liệu không chắc chắn. Thiết kế theo cơ chế hiện có và ghi quyết định vào trace.

## 7. Hợp đồng goal/facts cần triển khai

### Registry

Đề xuất `harness/generator_goals.json`, hoặc vị trí nhất quán hơn với repo sau khi kiểm hiện trạng. Kiểm kê toàn bộ goal mà planner phát ra, generator notes, QUESTION_GOALS, coverage và fallback đang dùng.

Mỗi goal cần:
- Ý nghĩa/mục tiêu phản hồi.
- Required facts, optional facts và kiểu dữ liệu phù hợp.
- Ý phải nói, điều kiện chỉ nói khi có dữ liệu.
- Chính sách câu hỏi; tổng hợp nhất quán ở cấp lượt để không yêu cầu nhiều câu hỏi mâu thuẫn.

Chuyển GOAL_NOTES hiện có, bổ sung goal thiếu (ví dụ `ask_address`, `ask_variant`, `cod_limit`). Chỉ đưa định nghĩa goal đang dùng vào request generator. Giữ câu trả lời tự nhiên, không ép toàn bộ thành câu mẫu cố định.

### Facts và kiểm trước generator

- Ưu tiên giữ `quote`, `order`, `update`, `callback`, `policy`... để tái sử dụng code.
- Kiểm tên goal hợp lệ, field bắt buộc, kiểu, giá trị rỗng, xung đột và nguồn kết quả. Không coi mọi `0` là thiếu dữ liệu.
- `order_created` chỉ được phát khi tool thành công; phải có mã đơn và tổng tiền hợp lệ. Ngày giao là tùy chọn khi nguồn không cung cấp.
- Mỗi loại dữ liệu phản ánh đúng nguồn: giá hiện tại/niêm yết/giá cũ; sản phẩm; chính sách hiệu lực; lời khách tự khai không biến thành xác nhận của shop.
- Thiếu thông tin khách → goal hỏi thích hợp; tool lỗi → goal lỗi thích hợp; lỗi hợp đồng nội bộ → fallback an toàn và trace. Không tự điền fact để vượt validator.
- Đồng bộ prompt, coverage và render fallback với registry. Coverage vẫn cần code kiểm tiền/ngày/nội dung, không coi JSON tự giải quyết toàn bộ ngữ nghĩa.
- Lưu provenance ở trace/metadata phù hợp; generator không cần đọc toàn bộ dữ liệu kỹ thuật.

Ví dụ chuỗi kết quả: action `place_order` → handler kiểm tồn kho → goal `out_of_stock` + fact sản phẩm. Không gửi goal `order_created` chỉ vì selector nhận ra ý đặt hàng.

## 8. Các giai đoạn triển khai và job

### Giai đoạn 0 — Mốc và đóng gói

- Kiểm code/data/cấu hình hiện tại, tạo manifest; rà runner không chạy baseline.
- Chuẩn bị cấu hình Qwen và adapter Jev giả lập. Để đo mốc không tốn Jev, cũng mô phỏng mọi đường Jev còn ở kiến trúc mốc và ghi rõ đó là mốc giả lập, không phải lặp nguyên cấu hình Jev thật cũ.
- Có thể dùng trace cũ làm dữ liệu phân tích nếu hash/schema phù hợp, nhưng không gắn nhãn là một lần chạy mới với cấu hình khác.

### Giai đoạn 1 — Goal/facts

- Registry, validator, notes, question policy, coverage và fallback.
- Kiểm hàm/hợp đồng meaningful, cộng full regression trên Kaggle. Mục tiêu giữ hành vi hợp lệ, phát hiện rõ các trường hợp contract cũ thiếu; không đòi trace parity tuyệt đối nếu thay đổi đã có chủ đích và được giải thích.

### Giai đoạn 2 — Planner mới

- Selector adapter, flags, executor đa hành động, prepare/state, tái sử dụng handler, tách phụ thuộc router.
- Qwen giả lập Jev; giữ generator/extractor mốc để tách tác động.
- Chạy probe + full dev + redteam, đọc paired failures để tìm nguyên nhân; không tune theo holdout đã mở.

### Giai đoạn 3 — Extractor mới

- Customer: rules/CERT → Qwen.
- Claim: rules + Qwen, dẫn chứng và chuẩn hóa, bỏ Jev ở claim.
- Question giữ cơ chế cũ với Jev được giả lập bằng Qwen; đảm bảo tách cờ không vô tình tắt question khi tắt Jev customer/claim.
- Đánh giá gold slot/claim riêng và full dev; không dùng RQR/HR đẹp hơn làm lý do duy nhất chọn extractor.

### Giai đoạn 4 — Ghép và đo DeepSeek

- Ghép thay đổi đã qua kiểm tra, full dev/redteam/public sample/câu mới.
- Chuyển các vai trò generator và extractor customer/claim sang DeepSeek theo yêu cầu cuối. Rà backend/model thực sự được hỗ trợ, PII, timeout và tham số; không tự suy đoán hỗ trợ API. Rà summarizer auto và ghi model hiệu lực.
- Selector/question vẫn dùng adapter Qwen giả lập Jev cho đến khi có thống nhất chạy Jev thật. Đo riêng biến thể DeepSeek để không trộn kết luận về model với kiến trúc.
- Tổng hợp kết quả Qwen và DeepSeek, chất lượng/latency/chi phí/lỗi, những gì còn giả lập và những vấn đề chưa đạt. Trình người dùng thống nhất cấu hình trước bước 5.

### Giai đoạn 5 — Bản cuối Jev thật

**Chỉ chạy sau khi người dùng thống nhất.** Bật Jev thật cho selector/flags và question theo cấu hình đã chọn; customer/claim dùng DeepSeek, generator DeepSeek. Đóng băng code/config/data trước lượt đánh giá cuối. Kiểm backend/fallback thực tế; không báo số giả lập thành số Jev thật. Không tự thay model do quota/lỗi mà giữ nhãn báo cáo cũ.

## 9. Kaggle: phân phối, đóng gói và theo dõi

- Dùng workflow trong `scripts/kaggle_job.py` và cấu trúc job hiện có sau khi đọc help/code; không đoán cờ CLI.
- Dùng tài khoản/khóa sẵn có trong đường dẫn được chỉ định; không hiển thị bí mật. Lập bảng job/account/dataset/version/variant/config/test set trước đẩy.
- CPU jobs cho kiểm tra hàm/schema/parity phù hợp; GPU jobs cho Qwen end-to-end. DeepSeek API jobs chọn tài nguyên theo nhu cầu thật: nếu selector/question giả lập vẫn dùng Qwen local thì vẫn cần model server tương ứng.
- Các nhóm độc lập như kiểm hợp đồng CPU, probe và full redteam có thể chia account chạy song song sau khi cùng bản code/dataset đã sẵn sàng. Job tích hợp chờ các thay đổi phụ thuộc hoàn tất.
- Rà Secrets hiện có và cơ chế tự chạy. Chỉ yêu cầu người dùng thao tác khi thực sự thiếu quyền/secret/khả năng API; tiếp tục các job không bị chặn.
- Kiểm `packed_at`, version dataset và manifest thực tế sau khởi động; tránh lỗi Kaggle gắn dataset cũ đã gặp trước đây.
- Mỗi job có timeout, output riêng, log backend, lỗi/fallback và cấu hình đã làm sạch bí mật. Không ghi đè trace/số chốt cũ.
- Theo dõi trạng thái và cập nhật ngắn cho người dùng trong luồng chính; kéo kết quả và phân tích đến khi công việc đã duyệt hoàn tất hoặc có blocker thật.

## 10. Điều kiện đánh giá và bàn giao kết quả

Kiểm tra cần thiết được thiết kế theo hành vi, không chỉ sao chép implementation:

- Hợp đồng goal/facts: goal thiếu định nghĩa, thiếu/sai field, thành công giả, optional date, xung đột goal/question, fallback thiếu dữ liệu.
- Planner: đa ý, phủ định/sửa ý, giỏ so với chốt, đổi địa chỉ so với đổi size/trả hàng, hỏi chính sách, retry/duplicate, trạng thái qua nhiều phiên.
- An toàn: proxy/người nhà, dữ liệu khách khác, xóa bộ nhớ, nội bộ, injection và memory poisoning; kiểm trực tiếp tool/memory state, không chỉ câu trả lời.
- Customer slots và agent claims: precision/recall hoặc chỉ số tương đương theo nhãn/giá trị, dẫn chứng, bỏ sót/gán thừa; có gold được rà.
- Question: giữ hành vi đã chọn, theo dõi sai lệch do adapter; không tuyên bố parity với Jev thật trước khi đo.
- Full: TSR, CCR, RQR, HR, vi phạm guardrail/quyền, Tool-Call Accuracy phù hợp, lỗi/fallback, TTFT/Total p50/p95 và chi phí. Chỉ full, không baseline.
- Ngưỡng đề BTC: chat TTFT p95 ≤ 3 s, Total p95 ≤ 8 s; giữ các ngưỡng chất lượng BTC khi báo đạt/chưa đạt. Không cộng p95 thành phần hoặc trừ thời gian giả định để thay số end-to-end.

Không giữ một thay đổi chỉ vì dev tăng nếu redteam hoặc điều kiện bắt buộc bị hỏng. Không nới kiểm tra, sửa extractor theo hướng bỏ claim/câu hỏi, hoặc sửa đáp án để làm đẹp số.

Artifact bàn giao:

1. Code/config thay đổi có thể review, chưa tự commit.
2. Bảng action → executor → goal/facts; registry và validator.
3. Manifest code/config/data/job/account và backend thực tế; không chứa khóa.
4. Kết quả kiểm tra và paired full comparisons từng giai đoạn, phân tích hồi quy.
5. Bằng chứng giai đoạn giả lập có 0 request Jev thật.
6. Báo cáo DeepSeek + giả lập để thống nhất trước Jev thật; bản cuối sau khi được thống nhất có báo cáo riêng.
7. Nhật ký và hướng dẫn tái lập cập nhật; không thay số holdout cũ.

## 11. Lời nhắn để bắt đầu ở luồng chính

> Đọc và thực hiện `docs/PLAN/KE-HOACH-TRIEN-KHAI-JEV-PLANNER-GOAL-FACTS-2026-11-08.md`. Tôi đã duyệt phạm vi trong file. Chỉ đánh giá full, dùng Qwen trước rồi DeepSeek cuối, giả lập mọi đường Jev để không tốn token trước khi thống nhất chạy Jev thật. Tất cả test chạy trên Kaggle, khóa ở `D:\User\Documents\kaggle_api_key`; chia job độc lập qua các tài khoản chạy song song nếu có. Kiểm hiện trạng để không ghi đè công việc đang có, rồi triển khai lần lượt và theo dõi job đến kết quả. Không tự commit.
