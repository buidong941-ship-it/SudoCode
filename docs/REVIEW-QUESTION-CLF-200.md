# Rà nhãn thủ công cho bộ phân loại câu hỏi của agent

File CSV đi kèm có 200 câu đã lấy từ trace `sample` và `dev`, đã khử trùng và loại đường dẫn `test`. Cột `weak_suggestion` chỉ là gợi ý từ luật/trace cũ, không phải nhãn chuẩn. Hãy điền `human_label_0_or_1` cho mọi dòng: `1` nếu câu hỏi khách, xin thông tin, yêu cầu khách làm/chọn/ xác nhận điều gì, hoặc đề nghị khách nêu nhu cầu; `0` nếu chỉ chào, cảm ơn, thông báo, khẳng định, hứa hẹn hay dặn dò mà không yêu cầu phản hồi.

Không dựa riêng vào dấu `?`: câu xin địa chỉ hoặc hẹn giờ gọi lại vẫn là `1` dù không có dấu hỏi. Câu “chị cân nhắc thêm nhé” là `0`; câu xin khách cân nhắc lại / cho biết lựa chọn là `1`. Nếu câu không thể phân loại độc lập, ghi chú lý do trong `review_note` và vẫn chọn nhãn phù hợp nhất theo định nghĩa trên.

Khi hoàn tất, gửi lại CSV có đủ 200 nhãn; lúc đó mới huấn luyện/đánh giá lại Nhiệm vụ 6. Không dùng cột gợi ý làm ground truth.
