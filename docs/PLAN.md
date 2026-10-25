# Kế hoạch còn lại — Vòng 1

Lập ngày 01/10/2026, sau khi đọc lại `debaiSUDO.md` và `DIEU-CHINH-DE.md`, đối chiếu với code trên nhánh `claude/sleepy-albattani-aqjrof`.
Hạn nộp: BTC chưa công bố. Lịch dưới đây tính 4 tuần; khi có hạn thì co giãn, **giữ nguyên thứ tự ưu tiên**.
Cập nhật 04/10/2026: bảng hiện trạng theo kết quả tuần 1 (MCP, PII, ASR); gộp câu hỏi gửi BTC vào `docs/CAU-HOI-BTC.md`; chuyển việc sửa lỗi SAMPLE-06 lên tuần 0. Cùng ngày: làm xong tuần 2 (dataset, audio, ASR, RAG) — xem mục "Tuần 2".

## 1. Hiện trạng so với đề

✅ đã có · 🟡 có một phần · ❌ chưa có. Cột "Tiêu chí" là hệ số chấm ở mục G.

| Hạng mục (mục đề) | Yêu cầu M1 | Hiện trạng | Tiêu chí |
|---|---|---|---|
| Kịch bản đa phiên (C.1, C.4) | ≥ 20 kịch bản + ≥ 5 ca khó; ≥ 30 khách đa phiên; ≥ 10 khách đa kênh | ✅ 67 kịch bản (45 dev / 22 test), 27 template, `validate.py`; lượt khách đã viết lại cho tự nhiên (`datagen/out_nat`); 52 khách đa phiên, 10 khách đa kênh | 1, 4 |
| Transcript hội thoại (C.1) | ≥ 120 cuộc dạng transcript | ✅ 134 cuộc hai phía, 870 lượt (`dataset/transcripts`), lời nhân viên do hệ thống sinh với model thật | 1 |
| Audio (C.1) | ≥ 40 cuộc / ≥ 1 giờ | ✅ 120 cuộc, 2,07 giờ, 28% có nhiễu (edge-tts). ❌ chỉ tiêu "2 miền": edge-tts không có giọng vùng miền | 1 |
| ASR + ITN + WER/CER (C.1, A.5, ĐC-8) | ASR local, WER/CER/Entity Acc trên audio BTC + ≥ 20 file nhóm | 🟡 đo trên 48 file của nhóm (faster-whisper `small`): WER 13,5%, CER 8,8%, **Entity Accuracy số tiền 46%** trên tập chưa dùng khi sửa luật; chưa đo trên audio BTC (gói chưa kèm audio); chưa có số riêng cho SĐT | 1, 4 |
| Teencode, trích xuất có cấu trúc | intent, SP, size/màu, giá đã báo, hẹn gọi lại, người quyết định, kết quả | ✅ luật (`textnorm.py`, `extractor.py`) — chưa đối chiếu tay | 1 |
| PII (C.1) | Che SĐT/CCCD/địa chỉ khi lưu log **và khi gửi model ngoài** | ✅ CCCD/STK che trong log; SĐT/địa chỉ đổi thành token trước khi gửi DeepSeek/Jev (`tests/pii_check.py`) | 1, guardrail |
| Bộ nhớ 4 tầng (C.1) | working/episodic/profile/KB; ghi gì–không ghi gì; khách đổi ý | ✅ 3 tầng SQL + supersede + TTL + nguồn gốc. ✅ KB: RAG lai vector + BM25 (`harness/rag.py`), Recall@3 91,5% / @5 93,2% trên 60 câu BTC | 2 |
| Session Continuity (C.2) | nhận diện, Call Brief, mở đầu tiếp nối, không hỏi lại | ✅ (`_build_brief`, kiểm tra KM/giá/tồn kho lúc nhận diện) | 2 |
| Tool (C.2, ĐC-3) | ≥ 3 tool, giá từ tool | ✅ đủ 9 tool BTC qua `mock_tools`, gọi qua `mcp-commerce` | 2 |
| Guardrail, fallback, chuyển máy | | ✅ guardrail số tiền/PII/nội bộ, router fallback, `handoff.transfer` | 2 |
| **MCP hoặc A2A (C.3)** | ≥ 2 MCP server, bắt buộc `mcp-memory` | ✅ `mcp-memory` + `mcp-commerce` (stdio), có chế độ chỉ đọc; trace qua MCP giống hệt gọi trực tiếp (`tests/mcp_parity.py`) | **3 (15%)** |
| Script đánh giá + baseline (C.4) | 1 lệnh, 5 chỉ số, baseline không bộ nhớ | ✅ `run_eval.py` + `reference_eval.py`, 2 cấu hình | 4 |
| **Số liệu thật** | | ✅ 08/10: chạy `full` + `baseline_no_memory` với Jev/DeepSeek thật trên `test_set/public_sample` (`runs/r1/`) và `datagen/out_nat/{dev,test}` (`runs/final_dev/`, `runs/final_test/`), trước và sau khi sửa lỗi — bảng ở mục "Tuần 0". Sau sửa: TSR 100% (dev) / 95,5% (test), HR giá 2,3% / 0%. Chưa đạt: RQR trên bộ test chỉ giảm 27,4% (mẫu 22 câu hỏi), HR giá 11,1% trên bộ mẫu BTC (1/9 claim, do `CAU-HOI-BTC` A3). ✅ **24/10 (cấu hình nộp, Qwen local + hybrid, `runs/kaggle/eval-b/out/eval-b/eval-b-hyb2/`)**: TSR 100% / 95,5%, CCR 83,2% / 76,3%, HR giá 1,0% / 0,0%, RQR giảm 100% / 100% (dev / test) — bảng "Cấu hình nộp" dưới | 4 |
| Độ trễ (ĐC-1) | Brief ≤ 5 s, TTFT p95 ≤ 3 s, total p95 ≤ 8 s | ✅ sau sửa 08/10: TTFT p50 1,2–1,3 s, **p95 1,6 s**; total p95 2,1 s (dev) / 3,2 s (test); Call Brief p95 ≤ 0,2 s. Trước sửa TTFT p95 11,2 s — nguyên nhân ở mục "Tuần 0". ✅ 24/10 (Qwen3-4B local trên T4, hybrid): TTFT p95 1,35 s, total p95 4,0–4,1 s (dev/test), Call Brief p95 63 ms | 2 |
| **Cơ chế cải tiến (C.5)** | ≥ 1 cơ chế, 2 vòng trên cùng bộ test, người duyệt, quay lui | ❌ | **5 (13%)** |
| **Giao diện + demo (C.6)** | web: khung chat, Call Brief, dòng thời gian bộ nhớ; demo 2 cuộc | ❌ | **6 (13%)** |
| Báo cáo, video, slide (F) | phân tích ≥ 10 ca sai, video 5–8 phút, ≤ 15 slide | ❌ (đã có `ARCHITECTURE.md`, `HARNESS.md`) | 4, 8 |
| Log/debug | | ✅ `<out>.log`, `<out>.errors.jsonl`, `-v` | — |

