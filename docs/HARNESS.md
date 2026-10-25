# Harness — cách chạy và cấu trúc code

Kiến trúc tổng thể: `docs/ARCHITECTURE.md`. File này mô tả phần đã code: **Jev làm orchestrator/router, DeepSeek sinh lời thoại**, tool và bộ nhớ đi qua **2 MCP server** (`mcp-commerce` bọc `eval/mock_tools.py`, `mcp-memory` bọc bộ nhớ SQLite/Postgres), xuất trace đúng `schemas/trace_log.schema.json`.

## Cài đặt

```bash
pip install -r requirements.txt
cp .env.example .env      # điền TYPESAFE_API_KEY, DEEPSEEK_API_KEY
```

## Lệnh BTC chạy

```bash
python run_eval.py --scenarios test_set/public_sample --config full --out runs/r0/full.jsonl
python run_eval.py --scenarios test_set/public_sample --config baseline_no_memory --out runs/r0/baseline.jsonl
python eval/reference_eval.py --scenarios test_set/public_sample --trace runs/r0/full.jsonl --baseline runs/r0/baseline.jsonl
```

Tùy chọn:

| Cờ | Ý nghĩa |
|---|---|
| `--router jev\|llm\|qwen\|rules` | Orchestrator. `llm` = DeepSeek trả JSON. `qwen` = model local qua vLLM, ép JSON Schema. `rules` = luật từ khóa, **chỉ dùng kiểm thử**. |
| `--generator deepseek\|qwen\|offline` | Sinh lời thoại. `qwen` = model local qua vLLM (không cần che PII vì dữ liệu không rời máy). `offline` = câu mẫu, **chỉ dùng kiểm thử**. |
| `--extractor rules\|llm\|hybrid` | Bộ trích `questions`/`claims`/slot khách (mục "Bộ trích" bên dưới). Mặc định `rules`. |
| `--workers N` | Chạy song song N tiến trình, mỗi kịch bản độc lập. |
| `--only SAMPLE-01 …` | Chạy một số kịch bản. |
| `--run-id` | Namespace bộ nhớ + tên lần chạy. |
| `--transport mcp\|direct` | `mcp` (mặc định): tool + bộ nhớ qua MCP server (tự khởi động, stdio). `direct`: gọi hàm trực tiếp — cho cùng trace, nhanh hơn ~35 ms/lượt. |
| `--verbose` / `-v` | In khối từng lượt ra màn hình và ghi log mức DEBUG vào `<out>.log`. |
| `--log-level DEBUG\|INFO\|WARNING\|ERROR` | Mức log ghi vào `<out>.log` (mặc định `LOG_LEVEL` trong `.env`, hoặc `INFO`). |

Mỗi lần chạy ghi thêm `<out>.config.json`: model, tham số, commit, thời gian. Không ghi khóa API.

## Log và debug

Mỗi lần chạy, cạnh file trace `<out>.jsonl` có:

| File | Nội dung |
|---|---|
| `<out>.log` | Log từng lượt, gom theo kịch bản (không bị trộn khi `--workers > 1`). Mỗi dòng có nhãn `[SAMPLE-01 call_2 t3]`. |
| `<out>.errors.jsonl` | Chỉ có khi có lỗi: `scenario_id`, `call`, `turn`, câu khách vừa nói, thông điệp lỗi, **traceback đầy đủ**. Tự xóa khi lần chạy sau không lỗi. |
| `<out>.config.json` | Cấu hình lần chạy, số lỗi. |

Mức log:
- **Màn hình** mặc định chỉ hiện WARNING trở lên: router lỗi hoặc không chắc nên dùng luật (`router.fallback`), guardrail bắt lỗi rồi sinh lại, lỗi API (kèm HTTP status), traceback khi kịch bản lỗi. `-v` hiện thêm khối từng lượt.
- **INFO** (mặc định trong file): đầu mỗi cuộc gọi (khách nhận diện được, `must_not_ask`, `stale_warnings`, thời gian Call Brief); mỗi lượt: câu khách, router (intent, độ tin cậy, cờ, ms), goals, tool đã gọi (đánh dấu tool trả lỗi), token và độ trễ LLM, câu agent, slot agent hỏi, bộ nhớ ghi gì.
- **DEBUG** (`-v` hoặc `--log-level DEBUG`): thêm kết quả tool đầy đủ, prompt gửi DeepSeek, xác suất từng intent của Jev, và dòng HTTP của thư viện (`POST …/chat/completions "200 OK"`, `POST …/v1/systemone <- 200 in 210ms`, "Retrying request…").

