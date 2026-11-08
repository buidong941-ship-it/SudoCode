# Phân tích cấu trúc planner và phương án dùng Jev chọn hành động

Ngày ghi: 08/11/2026.

Tài liệu phân tích kiến trúc và cách tái sử dụng thành phần; không mô tả một thay đổi runtime đã được triển khai hay kiểm thử. Phần hiện trạng dựa trên code đã đọc trong cuộc trao đổi. Kết quả probe chọn hàm không đồng nghĩa với TSR của toàn agent.

## 1. Vì sao planner có nhiều thành phần?

Không bắt buộc phải có nhiều file hoặc nhiều tầng như hiện tại. Hệ thống cần thực hiện một số công việc khác nhau: hiểu khách muốn làm gì, biết trạng thái hiện tại, kiểm tra điều kiện, gọi công cụ, rồi phản ánh đúng kết quả. Có thể gộp module, nhưng vẫn cần đảm nhiệm các công việc đó.

Ví dụ xuyên suốt: khách nói “Đổi địa chỉ đơn hôm trước sang 15 Nguyễn Huệ giúp chị”. Nhận ra hành động đổi địa chỉ mới là bước đầu. Hệ thống còn phải xác định đơn thuộc khách nào, lấy địa chỉ, kiểm quyền, gọi tool và xem cập nhật có thành công hay không.

## 2. Từng thành phần, vai trò và khả năng tái sử dụng

| Thành phần | Công việc hiện tại | Nếu thiếu | Khi chuyển sang Jev |
|---|---|---|---|
| `Ctx` trong `planner_table.py` | Gom lời khách, slots, route, goals và facts của lượt hiện tại | Vẫn làm được nhưng phải truyền nhiều tham số riêng giữa các hàm | Giữ hoặc thay bằng cấu trúc dữ liệu đơn giản hơn; đây là cách tổ chức code |
| `_prepare_pre()` và `_prepare()` | Cập nhật slot vào dữ liệu đang biết; tìm sản phẩm, focus, câu hỏi, tín hiệu lấy hàng và giỏ | Có nhãn hành động nhưng có thể thiếu SKU, địa chỉ hoặc đối tượng cần xử lý | Giữ phần chuẩn bị dữ liệu; tách việc thay đổi giỏ khỏi regex đoán ý trước quyết định của Jev |
| `planner_state.py` | Chụp trạng thái focus, cart, order_ids, discussed và suy ra stage | Cùng một câu sẽ khó được hiểu đúng trong các giai đoạn khác nhau | Dùng lại làm đầu vào cho Jev; snapshot không phải kho lưu trạng thái độc lập |
| `planner_rules.json` | Ánh xạ điều kiện sang handler theo priority, mode và group | Đường chọn hành động bằng luật không hoạt động | Jev có thể thay phần chọn nghiệp vụ; các ràng buộc cần thiết phải còn trong code thực thi |
| `PREDS` trong `planner_table.py` | Các hàm kiểm tra điều kiện có/không | Nếu bỏ cả kiểm tra trạng thái, code có thể thực thi khi thiếu đơn hoặc slot | Thay predicate đoán ý bằng Jev; giữ kiểm tra dữ liệu, quyền và điều kiện nghiệp vụ |
| `planner_selector.py` và `planner_actions.json` | Bộ chọn hiện dùng Qwen để trả danh sách hành động trong hợp đồng đóng | Không có bộ chọn ngữ nghĩa ở nhánh này; bảng luật vẫn có thể chọn | Thêm backend Jev tại đây; cần thiết kế lựa chọn nhiều hành động và xử lý abstain/lỗi |
| Handlers và hàm nghiệp vụ trong `CallSession` | Lấy tham số từ dữ liệu runtime, gọi tool, cập nhật trạng thái, tạo goals/facts | Mô hình chỉ đưa ra nhãn, chưa thực hiện được yêu cầu | Tái sử dụng nhiều nhất; rà lại regex đoán ý còn nằm trong hàm thực thi |
| `_finish()` và đường ra generator | Xử lý lỗi liên tiếp, chuyển nhân viên, khử trùng goal và cung cấp plan cho generator | Có thể phản hồi thiếu nhất quán hoặc không chuyển nhân viên khi lỗi lặp lại | Giữ công việc cần thiết; kiểm tra đường return sớm vì hiện không phải nhánh nào cũng qua `_finish()` |

Không nên đặt luật nghiệp vụ chỉ trong prompt. Ví dụ giới hạn COD, quyền sửa đơn hay hạn đổi trả cần được code kiểm tra trước khi thực hiện hành động.

## 3. Bước chuẩn bị có phải Call Brief không?

Hai thứ có liên quan nhưng khác phạm vi và thời điểm.