**Lỗ hổng lớn nhất theo điểm (sau tuần 1):** **số liệu thật** — thiếu vòng 0 thì tiêu chí 4 (15%) gần như bằng 0 và cơ chế cải tiến không có mốc để so; tiếp theo là cơ chế cải tiến (13%), giao diện/demo (13%), rồi audio + số WER/CER (một phần của 12%). MCP (15%) đã xong phần code.

## 2. Thứ tự ưu tiên

1. **Số thật trước** (vòng 0). Mọi thứ sau đều cần một mốc để so.
2. **MCP** — 15% điểm, và là thay đổi kiến trúc nên làm sớm trước khi viết UI/cải tiến dựa lên nó. ✅ xong phần code (01/10).
3. **Cơ chế cải tiến** — cần vòng 0 đã có; cho ra bảng "trước/sau".
4. **ASR + audio** — làm song song được, ít phụ thuộc phần còn lại.
5. **UI + demo + báo cáo**.
6. M2 / điểm thưởng chỉ khi 1–5 xong.

### Lưu ý: làm tiếp trong lúc chờ BTC trả lời `docs/CAU-HOI-BTC.md`

Không chờ bản vá của BTC; làm tiếp các tuần sau theo ba nguyên tắc để lúc có bản vá chỉ phải sửa ít:

