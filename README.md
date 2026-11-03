# Harness Agent Call Center — SUDO CODE 2026, Vòng 1

Agent telesale tiếng Việt có bộ nhớ khách hàng xuyên phiên và đa kênh. Tool và bộ nhớ đi qua hai MCP server; có script đánh giá so với baseline không bộ nhớ.

Tài liệu chi tiết: [docs/HARNESS.md](docs/HARNESS.md) (cách chạy, cờ lệnh), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (kiến trúc), [docs/DATASET.md](docs/DATASET.md) (dataset), [docs/PLAN.md](docs/PLAN.md) (tiến độ). Phần mô tả gói dữ liệu của BTC nằm ở cuối file này.

## 1. Cài đặt

```bash
git clone https://github.com/buidong941-ship-it/SudoCode.git
curl -fsSL https://claude.ai/install.sh | bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
cd SUDOCODE_task
python -m venv .venv && source .venv/bin/activate      # Windows (Git Bash): source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env                                   # điền TYPESAFE_API_KEY, DEEPSEEK_API_KEY
bash tests/smoke.sh                                    # kiểm thử không cần mạng, không cần khóa API
```

Các gói tùy chọn (ASR, RAG vector, sinh audio) ghi ở cuối `requirements.txt`; cấu hình cho server GPU ở [docs/HARNESS.md](docs/HARNESS.md), mục "Chạy trên server GPU".

## 2. Chạy đánh giá (lệnh BTC dùng để chấm)

```bash
python run_eval.py --scenarios test_set/public_sample --config full --out runs/r0/full.jsonl
python run_eval.py --scenarios test_set/public_sample --config baseline_no_memory --out runs/r0/baseline.jsonl
python eval/reference_eval.py --scenarios test_set/public_sample --trace runs/r0/full.jsonl --baseline runs/r0/baseline.jsonl
```

Thay `test_set/public_sample` bằng `datagen/out_nat/dev` hoặc `datagen/out_nat/test` để chạy trên bộ kịch bản của nhóm. Thêm `--workers N` để chạy song song.

Chạy trọn bộ (bật vLLM nếu cần, hai cấu hình, chấm, bảng tổng hợp) trên Kaggle, server thuê hoặc máy cá nhân, chỉ khác `RUN_PROFILE`:

```bash
RUN_PROFILE=server python scripts/run_suite.py --sets sample dev test --router qwen --generator qwen --extractor hybrid
python scripts/kaggle_job.py --cred "<kaggle.json>" push --job qwen-dev --sets dev --router qwen --generator qwen
```

Chi tiết: [docs/CHAY-KAGGLE-SERVER.md](docs/CHAY-KAGGLE-SERVER.md).

## 3. Dữ liệu ngoài repo

Dataset và kết quả chạy **không commit lên GitHub** (đã có trong `.gitignore`). Chúng được lưu trên Google Drive và tải về mỗi khi dựng máy mới.

| Thư mục | Nội dung | Dung lượng | Lấy ở đâu |
|---|---|---|---|
| `dataset/` | `transcripts/` (134 cuộc hai phía), `audio/` (120 file mp3 + mốc thời gian), `asr/` (ground truth, kết quả ASR), `index.json` | ~31 MB | **Drive** → giải nén vào gốc repo |
| `runs/` | Trace `.jsonl`, log, cấu hình và báo cáo của các lần chạy; kết quả RAG ở `runs/rag/` | ~2 MB | **Drive** → giải nén vào gốc repo |
| `asr/audio/` | Audio ASR của BTC (`D01.wav`…), khi BTC phát | — | Chép tay vào `asr/audio/` |
| `data/` | `memory.db` (bộ nhớ SQLite), `rag/` (index vector) | ~2 MB | **Không cần tải**: tự tạo lại khi chạy |
| Model (Whisper, bge-m3…) | Cache của Hugging Face, nằm ngoài repo (`~/.cache/huggingface`) | 0,5–5 GB mỗi model | **Không cần tải**: tự tải ở lần chạy đầu |
| `.env` | Khóa API | — | Chép tay, không đưa lên GitHub hay Drive công khai |

Những thứ **có** trong repo: code, kịch bản (`datagen/out`, `datagen/out_nat` kèm `rewrites.json` để bộ test không đổi giữa các lần chạy), dữ liệu BTC (`catalog/`, `policy/`, `test_set/`, `rag/`, `eval/`), tài liệu.

