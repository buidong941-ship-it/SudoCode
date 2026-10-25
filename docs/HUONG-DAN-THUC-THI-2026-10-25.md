# Hướng dẫn thực thi: cải tiến extractor và generator (25/10/2026)

Tài liệu này dành cho phiên Claude **phụ trách viết code**. Đề xuất do phiên "kỹ sư đề xuất" soạn ngày 25/10/2026 sau khi đọc code và tìm tài liệu. Làm theo thứ tự các giai đoạn. Mỗi nhiệm vụ có: mục tiêu, file cần sửa, các bước, tiêu chí đạt, cách kiểm.

---

## 0. Đọc trước khi làm

### 0.1 Bối cảnh
- Agent telesale tiếng Việt cho cuộc thi SUDO CODE 2026 vòng 1. Repo là `copy_project`, remote `SudoCode.git`, nhánh `main`.
- Cấu hình nộp hiện tại:
  - router Jev;
  - generator Qwen3-4B fp16 (vLLM trên Kaggle T4), `REPLY_STYLE=short`, `LLM_MAX_TOKENS=160`;
  - extractor `EXTRACTOR_BACKEND=hybrid` với `EXTRACTOR_ASYNC=1`. Mặc định trong code vẫn là `rules`.
- Chỉ số chấm bằng `eval/reference_eval.py`:
  - TSR, CCR, RQR, HR (giá và khuyến mãi, ngưỡng 5%);
  - TTFT p95 ≤ 3 s, total p95 ≤ 8 s.
  - BTC **chấm tay extractor**.
- Số mới nhất (`eval-b-hyb3`, xem `docs/NHAT-KY-2026-10-24.md` mục 5):

  | Chỉ số | sample | dev | test |
  |---|---|---|---|
  | TSR (%) | 85,7 | 100 | 95,5 |
  | CCR (%) | 76,2 | 83,2 | 73,7 |
  | RQR (%) | 0 | 0 | 0 |
  | HR giá (%) | 7,7 | 3,2 | 4,1 |

  - TTFT p95 khoảng 1,3 s; total p95 khoảng 3,9–4,2 s.
  - Sau các sửa ở mục 5.4 của nhật ký (chưa chạy lại trên Kaggle), HR ước lượng còn 7,7 / 1,1 / 0.
- Bộ đo riêng cho extractor: `tests/extract_eval/agent.jsonl` (120 câu) và `customer.jsonl` (60 câu). Lệnh chạy: `python scripts/extract_eval.py --modes rules llm hybrid`.

  | Đo trên Qwen3-4B (Kaggle) | rules P / R | llm P / R | hybrid P / R |
  |---|---|---|---|
  | Phát hiện câu hỏi | 100 / 60,0 | 100 / 53,3 | 100 / 60,0 |
  | Claim | 95,9 / 90,4 | 88,5 / 88,5 | 94,2 / 94,2 |
  | Slot khách | 97,2 / 87,5 | 71,1 / 67,5 | 75,5 / 92,5 |

### 0.2 Các file chính
| File | Vai trò |
|---|---|
| `harness/extractor.py` | Bộ luật: `customer_slots_rules`, `agent_questions`, `agent_claims`, `money_not_price`, `_about_focus`, `facts_used`. Cũng là lưới an toàn cho LLM |
| `harness/llm_extract.py` | LLM phân loại, code đọc giá trị: `CUSTOMER_SLOTS`, `NUMBER_ROLES`, `FACTS`, `_claim_ok`, `FIELD_CUE`, `FIELD_BLOCK`; đường bất đồng bộ `submit_/collect_customer_slots` |
| `core/llm/generator.py` | `SYSTEM` (14 quy tắc), `GOAL_NOTES`, `Generator.generate(plan, retry_note)`, `render_offline(plan)` (câu mẫu) |
| `harness/agent.py` | `turn()` (khoảng dòng 209–358): dựng plan, guardrail, sinh lại 1 lần, sau đó dùng câu mẫu. `_plan()` (khoảng dòng 420) quyết định goals và facts |
| `harness/guardrails.py` | `check()`: số tiền lạ, giá nội bộ, PII, nhận là người, chê đối thủ, `REQUIRED` (hiện chỉ có `no_info`, `is_bot`) |
| `core/llm/deepseek.py` | Client `LLM(provider)`: `chat()` (stream) và `json()` (ép schema, cache) |
| `scripts/serve_llm.sh` | Bật vLLM. Prefix caching và speculative n-gram **làm vLLM sập trên T4**, đang tắt |