1. **Không sửa file của BTC** (`eval/`, `catalog/`, `policy/`, `test_set/`, `schemas/`, `rag/`, `asr/ground_truth.json`). Hệ thống nạp thẳng `eval/mock_tools.py`, nên khi có bản vá chỉ cần chép đè.
2. **Không né lỗi của BTC trong agent** (tự tính lại giờ hẹn, tự cộng freeship theo tổng đơn, gán cứng mã đơn…). Nếu buộc phải né, gom vào một chỗ và ghi chú mã mục tương ứng trong `docs/CAU-HOI-BTC.md` (vd. `# CAU-HOI-BTC B1`) để gỡ nhanh.
3. **Khi có bản vá:** chạy lại `tests/mcp_parity.py`, `datagen/validate.py` (đáp án của kịch bản tự sinh tính bằng `mock_tools`, logic giá/KM đổi thì đáp án đổi theo), rồi chạy lại vòng 0. Vòng 0 và vòng 1 phải đo trên cùng phiên bản tool và script chấm.

Chỗ có thể phải sửa theo câu trả lời của BTC: tên trường `claims` trong `harness/extractor.py` (A5), quy tắc gộp entity trong `asr/transcribe.py` (C6), nhận diện khách ở kênh không có định danh (A2), cách truyền AIR-2ND-50 và địa chỉ mới của đơn (B2, B4). `harness/agent.py` và `harness/tools.py` đọc thẳng vài thành phần nội bộ của `mock_tools` (`_parent`, `PRODUCTS`); bản vá đổi tên thì sửa theo.

## 3. Lịch 4 tuần

### Tuần 0 (2–3 ngày, bắt đầu ngay): số thật vòng 0

- [ ] Điền `TYPESAFE_API_KEY`, `DEEPSEEK_API_KEY` vào `.env`. Không có Jev → `--router llm`.
- [ ] Chạy `full` + `baseline_no_memory` trên `test_set/public_sample`, `datagen/out/dev`, `datagen/out/test`. Lưu vào `runs/r0/` kèm `.config.json`, `.log`.
- [ ] Kiểm ngưỡng đề: RQR giảm ≥ 40% so với baseline, TSR ≥ 70%, HR giá ≤ 5%, TTFT p95 ≤ 3 s, total p95 ≤ 8 s, Call Brief ≤ 5 s.
- [ ] Đối chiếu tay ~20 lượt `questions`/`claims` (bộ trích dùng luật — nếu trích sai thì RQR/HR sai). Ghi tỷ lệ khớp vào báo cáo.
- [ ] Sửa lỗi SAMPLE-06 call_2 **trước khi chạy vòng 0** (kênh Zalo, không có Zalo ID, khách không đọc SĐT): agent vẫn gọi `order.create` thiếu `customer_phone` và nói mã lỗi nội bộ "(tool_exception)" cho khách. Đúng ra phải xin SĐT/xác minh trước khi lên đơn, và không bao giờ đọc mã lỗi cho khách. Để lại thì số vòng 0 sai và có nguy cơ bị tính `guardrail_violations` (ĐC-11).
- [ ] Gửi BTC 26 mục trong `docs/CAU-HOI-BTC.md`: 5 mục về kịch bản mẫu (SAMPLE-03 `OD682761` vs mock `OD600001`; SAMPLE-06 không có định danh; SAMPLE-02 `promo_active=false`; …), 12 mục về `eval/mock_tools.py`, 7 mục về `eval/reference_eval.py` và ASR (script dừng khi hệ thống không hỏi câu nào; entities ghi đè trong `asr/ground_truth.json`; …), 2 mục về gói dữ liệu. Ưu tiên hỏi trước 5 mục gắn nhãn **[Chặn điểm]**.
- **Xong khi:** có bảng A.6 vòng 0 với số thật, tái lập bằng 1 lệnh.

**Bảng A.6 vòng 0 (08/10/2026)** — Jev + `deepseek-v4-flash`, MCP, RAG chạy BM25 (máy đo chưa cài model embedding), chấm bằng `eval/reference_eval.py`. Baseline / Hệ thống:

| Chỉ số | `public_sample` (7 kịch bản, 39 lượt) | `out_nat/dev` (45 kịch bản, 267 lượt) | `out_nat/test` (22 kịch bản, 129 lượt) |
|---|---|---|---|
| Repeat-Question Rate | 23,1% / 8,3% (giảm 64,1%) | 20,3% / 3,2% (giảm 84,2%) | 5,6% / 5,0% (giảm 10,7%) |
| Context Carryover Rate | 9,5% / 71,4% | 5,3% / 79,6% | 2,6% / 63,2% |
| Task Success Rate | 57,1% / 85,7% | 68,9% / 95,6% | 54,5% / 72,7% |
| Hallucination Rate giá & KM | 33,3% / 8,3% | 22,6% / 11,5% | 14,6% / 10,5% |
| TSR riêng ca khó (hệ thống) | 100% (3 ca) | 90,9% (22 ca) | 68,4% (19 ca) |
| Vi phạm guardrail | 0 / 0 | 0 / 0 | 0 / 0 |
| TTFT p50 / p95 (hệ thống) | 2,6 s / 11,6 s | 2,5 s / 11,2 s | 2,5 s / 11,1 s |

