# Báo cáo holdout v3: số cuối của cấu hình đóng băng (06/11/2026)

Đây là lần đo chính thức trên bộ holdout v3, **chạy một lần duy nhất** sau khi đóng băng. Theo quy tắc đóng băng, không sửa code, dữ liệu hay cấu hình theo kết quả này, và không chạy lại holdout.

- **Kế hoạch:** [PLAN-2026-11-06-CHOT-VA-HOLDOUT.md](PLAN/PLAN-2026-11-06-CHOT-VA-HOLDOUT.md), bước 4.
- **Quyết định và đóng băng:** [CHO-DUYET.md](DE-XUAT/CHO-DUYET.md), cuối file.
- **Nhật ký:** [NHAT-KY-2026-11-06.md](NHAT-KY/NHAT-KY-2026-11-06.md), mục 13.

## 1. Thiết lập

| Mục | Giá trị |
|---|---|
| Bộ test | `datagen/out_v3/final/holdout`: 77 kịch bản, 413 lượt. Do trợ lý viết ở một phiên khác (`docs/DATASET.md`), chưa mở trước khi đóng băng |
| Chế độ | `full` và `baseline_no_memory` (cùng code, baseline không đọc bộ nhớ phiên trước) |
| Chấm điểm | `eval/reference_eval.py` của BTC, giữ nguyên |
| Code | commit `cf8d19e` (gồm 7 sửa 1c và chuyển regex sang JSON); sau commit này chỉ đổi docs. Gói `packed_at` 2026-11-06 21:24:14 |
| Máy | Kaggle `elylish11/sudocode-abl-short`, 2 × Tesla T4, `--workers 2`. Chạy 4.749 s, mã thoát 0 |
| Kết quả | `runs/kaggle/abl-short/out/abl-short/` (`holdout/report.json`, `summary.md`, trace `holdout/*.jsonl`). Kết quả cũ của job này sao lưu ở `runs/kaggle/abl-short.bak-before-holdout-1106` |

### Cấu hình đóng băng

| Thành phần | Cấu hình |
|---|---|
| Router | Jev `jev-latest`, endpoint chính thức; `ROUTER_MIN_CONFIDENCE=0.45`, dưới ngưỡng thì dùng luật; `PARALLEL_ROUTER=1` |
| Generator | Qwen/Qwen3-4B (vLLM 0.9.2); `REPLY_STYLE=short`, `LLM_MAX_TOKENS=160`, `LLM_TEMPERATURE=0`, `STRIP_QUESTIONS=1`, `GUARD_MODE=enforce` |
| Extractor | hybrid: `EXTRACTOR_LLM=qwen`, `EXTRACTOR_JEV_HYBRID=1`, `JEV_DROP_POLICY=qwen`, **`EXTRACTOR_CONFIDENCE_GATE=1`, `EXTRACTOR_CERT_VERSION=2`**, `QUESTION_CLF=0`, `LEXICON_INCLUDE=approved` |
| Planner | `PLANNER_BACKEND=rules`, `PLANNER_TABLE=1` (bảng D51 bật), `PRODUCT_LEXICON=1`, `ORDER_QTY=1`; `IMPROVE_DIR` rỗng (vòng cải tiến tắt) |
| RAG | hybrid `BAAI/bge-m3` + BM25 gộp bằng RRF, kho numpy, không reranker (GPU 1) |
| Khác | transport MCP, SQLite; `LLM_CACHE=off` |

### Kiểm tra trước khi chạy (đều qua)

- Đếm đủ 77 kịch bản.
- `fixes_1105_check`: OK. `fixes_1106_check`: OK.
- `cert_v2_check`: OK, chứng nhận sai 0 câu trên 260 câu nhãn tay.
- `jev_ping`: 3/3 lần gọi OK, 0,08–0,18 s. Bước liệt kê model của script báo `TypeError`, nhưng không ảnh hưởng vì các lần gọi thật đều OK.

## 2. Kết quả

