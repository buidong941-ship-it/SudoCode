# Hỏi đáp cho người mới vào project

Tài liệu này gom các câu một người mới đọc code sẽ hỏi: bài toán là gì, project giải từng phần ở file nào, và giải như thế nào. Mỗi câu trả lời chỉ tới file và dòng code.

- Viết ngày 19/10/2026, theo code ở commit `ec08d2f` và các tài liệu trong `docs/` cùng thư mục gốc.
- Số dòng trong file này lấy theo code hiện tại. Các bảng tra `HAM-*.md` ghi số dòng **trước** commit xóa comment (`ec08d2f`), nên có thể lệch vài chục dòng.
- Khi code và tài liệu cũ nói khác nhau, file này theo code.

**Thứ tự đọc gợi ý:** [debaiSUDO.md](../debaiSUDO.md) (đề) → [README.md](../README.md) → [SO-DO-CODE.md](SO-DO-CODE.md) (sơ đồ) → file này → [HAM-AGENT.md](HAM-AGENT.md) (bảng tra từng hàm của lõi).

---

## Mục lục

0. [Bản đồ nhanh](#0-bản-đồ-nhanh)
1. [Bài toán và cách chấm](#a-bài-toán-và-cách-chấm)
2. [Kiến trúc tổng thể](#b-kiến-trúc-tổng-thể)
3. [Nhận diện khách và Call Brief](#c-nhận-diện-khách-và-call-brief)
4. [Bộ nhớ](#d-bộ-nhớ)
5. [Hiểu lời khách](#e-hiểu-lời-khách-perceive-và-trích-slot)
6. [Planner và tool](#f-planner-và-tool)
7. [Sinh câu trả lời và guardrail](#g-sinh-câu-trả-lời-và-guardrail)
8. [Trace và chấm điểm](#h-trace-và-chấm-điểm)
9. [Dữ liệu, ASR, RAG](#i-dữ-liệu-asr-rag)
10. [Chạy, debug, hạ tầng](#j-chạy-debug-hạ-tầng)
11. [Chỗ còn thiếu và chỗ dễ vấp](#k-chỗ-còn-thiếu-và-chỗ-dễ-vấp)
12. [Câu giám khảo có thể hỏi khi phản biện](#l-câu-giám-khảo-có-thể-hỏi-khi-phản-biện)

---

## 0. Bản đồ nhanh

### Một lượt thoại đi qua đâu

```
Khách nói
  │
  ├─ (đầu vào ASR) asr/itn.py: itn()                     đổi số viết bằng chữ thành chữ số
  ├─ harness/textnorm.py: perceive()                     teencode, che CCCD/STK, rút số tiền, SĐT, ngày
  ├─ harness/extractor.py: customer_slots()              diện tích, ngân sách, size, địa chỉ, rào cản…
  ├─ (nếu khách đọc SĐT / xưng tên) gắn hồ sơ khách
  ├─ core/llm/router.py: Router.route()                  intent (11 nhãn) + 7 cờ rủi ro
  ├─ harness/agent.py: CallSession._plan()               CODE chọn việc cần làm, gọi tool → goals + facts
  ├─ core/llm/generator.py: Generator.generate()         LLM viết câu từ goals + facts
  ├─ harness/guardrails.py: check()                      số tiền lạ, lộ nội bộ, PII, nhận là người, chê đối thủ
  │     └─ vi phạm → sinh lại 1 lần → vẫn vi phạm → câu mẫu (render_offline)
  ├─ harness/extractor.py: analyze_agent(), facts_used() questions / claims / facts_used cho trace
  └─ CallSession._remember()                             ghi fact vào bộ nhớ → 1 dòng trace
```

Một cuộc gọi gồm `start()` (một lần: nhận diện khách, dựng Call Brief), nhiều `turn()` (mỗi câu khách một lần), rồi `end()` (một lần: lưu tóm tắt phiên).

### File nào làm gì

| File | Vai trò | Của ai |
|---|---|---|
| [debaiSUDO.md](../debaiSUDO.md), [DIEU-CHINH-DE.md](../DIEU-CHINH-DE.md), [GIAI-DAP-MENTOR.md](../GIAI-DAP-MENTOR.md) | Đề bài, điều chỉnh đề, trả lời mentor | BTC |
| `catalog/`, `policy/`, `test_set/`, `schemas/`, `rag/`, `eval/`, `simulator/`, `asr/ground_truth.json` | Dữ liệu, tool tham chiếu, script chấm. **Không sửa** | BTC |
| [run_eval.py](../run_eval.py) | Chạy một thư mục kịch bản → file trace `.jsonl` (lệnh BTC dùng) | Nhóm |
| [harness/agent.py](../harness/agent.py) | Lõi: `CallSession` (nhận diện, Call Brief, planner, ghi nhớ) | Nhóm |
| [harness/loader.py](../harness/loader.py) | Đọc kịch bản, giấu đáp án khỏi agent | Nhóm |
| [harness/textnorm.py](../harness/textnorm.py) | Chuẩn hóa tiếng Việt, đọc số tiền / SĐT / ngày, che PII | Nhóm |
| [harness/extractor.py](../harness/extractor.py) | Trích slot từ lời khách; trích `questions` / `claims` / `facts_used` từ lời agent | Nhóm |
| [harness/llm_extract.py](../harness/llm_extract.py) | Bản LLM của bộ trích (chế độ `llm` / `hybrid`) | Nhóm |
| [harness/tools.py](../harness/tools.py) | `ToolBox` gọi 9 tool BTC; nhận diện sản phẩm / biến thể trong câu | Nhóm |
| [harness/memory.py](../harness/memory.py) | Bộ nhớ khách hàng (SQL): hồ sơ, định danh, phiên, fact, báo giá | Nhóm |
| [harness/guardrails.py](../harness/guardrails.py) | Kiểm câu trả lời trước khi gửi khách | Nhóm |
| [harness/rag.py](../harness/rag.py), [harness/knowledge.py](../harness/knowledge.py) | Tra chính sách (BM25 + vector) | Nhóm |
| [harness/mcp_client.py](../harness/mcp_client.py), [mcp_servers/](../mcp_servers/) | Hai MCP server (`mcp-commerce`, `mcp-memory`) và client | Nhóm |
| [core/llm/router.py](../core/llm/router.py) | Phân loại intent + cờ (Jev / DeepSeek / Qwen / luật) | Nhóm |
| [core/llm/generator.py](../core/llm/generator.py) | Prompt hệ thống, `GOAL_NOTES`, câu mẫu offline | Nhóm |
| [core/llm/deepseek.py](../core/llm/deepseek.py) | Client LLM chung cho DeepSeek và Qwen | Nhóm |
| [core/llm/summarizer.py](../core/llm/summarizer.py) | Tóm tắt phiên và tóm tắt bàn giao bằng LLM | Nhóm |
| [core/pii.py](../core/pii.py) | Che SĐT / địa chỉ trước khi gửi model ngoài và khi ghi log | Nhóm |
| [core/config.py](../core/config.py) | Mọi cấu hình đọc từ biến môi trường / `.env` / profile | Nhóm |
| [datagen/](../datagen/) | Sinh kịch bản test, viết lại lời khách, xuất transcript, sinh audio | Nhóm |
| [asr/transcribe.py](../asr/transcribe.py), [asr/itn.py](../asr/itn.py) | ASR local (Whisper) và chuẩn hóa số cho đầu ra ASR | Nhóm |
| [scripts/run_suite.py](../scripts/run_suite.py), [scripts/kaggle_job.py](../scripts/kaggle_job.py), [kaggle/runner.py](../kaggle/runner.py) | Chạy trọn bộ đánh giá trên Kaggle / server / máy cá nhân | Nhóm |
| [tests/](../tests/) | Kiểm thử không cần mạng | Nhóm |

---

## A. Bài toán và cách chấm

### A1. Bài toán là gì, nói gọn trong một câu?

Xây một **agent telesale tiếng Việt nhớ được khách qua nhiều cuộc gọi và nhiều kênh**: khách gọi lại thì nhận ra, nạp lại ngữ cảnh cũ, mở đầu bằng câu tiếp nối thay vì hỏi lại từ đầu, giá và khuyến mãi luôn lấy từ tool, và có số liệu chứng minh tốt hơn một bản không có bộ nhớ (baseline). Đề đầy đủ: [debaiSUDO.md](../debaiSUDO.md) mục A–C.

### A2. Đề có 4 "case". Project đáp ứng từng case bằng gì?

| Case trong đề | Nỗi đau | Project giải bằng | Ở đâu |
|---|---|---|---|
| 1. Khách gọi lại bị coi như người lạ | Hỏi lại diện tích, ngân sách; báo giá khác | Bộ nhớ dài hạn + Call Brief + câu mở đầu tiếp nối | [memory.py](../harness/memory.py), [agent.py `_build_brief`](../harness/agent.py#L152), goal `opening_returning` ở [agent.py:413](../harness/agent.py#L413) |
| 2. Mỗi kênh biết một nửa sự thật | Fanpage báo 690k, hotline báo 790k | Hồ sơ hợp nhất theo SĐT / Zalo ID / FB ID; gộp hồ sơ tạm | [agent.py `start`](../harness/agent.py#L92), [`_bind`](../harness/agent.py#L115), [memory.py `merge_customer`](../harness/memory.py#L193) |
| 3. Bàn giao mù khi chuyển máy | Người nhận máy không biết gì | Handoff brief có cấu trúc + bộ nhớ dùng chung qua `mcp-memory` | [agent.py `_handoff_brief`](../harness/agent.py#L778), [mcp_servers/memory_server.py](../mcp_servers/memory_server.py) |
| 4. Kịch bản đóng băng, không học được | Không có vòng cải tiến | **Chưa làm.** Thiết kế có ở [ARCHITECTURE.md](ARCHITECTURE.md) mục 5.4 nhưng chưa có code `improve/` | — |

### A3. M1 và M2 khác nhau thế nào? Project đang ở mức nào?

M1 là bắt buộc, M2 là nâng cao. Chỉ làm M2 khi M1 ổn. Bảng hiện trạng theo từng hạng mục ở [PLAN.md](PLAN.md) mục 1. Tóm tắt:

- **Đã có:** dataset đủ chỉ tiêu M1 (trừ giọng vùng miền), bộ nhớ, Call Brief, 9 tool, 2 MCP server, guardrail, script đánh giá + baseline, RAG, ASR + WER.
- **Có thêm một phần M2:** `pricing.get_quote` chỉ trả KM còn hiệu lực, `order.status/update`, `schedule.callback`, phát hiện KM hết hạn trong Call Brief, TTL, xóa dữ liệu theo yêu cầu, chạy toàn bộ LLM local (Qwen).
- **Chưa có:** cơ chế cải tiến (tiêu chí 5, 13%), giao diện web + demo (tiêu chí 6, 13%), báo cáo / video / slide.

### A4. Năm chỉ số bắt buộc là gì, và trace của mình cung cấp gì cho từng chỉ số?

Script chấm chính thức là [eval/reference_eval.py](../eval/reference_eval.py) của BTC. Nó không đọc lời agent để tự hiểu, mà đọc các trường **do hệ thống của nhóm tự khai** trong trace. Vì vậy bộ trích (extractor) quyết định con số.

| Chỉ số | Công thức (đề Phụ lục A) | Trường trace dùng | Ai tạo trường đó | Hàm chấm |
|---|---|---|---|---|
| Repeat-Question Rate (RQR) | câu hỏi thừa / tổng câu hỏi | `questions[]` (`slot`, `type`: open/confirm) | [extractor.agent_questions](../harness/extractor.py#L100) | [reference_eval.py:61](../eval/reference_eval.py#L61) |
| Context Carryover Rate (CCR) | fact cũ dùng đúng / fact phải mang sang | `facts_used[]` + **tên** tham số tool | [extractor.facts_used](../harness/extractor.py#L177) | [reference_eval.py:88](../eval/reference_eval.py#L88) |
| Task Success Rate (TSR) | kịch bản đạt / tổng | `tool_calls[]`, `agent_text`, `claims` | planner gọi tool | [reference_eval.py:170](../eval/reference_eval.py#L170) |
| Hallucination Rate (HR) | claim sai / claim kiểm chứng được | `claims[]` (`field`, `value`) | [extractor.agent_claims](../harness/extractor.py#L124) | [reference_eval.py:224](../eval/reference_eval.py#L224) |
| WER / CER / Entity Accuracy | lỗi từ / ký tự; thực thể khớp tuyệt đối | `asr/hypotheses.json` | [asr/transcribe.py](../asr/transcribe.py) | `wer_cer()` trong reference_eval |

### A5. "Baseline không bộ nhớ" là gì, và khác bản `full` ở đúng chỗ nào trong code?

Đề bắt chạy song song một bản không nạp bộ nhớ phiên trước, cùng code, cùng model, cùng tham số. Trong project, khác biệt duy nhất là cờ `read_enabled`:

- [run_eval.py:83](../run_eval.py#L83): `open_memory(..., read_enabled=(config == "full"))`.
- Ba hàm đọc lịch sử trong [memory.py](../harness/memory.py) trả rỗng khi `read_enabled = False`: `past_sessions` ([:112](../harness/memory.py#L112)), `current_facts` ([:132](../harness/memory.py#L132)), `past_quotes` ([:186](../harness/memory.py#L186)).
- Baseline **vẫn ghi** bộ nhớ (để trace có `memory_writes`) và **vẫn tra CRM** (tên khách, đơn hàng), vì đó là dữ liệu hệ thống call center bình thường cũng có.

### A6. Ngưỡng đề yêu cầu là gì, project đạt chưa?

Ngưỡng: RQR giảm ≥ 40% so với baseline, TSR ≥ 70%, HR giá ≤ 5%, TTFT p95 ≤ 3 s, total p95 ≤ 8 s, Call Brief ≤ 5 s.

Số đo gần nhất (Hệ thống; nguồn [NHAT-KY-2026-10-23.md](NHAT-KY-2026-10-23.md) mục 6, [SO-SANH-2026-10-15.md](SO-SANH-2026-10-15.md) mục 6.1 và [NHAT-KY-2026-10-08.md](NHAT-KY-2026-10-08.md) mục 5). Cột **24/10** là cấu hình nộp: Jev + Qwen3-4B fp16 câu ngắn, bộ trích hybrid (`EXTRACTOR_BACKEND=hybrid`, `EXTRACTOR_ASYNC=1`):

| Chỉ số | 08/10: Jev + DeepSeek, dev · test | 15/10: Jev + Qwen3-4B fp16, dev · test | **24/10: Jev + Qwen3-4B câu ngắn + hybrid, dev · test** |
|---|---|---|---|
| Mức giảm RQR | 75,3% · 27,4% | 100% · — (cả hai bên không hỏi thừa) | **100% · 100%** |
| CCR (hệ thống) | 79,6% · 68,4% | 76,1% · 68,4% | **83,2% · 76,3%** |
| TSR (hệ thống) | 100% · 95,5% | 95,6% · 90,9% | **100% · 95,5%** |
| HR giá & KM (hệ thống) | 2,3% · 0,0% | 2,1% · 0,0% | **1,0% · 0,0%** |
| TTFT p95 | 1,6 s · 1,6 s | 1,2 s · 1,2 s | **1,35 s · 1,36 s** |
| Total p95 | 2,1 s · 3,2 s | 6,6 s · 9,3 s | **4,0 s · 4,1 s** |

Lưu ý khi đọc: bộ `test` chỉ có 16–22 câu hỏi nên mức giảm RQR không có ý nghĩa thống kê; LLM ở nhiệt độ 0,3 nên mỗi lần chạy lệch vài điểm. Biến thể "câu ngắn, 1 worker" ngày 15/10 đạt độ trễ nhưng chất lượng giảm ([SO-SANH](SO-SANH-2026-10-15.md) mục 7.1); 21 điểm yếu sửa ngày 23/10 lấy lại chất lượng ([NHAT-KY-2026-10-23](NHAT-KY-2026-10-23.md) mục 4–5). Cột 24/10 đạt mọi ngưỡng trên dev và test. Bộ mẫu BTC: TSR 85,7%, RQR giảm 24,9% khi chạy; sau khi sửa bộ lọc câu hỏi và chấm lại trên cùng trace thì giảm 57% (NHAT-KY-2026-10-23 mục 6).

### A7. Dữ liệu BTC phát gồm những gì, cái nào được sửa?

Danh sách ở cuối [README.md](../README.md). Tóm tắt: 40 sản phẩm + 96 biến thể (`catalog/products.json`), tồn kho theo ngày, 13 khuyến mãi có điều kiện, 50 khách CRM (có 2 người chung SĐT), 14 tài liệu chính sách (có bản hết hiệu lực, tài liệu nội bộ, tài liệu nhiễu), 60 câu hỏi RAG có nhãn, 7 kịch bản mẫu, tool tham chiếu `eval/mock_tools.py`, script chấm `eval/reference_eval.py`.

**Không sửa** `eval/`, `catalog/`, `policy/`, `test_set/`, `schemas/`, `rag/`, `asr/ground_truth.json` ([PLAN.md](PLAN.md) mục 2). Lý do: BTC chấm bằng chính các file này; khi BTC phát bản vá chỉ cần chép đè.

### A8. "Hôm nay" là ngày nào? Vì sao tool nào cũng nhận tham số `on`?

Ngày quy ước của dữ liệu là **15/10/2026** ([loader.py:12](../harness/loader.py#L12), `REF_DATE`). Ngày của từng cuộc gọi = `call_date` nếu có, không thì cộng dồn `days_later` ([loader.py `agent_view`](../harness/loader.py#L28)).

Giá, khuyến mãi, tồn kho thay đổi theo ngày (KM hết hạn giữa hai cuộc gọi, hàng về sau vài ngày). Vì vậy `ToolBox.call` tự gắn `on = ngày cuộc gọi` cho 4 tool phụ thuộc ngày ([tools.py:22 `DATED`](../harness/tools.py#L22), [tools.py:38](../harness/tools.py#L38)).

### A9. Một kịch bản test trông thế nào? Phần nào agent được thấy?

Ví dụ [test_set/public_sample/SAMPLE-01.json](../test_set/public_sample/SAMPLE-01.json): chị Hoa gọi 2 cuộc cách nhau 2 ngày. Mô tả các trường: [schemas/scenario_format.md](../schemas/scenario_format.md).

| Agent được thấy | Bị giấu (đáp án để chấm) |
|---|---|
| `customer_turns` hoặc `customer_turns_asr`, `channel`, `channel_identity`, ngày gọi, SĐT, `seed_history` | `facts_established`, `must_not_ask`, `must_carry_over`, `success_if`, `ground_truth_facts`, `memory_expectation`, `expected_outcome`, `notes`, `customer_name`, `_meta` |

Việc giấu nằm ở [loader.py `agent_view`](../harness/loader.py#L28): hàm chỉ chép sang những trường bên trái. Script chấm của BTC đọc file kịch bản theo cách riêng nên lấy được đáp án.

### A10. Bộ test ẩn có 19 ca khó. Code xử lý từng loại ở đâu?

| Ca khó (DIEU-CHINH-DE mục 11) | Code xử lý | Ở đâu |
|---|---|---|
| Khuyến mãi đã hết hạn | Call Brief báo giá lại, phát hiện KM hết → `stale_warnings` → goal `stale_promo` | [agent.py:163-178](../harness/agent.py#L163), [:420](../harness/agent.py#L420) |
| Hai người chung SĐT (memory poisoning) | CRM trả `ambiguous` → hỏi tên (`ask_identity`), chưa ghi bộ nhớ tới khi xác định | [agent.py:99](../harness/agent.py#L99), [:386](../harness/agent.py#L386), [`_resolve_candidate`](../harness/agent.py#L319), [`_remember`](../harness/agent.py#L801) |
| Khách quay lại sau 8 tháng | TTL theo slot; địa chỉ quá hạn chỉ hỏi xác nhận; SKU ngừng bán → mẫu thay thế | [memory.py:46 `TTL_DAYS`](../harness/memory.py#L46), [agent.py:635](../harness/agent.py#L635), [:504](../harness/agent.py#L504) |
| KM loại trừ size | Hỏi size trước khi báo giá | [`_promo_depends_on_size`](../harness/agent.py#L594), goal `ask_size_for_price` |
| Transcript ASR lỗi / teencode | ITN cho ASR, chuẩn hóa teencode, alias cách đọc tên SP | [agent.py:207](../harness/agent.py#L207), [textnorm.py `TEEN`](../harness/textnorm.py#L21), [tools.py `SPOKEN`](../harness/tools.py#L65) |
| PII (CCCD / STK) | Che ngay khi nhận câu; guardrail chặn ở đầu ra | [textnorm.py `mask_pii`](../harness/textnorm.py#L183), [guardrails.py:55](../harness/guardrails.py#L55) |
| Ép giá + dò giá nhập | `refuse_discount`, `refuse_internal`; guardrail chặn giá nhập / giá sàn | [agent.py:436](../harness/agent.py#L436), [:533](../harness/agent.py#L533), [guardrails.py `IMPORT_PRICES`](../harness/guardrails.py#L27) |
| 3 phiên thông tin đổi + hỏi trạng thái đơn | Supersede fact; `order.status`; nhớ `estimated_delivery` | [memory.py `write_fact`](../harness/memory.py#L147), [agent.py:449](../harness/agent.py#L449) |
| Hỏi AI hay người + yêu cầu xóa dữ liệu | Goal `is_bot`; `forget_customer` | [agent.py:422-429](../harness/agent.py#L422) |
| 16 lượt, 4 sản phẩm, > 10 triệu không COD | Giỏ hàng, tổng giỏ, chặn COD | [`_cart_quote`](../harness/agent.py#L602), [agent.py:649](../harness/agent.py#L649) |
| Đổi sản phẩm, hoàn chênh lệch | `order.update` + nhớ kết quả cho lượt sau | [`_plan_order_change`](../harness/agent.py#L685) |
| Câu hỏi theo chính sách cũ | RAG có luật "bản cũ cho đơn cũ" nhưng **agent chưa truyền ngày đơn** | [rag.py `_allowed`](../harness/rag.py#L250) |
| Hẹn gọi lại rơi vào ngày nghỉ | Dời sang ngày làm việc kế tiếp, nói lý do | [`_plan_callback`](../harness/agent.py#L748) |
| Không bình luận giá đối thủ | Goal `no_competitor_comment`; guardrail `COMPETITOR_RX` | [agent.py:534](../harness/agent.py#L534), [guardrails.py:29](../harness/guardrails.py#L29) |
| Hết hàng lúc khách quyết | Kiểm tồn trước khi lên đơn → `out_of_stock` + ngày về | [agent.py:645](../harness/agent.py#L645) |
| Câu hỏi y tế / ngoài phạm vi | Chuyển máy kèm handoff brief | [agent.py:430](../harness/agent.py#L430) |

---

## B. Kiến trúc tổng thể

### B1. "Harness" là gì? Sao không để LLM làm hết?

Harness là toàn bộ phần code bao quanh LLM: điều khiển vòng lặp, quyết định đưa gì vào prompt, gọi tool, kiểm lỗi, ghi nhớ ([debaiSUDO.md](../debaiSUDO.md) Phụ lục C).

Project chia việc theo nguyên tắc **"LLM phân loại hoặc viết câu; code đọc giá trị, quyết định và kiểm tra"** ([THAY-DOI-2026-10-15.md](THAY-DOI-2026-10-15.md) mục 1). Lý do:

- Giá phải khớp tuyệt đối với tool của BTC; LLM có thể làm tròn hay bịa.
- Entity Accuracy và HR chấm khớp tuyệt đối.
- Kết quả phải tái lập được và giải thích được khi phản biện.

### B2. Vì sao planner là code, không cho LLM tự gọi tool (function calling)?

Tham số `order.create` (sku, giá sau KM, mã KM, giỏ hàng) lấy thẳng từ `pricing.get_quote` vừa gọi cùng ngày ([agent.py `_plan_order`](../harness/agent.py#L616)). Nhờ vậy giá trong đơn luôn khớp mock của BTC và HR về giá gần như bằng 0 do thiết kế ([HARNESS.md](HARNESS.md) mục "Luồng một lượt").

Đánh đổi: planner dựa vào nhiều nhánh `if` và regex nên cứng; câu khách không khớp nhánh nào thì rơi về `closing` hoặc `ask_repeat`. Cuối [PLAN.md](PLAN.md) có đề xuất kiểu lai: LLM chỉ đề xuất tool ở chỗ planner bế tắc, code kiểm tra trước khi thực thi.

### B3. LLM được dùng ở những chỗ nào?

| Bước | LLM làm gì | Công tắc | LLM lỗi thì |
|---|---|---|---|
| Router | Chọn 1 trong 11 intent + chấm 7 cờ (0..1) | `--router jev\|llm\|qwen\|rules` | Luật từ khóa ([router.py:62](../core/llm/router.py#L62)) |
| Generator | Viết câu trả lời từ goals + facts | `--generator deepseek\|qwen\|offline` | Câu mẫu `render_offline` ([agent.py:261](../harness/agent.py#L261)) |
| Bộ trích (tùy chọn) | Phân loại slot / câu hỏi / claim | `--extractor rules\|llm\|hybrid` | Kết quả của luật |
| Tóm tắt phiên, handoff | Viết 1–4 câu tóm tắt + cảm xúc khách | `SUMMARY_BACKEND`, `HANDOFF_SUMMARY` | Câu ghép từ dữ liệu |

Những chỗ **cố ý không dùng LLM:** đọc số tiền / SĐT / ngày, che CCCD / STK, guardrail, planner và tham số đơn hàng, `facts_used`.

### B4. "Router" và "Jev" là gì?

Router trả lời câu "lượt này khách muốn gì". Đầu ra ([router.py](../core/llm/router.py)):

- `intent`: một trong 11 nhãn (`product_inquiry`, `price_promo`, `policy_question`, `place_order`, `order_change`, `order_status`, `callback`, `negotiate`, `out_of_scope`, `meta`, `greeting_or_other`), định nghĩa ở `INTENTS` [router.py:20](../core/llm/router.py#L20).
- `flags`: 7 cờ xác suất (`agrees_to_buy`, `defers_decision`, `asks_if_bot`, `wants_data_deleted`, `medical_question`, `asks_internal_cost`, `mentions_competitor`).

**Jev** (TypeSafe System One) là API phân loại có kiểu: trả nhãn kèm xác suất, không sinh văn bản. Nhờ có xác suất nên đặt được ngưỡng: Jev không chắc (`< ROUTER_MIN_CONFIDENCE = 0,45`) mà luật có tín hiệu rõ thì dùng luật, và ghi lý do vào `trace.router.fallback` ([router.py:67-72](../core/llm/router.py#L67)).

Backend `rules` (luật từ khóa) **chỉ dùng kiểm thử**, không dùng báo cáo số liệu.

### B5. "goals" và "facts" là gì?

Đây là hợp đồng giữa planner (code) và generator (LLM):

- **goals**: danh sách việc phải nói ở lượt này, theo thứ tự, ví dụ `["opening_returning", "stale_promo", "quote"]`.
- **facts**: dữ liệu đi kèm, lấy từ tool hoặc bộ nhớ, ví dụ `{"quote": {"final_price_vnd": 4890000, "promo_names": [...]}}`.

Generator nhận cả hai trong một JSON ([agent.py:239-242](../harness/agent.py#L239)) và chỉ được dùng con số có trong `facts`. Danh sách đầy đủ các goal nhìn ở `render_offline` ([generator.py:101](../core/llm/generator.py#L101)): mỗi nhánh `elif g == ...` là một goal.

### B6. MCP là gì, vì sao chọn MCP mà không làm A2A (multi-agent)?

MCP (Model Context Protocol) là chuẩn để agent gọi tool / dữ liệu qua một "server" riêng. Đề bắt chọn MCP hoặc A2A (tiêu chí 3, 15%); nếu chọn MCP thì bắt buộc có `mcp-memory`.

Project có 2 server chạy dạng tiến trình con (stdio):

| Server | Bọc | Tool |
|---|---|---|
| `mcp-commerce` ([commerce_server.py](../mcp_servers/commerce_server.py)) | `eval/mock_tools.py` của BTC | 9 tool BTC + `world.reset` |
| `mcp-memory` ([memory_server.py](../mcp_servers/memory_server.py)) | `harness/memory.py` | `memory.*` đọc / ghi; chế độ `MCP_MEMORY_MODE=ro` chỉ mở tool đọc |

Lý do chọn ([ARCHITECTURE.md](ARCHITECTURE.md) mục 4.1, 4.5): bộ nhớ là dữ liệu dùng chung giữa bot, nhân viên và giao diện. Đóng gói thành server thì mọi bên gọi cùng một cửa, và phân quyền được theo tool. Ví dụ Case 3: giao diện nhân viên mở `mcp-memory` ở chế độ chỉ đọc, thấy đúng thứ agent vừa ghi mà không thể ghi đè.

### B7. `--transport mcp` và `--transport direct` khác gì?

- `mcp` (mặc định): tool và bộ nhớ đi qua hai MCP server.
- `direct`: gọi thẳng hàm Python, nhanh hơn khoảng 35 ms mỗi lượt.

Hai đường cho trace giống hệt nhau (870/870 lượt, [tests/mcp_parity.py](../tests/mcp_parity.py)). Code chọn đường ở [tools.py:44](../harness/tools.py#L44) và [memory.py `open_memory`](../harness/memory.py#L254).

### B8. Client MCP bất đồng bộ, harness đồng bộ. Ghép thế nào?

[mcp_client.py](../harness/mcp_client.py): mỗi server chạy thành tiến trình con; một thread riêng giữ event loop và `ClientSession` sống suốt tiến trình harness; `call()` gửi coroutine sang loop đó rồi chờ kết quả. Kết nối tạo lười và tách theo PID, nên mỗi worker (`--workers N`) có bộ server riêng và trạng thái mock không lẫn nhau.

### B9. Cấu hình nằm ở đâu? Biến nào thắng?

[core/config.py](../core/config.py) đọc mọi thứ. Thứ tự ưu tiên: **biến môi trường đặt tay > profile (`profiles/<RUN_PROFILE>.env`) > `.env`**. Lý do: `_load_dotenv` dùng `os.environ.setdefault`, nên giá trị đã có không bị ghi đè.

Lưu ý: trong `.env` **không viết ghi chú cùng dòng với giá trị**. `_load_dotenv` không cắt ghi chú, nên `DEEPSEEK_THINKING=disabled  # ...` thành cả chuỗi và chế độ suy luận vẫn bật ([NHAT-KY-2026-10-08.md](NHAT-KY-2026-10-08.md) mục 3.1).

---

## C. Nhận diện khách và Call Brief

### C1. Làm sao biết người đang gọi là khách cũ?

[agent.py `start()`](../harness/agent.py#L92):

1. Chọn định danh theo kênh: Fanpage → `fb_id`, Zalo → `zalo_id`, hotline hoặc thiếu ID → SĐT.
2. Hỏi CRM (`crm.get_customer`):
   - nhiều hồ sơ (SĐT dùng chung) → lưu `candidates`, chờ khách xưng tên;
   - một hồ sơ → `_bind` vào hồ sơ đó;
   - không có → tra bộ nhớ của mình (`mem.lookup`);
   - vẫn không có → tạo hồ sơ tạm `N-<định danh>`.
3. Dựng Call Brief (`_build_brief`) và đo thời gian.

### C2. `_bind` làm gì?

[agent.py:115](../harness/agent.py#L115) gắn cuộc gọi vào một khách:

- lưu hồ sơ và mọi định danh (SĐT, Zalo, FB);
- gộp các hồ sơ tạm `N-…` trùng định danh vào hồ sơ này (đây là phần "identity resolution" đa kênh);
- nhập phiên cũ từ CRM;
- **chỉ khi `read_enabled`** (bản full) và khách chưa yêu cầu xóa: nạp fact và báo giá cũ, đặt sản phẩm đang bàn (`focus`) = sản phẩm đã chốt hoặc đã tư vấn.

### C3. Hồ sơ tạm `N-…` khi nào được gộp vào hồ sơ thật?

Khi khách đọc SĐT trong cuộc gọi ([agent.py:216-226](../harness/agent.py#L216)): hệ thống tra CRM bằng SĐT đó; nếu ra đúng một khách thì `merge_customer` chuyển fact, báo giá, phiên, định danh từ hồ sơ tạm sang hồ sơ thật ([memory.py:193](../harness/memory.py#L193)). Hai fact `current` cùng slot thì giữ cái mới hơn.

### C4. Khách nhắn Zalo không có Zalo ID và không đọc SĐT thì sao?

Không nhận diện được. Đây là `SAMPLE-06 call_2` ([CAU-HOI-BTC.md](CAU-HOI-BTC.md) A2, đang chờ BTC trả lời).

Theo code hiện tại còn một điểm nên biết: [run_eval.py:96](../run_eval.py#L96) chỉ truyền SĐT cho kênh hotline. Kênh chat có `channel_identity = null` thì `start()` không tạo hồ sơ nào, `self.customer` là `None`. Nhánh gắn SĐT ở [agent.py:216](../harness/agent.py#L216) lại đòi `self.customer` đã có, nên **kể cả khi khách đọc SĐT trong chat, cuộc chat đó vẫn không được gắn vào khách**. Bộ nhớ cũng không ghi gì vì `_remember` cần `customer_id`.

### C5. Hai người dùng chung một SĐT thì xử lý thế nào?

1. CRM trả `ambiguous: true` → `self.candidates` = danh sách hồ sơ ([agent.py:99](../harness/agent.py#L99)).
2. `_plan` trả ngay goal `ask_identity` khi còn `candidates` ([agent.py:386](../harness/agent.py#L386)): "cho em xin tên…".
3. Khách xưng tên ("chị Dung đây") → slot `self_name` → `_resolve_candidate` so tên (bỏ dấu) và gắn đúng hồ sơ ([agent.py:319](../harness/agent.py#L319)).
4. Trong lúc chưa rõ là ai, `_remember` **không ghi gì** ([agent.py:804](../harness/agent.py#L804)). Đây là cách chống ghi nhầm bộ nhớ sang người kia.

### C6. Call Brief là gì, gồm những gì?

Bản tóm tắt về khách nạp cho agent ngay trước khi bắt máy (đề C.2). Dựng ở [agent.py `_build_brief`](../harness/agent.py#L152) theo [schemas/call_brief.schema.json](../schemas/call_brief.schema.json):

| Trường | Nội dung |
|---|---|
| `customer_name`, `is_returning`, `n_previous_sessions` | Khách là ai, đã gọi mấy lần |
| `last_session` | Phiên gần nhất: ngày, kênh, tóm tắt, kết quả |
| `profile_facts` | Fact còn hạn (phòng 25 m², có con nhỏ…) |
| `products_advised` | Sản phẩm đã báo giá + giá cũ + giá hiện tại + KM còn không + còn hàng không |
| `orders` | Đơn của khách (`order.status`) |
| `open_blockers`, `open_questions` | Rào cản ("cần hỏi chồng"), câu khách hỏi lần trước chưa được trả lời |
| `must_not_ask` | Slot đã biết và còn hạn |
| `stale_warnings` | KM hết hạn, giá đổi, hết hàng, fact quá hạn |
| `suggested_opening`, `suggested_next_action` | Câu mở đầu và việc nên làm tiếp |

### C7. "Kiểm tính mới" (freshness check) lúc nhận diện là gì? Vì sao không precompute hết?

[DIEU-CHINH-DE.md](../DIEU-CHINH-DE.md) mục 6: được precompute phần tóm tắt ở cuối phiên trước, nhưng việc kiểm KM hết hạn, tồn kho, tương tác kênh khác **phải chạy lúc nhận diện** và tính vào độ trễ.

Code ([agent.py:163-178](../harness/agent.py#L163)): với mỗi sản phẩm đã báo giá, gọi lại `pricing.get_quote` + `inventory.check` với ngày hôm nay, so với báo giá cũ, rồi ghi cảnh báo vào `stale_warnings`. Phần precompute khai báo trong `precomputed_parts`. Số đo: Call Brief p95 ≤ 0,2 s (ngưỡng 5 s).

### C8. Câu mở đầu tiếp nối ("hôm 12/03 bên em có tư vấn chị mẫu X…") được tạo thế nào?

1. `_plan`, lượt 1, khách quay lại và có sản phẩm cũ → goal `opening_returning`, kèm `facts["brief"]` gồm tên sản phẩm, giá đã báo, ngày gọi trước, rào cản, cảnh báo ([agent.py:413-421](../harness/agent.py#L413)). Có cảnh báo KM thì thêm `stale_promo`.
2. Generator viết câu từ các facts đó. Bản câu mẫu ở `render_offline`, nhánh `opening_returning` ([generator.py `render_offline`](../core/llm/generator.py#L101)).

Giới hạn ([điểm yếu.md](../điểm%20yếu.md)): chỉ kích hoạt khi phiên trước có sản phẩm đang bàn (`prev_focus`). Khách quay lại mà chưa từng bàn sản phẩm nào thì không có câu tiếp nối.

### C9. `must_not_ask` trong Call Brief và `must_not_ask` trong kịch bản có phải một?

Không.

- Trong **kịch bản**: đáp án của BTC, bị giấu khỏi agent, dùng để chấm RQR.
- Trong **Call Brief**: hệ thống tự tính = các slot đang có trong bộ nhớ và còn hạn ([agent.py:180](../harness/agent.py#L180)).

Hai danh sách khớp nhau thì RQR tốt.

### C10. `seed_history` trong kịch bản được xử lý thế nào?

`seed_history` là phiên cũ "có sẵn trong CRM" trước cuộc gọi. Nó vào bộ nhớ, **không vào prompt**.

[run_eval.py:98-107](../run_eval.py#L98): sau `start()`, từng phiên cũ đi qua `import_old_session` ([agent.py:136](../harness/agent.py#L136)). Hàm này trích slot từ câu tóm tắt, lấy sản phẩm đầu tiên làm `product_advised`, số tiền đầu tiên làm `price_quoted_vnd`, rồi ghi thành fact với ngày gốc (để xét TTL) và độ tin 0,8. Bản `full` sau đó gọi lại `_bind` và dựng lại Call Brief để nạp các fact này.

### C11. Vì sao `call_brief_latency_ms` là `None` ở cuộc gọi đầu?

Cuộc 1 chưa có gì để nạp, nên không có ý nghĩa đo ([agent.py:315](../harness/agent.py#L315)). Brief vẫn được dựng và ghi vào trace lượt 1.

---

## D. Bộ nhớ

### D1. Đề yêu cầu 4 tầng bộ nhớ. Mỗi tầng nằm ở đâu?

| Tầng (đề C.1) | Ví dụ | Nơi lưu |
|---|---|---|
| Working | Khách vừa nói gì, đang chờ xác nhận gì | Trường của `CallSession` trong RAM (`known`, `focus`, `cart`, `history`…) + bảng `turns` |
| Episodic | "Cuộc 1 (12/03): tư vấn X, báo 4,89tr, hẹn hỏi chồng" | Bảng `sessions` (cột `summary`, `blockers_json`, `open_questions_json`) |
| Profile | Phòng 25 m², có con nhỏ, ngân sách 5tr | Bảng `facts` (có nguồn gốc, hạn dùng, trạng thái) |
| Semantic / KB | Giá, tồn kho, KM, chính sách | Tool (`mock_tools`) cho dữ liệu thay đổi; RAG trên `policy/` cho chính sách |

Thêm bảng `quotes` (lịch sử báo giá) để phát hiện KM hết hạn / giá đổi, và `customers` + `identities` cho danh tính đa kênh. Schema ở [memory.py:17-44](../harness/memory.py#L17).

### D2. Ghi gì và không ghi gì vào bộ nhớ?

[agent.py `_remember`](../harness/agent.py#L801) chạy cuối mỗi lượt:

- **Ghi:** slot khách vừa nói (diện tích, ngân sách, size, màu, địa chỉ, thanh toán, rào cản, hẹn gọi lại…); sản phẩm đang bàn + giá + mã KM + hạn KM; mã đơn, biến thể, ngày giao dự kiến.
- **Không ghi:** tên khách tự xưng (`self_name`); giá khách tự nêu (`claimed_prices`, vì có thể sai); CCCD / STK (đã bị che từ bước perceive nên không bao giờ tới đây); câu xã giao.
- **Không ghi gì cả** khi chưa nhận diện được khách, đang chờ xưng tên (SĐT chung), hoặc khách đã yêu cầu xóa dữ liệu.

### D3. Khách đổi ý ("thôi lấy màu trắng") thì sao?

[memory.py `write_fact`](../harness/memory.py#L147):

- Giá trị trùng fact hiện hành → không làm gì.
- Khác → thêm dòng mới, dòng cũ chuyển `status = superseded` và `superseded_by` trỏ sang dòng mới. Trace ghi `op: "supersede"` kèm `previous`.

Kết quả: không bao giờ có hai giá trị `current` cho cùng một slot, và vẫn truy được lịch sử thay đổi.

### D4. TTL (hạn dùng) của fact hoạt động thế nào?

- Bảng hạn theo slot: [memory.py:46 `TTL_DAYS`](../harness/memory.py#L46). Diện tích, trẻ nhỏ 365 ngày; size, màu, địa chỉ 180; ngân sách 90; sản phẩm đã tư vấn 60; giá đã báo, rào cản 30; hẹn gọi lại 14; slot khác 90.
- Lúc ghi: `expires_on = valid_from + TTL`.
- Lúc đọc: `current_facts(..., include_expired=True)` đánh dấu `expired`. `_build_brief` chuyển fact quá hạn sang `self.expired` và `stale_warnings` ([agent.py:158-161](../harness/agent.py#L158)).
- Fact quá hạn **chỉ được hỏi xác nhận**, không hỏi mở. Ví dụ địa chỉ cũ: [agent.py:635-641](../harness/agent.py#L635) hỏi "địa chỉ cũ bên em lưu là …, vẫn nhận ở đó đúng không ạ?". Đề cho phép không tính câu hỏi lại slot đã hết TTL là thừa.

### D5. "Truy vết nguồn gốc" fact là gì?

Mỗi fact có `source`: `call_1#turn3` (cuộc 1, lượt 3) hoặc `crm:<session_id>` (nhập từ CRM), kèm `session_id`, `valid_from`, `confidence` (1,0 khách nói rõ; 0,8 trích từ tóm tắt CRM).

### D6. `ns` (namespace) là gì? Vì sao xóa bộ nhớ ở đầu mỗi kịch bản?

Mọi bảng có cột `ns = <run_id>:<config>:<scenario_id>` ([run_eval.py:83](../run_eval.py#L83)). Nhờ vậy nhiều lần chạy, hai cấu hình và nhiều kịch bản dùng chung một file DB mà không lẫn nhau.

Đầu mỗi kịch bản có hai lệnh dọn ([run_eval.py:84-85](../run_eval.py#L84)), bảo vệ hai thứ khác nhau:

- `mem.wipe()` xóa namespace **của chính kịch bản đó**. Namespace đã tách các kịch bản với nhau, nên lệnh này chỉ có tác dụng khi chạy lại cùng `--run-id` (ví dụ `--run-id dbg`): không xóa thì dữ liệu của lần chạy trước còn nằm trong namespace và bị đọc lại. Mặc định `run_id` là thời điểm chạy nên hiếm khi trùng.
- `ToolBox.reset_world()` xóa trạng thái của **mock BTC**: đơn mới (`_ORDERS`), lịch hẹn, ticket, KM "mỗi khách một lần" (`_ONCE_USED`). Phần này **không có namespace**: nó là biến toàn cục trong tiến trình `mcp-commerce`, khóa theo SĐT, và một tiến trình phục vụ lần lượt nhiều kịch bản. Nhiều kịch bản cố ý dùng lại cùng khách CRM (T10, T11, SAMPLE). Không reset thì đơn của kịch bản trước hiện ra trong `order.status` của kịch bản sau, KM một lần bị coi là đã dùng, và mã đơn không còn bắt đầu từ `OD600001` như đáp án mong đợi.

### D7. `known`, `carried`, `expired` khác nhau thế nào?

| Trường của `CallSession` | Chứa gì | Dùng để |
|---|---|---|
| `carried` | Fact nạp từ phiên trước (chỉ bản full) | Tính `facts_used` (CCR): fact cũ nào được dùng lại |
| `known` | `carried` + mọi thứ khách nói trong cuộc này | Planner, và đưa vào prompt dưới tên `KNOWN` để LLM không hỏi lại |
| `expired` | Fact đã quá TTL | Chỉ hỏi xác nhận |

### D8. Khách yêu cầu xóa dữ liệu thì sao?

Router bật cờ `wants_data_deleted` → `_plan` gọi `forget_customer` ([agent.py:424-429](../harness/agent.py#L424)): xóa phiên, fact, báo giá; hồ sơ chuyển `deletion_requested` (giữ dấu vết của yêu cầu). Từ đó cuộc gọi không ghi gì nữa; lượt xóa ghi một dòng `op: "delete"` vào `memory_writes`. `end()` không lưu tóm tắt phiên.

### D9. Có chống "đầu độc bộ nhớ" (khách đưa thông tin sai) không?

Một phần:

- Giá khách tự nêu ("hôm trước em báo 4 triệu") không ghi vào bộ nhớ, và bị đưa vào tập số cấm đọc lại nếu không khớp báo giá hiện tại ([agent.py:257](../harness/agent.py#L257)).
- SĐT chung: không ghi khi chưa rõ là ai.

Chưa có: trạng thái `disputed` (đánh dấu fact mâu thuẫn với nguồn đáng tin hơn rồi kiểm lại bằng tool) như thiết kế ở [ARCHITECTURE.md](ARCHITECTURE.md) mục 3.1. Bảng `pii_vault` và `improvements` trong thiết kế cũng chưa có trong code.

### D10. Tóm tắt phiên (episodic) được viết thế nào?

[agent.py `end()`](../harness/agent.py#L827):

1. Dựng câu ghép từ dữ liệu: sản phẩm + giá, mã đơn, rào cản, lịch hẹn.
2. Gọi [summarizer.py](../core/llm/summarizer.py) để LLM viết 1–2 câu từ `FACTS` có cấu trúc. Code kiểm câu LLM: mọi số tiền phải nằm trong tập số được phép, độ dài trong giới hạn. Sai thì giữ câu ghép.
3. Lưu kèm rào cản (nếu chưa chốt), câu chưa trả lời, hành động tiếp theo.

[điểm yếu.md](../điểm%20yếu.md) nói "tóm tắt là ghép nguyên văn", "orders luôn rỗng", "open_questions luôn rỗng". Ba điểm này **đã sửa** ngày 14–15/10 ([THAY-DOI-2026-10-15.md](THAY-DOI-2026-10-15.md) mục 2.4 và 4). Khi chạy với `--generator offline` thì vẫn là câu ghép.

### D11. SQLite hay Postgres?

Mặc định SQLite (`data/memory.db`). Đặt `DATABASE_URL=postgresql+psycopg://…` để dùng Postgres, cho nhiều worker cùng ghi hoặc khi mở rộng. Đường Postgres mới chạy thử trên SQLite ([HARNESS.md](HARNESS.md) "Giới hạn hiện tại").

### D12. Bảng `turns` có ai đọc lại không?

Không. `log_turn` chỉ ghi ([agent.py:296](../harness/agent.py#L296)); không hàm nào đọc lại. Nó để dành cho giao diện dòng thời gian bộ nhớ (chưa làm).

---

## E. Hiểu lời khách (perceive và trích slot)

### E1. `perceive()` làm gì?

[textnorm.py:189](../harness/textnorm.py#L189), theo thứ tự:

1. Chuẩn hóa teencode / không dấu ("ko" → "không", "sp" → "sản phẩm", "dia chi" → "địa chỉ"), bảng `TEEN`.
2. Che CCCD và số tài khoản, giữ 4 số cuối (`mask_pii`).
3. Rút số tiền, SĐT (tìm trên câu đã che, để STK không bị nhận là SĐT), ngày giờ.

Trả `{raw, text, money, phone, when, pii_found}`.

### E2. Đọc số tiền tiếng Việt ("bốn triệu tám trăm chín mươi", "5tr2", "690k") ở đâu?

- `words_to_int` ([textnorm.py:44](../harness/textnorm.py#L44)): số bằng chữ, kể cả cách nói tắt ("năm triệu rưỡi" → 5.500.000, "năm triệu hai" → 5.200.000).
- `_num_from_compact` ([textnorm.py:76](../harness/textnorm.py#L76)): dạng gọn ("5tr2", "4tr890", "690k", "4.890.000đ").
- `find_money` ([textnorm.py:99](../harness/textnorm.py#L99)): tìm mọi số tiền trong câu, trả vị trí + giá trị.

Lỗi từng gặp: "45 **Tr**ần Hưng Đạo", "2024 **tr**ong" bị đọc là 45 triệu / 2024 triệu. Đã sửa: `tr` không được đứng trước chữ cái ([NHAT-KY](NHAT-KY-2026-10-08.md) mục 4.1).

### E3. Đầu vào là transcript ASR thì khác gì?

Chạy thêm `asr/itn.py: itn()` trước `perceive` ([agent.py:207-209](../harness/agent.py#L207)), vì Whisper viết số theo nhiều kiểu ("7,690.000", "hai mươi mét vuông"). Tên sản phẩm đọc sai ("xiao mi sờ mát bốn pờ rô") được bắt bằng bảng cách đọc `SPOKEN` trong [tools.py](../harness/tools.py#L65).

Dạng "1 triệu 590.000" của Whisper **chưa xử lý** (mất phần triệu), là nguyên nhân chính làm sai số tiền khi đo ASR ([DATASET.md](DATASET.md) mục 5).

### E4. Slot của khách được trích thế nào?

[extractor.py `customer_slots_rules`](../harness/extractor.py#L42) dùng regex cho từng slot. Phần khó nhất là **phân loại số tiền theo ngữ cảnh** (30 ký tự trước, 15 ký tự sau mỗi số):

| Ngữ cảnh | Slot |
|---|---|
| "bên kia", "Shopee", "Lazada" | `competitor_price_vnd` |
| "báo", "nói", "thấy", "còn" | `claimed_prices` (giá khách nói shop đã báo; không ghi vào bộ nhớ) |
| "ngân sách", "tầm", "khoảng", "tối đa" | `budget_vnd` |

Các slot khác: `room_area_m2`, `has_children` (`KIDS_RX`, tránh "màu be" và "bên em"), `size`, `color` (phải có chữ "màu"), `address` (`ADDRESS_RX`, cần cụm dẫn như "giao về", "địa chỉ là"), `payment`, `blocker`, `callback_requested`, `self_name`.

### E5. Ba chế độ bộ trích `rules` / `llm` / `hybrid` khác nhau thế nào?

| | Ai phân loại | Ai đọc giá trị | Khi LLM lỗi |
|---|---|---|---|
| `rules` (mặc định) | Regex | Regex | — |
| `llm` | LLM, đầu ra ép JSON Schema | Code đọc từ `span` (đoạn chữ nguyên văn LLM trích) | Dùng luật |
| `hybrid` | Luật + LLM | Như trên | Dùng luật |

Các kiểm tra của chế độ LLM ([llm_extract.py](../harness/llm_extract.py)):

- `span` không có trong câu (LLM bịa) thì bị loại và đếm vào `dropped_spans`.
- `hybrid` lấy **hợp** claim của luật và LLM, nên không bao giờ mất claim luật đã bắt. Bỏ sót claim sẽ làm HR thấp giả.
- Nhiệt độ 0 và cache theo mã băm request ([cache.py](../core/llm/cache.py)), nên chạy lại ra y hệt.

Chế độ `llm` / `hybrid` **chưa đo trên model thật** (cấu hình C và D phải chạy lại, [SO-SANH](SO-SANH-2026-10-15.md) mục 4).

### E6. Làm sao nhận ra khách đang nói sản phẩm nào, size nào?

[tools.py](../harness/tools.py):

- `_aliases` sinh mọi cách gọi một sản phẩm: tên đầy đủ, tên ngắn, mã SKU, cách đọc thương hiệu ("e pia" = AirPure), bỏ "smart / inverter".
- `find_products` khớp alias dài nhất trước, không khớp chồng.
- `find_variant` chọn biến thể theo size + màu. Nó **bỏ địa chỉ khỏi câu trước khi tìm size**, để số nhà "41 Trần Hưng Đạo" không bị hiểu là size 41.
- `find_color` khớp cụm dài nhất ("xanh navy" là `navy`, không phải `xanh`).

### E7. "Thứ hai tuần sau", "chiều mai" được đổi thành ngày giờ cụ thể ở đâu?

`parse_relative_datetime` ([textnorm.py:140](../harness/textnorm.py#L140)), tính từ ngày cuộc gọi. Không có giờ thì buổi sáng 09:00, chiều 15:00, tối 19:00. Slot `callback_requested` chỉ được đặt khi câu có "gọi lại / liên lạc / báo lại" ([extractor.py](../harness/extractor.py#L42)).

---

## F. Planner và tool

### F1. `_plan` dài gần 200 dòng. Đọc theo thứ tự nào?

[agent.py:378](../harness/agent.py#L378). Đi từ trên xuống, có nhiều chỗ `return` sớm:

1. Cập nhật `known`. Còn SĐT chung chưa rõ → `ask_identity` (dừng).
2. Tìm sản phẩm khách nhắc; "màng lọc"; "còn mẫu X thì sao" (so sánh); "lấy / thêm / chốt" (vào giỏ).
3. Lượt 1 của khách quay lại → `opening_returning` (+ `stale_promo`).
4. An toàn: hỏi máy hay người → `is_bot`; xóa dữ liệu → `data_deleted` (dừng); y tế / ngoài phạm vi → `handoff` (dừng); dò giá nhập → `refuse_internal`.
5. Đơn đã mua: đổi địa chỉ, đổi / trả (dừng, trừ khi quá hạn đổi trả), hỏi trạng thái đơn (dừng).
6. Chính sách → `policy_answer` hoặc `no_info`; hỏi bảo hành → số tháng của đúng sản phẩm.
7. Chưa có sản phẩm → `_recommend` (`ask_need` / `recommend` / `ask_product`).
8. Báo giá: hỏi size trước nếu giá / KM phụ thuộc size; ngừng bán → mẫu thay thế; so sánh → `alternative_quote`; hết hàng → `out_of_stock`; khách nhắc giá KM đã hết → `explain_price_change`.
9. Tổng giỏ, COD.
10. Mặc cả → `no_competitor_comment` hoặc `refuse_discount`.
11. Chốt đơn khi khách đồng ý và không còn đang hỏi.
12. Hẹn gọi lại / trì hoãn.
13. Không khớp gì → `greet` (lượt 1), `ask_repeat` (tối đa 2 lần), hoặc `closing`.

### F2. Gợi ý sản phẩm dựa trên gì?

[agent.py `_recommend`](../harness/agent.py#L356): đoán ngành hàng từ từ khóa (`CATEGORY_WORDS`). Máy lọc không khí mà chưa biết trẻ nhỏ / ngân sách thì hỏi nhu cầu trước. Lọc bỏ mẫu dưới 400.000đ, hết hàng, hoặc diện tích nhỏ hơn phòng khách. Chấm điểm: +2 nếu có khóa trẻ em khi nhà có trẻ nhỏ, −1 nếu vượt ngân sách 10%; hòa điểm thì lấy mẫu rẻ hơn.

### F3. Giá trong câu trả lời lấy từ đâu?

Luôn từ tool. [agent.py `_quote`](../harness/agent.py#L327) gọi `pricing.get_quote` + `inventory.check` rồi gom thành một báo giá:

- `public_view` bỏ mọi trường bắt đầu bằng `_`, ví dụ `_internal_price_floor_vnd` (giá sàn nội bộ, không được lộ).
- Bỏ KM phí ship / COD (`STACKABLE_SKIP`) khỏi danh sách "mã KM".
- Lưu báo giá vào bảng `quotes` để lần sau phát hiện KM hết hạn.

### F4. Lên đơn trải qua những kiểm tra nào?

[agent.py `_plan_order`](../harness/agent.py#L616), theo thứ tự:

1. Có sản phẩm chưa → không thì `ask_product`.
2. Đã rõ biến thể (size / màu) chưa → không thì `ask_variant`.
3. Đã đặt trùng chưa → `order_exists`.
4. Địa chỉ cũ quá hạn → hỏi xác nhận một lần.
5. Còn hàng không → `out_of_stock`.
6. COD mà tổng > 10 triệu → `cod_limit`.
7. Gọi `order.create` từng món với **giá lấy từ báo giá của tool**. Tool báo `price_mismatch` thì gọi lại một lần với giá tool yêu cầu ([agent.py:658-659](../harness/agent.py#L658)).

Thành công: nhớ `product_chosen`, `order_id`, `variant_sku`, `estimated_delivery`; đặt `outcome = chot_don`.

### F5. Khi nào planner coi là khách "đồng ý mua"?

Intent `place_order` **và** cờ `agrees_to_buy ≥ 0,5` ([agent.py:535](../harness/agent.py#L535)), và câu cuối không phải câu hỏi. Ngưỡng 0,5 sát nên có thể lên đơn sớm (GEN-T16).

Lưu ý: với router `rules`, mọi lượt có intent `place_order` đều được coi là đồng ý. Đây là một lý do số liệu chế độ `rules` chỉ dùng để bắt lỗi logic.

### F6. Đổi size / đổi sản phẩm / trả hàng được xử lý thế nào?

[agent.py `_plan_order_change`](../harness/agent.py#L685):

1. Tìm đơn khớp sản phẩm đã nhớ, không có thì lấy đơn cuối.
2. Quá **11 ngày** từ ngày đặt (xấp xỉ 7 ngày từ ngày nhận) → báo quá hạn đổi trả, chuyển sang tư vấn mua mới ([agent.py:695](../harness/agent.py#L695)).
3. Hỏi địa chỉ giao → `confirm_delivery_address`.
4. "Trả hàng / hoàn tiền" → `order.update(action="return")`.
5. Đổi size / sản phẩm: khách đang hỏi mà chưa đồng ý → báo trước (`exchange_offer`: còn hàng không, đổi lần đầu miễn phí); đồng ý → tạo yêu cầu.
6. `updates_done` nhớ yêu cầu đã tạo (khóa `(order_id, action, sku mới)`), nên khách xác nhận lại không tạo yêu cầu lần hai, và lượt sau hỏi "hoàn bao nhiêu" thì trả đúng số tiền.

### F7. Hẹn gọi lại rơi vào ngày nghỉ thì sao?

[agent.py `_plan_callback`](../harness/agent.py#L748): ngày rơi vào Chủ nhật hoặc ngày nghỉ (`mt.HOLIDAYS`) thì dời sang ngày kế, ghi lý do ("chủ nhật bên em nghỉ") để agent nói cho khách, rồi mới gọi `schedule.callback`. Hàm dời lịch của mock BTC có vài chỗ sai so với chính sách ([CAU-HOI-BTC.md](CAU-HOI-BTC.md) B1).

### F8. Khi nào chuyển máy cho người thật, và bàn giao kèm gì?

Khi intent là `out_of_scope` hoặc cờ `medical_question ≥ 0,7` ([agent.py:430](../harness/agent.py#L430)). Agent gọi `handoff.transfer` với brief từ [`_handoff_brief`](../harness/agent.py#L778) theo [schemas/handoff_brief.schema.json](../schemas/handoff_brief.schema.json): SĐT, tên, lý do chuyển, tóm tắt hội thoại, sản phẩm + giá đã báo, fact đã xác nhận, câu chưa trả lời, cảm xúc, việc nên làm tiếp.

Tóm tắt bằng LLM chỉ chạy khi generator là DeepSeek (`HANDOFF_SUMMARY=auto`). Với Qwen trên T4, lời gọi này cộng 10–13 s vào lượt đang chờ, nên dùng câu ghép 6 lượt gần nhất.

Đề tính chuyển máy đúng là Task Success cho ca `expected_outcome: "chuyen_may"`. Chuyển máy thừa bị đếm là vi phạm (`over_escalation`).

### F9. Tool lỗi hoặc timeout thì cuộc gọi có sập không?

Không:

- `ToolBox.call` bắt mọi ngoại lệ và trả `{"error": "tool_exception", "detail": …}` ([tools.py:38](../harness/tools.py#L38)). MCP có timeout 20 s (`MCP_TIMEOUT_S`).
- Planner đổi lỗi thành goal `order_failed` / `out_of_stock`.
- Câu mẫu và prompt (quy tắc 12) cấm đọc mã lỗi cho khách.
- `mcp-memory` lỗi hai lần liên tiếp thì lượt đó coi như khách chưa có bộ nhớ, ghi log ERROR, cuộc gọi tiếp tục ([memory.py `RemoteMemory._call`](../harness/memory.py#L226)).

### F10. Tool tham chiếu của BTC có lỗi không? Project xử lý thế nào?

Có. Nhóm ghi 26 mục trong [CAU-HOI-BTC.md](CAU-HOI-BTC.md). Các mục ảnh hưởng điểm: mã đơn SAMPLE-03 không sinh ra được (A1), SAMPLE-06 không có định danh (A2), `order.update` không có tham số địa chỉ (B4), script chấm dừng khi hệ thống không hỏi câu nào (C1), TSR tính cả lời gọi `order.create` bị lỗi (C2).

Nguyên tắc ([PLAN.md](PLAN.md) mục 2): **không né lỗi của BTC trong agent**. Nếu buộc phải né thì gom về một chỗ và ghi mã mục. Ví dụ: `_update_address` truyền địa chỉ mới qua `reason` vì tool không có tham số địa chỉ ([agent.py:608](../harness/agent.py#L608)).

### F11. Sao `catalog.search` không đi qua `ToolBox.call` như các tool khác?

`_recommend` gọi thẳng `mt.catalog_search` rồi tự thêm một dòng vào log tool ([agent.py:365-375](../harness/agent.py#L365)). Hệ quả: ở chế độ MCP, lời gọi này không qua `mcp-commerce`. Kết quả vẫn đúng vì cùng một hàm, nhưng không nhất quán với nguyên tắc "mọi tool qua MCP".

---

## G. Sinh câu trả lời và guardrail

### G1. Generator nhận gì và bị ràng buộc bởi quy tắc nào?

[generator.py `Generator.generate`](../core/llm/generator.py#L56) gửi cho LLM:

- **System prompt** `SYSTEM` với 12 quy tắc bắt buộc. Các quy tắc chính: mọi con số chỉ lấy từ FACTS; tối đa 1 câu hỏi mỗi lượt; không hỏi lại thông tin trong KNOWN; thiếu thông tin thì nói đúng cụm "em chưa có thông tin"; không nhận là người; không đọc mã SKU hay mã lỗi.
- **Dữ liệu lượt** (JSON): xưng hô, tên khách, câu khách vừa nói, intent, goals, facts, KNOWN, `GOAL_NOTES`.

`REPLY_STYLE=short` thêm quy tắc 13 (tối đa 2 câu, mỗi câu dưới 25 từ). Quy tắc này nhanh hơn nhưng làm mất "Dạ … ạ" và bỏ ý bắt buộc ([SO-SANH](SO-SANH-2026-10-15.md) mục 7.1).

### G2. `GOAL_NOTES` là gì, sao cần?

Ghi chú "phần bắt buộc phải nói" cho từng goal ([generator.py:31](../core/llm/generator.py#L31)). Ví dụ `order_updated`: phải nêu số tiền hoàn / bù và thời gian hoàn. Nó ra đời vì LLM chỉ nhận tên goal thì hay bỏ sót phần bắt buộc ([NHAT-KY](NHAT-KY-2026-10-08.md) mục 4.2).

Một số goal **chưa có** note (`no_competitor_comment`, `refuse_discount`, `refuse_internal`, `is_bot`), và đó là chỗ câu ngắn bị hỏng.

### G3. Guardrail kiểm những gì?

[guardrails.py `check`](../harness/guardrails.py#L46), không dùng LLM:

1. **Số tiền lạ:** mọi số tiền trong câu phải nằm trong tập "được phép".
2. **Lộ nội bộ:** giá nhập (đọc từ bảng trong `policy/ghi-chu-nhap-hang-NOI-BO.md`), giá sàn `_internal_*`, cụm "giá nhập / giá vốn / nhà cung cấp là…".
3. **Đọc lại giá sai khách nêu** (`forbidden_money`).
4. **PII:** CCCD hoặc dãy 9–14 số không phải SĐT.
5. **Nhận là người thật** (`HUMAN_RX`) và **chê đối thủ** (`COMPETITOR_RX`).

### G4. "Tập số tiền được phép" được dựng từ đâu?

[agent.py:243-253](../harness/agent.py#L243): số khách vừa nói + slot số đã biết + mọi số ≥ 1.000 trong kết quả tool của lượt (trừ trường `_`) + báo giá phiên trước (`prev_quotes`) + số trong FACTS + số trong đoạn chính sách đã tra + số nằm trong chuỗi của FACTS (ví dụ tên KM "… đơn từ 500k").

**Tập số cấm** ([agent.py:257](../harness/agent.py#L257)): giá khách nêu mà không khớp báo giá hiện tại và không có trong kết quả tool của lượt.

### G5. Guardrail chặn rồi thì sao?

[agent.py:273-288](../harness/agent.py#L273):

1. Sinh lại **một lần**, lời nhắc ghi rõ lý do và **đúng con số phải bỏ**.
2. Bản mới qua guardrail → dùng (`guardrail.action = "regenerated"`).
3. Vẫn sai → câu mẫu của goal (`"safe_template"`).

Mọi bản nháp bị chặn lưu trong `guardrail.rejected` để phân tích lỗi.

### G6. LLM lỗi, trả rỗng, hoặc trả sai định dạng thì khách nghe gì?

| Tình huống | Xử lý | Ở đâu |
|---|---|---|
| Generator ném lỗi (timeout, mất mạng, vLLM chết) | Câu mẫu, `action = "llm_error_template"` | [agent.py:261-267](../harness/agent.py#L261) |
| LLM trả chuỗi rỗng | Câu mẫu | [generator.py:75](../core/llm/generator.py#L75) |
| DeepSeek trả câu còn sót mã che `[SĐT_1]` | Câu mẫu | [generator.py:79](../core/llm/generator.py#L79) |
| Router lỗi / JSON hỏng | Luật từ khóa, ghi `fallback` | [router.py:62-66](../core/llm/router.py#L62) |
| JSON ép schema bị hỏng (vLLM) | Thử lại một lần bằng `json_object` | [deepseek.py `json`](../core/llm/deepseek.py#L78) |
| Câu khách không hiểu được | Xin nói lại (`ask_repeat`, tối đa 2 lần) | [agent.py:565-570](../harness/agent.py#L565) |

### G7. Che PII khi gửi model ngoài thế nào?

[core/pii.py `Redactor`](../core/pii.py#L31): trước khi gửi DeepSeek / Jev, SĐT và địa chỉ được thay bằng mã `[SĐT_1]`, `[ĐỊA_CHỈ_1]`. Nó tìm theo tên trường, regex SĐT, cụm dẫn ("giao về…") và mẫu "số nhà Tên, Quận, Tỉnh". Câu trả lời được `restore()` về giá trị thật. CCCD / STK đã che từ bước perceive và không bao giờ khôi phục.

Qwen chạy local nên **không che** (dữ liệu không rời máy). File log che một chiều qua `mask_for_log`; trace JSONL cho BTC chấm giữ nguyên.

Kiểm tra: [tests/pii_check.py](../tests/pii_check.py), 544 request gửi ra ngoài, 0 SĐT / địa chỉ lọt.

### G8. Guardrail có kiểm "những gì bắt buộc phải nói" không?

Không. Guardrail chỉ chặn cái **không được nói**. Câu thiếu "em chưa có thông tin" hay thiếu "hàng chính hãng" vẫn qua, dù script BTC chấm `agent_must_say` / `must_say_any`. Phần này đang dựa vào `GOAL_NOTES` ([HAM-GUARDRAILS.md](HAM-GUARDRAILS.md) mục 3).

### G9. Sao giá khuyến mãi cũ đôi khi lọt qua guardrail?

Tập số được phép gồm cả báo giá phiên trước (`prev_quotes`, [agent.py:248-249](../harness/agent.py#L248)). Nếu LLM đọc giá KM cũ thành giá hiện tại, con số đó vẫn "được phép" nên không bị chặn (SAMPLE-05, [SO-SANH](SO-SANH-2026-10-15.md) mục 7.1). Tập số cấm chỉ chứa giá **khách** nêu.

### G10. Agent có thể tự nhận là người thật không?

Bị chặn ở ba lớp: quy tắc 5 trong prompt; goal `is_bot` khi khách hỏi ("Dạ em là trợ lý AI của shop…"); guardrail `HUMAN_RX` ở đầu ra. Bộ trích cũng ghi claim `is_human`, để script BTC đếm vi phạm `claims_human` nếu có.

---

## H. Trace và chấm điểm

### H1. Một dòng trace có những gì?

Mỗi lượt khách là một dòng JSON ([agent.py:305-316](../harness/agent.py#L305)), theo [schemas/trace_log.schema.json](../schemas/trace_log.schema.json):

| Trường | BTC dùng để |
|---|---|
| `customer_text`, `agent_text` | PII, `must_say_any`, câu "không có thông tin" |
| `questions[]` | RQR |
| `facts_used[]` | CCR |
| `claims[]` | HR, `forbidden_claims`, `is_human` |
| `tool_calls[]` | TSR, CCR (tên tham số), chuyển máy thừa |
| `memory_writes[]` | PII trong bộ nhớ, `memory_expectation` |
| `latency` | TTFT, total |
| `call_brief`, `call_brief_latency_ms` (lượt 1) | Độ trễ Call Brief |

Các trường thêm cho phân tích lỗi (BTC bỏ qua): `router`, `goals`, `guardrail`, `llm_usage`, `extractor`, `latency.parts`.

### H2. Vì sao luôn nhắc "bộ trích không được ăn gian"?

`questions` và `claims` do chính hệ thống khai. Nếu bộ trích bỏ sót câu hỏi thì RQR thấp giả; bỏ sót claim thì HR thấp giả. BTC chấm tay ngẫu nhiên 20 lượt để kiểm ([README.md](../README.md) "Quy trình chấm chéo" bước 3).

Vì vậy luật chỉ được sửa khi câu bị hiểu sai nghĩa, không được bỏ claim đúng nghĩa ([NHAT-KY](NHAT-KY-2026-10-08.md) mục 4.1), và `hybrid` luôn giữ hợp claim. Việc đối chiếu tay ~20 lượt **vẫn chưa làm**.

### H3. RQR được tính chi tiết thế nào?

[reference_eval.py:61](../eval/reference_eval.py#L61), chỉ tính ở cuộc gọi có `must_not_ask`. Một câu hỏi là thừa khi:

- nó là câu **mở** về slot nằm trong `must_not_ask`; hoặc
- nó là câu **xác nhận** lần thứ 2 trở đi về cùng slot trong cùng cuộc.

Phía mình, [extractor.agent_questions](../harness/extractor.py#L100):

- chỉ nhận câu **kết thúc bằng "?"** (chế độ `rules`);
- gán slot bằng từ khóa `SLOT_KW`;
- câu nhắc đúng giá trị đã biết hoặc có "đúng không / vẫn lấy…" là `confirm`, còn lại `open`.

Lỗi script BTC: hệ thống không hỏi câu nào thì RQR = `None` và script dừng vì `TypeError` (CAU-HOI-BTC C1).

### H4. CCR được tính chi tiết thế nào?

[reference_eval.py:88](../eval/reference_eval.py#L88): fact "được dùng" nếu nằm trong `facts_used` **hoặc** trùng **tên** một tham số tool. Script không xét giá trị (CAU-HOI-BTC C3).

Phía mình, [extractor.facts_used](../harness/extractor.py#L177) so **giá trị** của fact cũ (`carried`) với lời agent hoặc tham số tool. Số → có trong số tiền của câu hoặc "N m²"; `has_children` → câu nhắc "bé / trẻ nhỏ"; `blocker` → câu nhắc "anh nhà / người nhà / trao đổi…"; `product_advised` → mã trong tham số tool hoặc tên trong câu. Đề cảnh báo không được đọc vẹt mọi fact cũ vào câu chào để lấy điểm.

### H5. TSR được chấm thế nào?

Nhị phân bằng assertion trong `success_if` của từng cuộc ([reference_eval.py `check_call`](../eval/reference_eval.py#L123)). Ví dụ: đã gọi `order.create` với `sku` và `price_vnd` khớp; đã gọi `handoff.transfer` với brief đủ trường; có nói cụm "không có thông tin"; không có claim cấm; trace không chứa mẫu PII. Một kịch bản đạt khi **mọi** cuộc gọi có `success_if` đều đạt. Có báo riêng TSR cho ca khó.

### H6. HR được chấm thế nào? Sao có claim đúng vẫn bị tính sai?

[reference_eval.py:224](../eval/reference_eval.py#L224): chỉ tính claim có `field` trùng một khóa trong `ground_truth_facts` của cuộc gọi; khác giá trị là sai. Field bắt đầu bằng `price` / `promo` / `list_price` tính vào HR giá & KM.

Vì mỗi cuộc gọi chỉ có **một** `price_vnd`, agent báo đúng giá của hai sản phẩm thì claim thứ hai bị tính sai (CAU-HOI-BTC C4, GEN-T10-01). Tên field cũng phải khớp cách BTC đặt tên (A5).

### H7. "Vi phạm guardrail" trong report BTC và `guardrails.py` của mình có phải một?

Không. Report BTC ([reference_eval.py:188](../eval/reference_eval.py#L188)) đếm trên trace: PII trong `agent_text` / `memory_writes`, chuyển máy thừa, claim `is_human = true`, mẫu cấm `trace_must_not_match`. `guardrails.py` là lớp chặn của mình **trước khi** câu tới khách. Lớp chặn tốt thì số vi phạm trong report bằng 0 (hiện đang 0 ở mọi lần đo).

### H8. TTFT và total latency đo từ đâu tới đâu?

[agent.py:297-304](../harness/agent.py#L297):

- **TTFT** = thời gian từ lúc nhận câu khách tới lúc bắt đầu gọi generator (perceive, trích slot, router, planner, dựng prompt) + thời gian LLM ra token đầu tiên.
- **Total** = tới khi câu trả lời **đã qua guardrail** (gồm cả sinh lại).
- **`post_ms`** (trích questions / claims + ghi bộ nhớ) ghi riêng, không cộng vào total, vì khách đã nhận câu trả lời.
- **`parts`**: thời gian từng bước, dùng để biết chậm ở đâu.

Cách đo thống nhất của BTC: [eval/huong-dan-do-latency.md](../eval/huong-dan-do-latency.md).

### H9. Sao chạy lại cùng lệnh mà số lệch vài điểm?

Generator chạy ở nhiệt độ 0,3, nên câu chữ đổi và claim / câu hỏi đổi theo. Cache chỉ áp cho lời gọi JSON nhiệt độ 0 (router `qwen`, bộ trích LLM, tóm tắt), không áp cho generator. Qua 3 lần chạy liên tiếp, RQR dev dao động 0–5,4% và HR giá 2,2–3,4%. [PLAN.md](PLAN.md) cuối file đề xuất báo trung bình nhiều lần chạy kèm khoảng dao động.

### H10. Điểm "Calls-to-Close" và "số lượt TB / cuộc" là gì?

- **Calls-to-Close:** đơn được tạo ở cuộc gọi thứ mấy (M2, script tính sẵn).
- **Số lượt TB / cuộc:** đếm số dòng trace. Vì lượt khách viết sẵn nên baseline và hệ thống luôn bằng nhau; dòng này trong bảng A.6 không phân biệt được hai cấu hình (CAU-HOI-BTC C7).

---

## I. Dữ liệu, ASR, RAG

### I1. Dataset của nhóm được sinh thế nào?

[DATASET.md](DATASET.md) mục 3, [datagen/README.md](../datagen/README.md):

```
datagen/templates/*.json (27 template, chỉ chứa ràng buộc)
  → resolver.py     chọn khách, sản phẩm, ngày thỏa ràng buộc; mọi con số lấy từ mock_tools
  → validate.py     kiểm đáp án khớp tool BTC (0 lỗi / 67 kịch bản)
  → naturalize.py   DeepSeek viết lại lời khách; chỉ nhận khi giữ đủ số, sản phẩm, tên riêng
  → run_eval.py     chạy chính hệ thống → lời nhân viên
  → export_transcripts.py → dataset/transcripts (134 cuộc)
  → make_audio.py   edge-tts + nhiễu điện thoại → dataset/audio (120 cuộc, 2,07 giờ)
```

Kết quả LLM viết lại lưu ở `datagen/out_nat/rewrites.json`, nên bộ test không đổi giữa các lần chạy.

### I2. Vì sao chia dev / test theo template, không theo kịch bản?

Để câu chữ của bộ test không rò sang lúc sửa lỗi trên dev. Việc chia làm trong từng nhóm ca khó: nhóm có ≥ 2 template thì có template ở cả hai bên; nhóm chỉ có 1 template thì chia theo bản sinh ra ([datagen/README.md](../datagen/README.md) "Nguyên tắc").

### I3. Dataset có hạn chế gì?

[DATASET.md](DATASET.md) mục 6:

- edge-tts chỉ có 2 giọng chuẩn, nên chỉ tiêu "2 miền" chưa đạt.
- Audio tổng hợp, đọc rõ, không ngắt lời; WER thấp hơn thực tế.
- Lời nhân viên do chính hệ thống sinh, nên mang theo lỗi của hệ thống.
- Lượt khách viết sẵn, không phản ứng theo lời nhân viên.
- Đa kênh sát ngưỡng (10 khách).
- Bộ tự sinh có thể dễ hơn bộ ẩn ([điểm yếu.md](../điểm%20yếu.md) "Làm gì với rủi ro này").

### I4. ASR chạy thế nào, kết quả ra sao?

[asr/transcribe.py](../asr/transcribe.py): faster-whisper (hoặc PhoWhisper) chạy local, tên sản phẩm làm `initial_prompt`; hậu xử lý bằng [asr/itn.py](../asr/itn.py) (chữ → số, trích thực thể); xuất `hypotheses.json` để `reference_eval.py --asr` chấm.

Con số nên báo là **tập chưa dùng khi sửa luật**: WER 13,5%, CER 8,8%, Entity Accuracy 42,9% (số tiền 46,2%). Chưa có audio của BTC, chưa có số riêng cho SĐT ([DATASET.md](DATASET.md) mục 5).

### I5. RAG chính sách làm thế nào?

[rag.py](../harness/rag.py):

1. Tách `policy/*.md` theo mã mục `## [XX-nn]` thành 99 chunk, gắn cờ `restricted` (tài liệu NỘI BỘ), `superseded` (HẾT HIỆU LỰC), `noise` (nội quy nhân viên).
2. Tìm lai: BM25 trên văn bản bỏ dấu (câu hỏi được thêm mã SKU của sản phẩm được nhắc) + vector (`bge-m3`, máy yếu tự lùi xuống `multilingual-e5-small`, rồi BM25).
3. Gộp hai bảng xếp hạng bằng RRF; tùy chọn xếp hạng lại bằng cross-encoder.
4. `search()` cho agent bỏ chunk nội bộ.

Kết quả trên 60 câu BTC: Recall@3 93,2%, Recall@5 93,2%, từ chối đúng câu nội bộ 100% ([NHAT-KY](NHAT-KY-2026-10-08.md) mục 6).

### I6. Sao chunk theo mã mục mà không cắt theo số ký tự?

`chunk_id` trùng nhãn BTC dùng để chấm Recall@k, nên không cần ánh xạ. Mỗi mục là một ý trọn vẹn. Văn bản đưa vào index kèm tên tài liệu, vì bảng giá nhập hay bảng thông số chỉ có nghĩa khi biết thuộc tài liệu nào ([ARCHITECTURE.md](ARCHITECTURE.md) mục 5.3).

### I7. "Chính sách cũ vẫn đúng cho đơn cũ" có chạy trong hội thoại không?

Chưa. `rag._allowed` chỉ cho dùng bản hết hiệu lực khi truyền `order_date` trước 01/10/2026 ([rag.py:250](../harness/rag.py#L250)), nhưng agent **chưa bao giờ truyền `order_date`** khi gọi `knowledge.search`. Vì vậy agent luôn trả lời theo bản đang hiệu lực. Luật này hiện chỉ được đo ở `run_rag_eval.py`.

### I8. Tài liệu nội bộ (giá nhập, nhà cung cấp) được chặn ở mấy lớp?

1. **RAG:** `search()` bỏ chunk `restricted`, nên nội dung không vào prompt.
2. **Router:** cờ `asks_internal_cost` → goal `refuse_internal`.
3. **Guardrail:** chặn số trùng giá nhập (`IMPORT_PRICES`), giá sàn `_internal_*`, và cụm "giá nhập / giá vốn / nhà cung cấp là…".
4. **`public_view`:** bỏ trường `_…` khỏi kết quả tool trước khi đưa cho LLM.

---

## J. Chạy, debug, hạ tầng

### J1. Muốn chạy thử ngay, không có mạng, không có khóa API?

```bash
bash tests/smoke.sh
```

Lệnh này chạy router `rules` + generator `offline` trên 7 kịch bản mẫu, chấm bằng script BTC, rồi dựng server API giả ([tests/fake_api_server.py](../tests/fake_api_server.py)) để kiểm đường Jev / DeepSeek / Qwen thật. Số ở chế độ offline **chỉ để bắt lỗi logic**.

### J2. Lệnh BTC dùng để chấm là gì?

```bash
python run_eval.py --scenarios test_set/public_sample --config full --out runs/r0/full.jsonl
python run_eval.py --scenarios test_set/public_sample --config baseline_no_memory --out runs/r0/baseline.jsonl
python eval/reference_eval.py --scenarios test_set/public_sample --trace runs/r0/full.jsonl --baseline runs/r0/baseline.jsonl
```

Các cờ của `run_eval.py`: [HARNESS.md](HARNESS.md) mục "Lệnh BTC chạy".

### J3. Một kịch bản bị trượt, debug thế nào?

```bash
python run_eval.py --scenarios test_set/public_sample --config full --out runs/dbg/full.jsonl --only SAMPLE-03 -v
grep -n "WARNING\|ERROR" runs/dbg/full.log
grep -n "SAMPLE-03 call_2 t2" runs/dbg/full.log
```

Cạnh trace có `<out>.log` (log từng lượt, mỗi dòng có nhãn `[kịch bản call_N tK]`), `<out>.errors.jsonl` (traceback đầy đủ khi có lỗi), `<out>.config.json` (cấu hình, commit). Log che SĐT / địa chỉ ([HAM-LOG.md](HAM-LOG.md)).

Thứ nên xem trong một dòng trace: `router` (intent đúng chưa), `goals` (planner chọn gì), `tool_calls` (tham số), `guardrail.rejected` (bản nháp bị chặn), `questions` / `claims` (bộ trích đọc đúng không).

### J4. Chạy `--workers N` song song có lẫn dữ liệu không?

Không. Mỗi kịch bản có namespace bộ nhớ riêng, mỗi worker tự mở bộ MCP server riêng (trạng thái mock tách theo tiến trình), và log gom theo kịch bản rồi mới ghi file ([core/log.py `capture`](../core/log.py#L72)). Lưu ý bộ nhớ máy: mỗi worker nạp một bản `bge-m3` (~2,3 GB).

### J5. Qwen, vLLM, Kaggle để làm gì?

- **Qwen** là LLM chạy local, thay DeepSeek / Jev. Chạy toàn bộ LLM local được điểm thưởng (tiêu chí G).
- **vLLM** là server phục vụ Qwen. Mọi worker gửi HTTP tới một server, không nạp model trong tiến trình.
- **Kaggle** cho GPU T4 miễn phí (30 giờ / tuần mỗi tài khoản).

Một lệnh chạy trọn bộ: [scripts/run_suite.py](../scripts/run_suite.py) (bật vLLM, chạy hai cấu hình, chấm, ghi `summary.md`). Khác biệt theo nơi chạy nằm trong `profiles/*.env`, chọn bằng `RUN_PROFILE`. Đẩy job lên Kaggle: [scripts/kaggle_job.py](../scripts/kaggle_job.py). Chi tiết và nhật ký các job: [CHAY-KAGGLE-SERVER.md](CHAY-KAGGLE-SERVER.md).

### J6. Sao Qwen chậm hơn DeepSeek nhiều vậy?

Trên T4, Qwen3-4B fp16 sinh khoảng 19 token/giây mỗi request, giới hạn bởi băng thông bộ nhớ. Khoảng 81% thời gian một lượt là phần sinh nốt câu ([SO-SANH](SO-SANH-2026-10-15.md) mục 6.2). Các cách đã thử: bỏ AWQ dùng fp16 (có ích), 1 worker, 2 bản Qwen, câu ngắn (nhanh nhất nhưng giảm chất lượng). Speculative n-gram làm vLLM 0.9.2 sập trên T4.

### J7. Thư mục `tests/` kiểm những gì?

| File | Kiểm |
|---|---|
| `smoke.sh` | Chạy tất cả bên dưới + 7 kịch bản mẫu offline + đường API thật qua server giả |
| `mcp_check.py` | 2 MCP server: đủ tool, từ chối sai kiểu, kết quả bằng gọi trực tiếp, supersede, baseline không đọc được, `ro` không ghi được |
| `mcp_parity.py` | Trace qua MCP giống hệt gọi trực tiếp |
| `pii_check.py` | Không SĐT / địa chỉ nào ra API ngoài hay vào log; ghép lại đúng |
| `llm_extract_check.py` | Bộ trích LLM (16 kiểm tra, không cần GPU) |
| `fake_api_server.py` | Giả lập Jev, DeepSeek, vLLM |

---

## K. Chỗ còn thiếu và chỗ dễ vấp

### K1. Phần nào của đề chưa làm?

| Hạng mục | Tiêu chí | Trạng thái |
|---|---|---|
| Cơ chế cải tiến (Knowledge Gap Loop / Exemplar Bank) + 2 vòng đo + người duyệt + quay lui | 5 (13%) | Chưa có code. Thiết kế ở [ARCHITECTURE.md](ARCHITECTURE.md) mục 5.4, kế hoạch ở [PLAN.md](PLAN.md) "Tuần 3" |
| Giao diện web (khung chat, Call Brief, dòng thời gian bộ nhớ) + demo 2 cuộc gọi | 6 (13%) | Chưa có |
| Báo cáo, phân tích ≥ 10 ca sai, video, slide | 4, 8 | Chưa có (đã có nhiều phân tích lỗi rải trong `NHAT-KY`, `SO-SANH`) |
| Giọng vùng miền trong audio | 1 | Chưa đạt |
| WER trên audio BTC, Entity Accuracy riêng cho SĐT | 1, 4 | Chưa có audio / dữ liệu |
| Đối chiếu tay ~20 lượt của bộ trích | 4 | Chưa làm |

### K2. Lỗi đã biết trong code mà chưa sửa

| Lỗi | Hậu quả | Nguồn |
|---|---|---|
| Sau `return`, câu "ok làm thủ tục" rơi vào nhánh đổi size → hỏi size | Câu hỏi thừa (GEN-T12-02) | [SO-SANH](SO-SANH-2026-10-15.md) mục 7.1 |
| Giá đã báo phiên trước nằm trong tập số được phép | Giá KM cũ đọc thành giá hiện tại không bị chặn (SAMPLE-05) | mục G9 ở trên |
| Generator Qwen không kiểm `TOKEN_RX` | Qwen bịa mã kiểu "[MÃ ĐƠN_1]" mà vẫn tới khách (GEN-T04-03) | [generator.py:77-80](../core/llm/generator.py#L77) |
| Bất kỳ "bảo hành N tháng" nào cũng thành claim `warranty_months` | Câu nhắc gói mở rộng / sản phẩm khác bị tính là bịa | [HAM-EXTRACTOR.md](HAM-EXTRACTOR.md) mục 3 |
| Chat không có ID: không gắn được khách kể cả khi khách đọc SĐT | Mất bộ nhớ của cuộc chat | mục C4 ở trên |
| Agent chưa truyền `order_date` khi tra chính sách | Luôn trả lời theo chính sách mới | mục I7 ở trên |
| GEN-T16-02 (4 sản phẩm vượt COD) trượt ở mọi cấu hình Qwen | Chưa phân tích | [SO-SANH](SO-SANH-2026-10-15.md) mục 8 |

### K3. Đáp án đòi một slot mà hệ thống không bao giờ ghi / trích

Theo [điểm yếu.md](../điểm%20yếu.md):

- `must_carry_over: objection`, `baby_age`: hệ thống không ghi hai slot này vào bộ nhớ, nên CCR bị chặn trần.
- `must_not_ask: baby_age`, `household_size`, `owned_product`: `SLOT_KW` không có ba slot này, nên agent hỏi "bé mấy tháng" bị xếp vào `other` và không bao giờ bị tính thừa. RQR thấp giả, đúng loại lỗi BTC chấm tay.
- `ground_truth_facts: restock_date`, `refund_vnd`, `total_vnd`, `order_id`…: không có field claim tương ứng, nên các khẳng định này không được chấm.

Đề xuất bổ sung các slot này đang chờ quyết định.

### K4. Những chỗ trong code dễ gây hiểu nhầm

- `CallSession.config` và `self.blockers` được gán nhưng không dùng. Baseline do `mem.read_enabled` quyết định, không phải `config`.
- Tham số `route` trong `_remember`, biến `full` trong `_resolve_candidate`, biến `out` trong `_update_address` không dùng.
- `perceive()["when"]` không được agent dùng; ngày hẹn do bộ trích tự tính.
- `rag.touches_restricted` không có nơi nào gọi.
- `knowledge.spent_ms` là biến toàn cục, `turn()` đặt về 0 trước `_plan` và đọc lại sau.
- `harness/agent.py` và `tools.py` đọc thẳng thành phần nội bộ của mock BTC (`_parent`, `PRODUCTS`, `PROMOS`, `HOLIDAYS`, `_ORDERS`). BTC đổi tên thì phải sửa theo.
- Code đã bỏ hết comment "vì sao" (commit `ec08d2f`). Lý do nằm trong `docs/` (HAM-*, THAY-DOI, SO-SANH, NHAT-KY).

### K5. Tài liệu nào đã cũ?

- [điểm yếu.md](../điểm%20yếu.md): các mục "orders luôn rỗng", "open_questions luôn rỗng", "tóm tắt là ghép nguyên văn", "câu mẫu đọc mã lỗi", "generator sập thì lượt sập", "ASR rác thì chào kết thúc" đã sửa ngày 14–15/10 ([THAY-DOI](THAY-DOI-2026-10-15.md) mục 4). Mục "sentiment gán cứng" chỉ còn đúng khi không dùng LLM tóm tắt.
- [Hướng dẫn cài đặt và chạy SUDO CODE.md](../Hướng%20dẫn%20cài%20đặt%20và%20chạy%20SUDO%20CODE.md): còn nhắc repo `SUDOCODE_task` và nhánh `claude/sleepy-albattani-aqjrof`; repo đang dùng là `SudoCode`.
- [ARCHITECTURE.md](ARCHITECTURE.md) mục 3 và 4.1: mô tả thiết kế (bảng `pii_vault`, `improvements`, trạng thái `disputed`, các file `perceive.py`, `brief.py`, `trace.py`…). Code thật gộp phần lớn vào `agent.py` và chưa có các bảng đó.
- `HAM-*.md`: số dòng trước commit xóa comment.

---

## L. Câu giám khảo có thể hỏi khi phản biện

Mỗi câu kèm chỗ đã trả lời trong file này.

| Câu hỏi | Xem |
|---|---|
| Baseline khác hệ thống ở đâu, có công bằng không? | A5 |
| Làm sao chắc agent không bịa giá? | B2, F3, G3–G5 |
| Đưa gì vào prompt, cắt gì khi ngữ cảnh dài? | B5, G1. Toàn bộ lịch sử phiên cũ không vào prompt, chỉ có KNOWN + facts + 4 lượt gần nhất cho router ([agent.py:229](../harness/agent.py#L229)) |
| Khi nào gọi tool, khi nào không? | F1 (planner quyết định theo intent và câu khách) |
| Tool timeout, ASR ra rác, LLM sai định dạng: khách nghe gì? | F9, G6 |
| Khi nào chuyển máy, bàn giao kèm gì? | F8 |
| Khách đổi ý thì bộ nhớ thế nào? | D3 |
| Ghi gì, không ghi gì? | D2 |
| Hai người chung SĐT? | C5 |
| Vì sao MCP mà không A2A? Một tình huống MCP giúp cụ thể? | B6 |
| Bộ trích có ăn gian không? Trích bằng cách nào? | E5, H2, H3 |
| Con số có tái lập được không? Dao động bao nhiêu? | H9, J2 |
| Vì sao planner là code? Có cứng quá không? | B2 |
| Xử lý PII khi gửi model ngoài? | G7 |
| Chi phí mỗi cuộc gọi? | Chưa tính. Trace có `llm_usage` (token) để tính ([PLAN.md](PLAN.md) "Tuần 4") |
| Mở rộng thêm ngành hàng / kênh mới thế nào? | Ngành hàng: thêm vào catalog + `CATEGORY_WORDS`, `NAME_PREFIXES`. Kênh: thêm loại định danh ở `start()` / `_bind`. Bộ nhớ: SQLite → Postgres giữ nguyên schema (D11) |
| Hạn chế lớn nhất là gì? | K1–K3, I3 |