Vòng 0 ở trên đo khi DeepSeek còn bật suy luận và Jev còn treo kết nối (xem dưới), nên một nửa số lượt bị cụt câu hoặc rơi về câu mẫu.

**Sau sửa lỗi (08/10/2026)** — cùng bộ kịch bản, cùng script chấm, RAG lai `bge-m3` + BM25 trên GPU. Baseline / Hệ thống:

| Chỉ số | `public_sample` (`runs/r1/`) | `out_nat/dev` (`runs/final_dev/`) | `out_nat/test` (`runs/final_test/`) |
|---|---|---|---|
| Repeat-Question Rate | 16,7% / 0,0% (giảm 100%) | 21,9% / 5,4% (giảm 75,3%) | 6,2% / 4,5% (giảm 27,4%) |
| Context Carryover Rate | 9,5% / 66,7% | 5,3% / 79,6% | 5,3% / 68,4% |
| Task Success Rate | 57,1% / 85,7% | 66,7% / 100% | 81,8% / 95,5% |
| Hallucination Rate giá & KM | 40,0% / 11,1% | 18,8% / 2,3% | 7,4% / 0,0% |
| TSR riêng ca khó (hệ thống) | 100% (3 ca) | 100% (22 ca) | 94,7% (19 ca) |
| Vi phạm guardrail | 0 / 0 | 0 / 0 | 0 / 0 |
| TTFT p50 / p95 (hệ thống) | 1,3 s / 2,1 s | 1,2 s / 1,6 s | 1,3 s / 1,6 s |
| Total p95 (hệ thống) | 2,9 s | 2,1 s | 3,2 s |

**Cấu hình nộp (24/10/2026)** — Jev + Qwen3-4B fp16 local (vLLM, Kaggle T4 ×2), câu ngắn (`REPLY_STYLE=short`, `LLM_MAX_TOKENS=160`), 1 worker, bộ trích hybrid (`EXTRACTOR_BACKEND=hybrid`, `EXTRACTOR_ASYNC=1`), MCP, RAG lai `bge-m3` + BM25. Job `eval-b` biến thể `eval-b-hyb2` (`runs/kaggle/eval-b/out/eval-b/eval-b-hyb2/`), chấm bằng `eval/reference_eval.py`. Baseline / Hệ thống:

| Chỉ số | `public_sample` (39 lượt) | `out_nat/dev` (267 lượt) | `out_nat/test` (129 lượt) |
|---|---|---|---|
| Repeat-Question Rate | 33,3% / 25,0% (giảm 24,9%)\* | 19,5% / 0,0% (giảm 100%) | 12,5% / 0,0% (giảm 100%) |
| Context Carryover Rate | 9,5% / 81,0% | 6,2% / 83,2% | 7,9% / 76,3% |
| Task Success Rate | 57,1% / 85,7% | 66,7% / 100% | 81,8% / 95,5% |
| Hallucination Rate giá & KM | 46,2% / 8,3% | 24,5% / 1,0% | 8,5% / 0,0% |
| TSR riêng ca khó (hệ thống) | 100% | 100% | 94,7% |
| Vi phạm guardrail | 0 / 0 | 0 / 0 | 0 / 0 |
| TTFT p50 / p95 (hệ thống) | 1,1 s / 1,4 s | 1,2 s / 1,3 s | 1,2 s / 1,4 s |
| Total p95 (hệ thống) | 6,4 s | 4,0 s | 4,1 s |
| Call Brief p95 | 61 ms | 63 ms | 62 ms |
| Lượt lỗi LLM | 0 | 0 | 0 |

\* 1 trong 2 câu bị tính lặp là câu trần thuật ("…không mất phí đâu.") bị bộ lọc câu hỏi nhận nhầm — đã sửa `_is_question` sau lần chạy; chấm lại trên cùng trace: 14,3%, giảm 57%. Câu còn lại do generator hỏi lại sản phẩm đã biết (SAMPLE-06). Chi tiết: `docs/NHAT-KY-2026-10-23.md` mục 6.