### 3.1. Tải dữ liệu về (máy mới hoặc server)

Sau khi clone và cài đặt:

```bash
pip install gdown
# cách 1: ghi link vào .env (DRIVE_DATASET=..., DRIVE_RUNS=...) rồi chạy
bash scripts/data_fetch.sh
# cách 2: truyền link trực tiếp
bash scripts/data_fetch.sh "<link dataset.tar.gz>" "<link runs.tar.gz>"
```

Script tải hai file nén vào `_download/` rồi giải nén ra `dataset/` và `runs/` ở gốc repo. Link là link chia sẻ của **từng file** trên Drive, đặt quyền "Bất kỳ ai có đường liên kết". Nếu không dùng script: tải tay hai file `.tar.gz`, đặt ở gốc repo rồi chạy `tar -xzf dataset.tar.gz && tar -xzf runs.tar.gz`.

Kiểm tra đã đúng chỗ:

```bash
ls dataset/transcripts | wc -l      # 134
ls dataset/audio/*.mp3 | wc -l      # 120
ls runs                             # rag  w2  ...
```

### 3.2. Đưa dữ liệu lên Drive (sau mỗi lần chạy có kết quả mới)

```bash
bash scripts/data_pack.sh           # → _upload/dataset.tar.gz, _upload/runs.tar.gz
```

Tải hai file trong `_upload/` lên thư mục Drive của nhóm (ghi đè bản cũ để giữ nguyên link), rồi cập nhật `DRIVE_DATASET` / `DRIVE_RUNS` trong `.env` nếu link đổi. Nên giữ thêm một bản có ngày trong tên (`runs-2026-10-04.tar.gz`) trước khi ghi đè, vì các vòng đo cần so với nhau.

### 3.3. Tạo lại từ đầu thay vì tải

Mọi thứ trong `dataset/` và `runs/` đều sinh lại được bằng lệnh (xem [docs/HARNESS.md](docs/HARNESS.md), mục "Dataset của nhóm"), nhưng lời nhân viên do LLM sinh nên sẽ khác bản trên Drive, và mất khoảng 1,5 giờ (chạy model thật, TTS, ASR). Dùng bản trên Drive khi cần số liệu khớp với báo cáo.

## 4. Trình tự trên server thuê

```bash
git clone ... && cd SUDOCODE_task
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt faster-whisper edge-tts av numpy sentence-transformers torch gdown
cp .env.example .env                 # điền khóa API và hai link Drive
bash scripts/data_fetch.sh           # dataset/ và runs/
python run_rag_eval.py --download    # tải model embedding (một lần cho mỗi máy)
bash tests/smoke.sh
# ... chạy các lượt đo ...
bash scripts/data_pack.sh            # rồi tải _upload/*.tar.gz lên Drive trước khi tắt server
```

Server thuê thường xóa ổ đĩa khi tắt, nên bước cuối là bắt buộc nếu muốn giữ kết quả.

## 5. Giao diện demo (UI)

UI Streamlit ở `ui/app.py` phục vụ phần demo của đề bài (C.6): khung hội thoại, Call Brief khi khách gọi lại, dòng thời gian bộ nhớ, bảng chỉ số so với baseline, và khu duyệt đề xuất cải tiến. UI tách khỏi core: nó chỉ gọi agent giống `run_eval.py`, không sửa gì trong `harness/` hay `core/`, và dùng DB bộ nhớ riêng.

### 5.1. Cài và mở

```bash
pip install -r requirements-ui.txt        # = requirements.txt + streamlit (chỉ cần cho UI)
streamlit run ui/app.py                   # mở http://localhost:8501
```

Trên Windows, chạy `set PYTHONIOENCODING=utf-8` trước. Nếu chạy trên server, mở cổng bằng `streamlit run ui/app.py --server.address 0.0.0.0 --server.port 8501`, rồi chuyển cổng về máy (`ssh -L 8501:localhost:8501 <server>`).

### 5.2. Chọn backend (thanh bên trái)