Không log khóa API: chỉ log URL, status, thời gian, token (header bí mật bị SDK che).

Cách khoanh vùng lỗi:
```bash
python run_eval.py --scenarios test_set/public_sample --config full --out runs/dbg/full.jsonl --only SAMPLE-03 -v
grep -n "WARNING\|ERROR" runs/dbg/full.log          # router fallback, guardrail, lỗi API
grep -n "SAMPLE-03 call_2 t2" runs/dbg/full.log       # toàn bộ một lượt
```

## Kiểm thử không cần mạng

```bash
bash tests/smoke.sh                 # tất cả bên dưới, ~1 phút
python tests/mcp_check.py           # 2 MCP server: đủ tool, kiểm schema, kết quả = mock, phân quyền ro
python tests/mcp_parity.py          # trace qua MCP == gọi trực tiếp (thêm --scenarios datagen/out/dev --workers 4)
python tests/pii_check.py           # không SĐT/địa chỉ nào ra API ngoài hay vào log; ghép lại đúng
python asr/transcribe.py --from-ground-truth   # hậu xử lý ASR (ITN, entity, WER) khi chưa có audio
```

Script gồm hai phần:
1. Chạy `rules` + `offline` trên 7 kịch bản mẫu, chấm bằng `reference_eval.py`.
2. Dựng `tests/fake_api_server.py` giả lập API Jev (`POST /v1/systemone`) và DeepSeek (`POST /chat/completions`, có stream). Sau đó chạy đường thật `--router jev --generator deepseek` qua SDK chính thức để kiểm định dạng request/response.

Số liệu ở chế độ offline chỉ để bắt lỗi logic. **Số báo cáo phải chạy với Jev + DeepSeek thật.**

## MCP

`mcp_servers/commerce_server.py` (9 tool BTC + `world.reset`) và `mcp_servers/memory_server.py` (`memory.*`). Harness tự khởi động chúng làm tiến trình con qua `harness/mcp_client.py`; không cần chạy tay. Muốn xem bằng MCP Inspector hoặc gắn vào client khác:

```bash
npx @modelcontextprotocol/inspector python mcp_servers/commerce_server.py
MCP_MEMORY_MODE=ro npx @modelcontextprotocol/inspector python mcp_servers/memory_server.py
```

## PII

SĐT và địa chỉ được thay bằng `[SĐT_1]`, `[ĐỊA_CHỈ_1]` trước khi gửi DeepSeek/Jev rồi ghép lại vào câu trả lời (`core/pii.py`); CCCD/STK che từ lúc nhận câu nói. `<out>.log` che SĐT/địa chỉ; trace JSONL giữ nguyên để BTC chấm.

## ASR

```bash
pip install faster-whisper
# đặt audio vào asr/audio/ với tên = id hội thoại (D01.wav …)
python asr/transcribe.py --audio-dir asr/audio --model small          # → asr/hypotheses.json + bảng WER/CER/Entity
python eval/reference_eval.py --scenarios test_set/public_sample --trace runs/r0/full.jsonl --asr asr
```

Model: `small` chạy CPU (~0,5 GB RAM); `large-v3` cần GPU ~4–5 GB VRAM (`--device cuda --compute-type float16`). PhoWhisper: `--backend phowhisper --model vinai/PhoWhisper-small` (cần `transformers torch`).

Trên bộ audio của nhóm (`dataset/audio`, xem `docs/DATASET.md`):

```bash
python asr/transcribe.py --audio-dir dataset/audio --ground-truth dataset/asr/ground_truth.json \
       --out dataset/asr/hypotheses.json --report dataset/asr/report.json --limit 24
```

`--limit N` lấy N file cách đều, giữ tỷ lệ sạch/nhiễu của cả bộ.

