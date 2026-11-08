# Đề xuất Jev chọn hành động và chuẩn hóa hợp đồng goals/facts

Ngày: 08/11/2026.

**Trạng thái: ĐỀ XUẤT, chưa triển khai.** Việc ghi tài liệu không đồng nghĩa các thay đổi runtime đã được duyệt hay thực hiện. Đây là phương án tổng hợp từ cuộc trao đổi về planner, extractor và generator. Chưa có số đo end-to-end cho cấu hình mới.

Tài liệu liên quan:
- [Phân tích cấu trúc planner](../PHAN-TICH-CAU-TRUC-PLANNER.md).
- [Vấn đề gốc của planner](VAN-DE-PLANNER-2026-11-7.md).
- [Nhật ký probe chọn hàm 07/11](../NHAT-KY/NHAT-KY-2026-11-7.md).

## 1. Mục tiêu và phương án tổng thể

Dùng Jev để hiểu lời khách và chọn một hoặc nhiều hành động nghiệp vụ trong danh sách đóng. Code kiểm điều kiện, điền tham số và thực thi handler/tool. Kết quả thực thi được chuyển thành goals/facts theo hợp đồng rõ ràng để generator viết câu trả lời.

Slot khách và claim agent chuyển sang đường rules/CERT phù hợp + Qwen hoặc DeepSeek, bỏ tầng Jev chọn nhãn ở hai công việc này. Agent question giữ đường xử lý hiện tại, gồm các nhánh rules/CERT/Jev/fallback theo cấu hình đang dùng.

Giữ bộ nhớ, Call Brief, MCP/tool, guardrail và các kiểm tra quyền. Cấu hình mới cần thay code; không thể đạt toàn bộ thiết kế chỉ bằng đổi biến môi trường hiện có.

## 2. Bảng cấu hình và thay đổi đề xuất

| Thành phần | Hiện trạng đã đọc | Đề xuất | Phần cần thực hiện |
|---|---|---|---|
| Call Brief | Code dựng ngữ cảnh đầu cuộc gọi từ bộ nhớ và dữ liệu runtime | Giữ | Cấp ngữ cảnh liên quan cho selector, không đưa toàn bộ hồ sơ nếu không cần |
| Working memory | Trạng thái nằm trong `CallSession`; `PlannerState` là snapshot một phần | Giữ và làm rõ trường nào là quan sát, trường nào là quyết định nghiệp vụ | Cập nhật theo slot đã kiểm và kết quả handler/tool |
| Slot khách | Rules/CERT, Jev chọn nhãn, Qwen khi chưa giải quyết được | Rules/CERT → Qwen hoặc DeepSeek trích slot kèm dẫn chứng | Bỏ Jev ở đường customer; kiểm span, chuẩn hóa, bảo toàn slot đã chứng nhận |
| Chuẩn bị planner | `_prepare_pre`, `_prepare` vừa chuẩn bị dữ liệu vừa thay đổi focus/giỏ theo regex | Giữ chuẩn bị dữ liệu; chuyển thay đổi giỏ mang ý nghĩa quyết định sang handler | Không để regex thêm giỏ trước rồi Jev mới quyết định khách có muốn thêm hay không |
| Router nghiệp vụ | Intent đơn và flags làm đầu vào cho planner bảng luật | Gộp việc hiểu ý nghiệp vụ vào selector Jev | Rà các thành phần đang đọc `route.intent`; chỉ bỏ đường intent riêng sau khi đã chuyển các phụ thuộc |
| Cờ an toàn | Router, luật và guardrail phối hợp | Giữ chức năng; có thể đưa phân loại cờ vào cùng request Jev chọn hành động | Thiết kế output rõ ràng; quyền truy cập và điều kiện thực thi vẫn kiểm bằng code |
| Selector | Có nhánh Qwen đa hành động; bảng luật vẫn là đường mặc định | Jev chọn đa hành động từ hợp đồng đóng | Thêm backend Jev, kiểm tên hành động hợp lệ, lỗi/abstain và trace |
| Bảng luật/predicate | Trộn đoán ý, điều kiện trạng thái, an toàn và điều phối hội thoại | Thay phần đoán ý bằng Jev; giữ điều kiện, an toàn và fallback cần thiết | Phân loại từng dòng; không bỏ nguyên bảng khi chưa chuyển đủ trách nhiệm |
| Handler và tool | Code lấy tham số, gọi MCP/tool và xử lý kết quả | Tái sử dụng | Tách regex đoán ý còn trong handler; kiểm đủ điều kiện và thực hiện đúng nhiều hành động |
| Goals/facts | Planner trả list goal + dict facts; hướng dẫn ở `GOAL_NOTES` và code liên quan | Chuẩn hóa hợp đồng chung | Kiểm tên goal, cấu trúc facts và điều kiện kết quả trước khi gọi generator |
| Generator | Qwen/DeepSeek dùng cùng cơ chế prompt, có fallback | Lần so sánh đầu giữ Qwen hiện tại | Chỉ đưa định nghĩa goal đang dùng; chưa đổi model generator cùng lúc |
| Claim agent | Rules, Jev chọn nhãn, Qwen khi chưa giải quyết được | Rules + Qwen hoặc DeepSeek trích claim kèm dẫn chứng | Bỏ Jev ở claim; giữ việc kiểm span, số và hợp nhất claim theo chính sách đã kiểm |
| Question agent | Có rules/CERT, Jev và fallback tùy cấu hình | Giữ như hiện tại | Khi bỏ Jev customer/claim phải tách điều khiển để không vô tình tắt Jev question |
| CERT claim | Chưa có chứng nhận riêng | Chưa thêm trong lần đổi này | Nếu làm sau phải đo độ đúng và bỏ sót claim độc lập, không chỉ nhìn HR |
| Guardrail, memory write, trace | Code điều phối | Giữ | Bổ sung trace quyết định selector, kiểm hợp đồng, thực thi và fallback |

