# Câu hỏi gửi BTC — lỗi logic trong code tham chiếu, kịch bản mẫu và script chấm

Khi làm lại tool và chạy thử trên gói dữ liệu BTC phát, team gặp một số chỗ chưa rõ là chủ ý hay lỗi. Team tổng hợp lại để hỏi một lần, tránh làm lệch đáp án chấm.

Mọi mục dưới đây đều đã được chạy thử trên gói dữ liệu hiện tại (ngày tham chiếu 15/10/2026). Tool được gọi trực tiếp từ `eval/mock_tools.py`, script chấm từ `eval/reference_eval.py`.

Mức ảnh hưởng ghi ở đầu mỗi mục:

- **[Chặn điểm]**: hệ thống làm đúng vẫn bị chấm trượt, hoặc script chấm dừng giữa chừng.
- **[Lệch kết quả]**: tool hoặc script cho kết quả khác chính sách; team cần biết đáp án chấm theo bên nào.
- **[Nhỏ]**: sai lệch ở trường hợp biên hoặc trong tài liệu.

| Phần | Nội dung | Số mục |
|---|---|---|
| A | Kịch bản mẫu `test_set/public_sample/` | 5 |
| B | Tool tham chiếu `eval/mock_tools.py` | 12 |
| C | Script chấm `eval/reference_eval.py` và dữ liệu ASR | 7 |
| D | Tài liệu và gói dữ liệu | 2 |

---

## A. Kịch bản mẫu

**A1. [Chặn điểm] SAMPLE-03: mã đơn trong đáp án không thể sinh ra từ `order.create`**

Ở `call_2`, `success_if.args_match` yêu cầu `order.update` với `order_id = "OD682761"`. Mã này chỉ có trong file kịch bản, không có trong `catalog/crm_seed.json` (khách C012 không có đơn nào). Đơn agent tạo ở `call_1` qua `order.create` luôn có mã `OD600001`. Vì vậy:

- agent gọi `order.update` với mã thật `OD600001` thì trượt `args_match`;
- agent gọi với `OD682761` thì tool trả `order_not_found`.

Hỏi: script chấm có bỏ qua `order_id` khi so `args_match`, hoặc ánh xạ sang mã đơn thực tế của `call_1`, không? Bộ test ẩn có cùng vấn đề này không?

**A2. [Chặn điểm] SAMPLE-06 `call_2`: không có cách nào nhận diện khách**

`call_2` có `channel: "zalo_oa"`, `channel_identity: null`. Khách C030 trong CRM có `zalo_id: null`. Trong ba lượt của `call_2`, khách không đọc số điện thoại. Trong khi đó kịch bản yêu cầu:

- `must_carry_over`: `product_advised`, `price_quoted_vnd`, `room_area_m2` từ `call_1`;
- `success_if`: gọi `order.create`, mà `customer_phone` là tham số bắt buộc theo `schemas/tools.schema.json`.

Hỏi:

- Hệ thống được phép dùng `customer_phone` ở đầu file kịch bản làm định danh cho mọi kênh, kể cả khi `channel_identity` là `null`, không?
- Nếu không, agent xin số điện thoại trước khi lên đơn thì kịch bản có được tính đạt không? Khách không có lượt nào để trả lời.

**A3. [Lệch kết quả] SAMPLE-02: `promo_active: false` trong khi KM còn hiệu lực**

`call_2` diễn ra ngày 18/10/2026. `pricing_get_quote("SKU-AP-X", on="2026-10-18")` vẫn áp `GIFT-FILTER` (hiệu lực đến 22/10), nhưng `ground_truth_facts` ghi `promo_active: false`. Khách hỏi "có tặng gì kèm không", nên agent trả lời theo tool sẽ nói có quà tặng.

Hỏi: `promo_active: false` là lỗi dữ liệu, hay nó chỉ một KM khác (vd. KM giảm giá)? Claim "đang tặng màng lọc" ở lượt này được chấm đúng hay sai?

**A4. [Lệch kết quả] SAMPLE-01: lời khách và `facts_established` không khớp**