| Mục | Lựa chọn | Cần gì |
|---|---|---|
| Chế độ | `full` (đọc bộ nhớ) / `baseline_no_memory` | Dùng để so trực tiếp: cùng kịch bản, chỉ khác việc đọc bộ nhớ |
| Router | `rules` (mặc định) / `jev` / `qwen` / `llm` | `jev` cần `TYPESAFE_API_KEY`; `qwen` cần vLLM ở `QWEN_BASE_URL`; `llm` cần `DEEPSEEK_API_KEY` |
| Generator | `offline` (mặc định) / `qwen` / `deepseek` | `offline` dùng câu mẫu, không cần mạng hay GPU, máy yếu chạy được; `qwen` cần GPU (vLLM); `deepseek` cần khóa |
| Tên khách demo | chuỗi bất kỳ | Mỗi tên là một namespace bộ nhớ riêng (`ui:<chế độ>:<tên>`) |

Khóa API đọc từ `.env`, giống phần còn lại của repo. Để demo cho giám khảo với câu trả lời tự nhiên, dùng router `rules` hoặc `jev` cùng generator `qwen` trên máy có GPU (hoặc `deepseek`). Nếu chỉ cần kiểm luồng thì dùng `offline`.

### 5.3. Các tab

- **Cuộc gọi:** nhập SĐT, kênh (hotline / Zalo / fanpage) và ngày gọi (để trống thì lấy 2026-10-15). Bấm **Bắt đầu cuộc gọi mới**, gõ lời khách vào ô chat, rồi bấm **Kết thúc cuộc gọi** để lưu phiên vào bộ nhớ. Gọi lần hai với cùng SĐT và một ngày sau đó thì **Call Brief** hiện ra: khách là ai, phiên trước nói gì, các mục không được hỏi lại, giá đã báo so với giá hiện tại, KM hết hạn, đơn đang có. Mỗi câu trả lời có mục "chi tiết lượt" ghi goal, nhánh planner, tool đã gọi, guardrail, claim và những gì được ghi vào bộ nhớ.
- **Demo C.6:** chọn chạy tới cuộc 1, 2 hoặc 3, rồi bấm **Chạy demo từ đầu**. Cuộc 1 là khách mới được tư vấn, báo giá kèm KM, hẹn "để hỏi ý vợ". Cuộc 2 diễn ra 3 ngày sau: agent nhận ra khách, mở đầu bằng xác nhận tiếp nối, không hỏi lại thông tin đã có, rồi chốt đơn. Cuộc 3 (mức M2) là khách hỏi vận đơn. Lời khách của demo nằm trong `ui/engine.py` (`DEMO_SCRIPT`), viết riêng cho demo, không lấy từ bộ test.
- **Bộ nhớ:** dòng thời gian của khách gồm phiên, báo giá và fact, mỗi mục có nguồn và hạn dùng. Fact cũ khi khách đổi ý vẫn hiện, ghi `superseded → #id` của fact mới. Có thể lọc theo loại hoặc ẩn các fact đã bị thay thế.
- **Chỉ số:** chọn một `report.json` có sẵn dưới `runs/` (do `eval/reference_eval.py` sinh ra, hoặc kéo về từ Kaggle) để xem bảng Baseline so với Hệ thống (RQR, CCR, TSR, HR giá & KM, số lượt, vi phạm guardrail) và danh sách cuộc gọi trượt TSR. Để có số mới, chạy ba lệnh ở mục 2 kèm `--out runs/<tên>/report.json`.
- **Cải tiến:** nhập tên người duyệt, rồi **Duyệt** hoặc **Loại** từng đề xuất trong `improve/pending/`. Tab này cũng hiện các đề xuất đã duyệt và các vòng đã chụp. Cách gom lỗi và tạo đề xuất bằng dòng lệnh xem ở [docs/HAM-IMPROVE.md](docs/HAM-IMPROVE.md).

### 5.4. Bộ nhớ của UI

- UI ghi vào `data/ui/memory.db`, không ghi vào `data/memory.db` mà `run_eval.py` dùng, nên chơi thử trên UI không làm sai số đo. Muốn dùng DB khác thì đặt `DATABASE_URL=sqlite:///<đường dẫn>` trước khi chạy `streamlit`.
- Nút **Xoá bộ nhớ khách này** ở thanh bên xoá namespace hiện tại và đặt lại trạng thái mock (đơn đã tạo, tồn kho). Nút **Chạy demo từ đầu** tự xoá trước khi chạy.
- Mặc định UI gọi tool trực tiếp (`TOOL_TRANSPORT=direct`). Muốn demo đường MCP thì đặt `TOOL_TRANSPORT=mcp`; trace của hai đường giống hệt nhau (`tests/mcp_parity.py`). Lưu ý: ở chế độ MCP, tab Bộ nhớ không hiện dòng thời gian vì nó đọc DB trực tiếp.