### Những lựa chọn chưa chốt

- Chọn Qwen hay DeepSeek cho slot khách và claim. Có thể khảo sát từng công việc riêng nếu dữ liệu cho thấy cần; chưa chốt dùng hai model khác nhau.
- Generator giữ Qwen trong lần so sánh đầu. Đổi sang DeepSeek là một thí nghiệm riêng nếu cần.
- Chi tiết cờ an toàn trong request Jev, chính sách abstain/lỗi và ngưỡng tin cậy cần được thiết kế, kiểm chứng trước khi bật.
- Nếu dùng Qwen local phải đo mức tranh GPU với generator. Nếu dùng DeepSeek bên ngoài phải giữ che PII và đo latency thực tế.

## 3. Luồng runtime dự kiến

```text
Đầu cuộc gọi:
  Bộ nhớ + dữ liệu runtime → Call Brief → nạp ngữ cảnh cho session

Mỗi lượt:
  Lời khách → chuẩn hóa → rules/CERT hoặc Qwen/DeepSeek trích slot
    → code kiểm slot, chuẩn bị dữ liệu và snapshot working memory
    → Jev chọn hành động nghiệp vụ + phân loại cờ an toàn theo hợp đồng
    → code kiểm quyền, điều kiện, xung đột và thứ tự
    → handler gọi tool, đọc kết quả, cập nhật trạng thái
    → tạo và kiểm hợp đồng goals/facts
    → generator viết phản hồi → guardrail/coverage/fallback
    → agent question: đường hiện tại
      agent claim: rules + Qwen/DeepSeek
    → ghi bộ nhớ, trace
```

Sơ đồ thể hiện trách nhiệm logic, không yêu cầu mọi bước đều chạy tuần tự. Chỉ song song hóa khi không phụ thuộc dữ liệu và đo latency của đường runtime thật.

## 4. Phần planner cũ có thể tái sử dụng

### 4.1. Code