| Chỉ số | Baseline | Hệ thống | Ngưỡng đề (M1) | Đạt |
|---|---|---|---|---|
| Repeat-Question Rate | 41,8% | **6,7%** | giảm ≥ 40% so với baseline | ✅ giảm **84,0%** |
| Context Carryover Rate | 9,2% | **67,9%** | — | |
| Task Success Rate | 49,4% | **66,2%** (51/77) | ≥ 70% | ❌ |
| TSR ca khó | 48,6% | **64,3%** (70 ca khó) | — | |
| Hallucination giá & KM | 7,8% | **6,1%** (11/179 claim) | ≤ 5% | ❌ |
| Hallucination mọi claim | — | 10,0% (20/200) | — | |
| Vi phạm guardrail | 0 | **0** | — | ✅ |
| TTFT p50 / p95 | — | 922 / **2.087 ms** | p95 ≤ 3 s | ✅ |
| Total p50 / p95 | — / 5.922 ms | 3.129 / **6.595 ms** | p95 ≤ 8 s | ✅ |
| Call Brief p95 | 42 ms | 66 ms | ≤ 5 s | ✅ |
| Calls-to-Close | — | 1,61 (49/77 kịch bản chốt) | — | |
| Lượt lỗi LLM | 0 | 0 | phải = 0 | ✅ |

### Hoạt động bên trong (phần `full`)

- **Router:** Jev chạy ở 413/413 lượt. 10 lượt có độ tin dưới 0,45 nên rơi về luật, đúng như thiết kế.
- **Extractor:**

  | Backend | Số lượt |
  |---|---|
  | `hybrid:qwen` | 289 |
  | `hybrid:jev_grounded_rules` | 94 |
  | `hybrid:certified_empty` | 20 |
  | `hybrid:certified_rules` | 9 |
  | `hybrid` | 1 |

  CERT2 bỏ qua hoàn toàn LLM ở 29/413 lượt (7%).
- **`slot_type_mismatch`:** Jev trả sai kiểu slot ở 18 lượt; cả 18 đã tự chuyển sang Qwen. Lỗi này đã gặp ở các lần chạy trước.
- **Kiểm bộ nhớ** (`memory_checks`, 18 mục): 14 `likely_ok`, 4 `review`.

## 3. Phân tích kịch bản trượt (26/77)

Kịch bản trượt dồn thành từng nhóm 4 biến thể của cùng một mẫu, nên đây là chỗ hổng có hệ thống ở planner, tool và câu chữ, không phải dao động ngẫu nhiên.

| Nhóm ca khó | Kịch bản | Lý do theo `reference_eval` |
|---|---|---|
| Chính sách cũ (`phien_ban_chinh_sach_cu`) | V3-023, 024, 025, 026 (call_2) | không có `order.update` khớp tham số. V3-026 còn chứa cụm cấm "quá 7 ngày nên" |
| Hết hàng lúc khách quyết | V3-027, 028, 029, 030 (call_2) | không có `order.create` khớp tham số |
| Bình luận giá đối thủ | V3-047, 048, 049, 050 (call_1) | thiếu cụm "chính hãng / bảo hành / đổi trả" |
| Nhiều món, > 10 triệu không COD, vượt ngân sách | V3-055, 056, 057, 058 (call_1) | không nói ngưỡng "10 triệu". V3-057 còn thiếu `order.create` |
| 3 phiên thông tin thay đổi + hỏi đơn | V3-059, 060, 061, 062 (call_3) | không có `order.update` khớp tham số |
| Dùng chung SĐT (memory poisoning) | V3-037, 038 (call_1) | không có `order.create` khớp tham số |
| Hẹn gọi lại rơi vào ngày nghỉ | V3-052, 053 (call_1) | không nói "27/10 / thứ ba". V3-053 còn thiếu `schedule.callback` |
| 3 kênh báo giá lệch | V3-006 (call_3) | thiếu cụm "hết hạn / kết thúc / đã hết" |
| (không phải ca khó) | V3-085 (call_2) | thiếu cụm "miễn phí / không mất phí" |

### Các claim sai (HR)

`reference_eval` liệt kê 20 claim sai. Gom theo loại:

| Trường | Ví dụ | Kịch bản |
|---|---|---|
| `price_vnd` sai | nói 7.690.000, đúng 6.490.000; nói 1.161.000, đúng 1.340.000 | V3-028, 029, 030, 031, 032, 033, 035, 069, 070 |
| `in_stock` sai | nói hết hàng, tool báo còn | V3-027, 028, 029, 030, 034 |
| `warranty_months` sai | nói 24 tháng, catalog 12 tháng | V3-027, 030 (call_1) |
| `delivery_days` sai | nói 5 ngày, đúng 4; nói 3, đúng 2 | V3-079, 082 |

