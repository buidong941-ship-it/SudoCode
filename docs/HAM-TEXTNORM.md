# Bảng tra hàm của `harness/textnorm.py`

[harness/textnorm.py](../harness/textnorm.py) là bước **Perceive**: chuẩn hóa lời khách tiếng Việt trước khi vào harness. Nó gồm bốn nhóm việc:

- **Teencode / viết tắt / không dấu** → câu chuẩn ("ko" → "không", "sp" → "sản phẩm").
- **ITN số tiền:** "năm triệu rưỡi" → 5.500.000, "5tr2" → 5.200.000, "690k" → 690.000, "4.890.000đ" → 4.890.000. SĐT đọc bằng chữ → chữ số.
- **Ngày giờ tương đối:** "thứ hai tuần sau", "mai", "chiều nay" → ngày cụ thể tính từ ngày cuộc gọi.
- **Che PII:** CCCD và số tài khoản bị che, giữ 4 số cuối, trước khi ghi log, ghi bộ nhớ hay gửi model ngoài.

Toàn bộ là code, vì Entity Accuracy chấm khớp tuyệt đối và che PII không được phép sót. Số dòng ứng với code ngày 17/10/2026.

**Ai dùng file này:** gần như mọi nơi. `harness/agent.py` (`perceive`, `find_money`, `fold`); `extractor.py`, `llm_extract.py` (`find_money`, `fold`, `parse_relative_datetime`); `guardrails.py` (`find_money`, `fold`, ba regex PII); `tools.py`, `rag.py`, `core/llm/router.py` (`fold`); `core/llm/summarizer.py` (`find_money`); `run_eval.py`, `datagen/export_transcripts.py`, `tests/` (`mask_pii`); `asr/itn.py` (`DIGIT`, `SCALE`, `words_to_int`, `_num_from_compact`).

## 1. Hằng số