**Call Brief** là bản tóm tắt được dựng khi bắt đầu cuộc gọi: khách là ai, đã tương tác gì, sản phẩm/đơn đang liên quan, thông tin còn hiệu lực và điều cần tiếp nối. Nó lấy dữ liệu từ bộ nhớ xuyên phiên và các nguồn runtime để giúp cuộc gọi mới bắt đầu đúng ngữ cảnh. Trong repo, đường dựng brief nằm ở `CallSession._build_brief()`.

**Bước chuẩn bị planner** chạy cho từng lượt. Nó kết nối câu khách vừa nói với slots và trạng thái đang có. Ví dụ brief cho biết khách đã có đơn OD123; lượt hiện tại cung cấp địa chỉ mới. Bước chuẩn bị giúp đưa hai nguồn đó tới lớp chọn và thực thi hành động.

Call Brief có thể được nạp vào working memory khi bắt đầu phiên. Sau nhiều lượt, working memory còn chứa những thay đổi mới chưa có trong brief ban đầu. Vì vậy brief không thay thế bước chuẩn bị theo lượt.

## 4. Trạng thái hội thoại có phải working memory không?

Có thể xem trạng thái planner là **một phần có cấu trúc của working memory**.

Working memory rộng hơn: lịch sử hội thoại gần đây, câu hỏi đang chờ trả lời, sản phẩm đang bàn, giỏ, đơn vừa tạo, slots mới, kết quả tool và các cờ điều khiển trong phiên. Dữ liệu này hiện nằm rải trong `CallSession` và các cấu trúc liên quan.

`PlannerState` hiện chỉ là một bản chụp nhỏ của working memory: `stage`, `focus`, `cart`, `order_ids`, `discussed`. Hàm `snapshot(session)` đọc từ session để tạo bản chụp; nó không tự duy trì một kho nhớ khác. `stage` hiện được suy ra từ việc có đơn, có giỏ hay có focus; chưa phải một state machine hội thoại đầy đủ.

Ví dụ cùng câu “đổi sang màu trắng”: khi chưa đặt hàng có thể là đổi lựa chọn trong giỏ; sau khi đặt hàng có thể là yêu cầu sửa/đổi đơn. Trạng thái giúp bộ chọn phân biệt hai tình huống.

## 5. Code hay LLM thực hiện và duy trì?

| Công việc | Bên thực hiện/duy trì | Vai trò của mô hình |
|---|---|---|
| Đọc bộ nhớ, dựng và nạp Call Brief | Code điều phối đọc dữ liệu và dựng brief | Một phần nội dung như tóm tắt phiên trước có thể đã được LLM tạo; không có nghĩa toàn bộ brief do LLM tạo |
| Chuẩn bị dữ liệu của lượt | Code chuẩn hóa, nối dữ liệu, nhận diện sản phẩm và cập nhật cấu trúc | Extractor phía trước có thể dùng rules/Jev/Qwen để đề xuất slot |
| Working memory và snapshot trạng thái | Code giữ trong session, cập nhật sau lời khách và kết quả thực thi | Mô hình đọc phần được đưa vào request; không tự giữ bộ nhớ ứng dụng qua các lần gọi |
| Chọn hành động | Hiện có đường bảng luật và nhánh selector Qwen; phương án mới dùng Jev | Jev phân loại/chọn hành động từ danh sách cho phép |
| Kiểm quyền, slot bắt buộc, tham số và luật nghiệp vụ | Code | Nhãn của Jev không tự cấp quyền thực hiện |
| Gọi tool và xử lý kết quả | Handler và lớp tools/MCP bằng code | Chỉ tham gia nếu có bước suy luận được thiết kế rõ ràng; không cần LLM để gửi lời gọi tool |
| Cập nhật trạng thái sau hành động | Code dựa trên kết quả tool | Không coi nhãn “muốn tạo đơn” là bằng chứng đã tạo đơn |
| Tạo goals/facts cho generator | Code thực thi tổng hợp từ kết quả và điều kiện thực tế | Generator dùng chúng để diễn đạt phản hồi |
| Viết câu trả lời | Generator LLM, đi qua guardrail/fallback bằng code | Chuyển mục tiêu phản hồi và dữ kiện được cung cấp thành câu tiếng Việt |

LLM có thể đề xuất thông tin để ghi nhớ, nhưng code quyết định chấp nhận, ghi vào đâu, thay thế thông tin cũ thế nào và duy trì dữ liệu đó. Ngữ cảnh gửi vào một request không tự trở thành bộ nhớ bền vững của mô hình.

## 6. Jev chọn hành động hay chọn tool?

Ở hợp đồng selector hiện tại, mô hình chọn **hành động nghiệp vụ**, ví dụ `place_order`, `change_order_address`, `ask_price`, `policy_question`. Đây không nhất thiết là tên tool MCP.