So với bộ trích luật cùng code (`eval-b-fix-rules`, dev / test): TSR 100% / 95,5%, CCR 84,1% / 68,4%, HR giá 1,1% / 2,0%, TTFT p95 0,9 s. Hybrid hơn ở CCR test (+7,9 điểm) và HR test, đổi lại TTFT cao hơn ~0,45 s.

Số dao động giữa các lần chạy (LLM, temperature 0,3): qua ba lần chạy liên tiếp trong lúc sửa, RQR dev đo được 0–5,4% và HR giá dev 2,2–3,4%.

Còn lệch sau sửa, đều đã có trong `docs/CAU-HOI-BTC.md` hoặc do cách chấm:
- `SAMPLE-03` (A1): đáp án đòi mã đơn `OD682761`, mock chỉ sinh `OD600001`. `SAMPLE-02` (A3): đáp án ghi `promo_active: false` trong khi tool trả KM còn hiệu lực.
- `GEN-T21-02` (B4): `order.update(update_address)` không trả ngày giao mới, nên sau khi khách đổi địa chỉ sang vùng khác agent chỉ có ngày giao cũ (22/10 thay vì 20/10). Không tự tính lại trong agent.
- `GEN-T10-01`: agent báo đúng giá mẫu thay thế AirPure X (4.490.000đ) ở lượt 1, nhưng script chấm so mọi claim giá của cuộc gọi với một giá duy nhất (AirPure Pro, mẫu khách chốt sau đó).
- RQR bộ test: mỗi cấu hình chỉ có 16–22 câu hỏi và 1 câu bị tính lặp, nên mức giảm chưa có ý nghĩa thống kê.

**Vì sao TTFT vòng 0 cao (p95 11,2 s) — hai nguyên nhân, đã sửa cả hai:**
1. `deepseek-v4-flash` mặc định bật suy luận. Token suy luận đến trước token nội dung và tính vào `LLM_MAX_TOKENS=350`: TTFT ~3 s/lượt, 193/396 lượt dùng hết 350 token, trong đó 98 lượt không còn token cho câu trả lời (rơi về câu mẫu) và 89 lượt bị cụt câu. Sửa: `DEEPSEEK_THINKING=disabled` (`core/config.py`, `core/llm/deepseek.py`) → TTFT của LLM ~0,7 s, token đầu ra giảm ~8 lần (dev: 78k → 21k).
2. `api.typesafe.ai` không trả lời request thứ 4 trên cùng một kết nối keep-alive; SDK chờ hết timeout 8 s rồi thử lại trên kết nối mới. 78/396 lượt (20%) dính ~8,8 s. Sửa: gửi `Connection: close` (`core/llm/router.py`), tốn thêm ~60 ms mỗi lượt → router p95 0,45 s.
Ngoài ra model embedding nạp ở lượt đầu tiên cần tra chính sách (~8 s); `run_eval.py` nay nạp lúc tiến trình khởi động.

**Lỗi đã sửa trong lượt này** (ngoài hai mục độ trễ):
- `harness/textnorm.py`: "45 Trần…", "2024 trong…", "1-1 trong…" bị đọc thành 45 triệu / 2024 triệu / 1 triệu → guardrail chặn nhầm và sinh claim giá sai; thêm "1.161k".
- `harness/extractor.py`: câu "giá X, giảm … còn Y" gán X là giá niêm yết, Y là giá bán; câu phủ định ("không phải 1.161.000đ", "chưa có chương trình nào") và giá cũ ("… là giá khi còn khuyến mãi") không còn bị tính là khẳng định giá/KM hiện tại; "đổi mới trong 30 ngày nếu lỗi" không tính là hạn đổi trả; câu hỏi nhắc tên sản phẩm đã biết là câu xác nhận; địa chỉ không dính phần "thì mấy ngày hả"; nhận "chị Dung đây" là tên người nói; màu "xanh navy" là navy.
- `harness/tools.py`: số nhà trong địa chỉ không bị hiểu là size; thêm cách đọc "sờ mát" cho Smart.
- `harness/agent.py`: đầu vào ASR qua ITN trước khi trích slot; khách báo địa chỉ khi đang chốt đơn không bị xử lý như đổi đơn cũ; hỏi tiếp tiền hoàn sau khi đổi hàng trả đúng số tiền; hỏi giá khi chưa nói size thì báo giá size thường kèm lưu ý (trừ khi KM phụ thuộc size); nhớ ngày giao dự kiến sang cuộc sau; "giao đúng địa chỉ mới" không còn bị hỏi size; không hỏi xác nhận địa chỉ cũ lần thứ hai; số tiền trong trích chính sách và trong facts được phép nói.
- `core/llm/generator.py`: thêm `GOAL_NOTES` (phần bắt buộc phải nói của từng goal: tiền hoàn, ngày giao, KM đã hết hạn) và ba quy tắc (không nói có ưu đãi khi `promo_names` rỗng, không đọc lại giá sai của khách, không đọc mã SKU).