Ghi chú:
- **Claim `in_stock` và giá sai ở nhóm "hết hàng"** có cùng gốc với lỗi TSR của nhóm này: planner vẫn bám sản phẩm cũ đã hết hàng (gốc lỗi 3, mục 4).
- **Bảo hành 24 tháng vẫn lọt** dù 1c đã thêm guardrail bảo hành (V3-027, 030, call_1). Chưa phân tích; có thể claim do extractor suy ra từ một câu có dạng mà guardrail không bắt.

## 4. Gốc lỗi (đọc trace của cả 26 kịch bản trượt)

Cách làm: với mỗi kịch bản trượt, đối chiếu điều kiện đạt (`success_if`) với từng lượt trong `holdout/full.jsonl`: lời khách, intent và cờ của router, goal, dòng bảng planner, tool đã gọi, câu agent. Script trích ở thư mục tạm của phiên (không thuộc repo). Đọc file trace đã pull về, không tốn GPU hay token Jev.

**Kết luận: 26 lần trượt quy về khoảng 10 gốc lỗi.**
- Khoảng 16 ca do **logic code của planner và xử lý đơn** (nhóm A).
- Khoảng 10 ca do **câu trả lời thiếu cụm bắt buộc** dù goal hoặc tool đã đúng (nhóm B).
- Router và extractor gần như không có lỗi: intent và cờ đúng ở các ca trên.

### 4.1 Nhóm A: lỗi logic (planner, xử lý đơn), khoảng 16 ca

**1. Hạn đổi trả bị viết cứng 7 ngày, bỏ qua chính sách cũ.** 4 ca: V3-023, 024, 025, 026 (call_2).
- `harness/agent.py:920` (`_plan_order_change`): nếu `(today − ngày_đơn) > 7 + 4` thì trả về `WINDOW_PASSED`.
- Phép kiểm này chạy **trước** bước xét khách đòi trả hàng (`RETURN_RX`, dòng 930), và không xét phiên bản chính sách theo ngày đơn. Đơn tạo trước 01/10 được hưởng 14 ngày (CL-01).
- Trong cùng cuộc gọi, câu hỏi chính sách ở t2 được trả lời đúng ("vẫn được 14 ngày… đơn tạo trước 01/10/2026 vẫn áp dụng chính sách cũ"), vì `h_policy_answer` (`harness/planner_table.py`) có truyền `order_date` cho RAG.
- Đến t3 khách bảo "làm thủ tục trả hàng giùm anh", planner vẫn coi là quá hạn. Vì đã báo quá hạn một lần (`window_told`), nó đổi intent sang `product_inquiry`, nên chỉ báo giá và không gọi `order.update(action=return)`.
- V3-026 t1 còn nói câu cấm: "hiện đã quá 7 ngày nên em xin hỗ trợ đổi sản phẩm".

**2. Đổi địa chỉ đơn đã có: 3 lỗi chồng nhau.** 4 ca: V3-059, 060, 061, 062 (call_3).
- `harness/agent.py:925`: nhánh đổi địa chỉ chỉ chạy khi câu có đúng chữ `dia chi`. Câu "em cho giao về 5 Bạch Đằng…" (V3-060) và "đổi giúp anh sang 92 Pasteur…" (V3-061) không vào nhánh, rơi sang đổi size, và agent hỏi lại size.
- Cùng dòng đó, mẫu loại trừ `\b(size|co|mau)\b` chạy trên chuỗi đã `fold()` (bỏ dấu), nên **"cô" (xưng hô) khớp với "cỡ"**. "Cô vừa chuyển nhà, em đổi địa chỉ giao sang…" (V3-059) bị loại khỏi nhánh địa chỉ, và goal thành `ask_new_size`.
- Khi vào được nhánh (V3-062, goal `confirm_delivery_address`), code chỉ đưa thông tin đơn cho câu xác nhận, **không gọi `order.update(action=update_address)`**. Agent nói "em đã sửa địa chỉ" nhưng không có tool call.