- `Ctx`: giữ hoặc thu gọn thành gói dữ liệu lượt; không cần thay chỉ vì đổi model selector.
- `planner_state.snapshot()`: dùng lại để cung cấp trạng thái cho Jev. Stage hiện suy ra từ đơn/giỏ/focus, chưa phải state machine đầy đủ.
- Các hàm tra giá, tư vấn, tính giỏ, tạo/sửa đơn, tra đơn, callback và handoff trong `CallSession`: tái sử dụng sau khi rà điều kiện và regex đoán ý.
- Hậu xử lý lỗi liên tiếp và handoff: giữ; kiểm tra các đường return sớm để không bỏ qua công việc bắt buộc.
- Transport MCP/direct, guardrail, ghi nhớ và trace: giữ cơ chế hiện có, mở rộng metadata cần thiết.

### 4.2. JSON

| Nguồn | Tận dụng | Cần lưu ý |
|---|---|---|
| `harness/planner_actions.json` | Tên, mô tả, instruction, requires và ý tưởng mapping handler | Hiện chưa có executor tổng quát đọc toàn bộ `handler`/`requires`; một số action còn cần bổ sung đường thực thi |
| `harness/planner_rules.json` | Điều kiện an toàn, danh tính, quản lý hội thoại, fallback, ví dụ và ghi chú | Các dòng chọn nghiệp vụ bằng intent/regex được rà để thay bằng Jev; không chuyển ví dụ thành đáp án runtime |
| Lexicon sản phẩm/cue trong `harness/lexicon/` | Nối cách gọi sản phẩm với SKU, chuẩn hóa và fallback | Cue nhận diện từ không tự được quyền quyết định thay đổi giỏ/đơn |

`PLANNER_BACKEND=jev` hiện chỉ là planner fallback chọn một goal an toàn, không phải selector nghiệp vụ chính. Cần phân biệt với backend Jev mới của selector. Các chỗ hiện kiểm `planner_selector == "qwen"`, gồm nhánh chính sách đổi trả, phải được rà khi thêm backend.

## 5. Phân biệt action, goal và fact

| Khái niệm | Ai quyết định/cung cấp | Ý nghĩa |
|---|---|---|
| Action | Jev đề xuất; code kiểm trước thực thi | Khách muốn thực hiện việc gì, ví dụ `place_order` |
| Goal phản hồi | Code xác định sau khi xét điều kiện và kết quả handler | Agent cần truyền đạt/hỏi gì tiếp, ví dụ `order_created`, `ask_variant`, `out_of_stock` |
| Facts cho generator | Code tổng hợp dữ liệu runtime, kết quả tool, tính toán và ngữ cảnh liên quan | Dữ kiện để diễn đạt goal trong lượt này |

Ví dụ: Jev chọn `place_order`, handler thấy hết hàng thì trả goal `out_of_stock`, không được trả `order_created`. Jev chọn đúng hành động chưa chứng minh hành động đã thành công.

`facts` của planner không đồng nghĩa slot khách, `KNOWN`, bộ nhớ dài hạn hay đáp án ground truth của evaluator. Tuyệt đối không lấy answer key scenario để điền vào đường agent.

## 6. Hiện trạng hợp đồng goals/facts

Đã có nền tảng để dùng lại:

- `core/llm/generator.py`: `GOAL_NOTES` giải thích nhiều goal; `payload()` chỉ đưa notes của goal trong lượt hiện tại.
- `SYSTEM`: chỉ dùng facts, làm theo goals theo thứ tự, không tự hứa thêm và xử lý thông tin chưa có.
- `QUESTION_GOALS` và `question_slot()`: điều khiển câu hỏi được phép.
- `harness/coverage.py`: kiểm nội dung bắt buộc cho một số goal.
- `render_offline()`: câu mẫu fallback.

Hạn chế: chưa có registry hợp đồng thống nhất; một số goal chưa có notes riêng; fact bắt buộc/tùy chọn chưa được khai báo đồng bộ với prompt và coverage. Các quy tắc còn nằm ở nhiều vị trí trong Python.

## 7. Đề xuất hợp đồng goal/facts thống nhất

### 7.1. Danh mục goal

Đề xuất file mới `harness/generator_goals.json` (chưa tạo trong thay đổi này). Mỗi goal có:

- `description`: mục tiêu phản hồi.
- `required_facts`: dữ liệu tối thiểu cần có; có thể rỗng với goal chỉ hỏi thông tin.
- `optional_facts`: dữ liệu được phép dùng nếu có.
- `response_requirements`: các ý phải diễn đạt.
- Quy định câu hỏi khi phù hợp; phải nhất quán với chính sách chọn câu hỏi cho cả lượt.

Ví dụ thiết kế, chưa phải schema hay runtime đã triển khai:

```json
{
  "order_created": {
    "description": "Thông báo đơn đã tạo thành công",
    "required_facts": ["order.order_id", "order.total_vnd"],
    "optional_facts": ["order.estimated_delivery_ddmm"],
    "response_requirements": [
      "Xác nhận đã tạo đơn, nêu mã đơn và tổng tiền",
      "Chỉ nêu ngày giao khi có dữ liệu",
      "Không hỏi xác nhận đặt đơn lại"
    ]
  },
  "ask_address": {
    "description": "Xin địa chỉ giao hàng còn thiếu",
    "required_facts": [],
    "optional_facts": [],
    "response_requirements": ["Hỏi địa chỉ giao hàng"],
    "question_slot": "address"
  }
}
```

Chuyển notes hiện có sang danh mục, bổ sung goal thiếu như `ask_address`, `ask_variant`, `cod_limit`. Rà toàn bộ goal thực tế planner phát ra và goal mà generator/coverage/fallback đang hỗ trợ; không chỉ bổ sung vài ví dụ.

### 7.2. Hợp đồng facts

Ưu tiên giữ các đường dữ liệu đang dùng (`quote`, `order`, `update`, `callback`, `policy`...) để tái sử dụng handler và generator. Bổ sung định nghĩa kiểu/điều kiện thay vì đổi tên hàng loạt.

- Kiểm kiểu, giá trị rỗng và đường field bắt buộc theo goal.
- Phân biệt rõ giá hiện tại, giá niêm yết, giá đã báo trước; dữ liệu sản phẩm nào phải gắn đúng sản phẩm đó.
- Trường bắt buộc không chỉ cần tồn tại: mã đơn phải không rỗng, số tiền phải hợp lệ; `0` không tự động bị coi là thiếu nếu nghiệp vụ cho phép.
- Fact không có thì không tự điền số/ngày/chính sách mặc định chỉ để qua kiểm hợp đồng.
- Lưu provenance trong trace hoặc metadata phù hợp: từ tool nào, slot khách hay phép tính nào. Không cần gửi toàn bộ metadata kỹ thuật cho generator.
- Dữ liệu khách tự khai về giá/chính sách không trở thành dữ kiện đã được shop xác nhận.

### 7.3. Kiểm trước khi gọi generator

Code kiểm:

1. Goal có trong registry.
2. Facts đáp ứng cấu trúc và dữ liệu tối thiểu.
3. Goal biểu thị thành công khớp kết quả handler/tool, không chỉ khớp việc có field.
4. Nhiều goal không mâu thuẫn và thứ tự hợp lý.
5. Goal hỏi thông tin không xung đột với dữ liệu đã biết và giới hạn câu hỏi của lượt.

Nếu hợp đồng sai: ghi trace lỗi, xử lý tại lớp điều phối theo tình huống. Thiếu thông tin khách thì chọn goal hỏi phù hợp; tool lỗi thì chọn goal lỗi phù hợp. Không tự đổi mọi trường hợp thiếu field thành `order_failed`, không để generator đoán dữ kiện hoặc suy diễn thành công.

### 7.4. Dùng chung cho prompt, coverage và fallback

- Chỉ đưa định nghĩa của các goal trong lượt vào prompt.
- Dùng registry làm nguồn chung cho hướng dẫn và yêu cầu dữ liệu/nội dung có thể kiểm bằng code.
- Coverage vẫn cần logic riêng cho việc đối chiếu tiền/ngày/ý nghĩa câu trả lời; không mặc định JSON tự kiểm được toàn bộ ngữ nghĩa.
- Giữ câu trả lời tự nhiên; notes là yêu cầu nội dung, không bắt mọi lượt đọc một câu mẫu cố định.
- Rà câu mẫu fallback để cùng tuân thủ hợp đồng, tránh prompt đúng nhưng fallback nói sai hoặc thiếu dữ liệu.