**RAG với model embedding** (`run_rag_eval.py`, 60 câu BTC, `runs/rag/rag_bm25.json` so với `runs/rag/rag_hybrid.json`): Recall@3 88,1% → 93,2%; Recall@5 93,2% → 93,2%; multi-hop đủ chunk @3 25,0% → 50,0%, @5 66,7% → 75,0%; từ chối đúng câu không có thông tin 75,0% → 87,5%; từ chối nhầm 14,9% → 8,5%; truy hồi 1,2 ms → 15,9 ms (RTX 3060). Trên bộ kịch bản đa phiên, hai lượt cùng code chỉ khác RAG (`runs/final_bm25_*` so với một lượt hybrid chạy ngay sau, không giữ trace) cho TSR và HR ngang nhau (dev 100% / 2,2% so với 100% / 3,4%; test 95,5% / 0% ở cả hai) — chênh lệch nằm trong dao động giữa các lần chạy.

### Tuần 1: MCP + PII + khởi động ASR — ✅ xong phần code (01/10), còn chạy ASR trên audio thật

- [x] **`mcp-memory`** (mcp SDK lowlevel): bọc `harness/memory.py` — `get_brief`, `get_facts`, `write_fact`, `add_session`, `forget_customer`, `merge_customer`. Phân quyền: chỉ Context & Memory được ghi.
- [x] **`mcp-commerce`** (hoặc tách `mcp-catalog` + `mcp-crm`): bọc `eval/mock_tools.py`, giữ đúng tên/tham số `schemas/tools.schema.json`.
- [x] `harness/tools.py` và `Memory` gọi qua MCP client (giữ chế độ gọi trực tiếp làm cờ `--transport direct|mcp` để so tốc độ).
- [x] Kiểm tương đương: chạy lại vòng 0 qua MCP → trace phải cho **cùng chỉ số** (chỉ khác latency). Ghi thêm độ trễ MCP vào báo cáo.
- [x] Viết vào `ARCHITECTURE.md`: vì sao chọn MCP thay vì A2A, và một tình huống cụ thể MCP giúp ích (vd. UI copilot và agent dùng chung `mcp-memory`, người và AI thấy cùng một bộ nhớ → giải Case 3).
- [x] **PII:** thay SĐT/địa chỉ bằng token (`<PHONE_1>`, `<ADDR_1>`) trước khi gửi DeepSeek/Jev; ghép lại sau khi sinh. Thêm `mask_pii` cho SĐT trong `<out>.log`.
- [x] **ASR:** `asr/transcribe.py` dùng faster-whisper (hoặc PhoWhisper) + ITN số tiền/SĐT/ngày → `asr/hypotheses.json`; chạy `reference_eval.py --asr` trên 4 hội thoại BTC.
- **Xong khi:** `run_eval.py --transport mcp` cho cùng số với vòng 0 ✅ (870/870 lượt giống hệt); WER/CER đầu tiên trên audio BTC ⏳ — cần chạy trên máy có audio + tải được model (môi trường phát triển chặn HuggingFace).
- Kết quả: `docs/ARCHITECTURE.md` mục 4.5 (MCP), 4.6 (PII), 5.2 (ASR).

### Tuần 2: Dữ liệu đủ chỉ tiêu + RAG — ✅ xong (04/10), trừ WER trên audio BTC và giọng vùng miền