- Khách nói "ngân sách tầm 5 triệu", nhưng `facts_established.budget_vnd = 5700000`.
- Sản phẩm trong đáp án là `SKU-AP-Y` giá 5.200.000đ, vượt mức 5 triệu khách nêu. Trong `asr/ground_truth.json` (D01, cùng tình huống), agent đề xuất AirPure Y, khách chê vượt ngân sách và chuyển sang AirPure X.
- Ở `call_2` khách nói "giao về địa chỉ cũ", nhưng `call_1` không có lượt nào nêu địa chỉ và CRM (C001) không lưu địa chỉ.

Hỏi:

- Giá trị chuẩn của `budget_vnd` là 5.000.000 hay 5.700.000?
- Agent tư vấn AirPure X (trong ngân sách) ở `call_1` thì `call_2` có trượt `args_match` (`sku: SKU-AP-Y`) không?
- "Địa chỉ cũ" lấy từ đâu? Agent hỏi lại địa chỉ có bị tính là câu hỏi thừa không?

**A5. [Lệch kết quả] Tên trường trong `ground_truth_facts` không thống nhất**

Script chấm Hallucination Rate chỉ tính claim có `field` trùng tên với một khóa trong `ground_truth_facts`; claim khác tên bị bỏ qua. Các kịch bản mẫu dùng nhiều cách đặt tên cho cùng một loại thông tin:

| Thông tin | Tên trong kịch bản |
|---|---|
| KM còn hiệu lực | `promo_active` (SAMPLE-01, 02, 04); `promo_AP-SEP_active`, `promo_GIFT-FILTER_active` (SAMPLE-05); `promo_NAM-SHIP0_active` (SAMPLE-06) |
| Ngày hàng về | `restock_date` (SAMPLE-06), trong khi tool trả `restock_expected` |

`schemas/trace_log.schema.json` chỉ quy định `field` là chuỗi, không có danh sách tên chuẩn.

Hỏi: BTC có danh sách tên `field` chuẩn cho `claims` không? Khi một sản phẩm có nhiều KM, dùng `promo_active` hay `promo_<MÃ>_active`?

---

## B. Tool tham chiếu `eval/mock_tools.py`

**B1. [Lệch kết quả] `schedule.callback` dời lịch hẹn ngoài giờ không theo "khung gần nhất"**

`policy/thong-bao-lich-nghi.md` quy định: thứ Hai–thứ Bảy làm 08:00–21:00, Chủ nhật 09:00–18:00. Nếu khách hẹn ngoài giờ thì *"đề xuất khung gần nhất trong giờ làm việc"*. Team so kết quả hàm với khung gần nhất mà team hiểu từ chính sách (tuần 17–19/10/2026: T7, CN, T2):

| Khách hẹn | Hàm trả về | Khung gần nhất theo chính sách |
|---|---|---|
| T2 19/10 05:00 | T2 08:00 | T2 08:00 ✓ |
| T2 19/10 21:30 | **T2 19/10 08:00** (sáng đã qua) | T3 20/10 08:00 |
| T7 17/10 22:00 | **T7 17/10 08:00** (sáng đã qua) | CN 18/10 09:00 |
| CN 18/10 07:45 | **T2 08:45** | CN 09:00 |
| CN 18/10 08:30 | **T2 08:30** | CN 09:00 |
| CN 18/10 18:30 | **T2 18:30** | T2 08:00 |
| T2 26/10 (ngày nghỉ) 10:00 | T3 27/10 10:00 | T3 27/10 10:00 ✓ (đúng LN-02) |
| T4 11/11 22:00 (ngày sale, mở 07:00–23:00) | **T4 11/11 08:00** | giữ nguyên 22:00 |

Nguyên nhân theo từng trường hợp:

- Hẹn **trước giờ mở cửa** vào ngày thường: hàm đổi giờ thành 08:00, đúng.
- Hẹn **sau giờ đóng cửa** vào ngày thường (từ 21:00): hàm cũng chỉ đổi giờ thành 08:00 mà không sang ngày hôm sau, nên lịch rơi vào buổi sáng đã qua (dòng 188).
- Hẹn **ngoài khung giờ của Chủ nhật** hoặc vào ngày nghỉ: hàm cộng thêm một ngày và **giữ nguyên giờ khách hẹn** (dòng 186–187). Hàm không xét khung Chủ nhật 09:00 còn trống, cũng không đưa về đầu giờ của ngày hôm sau.
- Giờ mở cửa riêng của ngày 11/11 (LN-02) không có trong hàm.

Hỏi: đáp án chấm của `schedule.callback` dựa trên kết quả hiện tại của hàm hay trên khung gần nhất theo chính sách (tức là hàm đang gặp lỗi logic)?

**B2. [Lệch kết quả] AIR-2ND-50 ("máy thứ 2 giảm 50%") cho kết quả khác điều khoản ở ba trường hợp**

KM-05 và FAQ-19: mua từ hai máy lọc không khí trong cùng đơn thì **máy có giá thấp hơn** được giảm 50%. Khi báo giá một máy, `pricing.get_quote` nhận `basket_skus` là các máy khác trong đơn rồi so giá (dòng 110–113).

| Trường hợp | Lời gọi | Kết quả của hàm |
|---|---|---|
| Hai máy cùng giá | `get_quote("SKU-AP-X", basket_skus=["SKU-AP-X"])` | Giảm 50% (2.445.000đ). Phép so là `<=`, nên báo giá máy nào thì máy đó cũng "rẻ nhất": **cả hai máy đều được giảm**. |
| Mua 2 máy cùng mã bằng `qty` | `get_quote("SKU-AP-X", qty=2)` | **Không giảm**, lý do `not_cheapest_item`, vì `basket_skus` rỗng. |
| Mua nhiều máy rẻ kèm một máy đắt | `get_quote("SKU-AP-MINI", qty=3, basket_skus=["SKU-AP-PRO"])` | **Cả 3 máy** MINI đều giảm 50% (1.095.000đ/máy; `order.create` ra tổng 3.285.000đ). |

Hỏi:

- Hai máy cùng giá thì cả hai được giảm 50% có phải là lỗi logic không?
- Mua hai máy cùng mã phải truyền `qty=2` hay `qty=1` kèm `basket_skus=[cùng mã]`? Đáp án `args_match` và `total_match_vnd` tính theo cách nào?
- KM chỉ áp cho một máy rẻ nhất, hay cho mọi máy trừ máy đắt nhất?

**B3. [Lệch kết quả] Đổi size bị tính thêm tiền vì hàm tính lại giá của biến thể mới**

`order.update` với `exchange_size` gọi lại `pricing_get_quote` cho biến thể mới (dòng 169) rồi lấy hiệu với giá đơn cũ. Nếu đơn cũ đã dùng một KM mỗi khách một lần, hoặc KM đã hết hạn vào ngày đổi, biến thể mới bị tính giá gốc.

```
order_create(P, "SKU-SN-RUN2-42-DEN", on="2026-10-15")      # giá 1.521.000đ, đã áp RUN-10
order_update("OD600001", "exchange_size", "SKU-SN-RUN2-40-DEN", on="2026-10-19")
→ fee_vnd = 0, price_diff_vnd = 169000, extra_payment_vnd = 169000
```

Khách đổi size 42 sang 40 cùng mẫu, cùng giá niêm yết, RUN-10 vẫn còn hiệu lực (đến 25/10), nhưng phải trả thêm 169.000đ. Lý do: RUN-10 đã bị đánh dấu "đã dùng" bởi chính đơn đang đổi. DT-03 quy định đổi size lần đầu miễn phí, và KM-01 quy định đơn đã tạo trước ngày hết hạn thì giữ giá.

Hỏi: đổi size trong cùng mẫu có phải trả chênh lệch này không? `ground_truth_facts` của ca đổi size (vd. `exchange_fee_vnd: 0` ở SAMPLE-03) có tính `extra_payment_vnd` không?

**B4. [Lệch kết quả] `order.update` không cập nhật đơn và thiếu tham số địa chỉ**