## RAG chính sách

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install sentence-transformers numpy
python run_rag_eval.py --download                       # tải model embedding một lần
python run_rag_eval.py --out runs/rag/rag_results.json  # truy hồi + sinh câu trả lời + chấm bằng rag_eval của BTC
python run_rag_eval.py --mode bm25 --no-generate        # so sánh: chỉ BM25, không cần khóa API
python eval/reference_eval.py --scenarios test_set/public_sample --trace runs/r0/full.jsonl --rag runs/rag/rag_results.json
```

`harness/rag.py` tách `policy/` theo mã mục `[XX-nn]` (99 chunk, đúng `chunk_id` BTC gán nhãn), tìm lai vector + BM25 (RRF). Biến môi trường:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `RAG_MODE` | `auto` | `auto`: tìm lai nếu máy đã có model, không thì BM25. `hybrid`: bắt buộc có model. `bm25`: tắt vector. |
| `EMBED_MODEL` | `BAAI/bge-m3` | Ở chế độ `auto`, máy chưa có model này thì dùng `intfloat/multilingual-e5-small` nếu có. |
| `EMBED_DEVICE` | `auto` | Tự dùng GPU nếu có. |
| `RERANK_MODEL` | `off` | Cross-encoder xếp hạng lại top-20. Trên server: `BAAI/bge-reranker-v2-m3`. Đo có/không có rồi mới giữ. |
| `RAG_STORE` | `numpy` | `pgvector`: lưu embedding trong Postgres (`DATABASE_URL`). |

Ở chế độ lai, mỗi tiến trình harness nạp model một lần. `bge-m3` cần khoảng 2,3 GB RAM (hoặc VRAM) mỗi worker; `multilingual-e5-small` khoảng 0,5 GB. Máy ít RAM nên đặt `EMBED_MODEL=intfloat/multilingual-e5-small`, giảm `--workers`, hoặc đặt `RAG_MODE=bm25`.

## Chạy trên server GPU (RAM ≥ 16 GB, GPU 8–12 GB)

Mặc định của code đã nhắm tới cấu hình này; máy yếu hơn tự lùi xuống, không cần sửa code.

```bash
pip install -r requirements.txt faster-whisper edge-tts av numpy sentence-transformers
pip install torch                                   # bản có CUDA (mặc định trên Linux)
docker compose up -d db                             # Postgres + pgvector
cp .env.example .env                                # điền khóa API, rồi bật các dòng dưới
#   DATABASE_URL=postgresql+psycopg://callcenter:callcenter@localhost:5432/callcenter
#   RAG_STORE=pgvector
#   RERANK_MODEL=BAAI/bge-reranker-v2-m3
RERANK_MODEL=BAAI/bge-reranker-v2-m3 python run_rag_eval.py --download    # tải bge-m3 + reranker một lần
```

| Thành phần | Máy yếu (CPU, 8 GB) | Server GPU | Cách bật |
|---|---|---|---|
| ASR | faster-whisper `small`, int8 | `large-v3`, float16 (~5 GB VRAM) | tự chọn; ép bằng `--model` hoặc `ASR_MODEL` |
| ASR tiếng Việt chuyên biệt | `vinai/PhoWhisper-small` | `vinai/PhoWhisper-large` | `--backend phowhisper` |
| Embedding | `multilingual-e5-small` | `bge-m3` trên GPU | tự chọn; ép bằng `EMBED_MODEL` |
| Xếp hạng lại | tắt | `bge-reranker-v2-m3` | `RERANK_MODEL` |
| Kho vector | ma trận numpy | pgvector | `RAG_STORE=pgvector` |
| Bộ nhớ khách hàng | SQLite | Postgres (nhiều worker ghi cùng lúc) | `DATABASE_URL` |
| Số worker khi đo | 2–3 | 6–8 | `--workers` |

Việc cần làm lại trên server, vì máy phát triển không chạy được:

1. `python asr/transcribe.py --audio-dir dataset/audio --ground-truth dataset/asr/ground_truth.json --out dataset/asr/hypotheses_large.json --report dataset/asr/report_large.json` trên cả 120 file, so với `small` (WER 13,5%).
2. `python run_rag_eval.py` với `RERANK_MODEL=off` và với `BAAI/bge-reranker-v2-m3`; giữ cấu hình có Recall@3 và tỷ lệ từ chối tốt hơn.
3. `RAG_STORE=pgvector python run_rag_eval.py --no-generate`: kết quả phải trùng với kho numpy.

GPU 8–12 GB chứa được `large-v3` (~5 GB) cùng `bge-m3` (~2,3 GB). Nếu bật thêm reranker (~2,3 GB) trên GPU 8 GB thì chạy ASR và đo agent thành hai lượt riêng, hoặc dùng `--compute-type int8_float16` cho ASR.

## Dataset của nhóm

```bash
python datagen/naturalize.py                 # viết lại lượt khách cho tự nhiên → datagen/out_nat (kết quả LLM lưu trong rewrites.json)
python datagen/validate.py datagen/out_nat/dev datagen/out_nat/test
python run_eval.py --scenarios datagen/out_nat/dev --config full --out runs/w2/full_dev.jsonl --workers 3
python datagen/export_transcripts.py --pair datagen/out_nat/dev runs/w2/full_dev.jsonl ...   # → dataset/transcripts
python datagen/make_audio.py                 # → dataset/audio + dataset/asr/ground_truth.json
```

Chi tiết và số liệu: `docs/DATASET.md`.

## Luồng một lượt (`harness/agent.py`)

```
lời khách ─► textnorm.perceive (teencode, ITN số tiền/SĐT/ngày, mask PII)
          ─► extractor.customer_slots (diện tích, ngân sách, size/màu, địa chỉ, thanh toán, rào cản, giờ hẹn)
          ─► Router (Jev): intent ∈ 11 nhãn + 7 cờ (đồng ý mua, trì hoãn, hỏi AI/người, xóa dữ liệu, y tế, giá nhập, đối thủ)
          ─► Planner (code xác định): gọi tool với tham số lấy từ kết quả tool → goals + facts
          ─► Generator (DeepSeek): nói theo goals, chỉ dùng số trong facts
          ─► guardrails.check (số tiền lạ, giá nhập/giá sàn nội bộ, PII, nhận là người, chê đối thủ) → sinh lại 1 lần → câu an toàn
          ─► extractor: questions[] / claims[] / facts_used → trace
          ─► memory: ghi fact (set/supersede, nguồn call_n#turn_k, TTL), báo giá, phiên
```

**Vì sao planner là code chứ không để LLM gọi tool:** tham số `order.create` (sku, giá sau KM, mã KM, giỏ hàng) lấy thẳng từ `pricing.get_quote` cùng ngày. Nhờ vậy giá trong đơn luôn khớp mock của BTC và HR về giá gần như bằng 0 do thiết kế. LLM chỉ lo câu chữ, Jev lo phân loại ý định (nhanh, có xác suất để đặt ngưỡng).

**Dự phòng:** Jev lỗi, hết thời gian chờ hoặc độ tin cậy dưới `ROUTER_MIN_CONFIDENCE` mà luật từ khóa có tín hiệu rõ thì chuyển sang luật. Lý do được ghi vào `trace.router.fallback`, để báo cáo tỷ lệ dự phòng.

## Bộ trích (`--extractor`)

Ba trường `questions`, `claims`, `facts_used` quyết định RQR, HR và CCR, nên bộ trích phải tái lập được và giải thích được trước người chấm tay.

| Chế độ | Ai phân loại | Ai đọc giá trị | Khi LLM lỗi |
|---|---|---|---|
| `rules` | luật/regex (`harness/extractor.py`) | luật | — |
| `llm` | LLM theo định nghĩa slot/field cố định (`harness/llm_extract.py`), đầu ra ép theo JSON Schema | code: `find_money`, `parse_relative_datetime`, `find_color`… trên đoạn trích (`span`) | dùng luật, ghi `extractor.fallback` |
| `hybrid` | luật + LLM: slot khách thì luật thắng khi trùng, LLM bổ sung; câu hỏi thì LLM phân loại, câu nào LLM bỏ qua thì giữ của luật; claims là hợp hai bên | như trên | như trên |

Chế độ `llm` và `hybrid` có thêm các kiểm tra sau:
- `span` không nằm trong câu (LLM bịa) thì bị loại và đếm vào `extractor.dropped_spans`.
- Câu hỏi nhắc đúng giá trị đã biết thì luôn là câu xác nhận.
- Nhiệt độ 0 và cache SQLite theo mã băm request (`LLM_CACHE`), nên chạy lại cho đúng kết quả cũ.
- `hybrid` không bao giờ bỏ claim mà luật đã bắt, vì bỏ sót claim sẽ làm HR thấp giả.

`facts_used` luôn tính bằng code. Kiểm thử không cần GPU: `python tests/llm_extract_check.py`.

## Các trường thêm trong trace (BTC bỏ qua, dùng cho phân tích lỗi)

`router` (intent, confidence, flags, backend, ms, fallback), `goals`, `guardrail` (`action`: `regenerated`, `safe_template`, `llm_error_template`), `llm_usage`, `extractor` (backend, ms, fallback, dropped_spans), `call_brief` (lượt 1).
Các trường này cũng được in trong `<out>.log` (xem "Log và debug").

## Cấu trúc thư mục

```
core/config.py            cấu hình từ .env
core/llm/router.py        Router: jev | llm | rules
core/llm/deepseek.py      client DeepSeek (OpenAI-compatible, streaming đo TTFT)
core/llm/generator.py     prompt hệ thống + câu mẫu offline
harness/loader.py         đọc kịch bản, CHỈ lộ phần agent được thấy
harness/textnorm.py       chuẩn hóa tiếng Việt, ITN, PII
harness/tools.py          bọc mock_tools + nhận diện sản phẩm/biến thể trong câu nói
harness/memory.py         bộ nhớ (SQLAlchemy; namespace theo run/config/kịch bản)
harness/knowledge.py      tra chính sách cho agent (lớp mỏng trên rag.py)
harness/rag.py            RAG: chunk [XX-nn], tìm lai vector + BM25, luật phiên bản / tài liệu nội bộ
run_rag_eval.py           chấm RAG trên rag/qa_labeled.json → rag_results.json
datagen/                  sinh kịch bản, viết lại lượt khách, xuất transcript, sinh audio
harness/extractor.py      slot khách; questions/claims/facts_used của agent
harness/guardrails.py     kiểm câu trả lời
harness/agent.py          CallSession: nhận diện, Call Brief, planner, ghi nhớ
run_eval.py               chạy bộ kịch bản → trace JSONL
tests/                    smoke test + server giả lập API
```

## Giới hạn hiện tại

- **Chính sách:** RAG đã có luật "chính sách cũ cho đơn cũ" (`order_date`), nhưng agent chưa truyền ngày đơn khi tra cứu, nên hiện luôn trả lời theo bản đang hiệu lực. Index là ma trận numpy, chưa dùng vector DB.
- **Postgres:** đường dẫn `DATABASE_URL=postgresql+psycopg://…` đã có nhưng mới chạy thử trên SQLite.
- **ASR:** đã đo trên audio TTS của nhóm; chưa đo trên audio BTC (gói dữ liệu chưa kèm file audio). Chưa có diarization.
- **Độ trễ:** đã sửa hôm 08/10 (tắt suy luận của DeepSeek, `Connection: close` cho Jev). TTFT p95 còn 1,6 s, total p95 2,1–3,2 s (`docs/NHAT-KY-2026-10-08.md`). Với Qwen local thì chưa đo; bộ trích `llm`/`hybrid` cộng thêm một lời gọi trước khi sinh câu (tính vào TTFT) và một lời gọi sau (tính vào total).
- **Bộ trích `claims`/`questions`:** chế độ `llm`/`hybrid` đã có nhưng chưa đo trên model thật. Cần đối chiếu tay khoảng 20 lượt với cả `rules` và `hybrid` trước khi chọn chế độ dùng cho báo cáo.
- **Lỗi giữa cuộc gọi:**
  - LLM của generator lỗi thì dùng câu mẫu (`guardrail.action = llm_error_template`).
  - `mcp-memory` lỗi hai lần liên tiếp thì lượt đó coi như chưa có bộ nhớ và cuộc gọi tiếp tục (log ERROR).
  - Câu khách không hiểu được thì agent xin nói lại (goal `ask_repeat`, tối đa 2 lần mỗi cuộc) thay vì chào kết thúc.
