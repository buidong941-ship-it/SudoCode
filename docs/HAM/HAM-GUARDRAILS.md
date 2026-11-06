# Bảng tra hàm của `harness/guardrails.py`

[harness/guardrails.py](../harness/guardrails.py) kiểm câu trả lời của agent **trước khi gửi khách**. Đây là lớp code kiểm tra LLM, nên không dùng LLM. Có vi phạm thì `agent.turn()` sinh lại một lần; vẫn vi phạm thì thay bằng câu mẫu của goal.

Năm loại kiểm tra:
1. **Số tiền lạ:** mọi số tiền trong câu phải nằm trong tập "được phép" do `agent.turn()` dựng (kết quả tool, báo giá đã lưu, số khách vừa nói, số trong FACTS).
2. **Lộ thông tin nội bộ:** giá nhập trong tài liệu `NOI-BO`, giá sàn (`_internal_*`) của tool, cụm "giá nhập / giá vốn / nhà cung cấp là…".
3. **PII:** CCCD hoặc số tài khoản nguyên văn.
4. **Nhận là người thật.**
5. **Chê đối thủ.**

Số dòng ứng với code ngày 17/10/2026.

**Ai dùng file này:** chỉ `harness/agent.py` (`collect_numbers`, `check` trong `turn()`).

## 1. Hằng số

| Tên | Ý nghĩa |
|---|---|
| `IMPORT_PRICES` [:27](../harness/guardrails.py#L27) | Tập giá nhập đọc từ bảng trong `policy/ghi-chu-nhap-hang-NOI-BO.md` lúc nạp module |
| `HUMAN_RX` [:28](../harness/guardrails.py#L28) | "em / mình / tôi là (cũng là) người thật / nhân viên thật / người" (trừ "người máy"). Rộng hơn `extractor.HUMAN_CLAIM_RX` để chặn chắc ở đầu ra |
| `COMPETITOR_RX` [:29](../harness/guardrails.py#L29) | "bên kia / shop kia … hàng giả / hàng nhái / kém chất lượng / lừa đảo / không uy tín" |

## 2. Hàm

| Hàm | Chức năng | Đầu vào | Đầu ra | Gọi tới |
|---|---|---|---|---|
| `_import_prices()` [:17](../harness/guardrails.py#L17) | Đọc các dòng `| SKU-… | giá |` trong tài liệu nội bộ; không đọc được file thì trả tập rỗng | không | set số nguyên | `settings.btc_dir` |
| `collect_numbers(obj, out)` [:32](../harness/guardrails.py#L32) | Gom mọi số ≥ 1.000 trong một cấu trúc lồng (kết quả tool, FACTS), bỏ khóa bắt đầu bằng `_` (trường nội bộ). Đây là phần chính của tập số tiền được phép nói | dict / list / số; `out` (set tích lũy, tùy chọn) | set số nguyên | gọi đệ quy chính nó |
| `check(text, allowed_money, internal_numbers, forbidden_money)` [:47](../harness/guardrails.py#L47) | Kiểm một câu trả lời. Với mỗi số tiền trong câu: là giá nhập / giá nội bộ → "lộ giá nội bộ"; nằm trong `forbidden_money` (giá khách nêu không khớp báo giá hiện tại) → "đọc lại giá … khách nêu"; không có trong `allowed_money` → "số tiền … không có trong dữ liệu tool". Sau đó kiểm CCCD (12 số bắt đầu bằng 0) hoặc dãy 9–14 số không phải SĐT 10 số; `HUMAN_RX`; `COMPETITOR_RX`; cụm nhắc thông tin nội bộ | câu trả lời; tập số được phép; tập số nội bộ; tập số cấm | list lý do vi phạm (rỗng = đạt) | `find_money`, `fold`, `CCCD_RX`, `BANK_RX`, `PHONE_RX` (từ `textnorm`) |

## 3. Ghi chú khi đọc code

- **Chỉ kiểm cái không được nói, chưa kiểm cái bắt buộc phải nói.** Câu thiếu "em chưa có thông tin" hay thiếu "hàng chính hãng" vẫn qua guardrail, dù script BTC chấm `agent_must_say` / `must_say_any` ([SO-SANH-2026-10-15.md](SO-SANH-2026-10-15.md) mục 7.1).
- **Tập số được phép gồm cả báo giá phiên trước,** nên giá KM cũ đọc thành giá hiện tại không bị chặn (SAMPLE-05). Chặn riêng chỉ có ở `forbidden_money`, và tập này chỉ chứa giá **khách nêu**.
- **"Vi phạm guardrail" trong report của BTC là chỉ số khác** (PII trong `agent_text` và `memory_writes`, chuyển máy thừa, claim `is_human`, `trace_must_not_match`), do `eval/reference_eval.py` tính, không phải file này.