- Sau khi đổi size thành công, `order.status` vẫn trả `sku` cũ (`SKU-SN-CAS-39-DEN`) và `status: "created"`. Cuộc gọi sau hỏi trạng thái đơn sẽ thấy size cũ.
- Lần đổi thứ hai tính chênh lệch so với giá đơn gốc, không so với lần đổi trước.
- `action: "update_address"` trả `status: "updated"`, nhưng hàm và `schemas/tools.schema.json` đều **không có tham số nào để truyền địa chỉ mới**.

Hỏi:

- Ca "3 phiên thông tin thay đổi + hỏi trạng thái đơn" trong bộ ẩn chấm theo `order.status` hiện tại (không đổi sau `order.update`) hay theo trạng thái đã cập nhật?
- Địa chỉ mới của `update_address` truyền qua tham số nào? `args_match` kiểm tra gì cho action này?

**B5. [Lệch kết quả] `order.update` không kiểm tra điều kiện đổi trả**

Tool chấp nhận `return` / `exchange_*` cho mọi đơn tìm thấy. Thử trả hàng sau 76 ngày (`on="2026-12-30"` cho đơn tạo 15/10) vẫn ra `refund_vnd` đầy đủ. Hàm không xét:

- hạn 7 ngày kể từ ngày nhận hàng (DT-01, DT-06);
- đơn tạo trước 01/10/2026 vẫn áp chính sách cũ 14 ngày (`policy/changelog.md`);
- hàng xả kho "không đổi trả", bình sữa đã bóc seal (DT-02, DT-06);
- đơn đã giao hay chưa, và đơn có thuộc khách đang gọi hay không.

Hỏi:

- Team hiểu agent phải tự kiểm tra và **không gọi** `order.update` khi khách không đủ điều kiện. Như vậy có đúng không?
- Kịch bản ẩn có chấm việc "không được gọi tool này" không?
- Tool của team có được trả lỗi (vd. `return_window_expired`) thay vì tạo ticket không?

**B6. [Lệch kết quả] Miễn phí vận chuyển và `min_order` tính theo giá một sản phẩm, không theo tổng đơn**

VC-02 quy định miễn phí vận chuyển theo **giá trị đơn** (từ 2.000.000đ; từ 500.000đ với mẹ & bé). Hàm so với giá **một đơn vị** (dòng 106 và 125), bỏ qua `qty`:

| Lời gọi | Tổng đơn | Hàm trả về |
|---|---|---|
| `get_quote("SKU-FAN-TWR", qty=2)` | 3.580.000đ | `freeship: false` |
| `get_quote("SKU-MB-MON", qty=2)` | 980.000đ | `MOM-FREESHIP` bị loại, lý do `min_order` |

Hỏi: `freeship` trong `ground_truth_facts` tính theo tổng đơn (chính sách) hay theo giá một đơn vị (hàm)?

**B7. [Lệch kết quả] Giới hạn COD 10 triệu chỉ xét từng lời gọi `order.create`**

Mỗi lời gọi `order.create` chỉ nhận một `sku`. Đơn nhiều sản phẩm phải gọi nhiều lần, và giới hạn COD được xét riêng cho từng lần:

```
order_create(P, "SKU-AP-PRO",  payment="COD")   → tạo đơn, 7.690.000đ
order_create(P, "SKU-SS-AX40", payment="COD")   → tạo đơn, 6.490.000đ
```

Tổng 14.180.000đ COD trong cùng một cuộc gọi vẫn được chấp nhận. Ngoài ra ngưỡng không thống nhất: VC-03 ghi "đơn **dưới** 10.000.000đ", QT-01 ghi "đơn **trên** 10.000.000đ không áp dụng COD", còn hàm chặn khi `total > 10000000` (đúng 10.000.000đ vẫn được COD).

Hỏi:

- Ca "4 sản phẩm, trên 10 triệu không COD" trong bộ ẩn chấm thế nào khi tool không chặn? Agent phải tự cộng tổng giỏ hàng và từ chối COD?
- Đơn đúng 10.000.000đ có được COD không?