### 5.5. Kiểm thử UI

```bash
python tests/ui_check.py       # chạy kịch bản C.6 không giao diện; nếu đã cài streamlit thì mở app bằng AppTest và bấm nút demo
```

`tests/smoke.sh` đã gồm bước này.

## 6. Cơ chế cải tiến (`improve/`)

Vòng cải tiến gồm các bước: gom lỗi từ dev → viết đề xuất → người duyệt → agent nạp các đề xuất đã duyệt → đo lại → quay lui nếu kết quả tệ hơn. Phần này tách khỏi core: `improve/` chỉ đọc trace, và agent chỉ nạp `improve/approved/` qua `harness/improve_hook.py` khi đặt `IMPROVE_DIR`. Mặc định `IMPROVE_DIR` tắt.

```bash
python -m improve collect --trace runs/<x>/dev/full.jsonl --report runs/<x>/dev/report.json   # gom lỗi → improve/gaps.jsonl
python -m improve exemplars --trace runs/<x>/dev/full.jsonl --report runs/<x>/dev/report.json # lọc lượt mẫu → pending/
python -m improve propose de_xuat.json            # thêm FAQ / playbook / cue → pending/ (chặn số tiền, SĐT, câu hứa)
python -m improve review                          # liệt kê; review approve|reject <id> --by <tên> --reason ...
python -m improve round save r0 --report dev=<report.json> --by <tên>     # chụp vòng
IMPROVE_DIR=improve python run_eval.py ...        # chạy agent có nạp approved/
python -m improve check --prev r0 --report dev=<report mới>              # TSR tụt quá 3 điểm hoặc HR tăng → mã thoát 2
python -m improve rollback --to r0 --by <tên>
python scripts/compare_rounds.py --round improve/rounds/r0 --round improve/rounds/r1
```

Chi tiết ở [docs/HAM-IMPROVE.md](docs/HAM-IMPROVE.md). Tab **Cải tiến** của UI (mục 5) cũng duyệt được đề xuất.

## 7. Cờ cấu hình thêm từ 01–02/11/2026

| Cờ | Mặc định | Ý nghĩa |
|---|---|---|
| `JEV_DROP_POLICY` | `qwen` | Jev bỏ slot `address`/`payment` mà luật đã cắt được thì gọi Qwen làm trọng tài (`accept` = hành vi cũ) |
| `EXTRACTOR_CERT_VERSION` | `1` | `2` = CERT v2 (`docs/DE-XUAT-CERT-V2-2026-11-02.md`) |
| `PLANNER_BACKEND` / `PLANNER_JEV_MIN_CONF` | `rules` / `0.6` | Planner LLM có giới hạn, chỉ dùng ở nhánh fallback (`harness/planner_llm.py`) |
| `LEXICON_INCLUDE` | `approved` | Mức nạp lexicon slot (`harness/lexicon/slots.json`, duyệt bằng `scripts/lexicon_review.py`) |
| `IMPROVE_DIR` | (trống) | Nạp đề xuất đã duyệt của `improve/` |

---

# Gói dữ liệu BTC — AI Challenge Vòng 1 (Harness Agent Call Center)

Ngày quy ước "hôm nay" của toàn bộ dữ liệu: **2026-10-15** (`reference_date`). Mọi kiểm tra "khuyến mãi còn hiệu lực" tính theo ngày này, hoặc theo `call_date` / `days_later` trong kịch bản.

## Phát cho các team (PUBLIC)