### 0.3 Quy tắc bắt buộc
1. **Không sửa thư mục của BTC:** `eval/`, `catalog/`, `policy/`, `test_set/`, `schemas/`, `rag/`.
2. **Không "ăn gian" extractor.** Không được bỏ claim hay câu hỏi chỉ để làm đẹp RQR/HR. Claims và questions phải phản ánh đúng điều agent nói trong văn bản. Plan chỉ được dùng làm gợi ý, kết luận cuối cùng phải dựa trên chữ.
3. **Không lấy câu nào từ bộ test** (`datagen/out/test/` và trace test) để chỉnh luật, viết ví dụ cho prompt hay làm dữ liệu huấn luyện. Dùng dev, sample, catalog, chính sách, hoặc câu tự viết.
4. **Hỏi người dùng trước khi** chạy job Kaggle tốn trên 3 giờ GPU, đẩy job lên Kaggle, commit, push, hoặc có quyết định thuộc về người dùng.
5. **Phong cách code:**
   - giữ đúng thói quen của repo: không docstring cho hàm/lớp, gần như không có comment `#`;
   - lý do thiết kế ghi vào docs (nhật ký `docs/NHAT-KY-<ngày>.md`), không ghi trong code;
   - đặt tên và viết theo idiom giống code xung quanh;
   - viết tài liệu bằng tiếng Việt.
6. Đầu đọc tiếng Việt không dấu dùng `fold()` trong `harness/textnorm.py`. Mọi regex từ khóa viết ở dạng đã fold (không dấu).
7. Mỗi nhiệm vụ xong phải chạy `tests/smoke.sh` (trong `venv`) và `python scripts/extract_eval.py --modes rules`. Ghi kết quả trước và sau vào nhật ký. Lỗi thì báo đúng output, không giấu.
8. Kết thúc mỗi giai đoạn: viết `docs/NHAT-KY-<ngày>.md` theo mẫu của `NHAT-KY-2026-10-24.md` (việc đã làm, số liệu, việc chưa làm).

---

## Giai đoạn 1: không cần GPU, làm trước

### Nhiệm vụ 1 (A2): lớp lọc theo slot cho lời khách

**Mục tiêu:** precision slot khách ở chế độ hybrid từ 75,5 lên ≥ 93, giữ recall ≥ 90. Hiện LLM gán thừa `objection` (4 lỗi), `blocker` (3), `competitor_price_vnd` (2).