**B8. [Lệch kết quả] `order.create` không kiểm tra số lượng và chấp nhận mã cha chưa chọn size**

- Tồn kho `SKU-AP-X` là 40, nhưng `order_create(P, "SKU-AP-X", qty=100, payment="bank")` vẫn tạo đơn 489.000.000đ. Hàm chỉ kiểm tra `in_stock`, không so `qty` với tồn kho.
- Tạo đơn xong tồn kho không giảm.
- `order_create(P, "SKU-SN-RUN1", ...)` (mã cha của giày, chưa có size và màu) vẫn tạo đơn thành công.

Hỏi:

- Agent có phải tự so `qty` với `inventory.check` trước khi lên đơn không?
- Đơn bằng mã cha (chưa chọn size) có được tính đạt khi `args_match` yêu cầu `variant_sku` không? Tool của team có được trả lỗi trong trường hợp này không?

**B9. [Lệch kết quả] Xác định vùng miền theo địa chỉ thiếu nhiều tỉnh và mặc định là miền Bắc**

`_region_of` (dòng 34–38) dò từ khóa có dấu trong địa chỉ; không khớp thì trả `bac`. KM-08 quy định miền Trung gồm cả Tây Nguyên, miền Nam từ Đồng Nai, Bình Dương, TP.HCM trở vào.

| Địa chỉ | Hàm trả về | Theo KM-08 |
|---|---|---|
| `"Cà Mau"`, `"Tây Ninh"` | `bac` | `nam` |
| `"Pleiku, Gia Lai"` | `bac` | `trung` |
| `"TP Ho Chi Minh"`, `"Sai Gon"` (không dấu) | `bac` | `nam` |
| không truyền `address` | `bac` | chưa xác định |

Hệ quả: khách miền Nam ở các tỉnh trên không được `NAM-SHIP0`. Báo giá khi chưa có địa chỉ có thể khác giá lúc `order.create` có địa chỉ, dẫn tới `price_mismatch`.

Hỏi:

- Đáp án chấm theo kết quả của hàm hay theo KM-08?
- Khi chưa biết địa chỉ, agent nên báo giá rồi báo lại sau khi có địa chỉ, hay phải hỏi địa chỉ trước khi báo giá?

**B10. [Lệch kết quả] `ineligible_promos` chỉ ghi một lý do khi KM trượt nhiều điều kiện**

Hàm kiểm tra lần lượt `min_qty` → `exclude_variant_size` → `region` → `requires_owned_sku` → `once_per_customer` → `min_order`, và mỗi điều kiện trượt **ghi đè** lý do trước (biến `why`, dòng 101–106).

Ví dụ với RUN-10 (giảm 10% RunLite; loại size 43; mỗi khách dùng 1 lần), cùng một khách:

```
pricing_get_quote("SKU-SN-RUN2-43-DEN", customer_phone=P)
→ ineligible_promos = [{"promo_code": "RUN-10", "reason": "exclude_variant_size"}]

order_create(P, "SKU-SN-RUN2-42-DEN", ...)        # khách mua size 42, đã dùng RUN-10

pricing_get_quote("SKU-SN-RUN2-43-DEN", customer_phone=P)
→ ineligible_promos = [{"promo_code": "RUN-10", "reason": "once_per_customer"}]
```

Ở lần báo giá thứ hai, size 43 trượt **cả hai** điều kiện, nhưng hàm chỉ trả `once_per_customer`. Agent sẽ giải thích "anh/chị đã dùng mã này rồi". Khách có thể hiểu là người khác mua size 43 vẫn được giảm.

Hỏi:

- Kịch bản chấm có kiểm tra **lý do** agent nêu cho khách khi KM không áp dụng không? Nếu có, lý do chuẩn là lý do hàm hiện trả hay toàn bộ các lý do?
- Tool của team có được **thêm** trường `reasons` (danh sách đủ các lý do) bên cạnh `reason` không?

**B11. [Nhỏ] Ngày giao dự kiến luôn lấy mức tối đa và không phân biệt khu vực**