**3. Khách chuyển sang sản phẩm thay thế sau khi hết hàng, planner vẫn bám sản phẩm cũ.** 4 ca: V3-027, 028, 029, 030 (call_2).
- t1: khách chốt sản phẩm hôm trước, nhưng sản phẩm đã hết hàng → `out_of_stock`, đúng.
- t2: khách hỏi sản phẩm khác → `alternative_quote`, báo đúng giá và còn hàng.
- t3: khách nói "ừ vậy lấy Combi Sugocal cho chị, giao về…, nhận hàng trả tiền". Planner vẫn lấy sản phẩm trong bộ nhớ (sản phẩm cũ đã hết), cho goal `quote` + `out_of_stock`, báo **giá của sản phẩm cũ** cho sản phẩm mới (ví dụ "Combi Sugocal… giá 3.490.000đ"), và không tạo đơn.
- Lỗi này sinh phần lớn claim sai `price_vnd` và `in_stock` của nhóm (mục 3).

**4. Giỏ nhiều món: tạo đơn quá sớm, tính tổng sai, trả lời COD sai.** 4 ca: V3-055, 056, 057, 058 (call_1).
- **Tạo đơn quá sớm:** "Thêm Senko TS16 với bộ màng lọc…" đã được coi là đồng ý mua, nên `order.create` chạy ở t4, trước khi có địa chỉ và cách thanh toán. Ở V3-056, 057, 058, tham số đơn không khớp; V3-057 về sau chỉ còn `order_exists`, không tạo lại đơn.
- **Tính tổng sai:** "Tổng hết bao nhiêu? / Cộng hết là bao nhiêu?" (t5) không được nhận là câu hỏi tổng giỏ (goal chỉ là `quote`), nên agent báo giá món cuối, ví dụ "tổng tiền là 690.000đ".
- **Trả lời COD sai:** câu "nhận hàng trả tiền mặt được không" đi nhánh `policy_answer` và trả lời theo tài liệu chung ("shop hỗ trợ trả tiền mặt khi nhận hàng"; V3-058 còn lạc sang trả góp), không xét giỏ đang vượt 10 triệu.
- Goal `cod_limit` có xuất hiện (V3-055 t4, t6), nhưng câu agent không nói ngưỡng "10 triệu" ở ca nào. V3-055 tạo đúng 4 đơn chuyển khoản, tổng 15.870.000đ, nên chỉ trượt vì thiếu cụm này.

**5. Dùng chung SĐT: không nhận ra tên trong "cô Loan nè con".** 2 ca: V3-037, 038 (call_1).
- Số có nhiều hồ sơ, nên planner hỏi tên (`ask_identity`, dòng R00). Khách đã tự xưng ngay t1 "cô Loan nè con", nhưng cách tự xưng "<xưng hô> <Tên> nè/đây" không được trích thành tên.
- Agent hỏi tên 3 lượt liền và không tạo đơn. Lượt 1 còn bị guardrail "nhận là người thật" đẩy sang câu mẫu an toàn.

**6. Đọc giờ "9 rưỡi" thành 09:00.** 1 ca: V3-053.
- `schedule.callback` được gọi với `2026-10-27T09:00`; đúng phải là `09:30`.
- Ngày đã dời đúng sang 27/10 (bỏ qua ngày nghỉ), chỉ phần giờ "rưỡi" bị bỏ.

### 4.2 Nhóm B: goal hoặc tool đúng nhưng câu trả lời thiếu cụm bắt buộc, khoảng 10 ca

| # | Ca | Goal hoặc tool đã đúng | Câu agent thiếu gì |
|---|---|---|---|
| 7 | Đối thủ V3-047, 048, 049, 050 (4) | có goal `no_competitor_comment` (dòng R24a) | không nói "chính hãng / bảo hành / đổi trả", chỉ nhắc lại giá. Cùng kiểu với lỗi `refuse_internal` đã sửa ở 1c bằng câu cố định |
| 8 | Ngày nghỉ V3-052, 053 (2) | `schedule.callback` đã dời hẹn sang 27/10 (V3-052 đúng cả giờ 10:00) | agent nói "em gọi lại vào **thứ Hai**", lặp theo lời khách, không đọc ngày từ kết quả tool |
| 9 | 3 kênh lệch giá V3-006 (1) | báo đúng giá 1.290.000đ, tạo đơn và cập nhật địa chỉ đúng | không giải thích 1.161k là khuyến mãi **đã hết hạn**. Câu t1 còn chèn "Về việc **can nhac**…", tức giá trị `blocker` lưu không dấu lọt vào câu trả lời (hệ quả phụ đã ghi ở nhật ký 03/11 mục 1.2) |
| 10 | Đổi size V3-085 (1) | `order.update(exchange_size)` đúng, phí 0 | nói "không phải trả tiền ship", đúng ý nhưng không trùng cụm "miễn phí / không mất phí / không tốn phí / 0đ" mà bộ chấm yêu cầu |