## 8. Các điểm tích hợp cần xử lý

1. `_prepare()` hiện tự thêm giỏ bằng regex trước selector: chuyển quyết định đó sang sau chọn hành động; phân biệt sản phẩm đang nhắc với sản phẩm đã chọn.
2. `_semantic_plan()` nhận nhiều action nhưng thường return sau nhánh đầu tiên: cần executor xử lý thứ tự, xung đột, hành động phụ và kết quả một phần; tránh tạo/sửa lặp.
3. Một số action trong danh mục chưa có nhánh thực thi đầy đủ: lập bảng action → executor → tool có thể dùng → các goal đầu ra.
4. Rà phụ thuộc `route.intent` và flags trước khi gộp/bỏ router nghiệp vụ riêng. Không bỏ chức năng an toàn khi bỏ một module.
5. Rà handler trộn đoán ý với thực thi: truyền action đã chọn rõ ràng, vẫn kiểm dữ liệu và luật nghiệp vụ bằng code.
6. Tách điều khiển Jev customer/claim/question nếu cờ hiện tại bật cả ba. Giữ question hiện hành khi bỏ Jev hai đường còn lại.
7. Bảo toàn hành vi chống đầu độc bộ nhớ, nhận diện người gọi, xóa dữ liệu và truy cập đơn theo danh tính được phép.

## 9. Lộ trình và đánh giá đề xuất

1. **Chuẩn hóa hợp đồng goals/facts trước:** kiểm kê goal/fact hiện có, đưa notes về registry, bổ sung validator và đồng bộ coverage/fallback. Chưa đổi model để giảm biến số.
2. **Đưa Jev vào selector:** giữ generator và extractor mốc; xử lý action đa nhãn, điều kiện và executor. Đo tác động riêng của planner.
3. **Thử đường slot/claim không Jev:** so Qwen/DeepSeek theo công việc, giữ agent question và generator mốc. Đo cả chất lượng trích xuất và độ trễ.
4. **Ghép cấu hình đã chọn:** chạy đánh giá toàn agent có baseline không bộ nhớ, cùng bộ dữ liệu/model/tham số ngoài khác biệt đọc bộ nhớ.

Các phép kiểm/đánh giá khi triển khai chạy trên Kaggle theo quy trình dự án. Đây là kế hoạch, chưa chạy thêm test trong lần ghi tài liệu.

Chỉ số cần xem:
- Slot khách: đúng nhãn/giá trị, phủ định, sửa ý, dẫn chứng, giá trị người khác, tác động bộ nhớ.
- Claim: đúng field/giá trị, bỏ sót và gán thừa; không chỉ dùng HR để chọn extractor.
- Planner: đúng hành động và tool/args, đủ nhiều ý, không thực hiện hành động chưa được yêu cầu.
- Goal contract: goal chưa định nghĩa, thiếu/sai facts, goal thành công không có kết quả thành công, xung đột câu hỏi.
- Toàn agent: TSR, CCR, RQR, HR, vi phạm an toàn, lỗi/fallback, TTFT/Total p50/p95 và chi phí.
- Đề BTC yêu cầu chat TTFT p95 ≤ 3 giây, Total p95 ≤ 8 giây; phải đo end-to-end thật, không cộng/trừ p95 thành phần để thay số tổng.

Probe chọn hàm Qwen ngày 07/11 chỉ là bằng chứng về khả năng chọn hành động, không chứng minh Jev sẽ đạt độ đúng tương tự hay cấu hình mới cải thiện TSR. Đánh giá trên câu mới và dữ liệu có nhãn độc lập; không sửa rồi chạy lại holdout đã đóng băng để thay số đã chốt.

## 10. Phạm vi của lần ghi tài liệu

Chỉ thêm file đề xuất này. Chưa đổi code, cấu hình runtime, dữ liệu benchmark, registry goal hay file JSON planner; chưa commit và chưa chạy kiểm thử.