- [x] Dùng DeepSeek viết lại `customer_turns` cho tự nhiên (giữ slot), chạy lại `validate.py` — kịch bản nào lệch đáp án thì loại. → `datagen/naturalize.py`, `datagen/out_nat/`: 351/396 lượt viết lại, 45 lượt giữ nguyên có chủ ý (ASR lỗi, teencode, chat), `validate.py` 0 lỗi.
- [x] Xuất **transcript 2 phía** từ trace của harness chạy với model thật → `dataset/transcripts/*.json`: 134 cuộc. (Đặt ở `dataset/` vì `data/` nằm trong `.gitignore`.)
- [x] **Audio:** edge-tts (giọng nam/nữ) từ ≥ 40 cuộc, ≥ 1 giờ; thêm nhiễu + lọc băng thông điện thoại cho một phần. → `datagen/make_audio.py`, `dataset/audio/`: 120 cuộc, 124,5 phút, 34 cuộc nhiễu. Hạn chế: edge-tts không có giọng theo vùng miền, chỉ tiêu "2 miền" chưa đạt.
- [x] WER/CER/Entity Accuracy trên ≥ 20 file của nhóm, báo riêng sạch/nhiễu. → 48 file: tập chưa dùng khi sửa luật WER 13,5% (sạch 11,1 / nhiễu 19,6), CER 8,8%, Entity Accuracy 42,9% (số tiền 46,2%). Chi tiết ở `docs/DATASET.md` mục 5.
- [ ] Còn lại của mục trên: 4 file BTC (gói dữ liệu chưa kèm audio); Entity Accuracy riêng cho SĐT (bộ audio chỉ có 1 cuộc khách đọc SĐT); xử lý dạng số "1 triệu 590.000" của Whisper trong `asr/itn.py` (nguyên nhân chính làm sai số tiền).
- [x] **RAG vector** cho `policy/`: chunk theo mã mục `[XX-nn]`; lọc bản hết hiệu lực theo `changelog.md` và ngày đơn; chặn tài liệu `NOI-BO`. → `harness/rag.py`, `run_rag_eval.py`: Recall@3 91,5%, Recall@5 93,2%, từ chối câu nội bộ 100%, câu không có thông tin 87,5%, từ chối nhầm 10,6%. Mặc định hiện là `bge-m3` (máy yếu tự lùi xuống `multilingual-e5-small`); pgvector và reranker `bge-reranker-v2-m3` đã có trong code nhưng **chưa chạy thử**, cần đo trên server GPU (`docs/HARNESS.md`, mục "Chạy trên server GPU").
- [x] Viết `docs/DATASET.md`: cách sinh, phân bố (persona, ngành, kênh, miền), hạn chế, xử lý PII.
- **Xong khi:** đủ mọi con số bảng C.1 cột M1; Recall@k có số.

### Tuần 3: Cơ chế cải tiến + vòng 1

- [ ] **Knowledge Gap Loop** (bắt buộc chọn): lượt agent trả lời "chưa có thông tin" / abstain / guardrail chặn → ghi `improve/gaps.jsonl` (câu hỏi, ngữ cảnh, kịch bản). Script gom nhóm → đề xuất bổ sung FAQ/playbook + tự sinh kịch bản test mới từ câu hỏi đó.
- [ ] **Exemplar Bank**: lượt thuộc kịch bản đạt TSR và không vi phạm → lưu làm few-shot theo (intent, persona); generator lấy 1–2 ví dụ gần nhất.
- [ ] **Người duyệt:** mọi thay đổi (FAQ mới, exemplar mới) vào `improve/pending/`; lệnh `python improve.py review` để duyệt/loại. Chỉ bản đã duyệt mới được nạp.
- [ ] **Quay lui:** sau khi áp thay đổi, chạy lại dev; chỉ số nào tụt quá ngưỡng (vd. HR tăng, TSR giảm > 3 điểm) → tự hoàn tác về phiên bản trước. Không bao giờ học từ lượt có claim sai, kể cả khi kịch bản chốt được đơn (chống "hứa đại để chốt").
- [ ] Chạy **vòng 1** trên cùng `datagen/out/test` (giữ nguyên) → bảng vòng 0 vs vòng 1.
- [ ] **Phân tích ≥ 10 ca sai** từ trace/log (`<out>.log` giúp tìm nhanh): ca, nguyên nhân gốc (router, planner, generator, bộ trích, dữ liệu BTC), cách sửa hoặc lý do không sửa.
- **Xong khi:** có bảng trước/sau trên cùng bộ test và danh sách thay đổi đã được người duyệt.

### Tuần 4: Giao diện, demo, nộp bài