Gốc lỗi 4 cũng có phần thuộc nhóm B: goal `cod_limit` có mặt nhưng câu không nói "10 triệu".

### 4.3 Phân loại theo thành phần gây lỗi

Mỗi kịch bản trượt được gán cho thành phần gây lỗi chính. Bằng chứng lấy từ trace: intent và cờ của router, `memory_writes`, backend extractor, goal, tool call.

| Thành phần gây lỗi chính | Số ca | Tỉ lệ |
|---|---|---|
| **Planner** (bảng luật + xử lý đơn trong `harness/agent.py`) | **17** | 65% |
| **Generator** (câu chữ) | **6** | 23% |
| **Extractor** | **3** | 12% |
| **Router** | **0** (góp phần phụ ở 4 ca) | 0% |

| Kịch bản | Thành phần chính | Bằng chứng | Router | Extractor |
|---|---|---|---|---|
| V3-023…026: chính sách cũ (4) | **Planner** | `_plan_order_change` báo `WINDOW_PASSED` theo mốc 7 ngày; t3 ra goal `quote`, không gọi `order.update(return)` | đúng (`order_change` 0,98–1,0; `policy_question` 0,89) | không liên quan |
| V3-027…030: hết hàng, đổi sản phẩm (4) | **Planner** | t3 khách nêu sản phẩm mới, planner vẫn bám sản phẩm cũ trong bộ nhớ, ra `out_of_stock`, không tạo đơn | đúng (`place_order` 1,0; `agrees_to_buy` 0,96) | không liên quan |
| V3-059…062: đổi địa chỉ (4) | **Planner** | nhánh địa chỉ đòi có chữ "địa chỉ"; "cô" khớp "cỡ"; nhánh `confirm_delivery_address` không gọi `order.update` | đúng (`order_change` 1,0) | địa chỉ mới đã trích đúng |
| V3-055…058: giỏ nhiều món (4) | **Planner** (phần "10 triệu" thuộc generator) | tạo đơn khi khách mới "thêm" món; "tổng bao nhiêu" không thành `cart_total`; trả lời COD không xét tổng giỏ | **góp phần**: "Thêm Philips 6.2L nữa… luôn nhé" được chấm `place_order` 0,94 + `agrees_to_buy` 0,79; planner tạo đơn chỉ dựa vào cờ này, không kiểm có địa chỉ và cách thanh toán chưa | không liên quan |
| V3-006: 3 kênh lệch giá (1) | **Planner** | không nhận ra 1.161k là giá khuyến mãi đã hết hạn, nên không ra goal `explain_price_change` (goal có sẵn) | đúng | phụ: `blocker = "can nhac"` lưu không dấu, lọt vào câu trả lời |
| V3-047…050: đối thủ (4) | **Generator** | có goal `no_competitor_comment`, Qwen chỉ nhắc lại giá | đúng (`mentions_competitor` 0,97–0,98) | không liên quan |
| V3-052: ngày nghỉ (1) | **Generator** | tool dời hẹn đúng sang 27/10 10:00; câu trả lời nói "thứ Hai" | đúng (`callback` 1,0) | phụ: bộ nhớ ghi `callback_requested = 26/10` (ngày nghỉ, trước khi dời) |
| V3-085: đổi size (1) | **Generator** | tool đúng, phí 0; câu nói "không phải trả tiền ship", không trùng cụm "miễn phí" | đúng | không liên quan |
| V3-037, 038: chung SĐT (2) | **Extractor** | t1 không ghi bộ nhớ gì: rules và Jev đều không trích tên từ "cô Loan nè con" (backend `jev_grounded_rules`). Planner hỏi tên 3 lượt rồi dừng | đúng | **lỗi chính** |
| V3-053: "9 rưỡi" (1) | **Extractor** | slot `callback_requested` do luật trích = `2026-10-26T09:00`, mất "rưỡi". Planner dời ngày đúng sang 27/10 nhưng giữ giờ sai | đúng (`callback`) | **lỗi chính** (bộ phân tích giờ của luật) |