Handler triển khai hành động đó bằng không, một hoặc nhiều lời gọi tool:

| Hành động | Handler có thể làm gì |
|---|---|
| `place_order` | Kiểm sản phẩm/biến thể, lấy báo giá và tồn kho, kiểm điều kiện thanh toán, rồi tạo đơn nếu hợp lệ |
| `change_order_address` | Xác định đơn thuộc khách và địa chỉ mới, gọi `order.update`, đọc kết quả |
| `policy_question` | Truy hồi chính sách và tạo fact cho câu trả lời; không cần sửa đơn |
| `defer_decision` | Ghi nhận khách muốn cân nhắc; có thể không cần gọi tool commerce |

Do đó, Jev trả `place_order` không đồng nghĩa với gọi ngay `order.create`. Code có thể phát hiện thiếu biến thể và trả goal `ask_variant`, hết hàng và trả `out_of_stock`, hoặc tạo thành công và trả `order_created`.

Nếu thiết kế cho Jev chọn trực tiếp tên tool thì vẫn cần lớp kiểm tham số, quyền, thứ tự gọi và kết quả. Phương án chọn hành động nghiệp vụ tận dụng tốt hơn các handler hiện có.

## 7. Luồng đề xuất gọn

```text
Đầu cuộc gọi: bộ nhớ xuyên phiên → Call Brief → nạp ngữ cảnh cho session

Mỗi lượt:
Lời khách → chuẩn hóa/trích slot
         + working memory hiện tại
         → chuẩn bị dữ liệu và snapshot trạng thái
         → Jev chọn một hoặc nhiều hành động
         → code kiểm điều kiện, điều phối handler
         → handler gọi tool, đọc kết quả, cập nhật working memory
         → goals + facts phản ánh kết quả thực tế
         → generator viết câu trả lời → guardrail/fallback
```

`goal` cuối cùng là việc cần nói/làm tiếp sau khi thực thi; `facts` là dữ kiện để nói đúng. Ví dụ tool đổi địa chỉ thành công thì goal là `address_updated`; thiếu địa chỉ thì `ask_address`; tool lỗi thì `order_failed`. Không để generator suy ra “đã thành công” chỉ từ nhãn Jev chọn.

## 8. Những điểm cần chỉnh nếu gắn Jev vào selector hiện tại

1. `PLANNER_BACKEND=jev` hiện chỉ gọi planner LLM ở fallback, chọn một goal an toàn. Nó không thay toàn bộ planner và không cho chọn tạo/sửa đơn.
2. Nhánh chọn hành động chính nằm ở `planner_selector.py`, được gọi qua `_semantic_plan()` trong `planner_table.py`. Một số điều kiện hiện chỉ bật khi `planner_selector == "qwen"`, kể cả nhánh chính sách đổi trả trong `agent.py`; thêm Jev phải rà các điểm này.
3. `_prepare()` đang thay đổi giỏ bằng regex trước selector. Cần tách chuẩn bị dữ liệu khỏi thay đổi trạng thái mang ý nghĩa nghiệp vụ.
4. Selector có thể trả nhiều hành động nhưng `_semantic_plan()` hiện thường return sau nhánh đầu tiên. Cần điều phối rõ thứ tự, xung đột và việc thực hiện đủ các ý.
5. Handler hiện còn trộn thực thi với regex đoán ý. Cần truyền hành động đã chọn xuống rõ ràng, giữ kiểm tra nghiệp vụ trong code.
6. `planner_actions.json` có thể dùng lại làm hợp đồng hành động. Điều kiện `requires` hiện không nên được hiểu là đã có một bộ thực thi tổng quát kiểm đầy đủ mọi điều kiện; vẫn cần rà phần kiểm cụ thể.

## 9. Nguồn liên quan

- `harness/planner_table.py`: Ctx, predicate, handlers, chuẩn bị, bảng luật, nhánh semantic và hậu xử lý.
- `harness/planner_rules.json`: bảng điều kiện và handler.
- `harness/planner_selector.py`, `harness/planner_actions.json`: selector Qwen và hợp đồng hành động.
- `harness/planner_state.py`: snapshot trạng thái.
- `harness/planner_llm.py`: planner fallback giới hạn, có backend Jev.
- `harness/agent.py`: Call Brief, session, hàm thực thi nghiệp vụ và đường goals/facts tới generator.
- `docs/DE-XUAT/VAN-DE-PLANNER-2026-11-7.md`: vấn đề trộn hiểu ý, trạng thái và nghiệp vụ.
- `docs/NHAT-KY/NHAT-KY-2026-11-7.md`: probe chọn hàm và giới hạn bằng chứng.