| Tên | Ý nghĩa |
|---|---|
| `TEEN` [:24](../harness/textnorm.py#L24) | Cặp (regex, thay thế) cho teencode và chữ không dấu hay gặp ("k / ko / kg" → "không", "dc" → "được", "gia" → "giá", "dia chi" → "địa chỉ"…) |
| `DIGIT` [:42](../harness/textnorm.py#L42), `SCALE` [:44](../harness/textnorm.py#L44) | Chữ số tiếng Việt ("một / mốt", "năm / lăm / nhăm", "tư"…) và đơn vị ("mươi", "trăm", "nghìn / ngàn", "triệu", "tỷ") |
| `_NUM_WORD` [:45](../harness/textnorm.py#L45) | Regex một từ số bằng chữ |
| `MONEY_RX` [:97](../harness/textnorm.py#L97) | Số tiền viết bằng chữ số: "1.161k", "4.890.000đ", "5tr2", "5 triệu rưỡi", "690k", "1500000đ". "45 Trần…", "2024 trong…" không bị đọc là triệu |
| `MONEY_WORDS_RX` [:103](../harness/textnorm.py#L103) | Chuỗi từ số bằng chữ liên tiếp |
| `_DIG1` [:134](../harness/textnorm.py#L134) | Chữ số đọc từng chữ để ghép SĐT |
| `WEEKDAY` [:146](../harness/textnorm.py#L146) | "thứ hai / thứ 2" … "chủ nhật" → thứ trong tuần |
| `CCCD_RX` [:184](../harness/textnorm.py#L184), `BANK_RX` [:185](../harness/textnorm.py#L185), `PHONE_RX` [:186](../harness/textnorm.py#L186) | CCCD (12 số bắt đầu bằng 0), STK (9–14 số), SĐT (10 số bắt đầu bằng 0) |
| `ACCOUNT_CTX_RX` [:188](../harness/textnorm.py#L188) | Cụm đứng ngay trước một dãy số cho biết đó là STK ("số tài khoản", "STK", tên ngân hàng…) |

## 2. Hàm

### 2.1. So khớp và teencode

| Hàm | Chức năng | Đầu vào | Đầu ra |
|---|---|---|---|
| `strip_accents(s)` [:13](../harness/textnorm.py#L13) | Bỏ dấu tiếng Việt, "đ" → "d" | chuỗi | chuỗi |
| `fold(s)` [:18](../harness/textnorm.py#L18) | Dạng so khớp dùng khắp project: chữ thường, bỏ dấu, gộp khoảng trắng | chuỗi | chuỗi |
| `normalize_teencode(text)` [:34](../harness/textnorm.py#L34) | Áp lần lượt các cặp `TEEN` | câu | câu chuẩn |

### 2.2. Số tiền và SĐT

| Hàm | Chức năng | Đầu vào | Đầu ra |
|---|---|---|---|
| `words_to_int(words)` [:48](../harness/textnorm.py#L48) | Số bằng chữ → số nguyên, kể cả cách đọc tắt sau đơn vị lớn: "bốn triệu tám trăm chín mươi nghìn" → 4.890.000; "năm triệu rưỡi" → 5.500.000; "năm triệu hai" → 5.200.000 | chuỗi từ số | số nguyên |
| `_num_from_compact(s)` [:82](../harness/textnorm.py#L82) | Dạng viết gọn → số: "5tr2" → 5.200.000; "4tr890" → 4.890.000; "690k" → 690.000; "4.890.000đ" → 4.890.000 | chuỗi | số nguyên / `None` |
| `find_money(text)` [:106](../harness/textnorm.py#L106) | Tìm **mọi** số tiền trong câu, cả chữ số lẫn bằng chữ; bỏ giá trị dưới 1.000 (chữ số) hoặc dưới 10.000 (bằng chữ, phải có "triệu / nghìn / trăm / tỷ") | câu | list `(vị trí đầu, vị trí cuối, giá trị)`, sắp theo vị trí |
| `find_phone(text)` [:137](../harness/textnorm.py#L137) | SĐT 10 số bắt đầu bằng 0, viết liền hoặc cách bằng dấu cách / chấm / gạch, hoặc đọc từng chữ ("không chín tám…") | câu | chuỗi SĐT / `None` |

### 2.3. Ngày giờ

| Hàm | Chức năng | Đầu vào | Đầu ra |
|---|---|---|---|
| `parse_relative_datetime(text, today)` [:150](../harness/textnorm.py#L150) | Ngày: "ngày kia / ngày mốt" (+2), "mai" (+1), "hôm nay / chiều nay…", thứ trong tuần (lần tới; "tuần sau / tuần tới" sang tuần kế), "dd/mm". Giờ: "9 giờ / 9h / 9g30", buổi chiều / tối +12 giờ; không có giờ thì sáng 09:00, chiều 15:00, tối 19:00 | câu; ngày cuộc gọi `YYYY-MM-DD` | `(YYYY-MM-DD, HH:MM hoặc None)` / `None` |

### 2.4. PII và điểm vào

| Hàm | Chức năng | Đầu vào | Đầu ra |
|---|---|---|---|
| `_is_account(text, start)` [:192](../harness/textnorm.py#L192) | 40 ký tự trước dãy số có cụm chỉ tài khoản không | câu; vị trí bắt đầu dãy số | `True` / `False` |
| `mask_pii(text)` [:196](../harness/textnorm.py#L196) | Che CCCD và STK, giữ 4 số cuối. SĐT 10 số giữ nguyên vì nghiệp vụ cần, **trừ khi** đứng sau "số tài khoản / STK / ngân hàng" (STK 10 số bắt đầu bằng 0) | câu | câu đã che |
| `perceive(raw, today)` [:203](../harness/textnorm.py#L203) | Điểm vào của bước Perceive: chuẩn hóa teencode → che PII → rút số tiền, SĐT (trên câu đã che, để STK không bị nhận là SĐT), ngày giờ | câu thô; ngày cuộc gọi | `{raw, text, money, phone, when, pii_found}` |

## 3. Ghi chú khi đọc code

- **`perceive()["when"]` không được agent dùng.** Ngày hẹn gọi lại do `extractor.customer_slots_rules` tự gọi `parse_relative_datetime` (chỉ khi câu có "gọi lại / liên lạc / báo lại").
- **Đầu vào ASR đi qua `asr/itn.py` trước `perceive`** (`agent.turn`), vì Whisper viết số bằng chữ theo nhiều kiểu.
- **Dạng "1 triệu 590.000" của Whisper chưa xử lý** (mất phần triệu), là nguyên nhân chính làm sai số tiền khi đo ASR ([DATASET.md](DATASET.md) mục 5).