`_eta` (dòng 145–151) cho 2 ngày làm việc nếu địa chỉ chứa "hà nội", "hcm", "hồ chí minh", "đà nẵng", còn lại 4 ngày. So với VC-01:

- Bình Dương, Đồng Nai, Hải Phòng, Cần Thơ: chính sách 2–3 ngày, hàm 4 ngày.
- Phú Quốc, Côn Đảo: chính sách 5–7 ngày, hàm 4 ngày.
- Không xét "đặt sau 16h tính từ ngày kế tiếp".

Hỏi: claim `delivery_days` chấm theo `estimated_delivery` của tool hay theo khoảng ngày trong VC-01?

**B12. [Nhỏ] `handoff.transfer` và `mask_pii`**

- `handoff_transfer` chỉ kiểm tra có đủ khóa. Brief với mọi trường là chuỗi rỗng vẫn nhận `brief_ok: true`, dù `schemas/handoff_brief.schema.json` yêu cầu `conversation_summary` tối thiểu 20 ký tự, `customer_phone` đúng mẫu, `escalation_reason` thuộc danh sách cho trước. `reference_eval.py` cũng chỉ kiểm tra các trường trong `brief_must_contain` khác rỗng.
- `mask_pii("0984726714")` trả `"******6714"`: mẫu `bank` (9–14 chữ số) che luôn số điện thoại, còn mẫu `phone` được khai báo nhưng không dùng.

Hỏi: "brief hợp lệ theo schema" (mục 4 của `DIEU-CHINH-DE.md`) có được kiểm tra bằng JSON Schema khi chấm không?

---

## C. Script chấm `eval/reference_eval.py` và dữ liệu ASR

**C1. [Chặn điểm] Script dừng với `TypeError` khi hệ thống không hỏi câu nào**

Nếu ở các cuộc gọi có `must_not_ask`, hệ thống không đặt câu hỏi nào, `repeat_question_rate` trả `value: None`. Dòng 371 tính `(rq_b - rq_s) / rq_b` với `rq_s = None`:

```
TypeError: unsupported operand type(s) for -: 'float' and 'NoneType'
```

Script dừng trước khi ghi `report.json` và in bảng A.6. Trường hợp này dễ gặp với bộ test nhỏ và hệ thống có bộ nhớ tốt.

Hỏi: BTC có sửa script không? RQR của hệ thống không hỏi câu nào được tính là 0% hay không xác định?

**C2. [Chặn điểm] Task Success tính cả lời gọi `order.create` bị tool từ chối**

- `check_call` (dòng 143) chỉ so tên tool và tham số, không xem `result`. Một lời gọi `order.create` trả `out_of_stock` hay `price_mismatch` vẫn được tính là đạt.
- `total_match_vnd` (dòng 149) cộng `price_vnd × qty` của **mọi** lời gọi `order.create`, kể cả lời gọi lỗi. Agent thử COD, nhận `cod_limit_exceeded`, rồi tạo lại bằng chuyển khoản sẽ bị cộng gấp đôi và trượt:

```
order.create(sku=X, price_vnd=100, payment="COD")   → cod_limit_exceeded
order.create(sku=X, price_vnd=100, payment="bank")  → tạo đơn
total_match_vnd = 100  →  script báo "tổng đơn 200 ≠ 100"
```

- `calls_to_close` (dòng 267) cũng tính cả lời gọi lỗi.

Hỏi: lời gọi tool trả lỗi có được loại khỏi các phép tính này không? Agent có bị phạt khi gọi `order.create` hai lần (một lần lỗi) không?

**C3. [Lệch kết quả] Context Carryover tính theo tên tham số, không xét giá trị**

Dòng 100 đưa **tên** mọi tham số của tool call vào tập "fact đã dùng". Lời gọi `order.update(order_id="SAI", sku="SAI")` vẫn được tính đã mang sang `order_id` và `sku` (thử thật: CCR = 100%). Ngược lại, slot `variant_sku`, `size`, `color`, `product_advised` không trùng tên tham số nào nên chỉ được tính qua `facts_used` do hệ thống tự khai.

Hỏi: CCR có kiểm tra giá trị không? BTC kiểm tra `facts_used` tự khai bằng cách nào?

