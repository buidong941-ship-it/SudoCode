# Đề xuất định nghĩa lại toàn bộ slot khách (D10, chờ duyệt)

Định nghĩa đang dùng là `CUSTOMER_SLOTS` trong `harness/llm_extract.py`. Jev và Qwen dùng chung định nghĩa này để quyết định một câu khách có mang slot hay không. Bản dưới đây **chưa áp vào code**.

## Quy tắc chung (áp cho mọi slot)

1. **Có slot** khi câu hiện tại của khách **nói ra giá trị đó**, dù câu ở dạng khẳng định, câu hỏi hay câu yêu cầu. Ví dụ "ship đến 5 Trần Phú mất mấy ngày?" vẫn **có** địa chỉ.
2. **Không có slot** khi khách **hỏi shop** về giá trị đó mà không tự nêu ra ("phòng bao nhiêu mét thì hợp?", "có những màu gì?").
3. Chỉ xét **câu hiện tại**. Ngữ cảnh trước chỉ dùng để hiểu nghĩa, không chép lại giá trị đã nói ở lượt trước. Riêng câu xác nhận ngắn ("ừ đúng rồi", "vẫn địa chỉ đó") thì không tính là nêu giá trị mới.
4. **Mã che thông tin** như `[ĐỊA_CHỈ_1]`, `[SĐT_1]` là giá trị thật đã bị che, nên câu có mã này **có** giá trị tương ứng.
5. Khách **tự sửa** ("45, à không, 50 mét") thì lấy **giá trị cuối cùng**.
6. Giá trị nói về **người khác** (con, chồng, khách khác) chỉ được tính khi slot đó vốn mô tả hộ gia đình của khách (`has_children`, `household_size`, `baby_age`).

## Từng slot

| Slot | Có slot khi | Giá trị | KHÔNG phải slot khi |
|---|---|---|---|
| `room_area_m2` | Khách nêu diện tích phòng sẽ dùng sản phẩm (m², mét vuông, "phòng 20 mét"), kể cả đọc bằng chữ | số nguyên m² | kích thước đồ vật hay khoảng cách ("kệ cao 1 mét", "dây dài 2 mét"); khách hỏi máy dùng cho phòng bao nhiêu m² |
| `has_children` | Khách khẳng định nhà có trẻ nhỏ / em bé / cháu nhỏ (`co`), hoặc khẳng định không có (`khong`) | `co` / `khong` | "bể cá", "bể nước"; tên mẫu có chữ "bé"; con đã lớn, đi học xa (nếu không nói rõ là không có trẻ nhỏ thì để trống) |
| `budget_vnd` | Khách nêu số tiền mình **định chi / tối đa / tầm** cho lần mua này | VND | giá shop đã báo; giá nơi khác; khách hỏi giá; nhận xét "giá này hơi cao" |
| `competitor_price_vnd` | Khách nêu giá thấy ở **nơi bán khác** (Shopee, Lazada, cửa hàng khác, "bên kia") | VND | ngân sách; giá trên fanpage / Zalo của chính shop; nhắc nơi bán khác mà không nêu giá |
| `claimed_price_vnd` | Khách nêu giá mà khách nhớ **shop đã báo trước đó** ("hôm trước em báo 5 triệu 2") | VND | ngân sách; giá nơi khác; giá khách tự đoán |
| `size` | Khách **chọn** size / cỡ / số (giày, áo) | chữ in hoa: `42`, `L`, `XL` | số nhà trong địa chỉ ("số 12 Nguyễn Trãi"); số lượng ("lấy 2 đôi"); khách hỏi size nào hợp |
| `color` | Khách **chọn** màu cho sản phẩm định mua | tên màu | khách hỏi có màu gì; màu của đồ đang dùng |
| `address` | Khách đọc địa chỉ giao hàng có **số nhà / ngõ / hẻm / kiệt / tên đường**, kể cả trong câu hỏi giao hàng, kể cả dạng mã `[ĐỊA_CHỈ_n]` | nguyên địa chỉ, không kèm "giao về", "bên em…", "anh trả tiền…" | nơi ở chung chung ("nhà ở Huế"); hỏi "giao đến khi nào"; người nhận ("gửi về cho mẹ"); địa chỉ cửa hàng; "địa chỉ cũ / như cũ" (đây là xác nhận, không phải giá trị mới) |
| `payment` | Khách **chọn** cách trả: tiền mặt khi nhận (`COD`), hoặc chuyển khoản / ví điện tử (`bank`) | `COD` / `bank` | hỏi shop có COD hay chuyển khoản được không; nói về cài đặt thanh toán của phần mềm; "ck" nghĩa là chồng |
| `blocker` | Khách nói lý do **chưa quyết mua**: `can hoi chong` / `can hoi vo` / `can hoi nguoi nha` (phải nhắc rõ người nhà), `so sanh gia` (muốn so giá, xem chỗ khác), `can nhac` (suy nghĩ, xem thêm, để sau, bàn lại) | một nhãn | đã hỏi người nhà xong và chốt; từ chối hẳn; chỉ hỏi thông tin; "cân nhắc" nói về khách hàng của khách |
| `callback_requested` | Khách hẹn shop gọi / nhắn lại vào **thời điểm cụ thể** ("mai 9h", "thứ 7") | ngày giờ (span = cụm thời gian) | hẹn mà không có thời điểm ("có gì em gọi lại"); phàn nàn shop chưa gọi lại; hỏi bao giờ shop gọi |
| `self_name` | Khách **tự xưng tên mình** ("chị Dung đây", "anh là Minh") | tên riêng | vai trò ("chị là khách cũ", "anh là chủ quán"); tên người khác ("con gái cô tên Lan") |
| `household_size` | Khách nêu số người trong nhà / số người sẽ dùng | số nguyên | số lượng sản phẩm; số người ở chỗ khác |
| `baby_age` | Khách nêu tuổi của bé nhà mình | "6 tháng", "2 tuổi" | tuổi người lớn; tuổi sản phẩm |
| `objection` | Khách **phản đối giá**: `dat_qua` (chê đắt, thấy chênh hơn bên khác) hoặc `ep_gia` (đòi bớt, ép giá) | một nhãn | chỉ hỏi giá; hỏi có khuyến mãi không; hỏi tiền chênh khi đổi hàng |
| `owned_product` | Khách nói sản phẩm **đang dùng / đã có** | tên sản phẩm | sản phẩm đang xem hoặc hỏi mua |

## Áp vào code thế nào (sau khi duyệt)

- Thay `CUSTOMER_SLOTS` trong `harness/llm_extract.py` bằng cột "Có slot khi" và "KHÔNG phải slot khi" ở trên. Jev và Qwen đều đọc từ đây.
- Thêm "Quy tắc chung" 1–5 vào câu hướng dẫn gửi Jev (`harness/jev_hybrid.py`) và vào prompt Qwen.
- Cập nhật `datagen/slot_specs.json` cho khớp, để câu tự sinh dùng cùng định nghĩa.
- Kiểm: chạy `tests/llm_extract_check.py` và `tests/jev_hybrid_check.py` (mock) trên Kaggle CPU; đo bằng Jev thật trong job GPU sau.
- Lưu ý: định nghĩa đổi thì cache LLM của extractor Qwen tự hết hiệu lực (khóa cache tính trên cả prompt), nên số lần chạy sau không so thẳng được với số trong cache cũ.
