# Vấn đề gốc: Một khối regex làm cả ba việc khác nhau (07/11/2026)

Planner hiện tại (bảng `planner_rules.json` cùng các hàm xử lý trong `agent.py`) đang gánh ba việc. Mỗi việc cần một cách làm khác, nhưng cả ba đều đang được giải bằng regex trên câu đã bỏ dấu cộng với thứ tự ưu tiên của các dòng bảng:

| Việc | Cần gì | Hiện tại làm bằng | Hệ quả đã đo |
| :--- | :--- | :--- | :--- |
| **1. Hiểu khách muốn gì** | Chịu được nhiều cách nói | Regex từ khóa + 1 intent của router | Sai khi khách nói khác dev: `"giao về X"` không được nhận là đổi địa chỉ; `"đặt cho anh X"` không được nhận là đặt hàng (luật thuần); `"cô"` bị khớp thành `"cỡ"` |
| **2. Nhớ cuộc hội thoại đang ở đâu** | Trạng thái tường minh | Các biến rời rạc trong `CallSession` (`focus`, `window_told`, `pending_size`, `updates_done`...) | Bám sản phẩm cũ trong bộ nhớ dù khách vừa chọn sản phẩm khác; tạo đơn khi khách mới "thêm" món |
| **3. Áp luật nghiệp vụ** | Một nguồn sự thật duy nhất | Hằng số viết cứng trong hàm quyết định (7 + 4 ngày) | RAG trả lời *"đơn trước 01/10 được 14 ngày"*, ngay lượt sau planner lại coi đơn là quá hạn |

Vì cả ba trộn chung, sửa lỗi nào cũng thành thêm một regex cho đúng câu bị lỗi. Bảng D51 được viết từ chính các ca trượt của dev, nên v3 dev đạt 98,8% mà holdout chỉ 66,2%. Probe trên câu mới (phần D) xác nhận điều này: luật thuần 72, Qwen bản 2 là 92.

---

## Các vấn đề cụ thể sinh ra từ gốc đó

1. **Mỗi lượt chỉ có một intent, trong khi khách nói nhiều ý trong một câu.**
   - Ví dụ: *"Thêm X nữa, tổng bao nhiêu?"*, hay *"Lấy đủ bốn món, giao về Y"*.
   - Planner rẽ nhánh theo intent trước, rồi mới dùng regex chọn hành động con bên trong nhánh.
   - `order_change` gộp chung đổi size, đổi địa chỉ, trả hàng và hủy đơn; lỗi "đổi địa chỉ thành đổi size" sinh ra đúng ở bước chọn con này.

2. **Không có khái niệm giai đoạn hội thoại.**
   - Không có trạng thái rõ ràng kiểu `đang chọn món → đang chốt → đã có đơn → sau bán`.
   - Vì vậy:
     - *"thêm X"* bị hiểu là chốt đơn;
     - Đã báo *"quá hạn"* một lần (`window_told`) thì lượt sau khách đòi trả hàng sẽ bị chuyển sang báo giá;
     - Sản phẩm khách vừa nêu không được ưu tiên hơn sản phẩm trong bộ nhớ.

3. **Hiểu ý và thực thi dính vào nhau.**
   - Ví dụ: `_plan_order_change` vừa đoán khách muốn gì, vừa tự tính hạn đổi trả, vừa gọi `order.update`.
   - Kết quả là phép kiểm quá hạn chạy trước khi xét khách muốn trả hàng, và khó kiểm hay thay từng phần riêng.

4. **Thành phần này không đối chiếu với thành phần kia.**
   - Extractor đã trích được địa chỉ mới, nhưng planner không dùng tới.
   - Tool đã dời lịch hẹn sang thứ Ba, nhưng câu trả lời vẫn nói "thứ Hai".
   - RAG nói 14 ngày, planner lại nói 7 ngày.
   - *Không có bước nào kiểm "các thành phần có nói cùng một điều không".*

5. **Tin luật nhiều nhất đúng ở chỗ luật yếu nhất.**
   - LLM chỉ được gọi khi không dòng luật nào khớp. Nhưng lỗi nằm ở những lượt luật khớp sai, nên LLM không bao giờ thấy.
   - Job A/B hôm nay đếm được 0/200 lượt rơi vào nhánh fallback, nên planner hybrid hiện tại không có tác dụng.

6. **Chất lượng planner phụ thuộc vào router.**
   - Planner chỉ đọc một intent cộng các ngưỡng cờ.
   - Router luật thuần làm planner tụt khoảng 10 điểm so với dùng Jev (probe: A 87 so với 97).
   - Khi Jev lật intent ở câu sát ngưỡng (V3-095: 0,35 so với 0,36), goal của planner cũng lật theo.

7. **Quy trình sửa lỗi làm vấn đề nặng thêm.**
   - Mỗi vòng đều theo kiểu: *"thấy ca trượt trên dev → thêm dòng hoặc regex cho ca đó → dev qua"*.
   - Không có bộ câu mới để kiểm sau mỗi lần sửa, nên không phát hiện được là mình đang khớp quá sát với dev.

---

## Những gì planner đang làm tốt (không nên bỏ)

- **Tham số tool chính xác và tất định:** Mã đơn, SKU, giá đều lấy từ tool và bộ nhớ. Đây là thứ bộ chấm đòi khắt khe nhất.
- **Nhóm an toàn ổn định:** Nội bộ, bảo mật, AI hay người, xóa dữ liệu. Probe cho thấy luật thuần đúng 3/3 ca an toàn trên D, và không có vi phạm guardrail nào trên holdout.
- **Đọc và duyệt được từng dòng:** Điều giám khảo đánh giá cao.

---

## Hướng sửa theo đúng gốc

Tách ba việc ra, mỗi việc làm theo cách hợp với nó:

| Việc | Hướng | Bằng chứng ủng hộ |
| :--- | :--- | :--- |
| **Hiểu ý** | LLM chọn hàm (đa nhãn) trong danh sách đóng; nhóm an toàn giữ luật | Probe D: 92 so với 72 |
| **Trạng thái** | Một đối tượng trạng thái tường minh: giỏ, đơn đang mở, sản phẩm đang bàn (ưu tiên sản phẩm vừa nhắc), giai đoạn | Giải quyết gốc lỗi 3, 4 và lỗi `window_told` |
| **Luật nghiệp vụ** | Một chỗ duy nhất: hạn đổi trả theo ngày đơn, ngưỡng COD 10 triệu, ngày nghỉ. Planner, RAG và câu trả lời cùng gọi chung | Giải quyết gốc lỗi 1 và các lỗi "nói một đằng, làm một nẻo" |
| **Đối chiếu** | Bất biến kiểm chéo giữa slot, kế hoạch và kết quả tool (`requires` / `on_missing` thuộc lớp này) | Gốc lỗi 2, các lỗi của generator |
| **Quy trình** | Sửa theo bất biến; mỗi lần sửa phải đo trên bộ câu mới chưa xem | Khoảng cách dev và holdout |

---

## Giới hạn của nhận định này

- Dựa trên 26 ca trượt và 251 mục probe, nhãn do một mình tôi gán. Probe mới đo việc chọn hàm, chưa đo TSR.
- Đây là thay đổi kiến trúc lớn của planner. Nó thuộc vòng cải tiến, không thay đổi số holdout đã chốt, và cần bạn duyệt từng phần trước khi làm.