| Đường dẫn | Nội dung | Dùng cho |
|---|---|---|
| `catalog/products.json`, `products.csv` | 40 sản phẩm (3 ngành) + 96 biến thể size/màu (có phụ thu size lớn), 2 SKU ngừng bán có successor, 2 combo | tool `catalog.search`, `inventory.check` |
| `catalog/inventory_timeline.json` | Tồn kho thay đổi theo ngày (hết hàng giữa 2 cuộc gọi, ngày về hàng) | `inventory.check(on=...)` |
| `catalog/promotions.json` | 14 chương trình KM: có điều kiện (min_qty, loại size, 1 lần/khách, theo vùng, thu cũ đổi mới), 3 **đã hết hạn**, 1 chưa bắt đầu | `pricing.get_quote`, HR, KM-04 chọn KM có lợi nhất |
| `catalog/crm_seed.json` | 50 khách seed (SĐT, Zalo ID, FB ID); có khách lịch sử 8 tháng, đơn đang giao, **2 người chung SĐT** | `crm.get_customer`, identity resolution, TTL |
| `policy/*.md` | 14 tài liệu, 99 chunk `[XX-nn]`: chính sách hiện hành + **bản cũ hết hiệu lực** + changelog + **tài liệu nội bộ không được lộ** + lịch nghỉ + spec bảng + playbook + tài liệu nhiễu | RAG, guardrail, version conflict |
| `rag/qa_labeled.json` | 60 câu, 6 loại (single/multi_hop/version_conflict/unanswerable/restricted/numeric) | Recall@k, abstain, version accuracy (M2) |
| `schemas/` | Schema tool mock, HandoffBrief, CallBrief, trace log, `scenario_format.md` | thống nhất để chấm chéo |
| `eval/mock_tools.py` | **Mock tool tham chiếu** (giá sau KM theo điều kiện, tồn kho theo ngày, COD limit, dời lịch ngày nghỉ, SĐT chung, mask PII) | nhóm bọc thành MCP hoặc đối chiếu |
| `simulator/` | Spec customer simulator + 12 persona prompt chuẩn | M2, so sánh chéo |
| `eval/llm_judge_rubric.json` | 12 tiêu chí PASS/FAIL + prompt judge | M2, tiêu chí 6 |
| `test_set/public_sample/` | 7 kịch bản mẫu (5 thường + 2 ca khó: ASR lỗi/teencode, chính sách cũ) | để team làm script chấm chạy được trên định dạng của BTC |
| `asr/ground_truth.json` | 12 hội thoại đa lượt (86 lượt, 2 người nói, ~12 phút), 4 có nhiễu; entity theo lượt | WER/CER/Entity Accuracy + diarization (M2); audio BTC sinh bằng `make_audio.py` (Gemini TTS / ElevenLabs / F5-TTS-Vietnamese) |
| `eval/reference_eval.py` | Script chấm tham chiếu: 5 chỉ số, TSR ca khó, guardrail violations, memory checks, latency, WER/CER/diarization, RAG (`--rag`) | con số của team phải tái lập được bằng script này |
| `eval/validate_scenarios.py` | Kiểm tra kịch bản ↔ catalog nhất quán qua mock_tools | BTC chạy sau mỗi lần sửa |
| `eval/make_example_trace.py`, `eval/runs/` | Trace ví dụ + báo cáo mẫu | xem định dạng trace |
| `eval/huong-dan-do-latency.md` | Quy tắc đo TTFT / Total / TTFA / Call Brief | bảng hiệu năng (đã chỉnh sửa) |
| `DIEU-CHINH-DE.md` | Các điểm đề thi được điều chỉnh/bổ sung | mọi team |
| `GIAI-DAP-MENTOR.md` | Trả lời câu hỏi của mentor Team 5, 8, 10 | mọi team |

## Những gì BTC giữ lại (team không nhận)

Bộ test ẩn 41 kịch bản (cùng định dạng `test_set/public_sample/`), 8/12 hội thoại ground truth ASR (team nhận 4 mẫu D01–D04), và script sinh dữ liệu. Ngày chấm BTC phát bộ ẩn + audio đầy đủ, chạy hệ thống của team ở 2 cấu hình và chấm bằng `eval/reference_eval.py` đúng như file trong gói này.

## Quy trình chấm chéo

1. Team nộp repo; README của team phải có lệnh dạng `python run_eval.py --scenarios <dir> --config full|baseline_no_memory --out trace.jsonl`.
2. BTC thay `<dir>` bằng bộ ẩn, chạy 2 cấu hình, rồi `python eval/reference_eval.py --scenarios <dir> --trace full.jsonl --baseline baseline.jsonl --asr <asr_dir>`.
3. Bảng A.6 in ra từ script là con số chính thức để so giữa các team. Phần `questions[]`/`claims[]` trong trace do extractor của team sinh — BTC chấm tay ngẫu nhiên 20 lượt để kiểm tra extractor có "ăn gian" không (bỏ sót câu hỏi/claim).
4. Metric team tự bổ sung, simulator, Recall@k trên tài liệu riêng: chấm ở tiêu chí 4/6 theo chất lượng phân tích, không so số tuyệt đối.