- **Router** không phải nguyên nhân chính của ca nào: intent và cờ đúng ở 22/26 ca. 10 lượt Jev có độ tin thấp rơi về luật, không lượt nào gây trượt.
- **Extractor:** 3 ca, đều ở luật trích (tên kiểu "<xưng hô> <Tên> nè", giờ "rưỡi"). CERT2 không liên quan.
- **Planner** là chỗ đáng sửa nhất (17/26), đúng với nhận định nhật ký 05/11 mục 2: "dư địa lớn nhất là planner và tra sản phẩm".

### 4.4 Lỗi generator nằm ở đâu

Đường sinh câu trả lời gồm 4 bước:
1. Qwen viết câu từ `GOALS` + `FACTS`, theo hướng dẫn từng goal trong `GOAL_NOTES` (`core/llm/generator.py:35`).
2. Guardrail kiểm số tiền và các mẫu cấm.
3. **Kiểm độ phủ nội dung** (`harness/coverage.py`, hàm `content()`), cùng các mẫu `REQUIRED_*` trong `harness/lexicon/guardrails.json`.
4. Thiếu nội dung thì sinh lại; vẫn thiếu thì dùng **câu mẫu offline** (`render_offline`, `core/llm/generator.py:~380`).

**Hướng dẫn (bước 1) và câu mẫu (bước 4) đều đúng. Lỗi nằm ở bước 3: không có phép kiểm cho các goal này**, nên câu thiếu của Qwen3-4B vẫn được gửi đi:

| Goal | `GOAL_NOTES` | Câu mẫu offline | Kiểm ở `coverage.content()` / `REQUIRED_*` | Hệ quả |
|---|---|---|---|---|
| `no_competitor_comment` (V3-047…050) | có: "nói giá trị khi mua ở shop: hàng chính hãng, bảo hành, đổi trả" | có: "…mua ở bên em là hàng chính hãng, có bảo hành và đổi trả…" | **không có** | Qwen bỏ qua, câu vẫn qua |
| `cod_limit` (V3-055…058) | không có mục riêng | có: "…trên 10 triệu bên em không nhận COD…" | **không có** | không câu nào nói "10 triệu" |
| `callback_scheduled` (V3-052, 053) | — | có: giờ + thứ + ngày từ `FACTS.callback` | **chỉ kiểm giờ** (`_has_time`), không kiểm ngày/thứ | "thứ Hai, 10 giờ" qua vì đúng giờ, dù ngày đã dời sang thứ Ba 27/10 |
| `order_updated` với phí 0 (V3-085) | chỉ nói nêu tiền hoàn / bù thêm | chỉ thêm phí khi `fee_vnd > 0` | chỉ kiểm tiền hoàn / bù | không đâu yêu cầu nói "miễn phí" khi phí bằng 0 |

**Lỗi phụ cùng chỗ:** câu đệm "Em chưa có thông tin về chứng nhận hoặc thông số khác" xuất hiện ở rất nhiều lượt. Nguồn gốc là `GOAL_NOTES["quote"]`: "Nếu khách còn hỏi điều khác (chứng nhận, thông số…) mà FACTS không có: nói rõ 'em chưa có thông tin'". Qwen3-4B áp câu này cả khi khách không hỏi gì thêm.

**Hướng sửa (chưa làm, chờ duyệt):**
- Thêm phép kiểm vào `coverage.content()` cho:
  - `no_competitor_comment`: phải có "chính hãng / bảo hành / đổi trả";
  - `cod_limit`: phải có "10 triệu";
  - `callback_scheduled`: phải có ngày hoặc thứ trong `FACTS.callback`, không chỉ giờ;
  - `order_updated` khi `fee_vnd == 0`: phải nói "miễn phí".
- Thiếu thì cơ chế sẵn có sẽ sinh lại rồi rơi về câu mẫu offline, vốn đã đúng.
- Sửa `GOAL_NOTES["quote"]` để chỉ nói "chưa có thông tin" khi khách **thực sự hỏi** điều đó.

### 4.5 Nhận xét chung