**C4. [Lệch kết quả] Hallucination Rate tính sai khi một cuộc gọi nhắc giá nhiều sản phẩm**

`ground_truth_facts` chỉ có một `price_vnd` cho mỗi cuộc gọi (dòng 242). Agent báo đúng giá hai sản phẩm thì claim thứ hai bị tính là bịa:

```
ground_truth_facts = {"price_vnd": 4890000}
claims = [price_vnd=4890000 (AirPure X), price_vnd=2990000 (Xiaomi 4 Lite, đúng catalog)]
→ HR = 50%
```

SAMPLE-02 có `alt_suggested: "SKU-XM-4L"`, nên agent làm đúng kịch bản sẽ gặp trường hợp này.

Hỏi: claim giá của sản phẩm khác sản phẩm chính nên xuất với `field` nào để không bị tính sai?

**C5. [Lệch kết quả] Mẫu PII trong `guardrail_violations`**

Thử từng chuỗi trong `agent_text` (dòng 105 và 197–201):

| Chuỗi | Số vi phạm được đếm | Ghi chú |
|---|---|---|
| CCCD `079188001234` | 2 | Khớp cả hai mẫu nên đếm hai lần |
| STK `0123456789` | 0 | 10 chữ số bắt đầu bằng 0 được coi là số điện thoại, nên **lọt** |
| STK `1234567890` | 1 | Đúng |
| SĐT `+84984726714` | 1 | Số điện thoại dạng +84 bị tính là PII |

Hỏi: số tài khoản 10 chữ số bắt đầu bằng 0 có trong bộ ẩn không? Số điện thoại dạng `+84` có được phép xuất hiện không?

**C6. [Chặn điểm] `asr/ground_truth.json`: entity cấp hội thoại bị ghi đè khi một khóa có nhiều giá trị**

Trong D01, agent nhắc AirPure Y giá 5.200.000đ (lượt 5) rồi AirPure X giá 4.890.000đ (lượt 7). `entities` cấp hội thoại chỉ giữ giá trị nhắc sau (`sku: SKU-AP-X`, `price_vnd: 4890000`), và script so mỗi khóa với đúng một giá trị (dòng 313–314). Hệ thống trích đúng cả hai giá chỉ được điểm nếu tự gộp theo quy tắc "giá trị sau thắng".

Hỏi:

- Entity Accuracy chấm theo cấp hội thoại (giá trị sau thắng) hay theo từng lượt?
- BTC có phát bản sửa `ground_truth.json` và cách chấm entity tương ứng không?

**C7. [Nhỏ] Hai chỉ số phụ**

- "Số lượt TB / cuộc" (dòng 259) đếm số dòng trace. Lượt của khách được viết sẵn nên baseline và hệ thống luôn bằng nhau (báo cáo mẫu `eval/runs/report_example.json`: 3 và 3). Dòng này trong bảng A.6 không phân biệt được hai cấu hình.
- `p95` (dòng 49) trả về giá trị lớn nhất khi n = 10 hoặc 20, và phần tử thứ 96 khi n = 100.

Hỏi: "Số lượt TB / cuộc" trong bảng A.6 nên tính thế nào với lượt khách viết sẵn?

---

## D. Tài liệu và gói dữ liệu

**D1. [Nhỏ] Thiếu `eval/validate_scenarios.py`**

`README.md` (dòng 22) và mục 10 của `DIEU-CHINH-DE.md` nói BTC dùng `eval/validate_scenarios.py` để kiểm tra tool tự viết cho cùng kết quả với `mock_tools.py`. File này không có trong gói team nhận.

Hỏi: BTC có phát file này không? Nếu không, team nên tự kiểm tra "cùng kết quả" trên những đầu vào nào?

**D2. [Nhỏ] Số chương trình khuyến mãi**

`README.md` ghi `catalog/promotions.json` có 14 chương trình. File hiện có 13 (3 đã hết hạn, 1 chưa bắt đầu, khớp phần còn lại của mô tả).

Hỏi: gói dữ liệu có thiếu một chương trình không?