**Nền tảng:** Claimify (Microsoft, ACL 2025, https://www.microsoft.com/en-us/research/?p=1130106): chỉ trích khi chắc chắn cách hiểu câu, mơ hồ thì không trích.

**File:** `harness/llm_extract.py`.

**Các bước:**
1. Thêm `CUSTOMER_CUE` (regex ở dạng fold) và hàm `_customer_slot_ok(slot, value, text)`, viết giống `_claim_ok` / `FIELD_CUE`. Gợi ý:

   | Slot | Điều kiện |
   |---|---|
   | `objection` | `dat_qua`: có từ chê giá (`dat`, `mac`, `chenh`, `cao`, `chat`, `re hon`…). `ep_gia`: có từ đòi bớt (`bot`, `giam them`, `giam cho`, `ep`, `thap nhat`…). Câu hỏi giá thông thường ("giá bao nhiêu", "có giảm gì không") **không** tính |
   | `competitor_price_vnd` | có nơi bán khác (`ben kia`, `ben khac`, `shopee`, `lazada`, `tiki`, `facebook`, `cho khac`, `cua hang khac`, `tren mang`…) **và** `find_money(text)` không rỗng |
   | `blocker` | có động từ hỏi/bàn/cân nhắc (`hoi`, `ban voi`, `trao doi`, `can nhac`, `suy nghi`, `so sanh`, `tham khao`, `xem them`…) |
   | `has_children` | có `KIDS_RX` (lấy từ `extractor`) |
   | `budget_vnd` | có tiền và có ít nhất một từ (`ngan sach`, `tam`, `khoang`, `toi da`, `duoi`, `chi`, `du dinh`…) **hoặc** câu agent ngay trước (`context`) hỏi ngân sách |
   | Còn lại | qua luôn (giá trị đã do code đọc từ span) |

2. Trong `customer_slots()`, sau `_slot_value`, gọi `_customer_slot_ok`. Không qua thì `dropped += 1; continue`.
3. Đọc `customer.jsonl`, xem các lỗi FP mà `runs/extract_eval.json` liệt kê (chạy lại `extract_eval` với hybrid qua fake server nếu không có Qwen; nếu không có đường giả lập phù hợp thì kiểm bằng unit test với phản hồi LLM giả lập, như `tests/llm_extract_check.py`).
4. Thêm ca vào `tests/llm_extract_check.py`: LLM giả gán `objection` cho "giá bao nhiêu em" thì bị bỏ; gán `competitor_price_vnd` cho câu không có nơi bán khác thì bị bỏ; câu "bên Shopee bán 5.790.000đ" thì vẫn giữ.

**Tiêu chí đạt:** smoke OK. Số của luật trên `extract_eval` không đổi (luật không bị đụng). Ca giả lập chặn đúng. Số hybrid thật chỉ có sau lần chạy Kaggle kế tiếp (gộp ở Giai đoạn 3).

---

### Nhiệm vụ 2 (B3): planner chỉ định câu hỏi của lượt

**Mục tiêu:** tách "hỏi gì" (planner quyết) khỏi "nói thế nào" (generator). Giảm câu hỏi thừa, hỏi lại slot đã biết (SAMPLE-06) và câu hỏi ở goal kết thúc.

**File:** `harness/agent.py` (`_plan`, `turn`), `core/llm/generator.py`.

**Các bước:**
1. Viết bảng ánh xạ goal → slot câu hỏi (tên slot lấy đúng theo `QUESTION_SLOTS` / `SLOT_KW`):
   - `ask_address` → `address`
   - `ask_size_for_price`, `ask_new_size`, `ask_variant` → `size`
   - `ask_need` → slot đầu tiên trong `need_slots_missing`
   - `ask_product` → `product_advised`
   - `ask_identity` → `customer_name`
   - `confirm_order`, `confirm_new_price` → `confirm_order`
   - `confirm_old_address` → `address` (xác nhận)
   - `opening_returning` có `brief.blocker` → `blocker`
   - `exchange_offer` → `confirm_order`
   - `order_not_found` → `order_id`
   - `ask_repeat` → `other`
   - `cod_limit` → `payment`
   - `greet` → `other`

   Đọc kỹ `render_offline` và `_plan` để bảng đủ và đúng. Goal nào không có trong bảng thì không hỏi.
2. Trong `turn()`: `plan["question_slot"]` = slot của goal hỏi **cuối cùng** trong `goals` (tối đa 1), hoặc `None`.
3. `SYSTEM` thêm quy tắc: "`question_slot` = null thì KHÔNG đặt câu hỏi nào. Khác null thì đúng 1 câu hỏi, về đúng slot đó." Sửa quy tắc 3 cho khớp.
4. `GOAL_NOTES` của `closing`, `defer_ack`, `order_created`, `order_updated`, `address_updated`, `confirm_delivery_address` giữ ý "không hỏi".

**Tiêu chí đạt:** smoke OK. `render_offline` không đổi hành vi. Trong trace offline của `test_set/public_sample`, `question_slot` khớp với câu hỏi của câu mẫu.

---

### Nhiệm vụ 3 (B2): kiểm đủ nội dung cho mọi goal, sửa có mục tiêu

**Mục tiêu:** chặn bản nháp thiếu ý bắt buộc (lỗi của câu trả lời ngắn), hỏi sai slot, hỏi lại slot đã biết, hoặc hỏi khi không được hỏi. Sinh lại kèm thông báo lỗi cụ thể.

**Nền tảng:**
- Slot error rate: Dušek & Kasner 2020, https://arxiv.org/pdf/2011.10819
- VCP, kiểm từ khóa rồi sửa bằng prompt: https://arxiv.org/html/2306.15933v2

**File:** `harness/guardrails.py` (hoặc file mới `harness/coverage.py` nếu `guardrails.py` quá dài), `harness/agent.py`.

**Các bước:**
1. Hàm `coverage(text, plan, known)` trả danh sách lỗi (chuỗi tiếng Việt, dùng làm `retry_note`):
   - Nội dung bắt buộc theo goal (so bằng `find_money`, chuỗi mã đơn, ngày dạng d/m):

     | Goal | Phải có |
     |---|---|
     | `quote`, `recommend` | có `facts.quote.final_price_vnd` |
     | `order_created` | có `order_id`, `total_vnd`, ngày giao (nếu có `estimated_delivery`) |
     | `order_updated` | có `refund_vnd` hoặc `extra_payment_vnd` nếu khác 0 |
     | `cart_total` | có `cart.total_vnd` |
     | `callback_scheduled` | có giờ hẹn |
     | `order_status` | có trạng thái hoặc ngày giao của đơn |
     | `no_info`, `is_bot` | giữ như `REQUIRED` hiện tại |

   - Câu hỏi: chạy `extractor.agent_questions(text, known)`:
     - `question_slot is None` mà có câu hỏi → lỗi "không được hỏi";
     - có nhiều hơn 1 câu hỏi → lỗi;
     - hỏi **mở** (`type=open`) một slot đã có trong `KNOWN` → lỗi "không hỏi lại <slot>";
     - hỏi slot khác `question_slot` → chỉ ghi log, **không** chặn ở vòng đầu (bộ phát hiện slot còn yếu, tránh sinh lại thừa).
2. Trong `turn()`: gộp `coverage(...)` vào `problems` cùng `guardrails.check(...)`. Sinh lại 1 lần với `retry_note`. Vẫn sai thì:
   - lỗi về số tiền hoặc PII → dùng `render_offline` (giữ nguyên như cũ);
   - **chỉ** lỗi thiếu nội dung → dùng `render_offline` cho phần goal bị thiếu. Đơn giản nhất là dùng toàn câu mẫu. Ghi `guard["action"]="coverage_template"`.
3. Ghi `guard["coverage"]` vào trace để đếm tỷ lệ.
4. Unit test: bản nháp thiếu giá bị bắt; câu "Dạ em cảm ơn chị, chị cần gì thêm không ạ?" ở goal `closing` bị bắt; câu hỏi lại sản phẩm đã có trong `KNOWN` bị bắt; câu đúng thì không bị bắt.

**Tiêu chí đạt:** smoke OK. Trên trace cũ `runs/kaggle/eval-b-hyb3/`, script tạm (để trong scratchpad, không commit) chạy `coverage` lên `agent_text` để đếm số lượt sẽ bị chặn. Báo con số này cho người dùng **trước** khi chạy Kaggle (nếu trên 15% lượt bị chặn thì latency tăng đáng kể, cần nới bớt điều kiện).

---

### Nhiệm vụ 4 (B6 phần an toàn): gọn JSON plan
**Mục tiêu:** giảm token prefill để giảm TTFT, không đổi nội dung.

**File:** `core/llm/generator.py` (`Generator.generate`).

**Các bước:** trước khi `json.dumps`, đệ quy bỏ các khóa có giá trị `None`, `""`, `[]`, `{}`. Không bỏ `False` và `0` (vd `in_stock: false` mang thông tin). Dùng `separators=(",", ":")`. Đo số token trước và sau trên 7 kịch bản sample (in độ dài chuỗi, hoặc dùng tokenizer Qwen nếu có).

**Tiêu chí đạt:** smoke OK, plan giảm ≥ 10% ký tự, không mất khóa mà `GOAL_NOTES` nhắc tới.

---

## Giai đoạn 2: thay đổi lớn, kiểm tại máy trước

### Nhiệm vụ 5 (B1): sinh câu có placeholder, code điền giá trị

**Mục tiêu:** số tiền, mã đơn, ngày do code điền, nên HR và "số tiền lạ" về gần 0 ngay từ lúc sinh. Đầu ra ngắn hơn (`{GIA_BAN}` khoảng 3–4 token so với "4.490.000đ" khoảng 8–10 token).

**Nền tảng:**
- DIALIGHT https://arxiv.org/pdf/2401.02208
- AuGPT https://arxiv.org/pdf/2102.05126
- Slot-consistent NLG (ACL 2020) https://preview.aclanthology.org/moar-dois/2020.acl-main.10.pdf

**Bật/tắt bằng biến môi trường** `GEN_PLACEHOLDERS=1` (thêm vào `core/config.py`, mặc định `0`) để so A/B.

**Các bước:**
1. Hàm `build_slots(plan) -> dict[mã, chuỗi đã định dạng]` đọc từ `facts`:

   | Mã | Nguồn |
   |---|---|
   | `{GIA_BAN}` | `quote.final_price_vnd` |
   | `{GIA_NIEM_YET}` | `quote.list_price_vnd` (chỉ khi khác giá bán) |
   | `{GIA_DA_BAO}` | `brief.price_quoted_vnd`, giá cũ |
   | `{GIA_THAY_THE}` | `alternative.final_price_vnd` |
   | `{TONG_TIEN}` | `order.total_vnd` / `cart.total_vnd` |
   | `{MA_DON}` | `order.order_id` |
   | `{NGAY_GIAO}` | ngày d/m |
   | `{TIEN_HOAN}`, `{TIEN_BU}` | `update.refund_vnd`, `update.extra_payment_vnd` |
   | `{GIO_HEN}` | giờ hẹn gọi lại |
   | `{NGAY_CO_HANG}` | `restock_expected` |
   | `{TEN_SP}` | tên sản phẩm (tùy chọn, tên dài thì có lợi) |

   Tiền định dạng bằng `_vnd`, ngày bằng `_dm`. Chỉ đưa vào bảng các mã có giá trị.
2. Đưa vào prompt một mục `PLACEHOLDERS: {mã: mô tả ngắn}`, **không đưa giá trị** để model không chép số. Ở chế độ này, xóa các trường số tương ứng khỏi `facts` gửi cho LLM, hoặc thay bằng mã. Quy tắc mới trong `SYSTEM`: "Khi nói giá, mã đơn, ngày… chỉ viết đúng mã trong PLACEHOLDERS, không viết con số". Quy tắc 14 sửa cho khớp.
3. Điền khi stream: `LLM.chat()` hiện trả cả chuỗi sau khi stream xong (TTFT đo ở token đầu). Điền sau khi nhận đủ là được. Nếu sau này có stream ra ngoài thì đệm từ `{` đến `}`.
4. Kiểm: mã ngoài bảng, hoặc còn số tiền viết tay trong câu → coi là lỗi, sinh lại với `retry_note`. `MASK_TOKEN_RX` / `TOKEN_RX` giữ nguyên.
5. Sau khi điền, mọi thứ chạy như cũ: guardrail `check` (vẫn chạy để chắc chắn), `coverage`, extractor.
6. Giữ ngữ cảnh "giá cũ": `{GIA_DA_BAO}` chỉ được dùng kèm "hôm trước / đã hết hạn". `stale` trong guardrail vẫn bắt lỗi sau khi điền.
7. Khi dùng DeepSeek (API ngoài), `Redactor` vẫn chạy như cũ. Mã placeholder không được trùng dạng `[SĐT_1]`, nên dùng ngoặc nhọn `{}`.

**Tiêu chí đạt:** smoke OK ở cả `GEN_PLACEHOLDERS=0` và `1`. Đường offline không đổi. Unit test: bản nháp "Dạ giá {GIA_BAN} ạ" được điền đúng; "{GIA_XYZ}" và "giá 1.234.000đ" viết tay bị chặn.

**Rủi ro cần báo người dùng:** Qwen3-4B có thể viết mã sai cú pháp. Nên đo tỷ lệ sinh lại trên dev bằng một lần chạy Kaggle (Giai đoạn 3).

---

### Nhiệm vụ 6 (A1): bộ phân loại câu hỏi/yêu cầu nhỏ học từ luật

**Mục tiêu:** recall phát hiện câu hỏi từ 60% lên ≥ 85%, precision ≥ 95%, chạy trên CPU vài ms mỗi câu.

**Nền tảng:**
- Snorkel / data programming https://arxiv.org/pdf/1711.10160: luật là labeling function, gộp phiếu thành nhãn xác suất, rồi huấn luyện bộ phân loại.
- Encoder: PhoBERT-base (`vinai/phobert-base-v2`, cần tách từ) hoặc `microsoft/mdeberta-v3-base`.

**Các bước:**
1. **Dữ liệu chưa gán nhãn:** gom `agent_text` từ trace dev và sample trong `runs/` (mọi lần chạy, khử trùng), tách câu bằng `_sentences`. **Loại mọi câu thuộc kịch bản test** (đối chiếu tên kịch bản với `datagen/out/test/` và `test_set/`).
2. **Labeling function** (mỗi hàm trả nhãn hoặc bỏ phiếu trắng): dấu `?`, `REQUEST_RX`, `MAYBE_ASK_RX`, `QUESTION_TAIL_RX` có loại trừ "không… đâu", `CONFIRM_RX`, từng mục `SLOT_KW`, nhãn Qwen (từ `llm_extract.agent`, nếu có trace `extractor`), nhãn DeepSeek (chỉ khi người dùng cho phép gọi API; nhớ che PII bằng `Redactor`).
3. **Gộp phiếu:** dùng `snorkel` (`LabelModel`) nếu cài được. Không thì bỏ phiếu theo trọng số, với trọng số ước lượng trên `agent.jsonl`.
4. **Nhãn:** hai đầu ra.
   - (a) `is_question`: không hỏi / hỏi mở / hỏi xác nhận.
   - (b) `slot` thuộc `QUESTION_SLOTS`.

   Có thể bắt đầu bằng (a) và để luật/`SLOT_KW` lo (b).
5. **Huấn luyện:** fine-tune trên CPU hoặc Kaggle (vài phút, **hỏi trước khi đẩy job**). Lưu model ở `models/question_clf/`, và thêm thư mục này vào `.gitignore` nếu nặng.
6. **Tích hợp:** `agent_questions()` thêm nhánh `QUESTION_CLF=1`: câu được bộ phân loại cho là câu hỏi với p ≥ τ thì vào danh sách; slot lấy theo `SLOT_KW` như cũ, hoặc lấy đầu (b). Luật `?` vẫn luôn bắt (hợp). τ chọn trên một nửa `agent.jsonl`, báo số trên nửa còn lại.
7. **Gán tay thêm:** cần khoảng 200 câu có nhãn để đo tin cậy. Lấy thêm từ câu dev và **nhờ người dùng kiểm** nhãn (`agent.jsonl` hiện do Claude gán, chưa người kiểm).

**Tiêu chí đạt:** trên nửa giữ lại, recall ≥ 85% và precision ≥ 95%. Latency CPU p95 < 20 ms mỗi lượt. Smoke OK khi không có model (tự tắt, dùng luật).

---

### Nhiệm vụ 7 (A6): gắn claim với sản phẩm
**Mục tiêu:** bớt claim bảo hành, đổi trả hoặc giá của **sản phẩm khác** bị gán cho sản phẩm đang tư vấn (GEN-T26-01).

**File:** `harness/extractor.py`.

**Các bước:**
1. Hàm `claim_sku(sentence, focus_sku)` theo thứ tự:
   - sản phẩm có tên trong câu (`find_products`);
   - câu có "sản phẩm / mặt hàng / ngành hàng / loại / mẫu / hãng khác" → `None` (không về sản phẩm đang tư vấn);
   - còn lại → `focus_sku`.
2. Gom logic `_about_focus` vào hàm này. Giữ `_about_focus` gọi qua hàm mới để `llm_extract._claim_ok` không phải đổi.
3. Ghi thêm khóa `sku` vào claim khi xác định được (schema cho phép khóa thêm; **kiểm lại** `schemas/trace_log.schema.json` và `eval/reference_eval.py` có chấp nhận khóa lạ không, nếu không chấp nhận thì không ghi).

**Tiêu chí đạt:** `extract_eval` rules không giảm. Câu GEN-T26-01 (viết lại dạng tương tự, không chép câu test) không sinh claim `warranty_months`.

---

## Giai đoạn 3: tinh chỉnh LLM rồi chạy lại trên Kaggle

### Nhiệm vụ 8 (A4): định nghĩa slot kèm phản ví dụ
**Nền tảng:** FnCTOD (ACL 2024) https://aclanthology.org/2024.acl-long.471: schema được viết như mô tả hàm.

**File:** `harness/llm_extract.py`.

**Các bước:**
- Mỗi mục `CUSTOMER_SLOTS`, `NUMBER_ROLES`, `FACTS` thêm vế "KHÔNG phải khi …". Ví dụ:
  - `objection`: "KHÔNG phải khi khách chỉ hỏi giá hay hỏi có khuyến mãi không";
  - `blocker`: "KHÔNG phải khi khách chỉ nói 'để chị xem'… mà không nêu lý do". Cân nhắc kỹ, vì luật hiện vẫn coi "xem thêm" là `can nhac`;
  - `nhan_la_nguoi_that`: "KHÔNG gán cho câu báo giá, chào, xác nhận đơn".
- Thêm 2–3 ví dụ đối chứng ngắn mỗi prompt, **tự viết từ catalog/chính sách**, không lấy từ dev/test.
- Prompt dài thêm vừa phải. Phía khách chạy bất đồng bộ nên không ảnh hưởng TTFT; phía agent chạy sau khi đã sinh câu nên không ảnh hưởng total.

### Nhiệm vụ 9 (A3): lọc theo độ tự tin cho field hiếm
**Lưu ý từ tài liệu:** Beyond Logprobs (2026) https://arxiv.org/pdf/2606.24420: self-consistency tăng AUC nhưng ít cải thiện việc định tuyến, và điểm tự tin hay dồn sát 1. Chỉ áp cho vài field.

**Các bước:**
1. `LLM.json()` thêm tùy chọn `logprobs=True, top_logprobs=5` (vLLM OpenAI API). Lấy xác suất token đầu của giá trị nhãn trong JSON. Cần dò vị trí token, nên tách thành hàm riêng, có unit test.
2. Áp ngưỡng τ theo field cho `is_human`, `promo_active` (phía agent) và `objection`, `blocker`, `competitor_price_vnd` (phía khách). τ chọn trên `extract_eval`.
3. Không lấy được logprob (DeepSeek, cache cũ) thì bỏ qua lớp lọc này, không lỗi.
4. Cache (`core/llm/cache.py`): key phải gồm cả `logprobs` để không trả nhầm bản cũ.

### Nhiệm vụ 10 (B4): sinh 2 bản song song thay cho sinh lại tuần tự
**Bật/tắt:** `GEN_PARALLEL_N=2` (mặc định 1).

**Các bước:**
1. `LLM.chat()` hỗ trợ `n>1` khi stream. vLLM trả các `choice.index` khác nhau, cần gom theo index. TTFT = token đầu của bất kỳ bản nào.
2. Cách đơn giản hơn: gửi 2 request song song bằng thread, một bản nhiệt độ 0 và một bản 0,7.
3. Chọn bản **đầu tiên theo thứ tự ưu tiên** (bản nhiệt độ 0 trước) qua được `check` và `coverage`. Không bản nào qua thì đi đường sinh lại như cũ.
4. Đo trên Kaggle: TTFT p95, total p95, tỷ lệ `regenerated`, tỷ lệ `safe_template`.

### Nhiệm vụ 11: chạy lại `eval-b` trên Kaggle
- Gộp: các sửa mục 5.4 của nhật ký 24/10 (chưa chạy lại) + Nhiệm vụ 1–5, 7, 8 (+ 9, 10 nếu xong).
- Biến thể đề xuất (mỗi biến thể khoảng 2,6–2,7 giờ):
  1. `hyb4`: mọi thay đổi, `GEN_PLACEHOLDERS=0`;
  2. `hyb4-ph`: như trên, `GEN_PLACEHOLDERS=1`.
- **Hỏi người dùng trước khi đẩy.** Token và tài khoản Kaggle xem `docs/CHAY-KAGGLE-SERVER.md`. Không tự đổi tài khoản.
- `SUITE_EXTRACT_EVAL=1` để có số extractor thật với Qwen.
- Kết quả kéo về `runs/kaggle/eval-b-hyb4*/`. So với `fix-rules`, `hyb2`, `hyb3` trong bảng nhật ký, đủ các chỉ số: TSR, CCR, RQR, HR, TTFT p95, total p95, vi phạm, tỷ lệ sinh lại / câu mẫu.

---

## Giai đoạn 4: hướng nặng (cần người dùng duyệt GPU)

### Nhiệm vụ 12 (A5): chưng cất bộ trích sang model nhỏ
**Nền tảng:**
- LDST (EMNLP 2023) https://arxiv.org/pdf/2310.14970: LoRA khoảng 0,12% tham số, ngang ChatGPT về theo dõi trạng thái hội thoại.
- NuExtract https://numind.ai/blog/nuextract-a-foundation-model-for-structured-extraction: model trích chuyên dụng nhỏ.

**Các bước:**
1. Sinh câu khách và câu agent từ `datagen/` (dev) cộng câu tổng hợp mới dựa trên catalog. **Không dùng test.**
2. DeepSeek làm thầy, gán nhãn theo đúng schema của `llm_extract` (che PII).
3. Chỉ giữ mẫu mà thầy qua được `_claim_ok` / `_customer_slot_ok` và không mâu thuẫn với luật ở field luật chắc chắn (tiền, ngày).
4. LoRA cho Qwen3-1.7B, hoặc Qwen3-4B phục vụ bằng `--enable-lora` trên cùng vLLM (kiểm vLLM 0.9.2 trên T4 có chạy LoRA không).
5. Model đủ nhanh (p95 dưới khoảng 300 ms) thì cân nhắc trích lời khách **đồng bộ** để slot vào plan ngay trong lượt (CCR).

### Nhiệm vụ 13 (B5): chưng cất phong cách cho generator (ReST)
**Nền tảng:** ReST (DeepMind 2023) https://arxiv.org/abs/2308.08998v1: lấy mẫu, lọc bằng hàm thưởng, rồi SFT.

**Các bước:**
1. Plan lấy từ trace dev và sample, cộng plan tổng hợp.
2. DeepSeek và Qwen sinh nhiều bản cho mỗi plan.
3. Lọc bằng `guardrails.check` + `coverage` + độ dài (≤ 2 câu, mỗi câu < 25 từ) + mở bằng "Dạ" và có "ạ".
4. LoRA SFT Qwen3-4B. Sau đó thử rút gọn `SYSTEM` / `GOAL_NOTES` và đo lại TTFT cùng chất lượng.

### Nhiệm vụ 14 (B6 phần rủi ro): EAGLE-3
- Draft `AngelSlim/Qwen3-4B_eagle3` (https://nvidia.github.io/TensorRT-Edge-LLM/0.9.1/user_guide/examples/speculative-decoding.html). Baseten báo tăng tốc 1,5–2,5 lần trên Qwen3-4B (https://www.baseten.co/blog/how-to-train-custom-eagle-3-heads-for-speculative-decoding/).
- n-gram và prefix caching đã làm vLLM 0.9.2 sập trên T4 (engine V0), nên khả năng cao EAGLE cũng sập. Chỉ thử trong một job riêng ngắn. Không đưa vào cấu hình nộp nếu chưa chạy ổn định đủ 3 bộ.

---

## Ngoài phạm vi / không làm
- GLiNER (https://alphaxiv.org/abs/2311.08526): chưa có bằng chứng hỗ trợ tốt tiếng Việt. Không làm, trừ khi người dùng yêu cầu.
- MiniCheck (https://arxiv.org/pdf/2404.10774): chỉ để tham khảo cho guardrail kiểm câu không có số. Chưa cần, vì guardrail số tiền và `coverage` đã che phần lớn.
- Không đổi router (Jev giữ mặc định; Laya đã bị loại ngày 23/10).

## Thứ tự và ước lượng
| Thứ tự | Nhiệm vụ | Công | GPU |
|---|---|---|---|
| 1 | 1 (A2) lớp lọc slot khách | ½ ngày | không |
| 2 | 2 + 3 (B3 + B2) chỉ định câu hỏi, kiểm đủ nội dung | 1 ngày | không |
| 3 | 4 gọn JSON plan | 1–2 giờ | không |
| 4 | 5 (B1) placeholder | 1–1,5 ngày | không (kiểm thật ở 11) |
| 5 | 7 (A6) claim theo sản phẩm | ½ ngày | không |
| 6 | 6 (A1) bộ phân loại câu hỏi | 1–2 ngày + người dùng kiểm nhãn | vài phút (hỏi trước) |
| 7 | 8, 9, 10 | mỗi việc ½ ngày | không (kiểm thật ở 11) |
| 8 | 11 chạy lại Kaggle | khoảng 2,7 giờ mỗi biến thể | **hỏi trước** |
| 9 | 12, 13, 14 | nhiều ngày | **trên 3 giờ, hỏi trước** |

Sau mỗi nhiệm vụ: chạy smoke và `extract_eval`, ghi nhật ký, rồi báo người dùng ngắn gọn (đã làm gì, số trước/sau, việc tiếp theo). Không commit hay push khi người dùng chưa bảo.