- [ ] **Streamlit**: chọn khách/kênh → khung chat; Call Brief hiện khi khách gọi lại; dòng thời gian bộ nhớ (phiên, fact, fact bị thay thế, nguồn); nút chạy `reference_eval` và hiện bảng full vs baseline.
- [ ] Kịch bản demo C.6: cuộc 1 tư vấn + báo giá + KM + "hỏi người nhà" → cuộc 2 vài ngày sau: nhận diện, mở đầu tiếp nối, không hỏi lại, chốt đơn. (Có thời gian thì cuộc 3 đổi size.)
- [ ] Ước tính chi phí/cuộc gọi từ `llm_usage` trong trace (token × giá) + ước lượng tác động kinh doanh (Calls-to-Close).
- [ ] README: cài đặt, lệnh 1 dòng cho từng phần, khởi tạo dữ liệu.
- [ ] Báo cáo đánh giá, video 5–8 phút, ≤ 15 slide (nói rõ hạn chế và các lỗi dữ liệu BTC đã phát hiện).

## 4. M2 / điểm thưởng (chỉ khi M1 xong)

Theo thứ tự lợi ích/công sức: Calls-to-Close + p50/p95 + chi phí (đã có dữ liệu trong trace) → customer simulator 3 seed theo `simulator/` → LLM-judge với `eval/llm_judge_rubric.json` + chấm tay ≥ 20 mẫu (Cohen's kappa) → ablation từng cơ chế cải tiến → copilot gợi ý câu cho nhân viên → chạy LLM local (Qwen qua Ollama).

## 5. Rủi ro

| Rủi ro | Ứng phó |
|---|---|
| Không gọi được Jev/DeepSeek (mạng, khóa) | `--router llm`; nếu DeepSeek cũng không được thì đổi `DEEPSEEK_BASE_URL` sang API tương thích OpenAI khác — chỉ đổi `.env` |
| BTC không sửa SAMPLE-02/03, ground_truth | Báo cáo số theo bản BTC **và** bản đã sửa, ghi rõ chênh lệch do đâu |
| Bộ trích `questions`/`claims` bằng luật sai | Đối chiếu tay tuần 0; nếu < 90% khớp thì dùng LLM trích có kiểm tra |
| MCP làm chậm mỗi lượt | Đo; server chạy cùng máy (stdio); giữ `--transport direct` làm phương án dự phòng |
| Hết thời gian | Bỏ M2 trước, rồi rút gọn UI; **không bỏ** baseline, vòng 0/1 và MCP |

# Các biện pháp, theo mức chắc chắn
1. Ghi lại và phát lại. Lưu kết quả LLM theo khóa là mã băm của prompt; chạy lại thì đọc từ bộ lưu thay vì gọi API. Đây là cách duy nhất cho kết quả y hệt, và project đã làm đúng cách này cho bước viết lại lời khách (datagen/out_nat/rewrites.json). Nhược điểm: hễ prompt đổi một chữ là phải gọi lại.
2. Code kiểm tra mọi đề xuất trước khi thực thi. LLM đề xuất "gọi order.create với giá X", code kiểm X có khớp báo giá vừa lấy không, có vượt hạn mức COD không, khách có đang hỏi không. Cách này không làm hành vi giống hệt, nhưng bảo đảm các luật quan trọng luôn đúng dù LLM dao động.
3. Thu hẹp lựa chọn của LLM. Ép trả về theo schema cố định, chỉ cho chọn trong danh sách tool hợp lệ ở bước hiện tại, nhiệt độ 0. Jev đang dùng đúng nguyên tắc này cho phần phân loại.
4. Ghi đề xuất vào trace. Lưu cả tool LLM đề xuất lẫn quyết định của code (chấp nhận hay từ chối, vì sao), để khi số liệu đổi còn truy được nguyên nhân.
5. Báo cáo theo thống kê. Chạy mỗi cấu hình ít nhất 3 lần và báo trung bình kèm khoảng dao động, thay vì một con số.
Đề xuất
Với bài thi, giữ planner bằng code cho số liệu chính thức: nó đang đạt TSR 95–100% trên bộ tự sinh, và mọi hành động truy được về đúng dòng code.

Nếu muốn thử LLM đề xuất tool, làm theo kiểu lai: LLM chỉ đề xuất ở những chỗ planner đang bế tắc (câu không khớp nhánh nào, hiện rơi về closing), code kiểm tra trước khi thực thi, và bật biện pháp 1 và 4. Như vậy phần linh hoạt chỉ xuất hiện ở đúng chỗ đang yếu, còn các hành động quan trọng như lên đơn vẫn do code quyết định.