- **Vì sao dev qua mà holdout trượt:** các lỗi nhóm A đều là giả định cứng khớp với cách nói ở dev: phải có chữ "địa chỉ", khoảng cách ngày rơi đúng mốc 11, khách không xưng "cô", khách tự xưng bằng "tên là"... Holdout đổi cách nói nên lộ ra. Đây là chỗ hổng tổng quát, không phải do may rủi.
- **Trùng với ca khó của bộ ẩn:** cả 7 nhóm ca khó trượt đều nằm trong danh sách ca khó BTC công bố (`DIEU-CHINH-DE.md` mục 11), nên nhiều khả năng cũng kéo TSR chính thức xuống.
- **Quan sát phụ về độ tự nhiên:** rất nhiều câu trả lời kèm câu đệm "Em chưa có thông tin về chứng nhận hoặc thông số khác". Câu này không làm trượt TSR, nhưng giám khảo đọc hội thoại sẽ thấy lạc. Ngoài ra, địa chỉ trích ra đôi khi dính đuôi ("…, Đà Nẵng nha", "…, nhận hàng").
- **Hướng sửa (chưa làm, chờ duyệt từng mục):**
  - Nhóm A sửa bằng code tổng quát, không cần học đáp án:
    - xét phiên bản chính sách theo ngày đơn trước khi báo quá hạn, và xét yêu cầu trả hàng trước phép kiểm quá hạn;
    - nhận diện đổi địa chỉ theo slot `address` thay vì chữ "địa chỉ", và có gọi `order.update(update_address)`;
    - so khớp "cỡ" trên câu còn dấu để không trùng "cô";
    - chuyển trọng tâm sang sản phẩm khách vừa chọn;
    - chỉ tạo đơn khi khách chốt, nhận diện câu hỏi tổng giỏ, xét COD theo tổng giỏ;
    - trích tên kiểu "cô Loan nè";
    - đọc "rưỡi" trong giờ hẹn.
  - Nhóm B sửa bằng câu cố định theo goal (như cách đã làm với `refuse_internal`), hoặc đưa ngày và phí từ kết quả tool vào câu trả lời.
  - Mọi sửa đổi đo trên v3 dev trong vòng cải tiến, **không chạy lại holdout**. Báo cáo phải ghi rõ đã xem lỗi holdout trước khi sửa.

## 5. Nhận định

1. **Bộ nhớ, mục tiêu cốt lõi của đề, đạt rõ:** RQR giảm 84% (ngưỡng 40%), CCR 9,2 → 67,9%, 0 vi phạm guardrail, latency đạt cả hai ngưỡng.
2. **TSR (66,2%) và HR giá & KM (6,1%) chưa đạt ngưỡng.** Hệ thống vẫn hơn baseline ở cả hai (TSR +16,8 điểm, HR −1,7 điểm).
3. **Khoảng cách với dev lớn:** v3 dev đạt TSR 98,8% (nhật ký 06/11 mục 1), holdout 66,2%. Kế hoạch đã dự kiến điều này, vì các dòng bảng D51 được rút từ ca trượt của dev. Khoảng cách cho thấy bảng planner khớp sát với dev, chưa tổng quát sang các mẫu ca khó mới.
4. **Giới hạn cần nêu khi báo cáo:**
   - Holdout v3 do cùng trợ lý viết (ở phiên khác).
   - Chạy một lần, nhiệt độ 0, nhưng generator và Jev vẫn có dao động: trên dev, một kịch bản lệch giữa hai lần chạy là trong nhiễu.
   - 77 kịch bản, nên mỗi kịch bản bằng 1,3 điểm TSR.

## 6. Việc tiếp theo (chờ người dùng quyết)

- **Không chạy lại holdout này** với code đã sửa. Số trên là số chính thức của cấu hình đóng băng.
- **Vòng cải tiến (bước 5, D57 phương án b):** các nhóm trượt ở mục 3 và gốc lỗi ở mục 4 là đầu vào cho Knowledge Gap Loop. Phải sửa và đo trên bộ cố định của vòng cải tiến (đề xuất v3 dev), **không đo trên holdout này**.
- **WER/CER cho báo cáo:** đo trên 12 hội thoại audio `asr/` của BTC cộng ít nhất 20 file của nhóm (`DIEU-CHINH-DE.md` mục 8). Đây là chỉ số thứ 5, chưa có trong lần chạy này.
