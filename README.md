# Harness Agent Call Center — SUDO CODE 2026, Vòng 1

Agent telesale tiếng Việt có bộ nhớ khách hàng xuyên phiên và đa kênh. Tool và bộ nhớ đi qua hai MCP server; có script đánh giá so với baseline không bộ nhớ.

Tài liệu chi tiết: [docs/HARNESS.md](docs/HARNESS.md) (cách chạy, cờ lệnh), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (kiến trúc), [docs/DATASET.md](docs/DATASET.md) (dataset), [docs/PLAN.md](docs/PLAN.md) (tiến độ). Phần mô tả gói dữ liệu của BTC nằm ở cuối file này.

## 1. Cài đặt

```bash
git clone https://github.com/buidong941-ship-it/SudoCode.git
cd SudoCode
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

## 2A. Cấu hình B2 và bản chốt v6p15

**Cập nhật 24/11/2026:** `profiles/local.env`, `profiles/kaggle.env`, `profiles/server.env` và `.env.example` đã bật cờ bản chốt v6p15; các cờ mới trong code vẫn mặc định tắt. JSON UI B2 là cấu hình tham chiếu riêng, không tự đổi thành profile v6p15. Hướng dẫn mở dashboard mới từ đầu nằm ở **mục 5**. Phần dưới giữ thông tin và lệnh đối chiếu B2-v52n ngày 17/11.

**R0 `integ-ui7c` đã có trong cây mã Git:** dùng `profiles/b2_integ_tt.json` để chạy đúng chế độ B2 hai tầng đã đo; profile mặc định vẫn là B2-v52n để không tự đổi hành vi khi nâng cấp. R0 để `PLANNER_GUIDANCE_DIR` và `IMPROVE_DIR` rỗng. Đường feedback → nháp DeepSeek Flash → người duyệt → gói guidance → đo R1 có trong `scripts/guidance_*.py`, `harness/guidance.py`, `improve/guidance_edit.py` và `ui/app_v2.py`; gói R1 chỉ nạp khi được chọn rõ, không tự kích hoạt.

```bash
python scripts/with_profile.py profiles/b2_integ_tt.json -- python run_eval.py --scenarios test_set/public_sample --config full --router rules --generator qwen --extractor hybrid --out runs/r0-integ/full.jsonl
UI_PROFILE=b2_integ_tt streamlit run ui/dashboard.py --theme.base=light
```

Nguồn là snapshot `runs/freeze/20261118-integ-ui7c`; kiểm tra SHA-256 trong snapshot khớp 284/284 file lúc ghép. `runs/` không lên Git, nên bản clone cần bộ kịch bản/dữ liệu đánh giá riêng để tái lập số dev92. R0 là bản tham chiếu tương đối: H13 còn các ca tạo đơn trái ý khách.

**Bản tham chiếu B2-v52n ngày 17/11** có kiến trúc và env giống hệt B2-v51-A:
- `ARCH=target`, `PLANNER_VARIANT=b2_jev`;
- DeepSeek `deepseek-v4-flash` hiểu lời khách (tắt thinking);
- Jev `jev-latest` chọn từng bước của planner;
- Qwen3-4B (vLLM) ghép câu có giới hạn; giá, KM và kết quả thao tác do code dựng từ kết quả tool.

Khác v51-A ở lõi (V52, thu hẹp):
- phản hồi ngân sách khách nêu (so với giá mẫu đang bàn, gợi ý mẫu thay thế hoặc báo chưa có);
- trả lời theo nhóm hàng khách vừa nêu (không quay về mẫu đang bàn, hỏi rõ khi khách nêu nhiều nhóm);
- phạm vi câu hỏi chốt đầu lượt, không mời đọc mẫu ngoài nhóm khách hỏi (P1).

Env nằm trong [profiles/b2_v52n.json](profiles/b2_v52n.json) (có trong Git; env giống hệt `profiles/b2_v51a.json`). **Mặc định của `core/config.py` vẫn là B1**: không nạp profile thì lệnh chạy **không phải** B2.
- Code: freeze `runs/freeze/20261117-v52n-ui`. Lõi = `runs/freeze/20261117-v52n-cand`; chỉ khác ở UI / profile / tunnel.
- Snapshot và bằng chứng: `runs/snapshots/20261117-b2-v52n/` (thư mục `runs/`, không có trong Git), gồm source, freeze, kết quả CPU / cổng / API, test và quyết định nghiệm thu.
- **Nghiệm thu theo quyết định bổ sung sau kết quả** (`docs/DE-XUAT/QUYET-DINH-NGHIEM-THU-BO-SUNG-V52N-2026-11-17.md`): nghiệm thu ban đầu vi phạm ở N-TXN (lỗi có sẵn). **Không phải mọi test đều đạt.**
- **Quay lui:** `c5-cand` (B2-v51-A + UI / C.5): `profiles/b2_v51a.json`, freeze `runs/freeze/20261116-c5-cand`, tệp gốc ở `runs/extra_1115/c5_files/` và `runs/extra_1115/v52nui_rollback/`.

**Hạn chế công khai (còn tồn tại):**
- N-TXN: khách vừa đặt hàng vừa hỏi nhóm khác → đơn đúng, câu hỏi bị bỏ sót;
- `asks=other`: câu hỏi nhóm hàng đôi khi bị hiểu là "khác" → "chưa có thông tin";
- ngân sách lẫn giá: "vượt 2 triệu cũng được, lên đơn" bị hỏi lại xác nhận giá;
- vòng lặp xác nhận: sau khi khách bổ sung địa chỉ, "Tôi xác nhận" có thể bị hỏi lại (tái hiện được ở CPU);
- mặt hàng ngoài danh mục;
- đại từ mơ hồ giữa nhiều mẫu ("lấy cái máy đó").

**Số đo:** chưa có số dev92 cho v52n. Các số TSR 93,5% / HR giá 7,4% / TTFT p95 khoảng 3,9 s là của **B2-v50** (dev50, 16/11). R0 / R1 sẽ đo trên đúng source này.

### Cần gì

| Thành phần | Máy cá nhân (không GPU) | Kaggle (GPU T4 ×2) |
|---|---|---|
| `DEEPSEEK_API_KEY`, `TYPESAFE_API_KEY` | Ghi vào `.env` (từ `.env.example`). Không đưa lên Git | Kaggle → Add-ons → **Secrets** của notebook |
| Qwen3-4B qua vLLM | Không chạy được trên máy yếu. Dùng `--generator offline` / `UI_QWEN=off`, kết quả **khác cấu hình đo** | `scripts/run_suite.py` tự bật vLLM |
| RAG | `RAG_MODE=bm25` (không cần model embedding) | như cấu hình đo |

### Chạy trên máy cá nhân

Trên Windows, đặt `PYTHONIOENCODING=utf-8` trước khi chạy. `scripts/with_profile.py` nạp đúng env của profile cho lệnh phía sau. Biến có trong profile luôn ghi đè biến cùng tên còn sót trong shell, và script in cảnh báo khi ghi đè.

```bash
python scripts/with_profile.py profiles/b2_v52n.json --show          # xem env sẽ dùng (không có khóa)
# chạy thử luồng B2 trên bộ mẫu BTC; generator offline vì máy không có vLLM → KHÔNG dùng số này để báo cáo
python scripts/with_profile.py profiles/b2_v52n.json -- python run_eval.py --scenarios test_set/public_sample \
    --config full --router rules --generator offline --extractor hybrid --out runs/local/b2_full.jsonl
python scripts/with_profile.py profiles/b2_v52n.json -- python run_eval.py --scenarios test_set/public_sample \
    --config baseline_no_memory --router rules --generator offline --extractor hybrid --out runs/local/b2_base.jsonl
python eval/reference_eval.py --scenarios test_set/public_sample --trace runs/local/b2_full.jsonl --baseline runs/local/b2_base.jsonl
```

Muốn có đúng cấu hình đo trên máy có GPU, thay `--generator offline` bằng `--generator qwen` và bật vLLM theo [docs/HARNESS.md](docs/HARNESS.md).

### Chạy trên Kaggle (cách nhóm dùng để đo)

1. **Chuẩn bị:**
   - `pip install kaggle`;
   - tải API token `kaggle.json` của tài khoản Kaggle;
   - lệnh `kaggle` phải có trong PATH. Trên Windows thường ở `%APPDATA%\Python\Python3xx\Scripts`.
2. **Đẩy job.** `kaggle_job.py` đóng gói repo thành dataset `<user>/sudocode-repo` (bỏ `runs/`, `data/`, `.env`, khóa…), rồi đẩy kernel.

   **Kernel tự chạy ngay khi đẩy.** Job cần khóa API thì lần tự chạy đầu sẽ dừng vì chưa có secret. Khi đó mở kernel → Add-ons → Secrets → bật `DEEPSEEK_API_KEY` và `TYPESAFE_API_KEY` → Save Version / Run All.

   ```bash
   ENV="$(python scripts/with_profile.py profiles/b2_v52n.json --kaggle-env)"
   # bộ mẫu BTC, Full (GPU)
   python scripts/kaggle_job.py --cred kaggle.json push --job b2-sample-full --sets sample --configs full \
       --router rules --generator qwen --extractor hybrid --workers 1 --max-hours 2 --env $ENV
   # bộ dev92 của nhóm: dựng suite từ registry trong job (cần datagen/datasets/), Baseline
   python scripts/kaggle_job.py --cred kaggle.json push --job b2-dev-base --sets /tmp/suites/dev --configs baseline_no_memory \
       --router rules --generator qwen --extractor hybrid --workers 1 --max-hours 3 --env $ENV \
       --pre '{python} scripts/registry_sync_check.py --suite dev --materialize /tmp/suites/dev --out {out}/registry'
   ```

   - Full và Baseline nên chạy **hai job song song trên hai tài khoản**, mỗi job khoảng 45–55 phút trên dev92.
   - Cùng một máy thì đẩy **lần lượt từng job**, vì các job dùng chung thư mục `build/`.
3. **Theo dõi và lấy kết quả:**
   ```bash
   python scripts/kaggle_job.py --cred kaggle.json status --job b2-dev-base
   python scripts/kaggle_job.py --cred kaggle.json pull --job b2-dev-base         # → runs/kaggle/b2-dev-base/
   ```
   Chấm hai trace bằng `eval/reference_eval.py`, như mục 2.
4. **Kiểm CPU không cần khóa** (fixture ép nhãn, không gọi API):
   ```bash
   python scripts/kaggle_job.py --cred kaggle.json push --job cpu-check --accelerator none --no-setup --pre-only \
       --sets sample --configs full --router rules --generator offline --extractor rules \
       --pre "{python} tests/target_arch_check.py" --pre "{python} tests/c5_loop_check.py" --pre "{python} tests/ui_b2_check.py"
   ```
   `tests/ui_b2_check.py` cần `profiles/b2_v51a.json`; `tests/ui_v52n_check.py` cần `profiles/b2_v52n.json` (cả hai có trong repo) cùng tệp freeze / snapshot của v52n.
5. **Lỗi hay gặp trên Windows:**
   - `PermissionError … .kaggle-uploads`: đặt `TMP` / `TEMP` sang một thư mục ghi được rồi đẩy lại.
   - `UnicodeEncodeError`: đặt `PYTHONIOENCODING=utf-8`.

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
git clone ... && cd SudoCode
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

## 5. Dashboard: chạy từ đầu trên máy cá nhân và Kaggle

Giao diện mới chạy bằng **`ui/dashboard.py`**; trên Kaggle dùng **`kaggle/ui_dashboard.py`**. Dashboard dùng lại engine và năm tab của `ui/app_v2.py`, thêm theme và biểu đồ từ report thật. Font được đóng gói trong `ui/assets/fonts/`. Tool thương mại vẫn là mock của BTC.

| Cách chạy | Máy cá nhân | Kaggle | Dữ liệu UI |
|---|---|---|---|
| **Máy yếu: chạy toàn bộ trên Kaggle (5.1c)** | Chỉ mở trình duyệt | Chạy UI, agent và Qwen | Tải về trước khi tắt phiên |
| **Giữ bộ nhớ tại máy: UI cá nhân + Qwen Kaggle (5.1 → 5.1b)** | Chạy Streamlit, agent và gọi DeepSeek/Jev qua API | Chỉ chạy Qwen GPU | Giữ tại máy cá nhân |

**Chọn cấu hình:** `RUN_PROFILE=local|kaggle` nạp `profiles/<tên>.env` theo nơi chạy; các file env này đã có cờ v6p15. `UI_PROFILE` chọn một JSON trong `ui/engine.py`, ghi đè các biến có trong JSON đó. Các lệnh dưới dùng `b2_integ_tt` để mở luồng candidate có tư vấn hai tầng và duyệt hướng dẫn. JSON này hiện vẫn mang nhãn H13 Jev gate v6; **mở dashboard không đồng nghĩa tái lập đúng cấu hình đã đo của v6p15**. `b2_v52n`/`b2_v51a` là các profile đối chiếu cũ. Muốn đổi `UI_PROFILE`, dừng rồi khởi động lại Streamlit.

### 5.1. Chuẩn bị máy cá nhân từ đầu (Windows / PowerShell)

**Bước 1 — chuẩn bị Python, Git và mã nguồn.** Cài Python 3 có `pip`/`venv` và Git, mở PowerShell mới, kiểm `py --version` và `git --version`.

Máy mới, clone bản đã commit **và push** lên GitHub:

```powershell
git clone https://github.com/buidong941-ship-it/SudoCode.git
Set-Location SudoCode
```

Nếu đã có dự án trên máy thì bỏ bước clone, mở PowerShell tại gốc repo. Ví dụ:

```powershell
Set-Location 'D:\User\Documents\competition\SUDO CODE\copy_project'
```

**Bước 2 — tạo môi trường và cài UI.** Không cần kích hoạt venv, nên không vướng PowerShell Execution Policy:

```powershell
py -3 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements-ui.txt
```

`requirements-ui.txt` đã bao gồm dependency core. Không cài vLLM lên Windows trong luồng này: Qwen chạy ở Kaggle. Không cần tải `dataset/`, kết quả đánh giá hay model embedding để mở UI với BM25. Nếu máy quá ít RAM để cài dependency, dùng **5.1c**, chỉ mở trình duyệt tại máy cá nhân.

**Bước 3 — điền khóa API.** Chỉ tạo `.env` nếu chưa có, không ghi đè cấu hình cũ:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Điền giá trị thật vào hai dòng trong `.env`, lưu rồi đóng Notepad:

```dotenv
DEEPSEEK_API_KEY=<khóa DeepSeek của bạn>
TYPESAFE_API_KEY=<khóa TypeSafe/Jev của bạn>
```

Tiếp tục **5.1b** để bật Qwen rồi mở UI. Giữ `.env` ngoài Git.

### 5.1b. UI ở máy cá nhân, Qwen trên GPU Kaggle

**Trên Kaggle:** tạo notebook Private, bật **Internet** và **GPU T4** (hoặc T4 x2), rồi chạy **cell 1 của mục 5.1c** để clone repo. Cách này không cần gắn khóa DeepSeek/Jev hay mật khẩu UI vào Kaggle, vì agent và UI nằm trên máy cá nhân.

Chạy cell sau và giữ cell chạy trong lúc dùng UI:

```python
%cd /kaggle/working/SudoCode
!python -u kaggle/qwen_tunnel.py
```

Script tự cài vLLM, tải `Qwen/Qwen3-4B`, mở endpoint qua tunnel có khóa. Chờ khối **ĐẶT Ở MÁY CÁ NHÂN** in ra URL có đuôi `/v1` và khóa. Không chia sẻ output chứa khóa này.

**Trên máy cá nhân:** trong PowerShell tại gốc repo, dán URL/khóa từ Kaggle vào hai dòng đầu:

```powershell
$env:QWEN_BASE_URL = 'https://<tunnel-vua-in>.trycloudflare.com/v1'
$env:QWEN_API_KEY = '<khoa-Qwen-vua-in>'
$env:PYTHONIOENCODING = 'utf-8'
$env:RUN_PROFILE = 'local'
$env:UI_PROFILE = 'b2_integ_tt'
$env:RAG_MODE = 'bm25'
$env:TOOL_TRANSPORT = 'direct'
Remove-Item Env:UI_QWEN -ErrorAction SilentlyContinue
.\venv\Scripts\python.exe -m streamlit run ui/dashboard.py --theme.base=light --server.address=127.0.0.1 --server.port=8501
```

Mở **http://localhost:8501** trên trình duyệt. Giữ terminal Streamlit và cell Kaggle đang chạy. Lần sau không cần cài lại: bật Qwen, đặt **URL và khóa mới**, chạy lại khối lệnh trên. Dữ liệu UI vẫn ở máy cá nhân. Dừng UI bằng **Ctrl+C**, rồi dừng cell Qwen và Stop session trên Kaggle.

**Không có Qwen:** `$env:UI_QWEN='off'` chỉ tắt Qwen compose; UI ghi nhãn khác cấu hình đo. Cờ này **không tắt toàn bộ backend Qwen** (profile vẫn có extractor Qwen), cũng không tắt DeepSeek/Jev, nên không coi đây là cách chạy hoàn toàn offline. `legacy_offline` là profile giao diện/pipeline cũ, không dùng làm bằng chứng chất lượng B2/v6p15. TTFT qua tunnel có thêm độ trễ mạng, không so trực tiếp với số đo trên Kaggle.

### 5.1c. Chạy toàn bộ trên Kaggle — hướng dẫn từng cell notebook

Máy cá nhân chỉ cần trình duyệt. **Commit và push bản có dashboard lên GitHub trước khi clone**; commit riêng ở máy chưa làm Kaggle thấy code mới. Repo cần có `ui/dashboard.py`, `ui/assets/`, `.streamlit/config.toml` và `kaggle/ui_dashboard.py`.

**Chuẩn bị notebook:** tạo notebook Python **Private**, bật **Internet** và **Accelerator: GPU T4 x2** (hoặc T4). Hoàn tất xác minh tài khoản nếu Kaggle yêu cầu. Không chọn P100 cho launcher vLLM này.

**Tự thêm khóa qua Add-ons:** mở **Add-ons → Secrets → Add Secret**, tạo đúng tên sau, rồi **tích gắn cả ba secret cho notebook hiện tại**:

| Label — phải đúng tên | Value — tự điền trong cửa sổ Secrets |
|---|---|
| `DEEPSEEK_API_KEY` | Khóa DeepSeek của bạn |
| `TYPESAFE_API_KEY` | Khóa Jev/TypeSafe của bạn; không đặt tên `JEV_API_KEY` |
| `UI_PASSWORD` | Mật khẩu mở UI tự đặt, ít nhất 8 ký tự |

Khóa không ghi vào code cell, không đưa `.env` lên GitHub. Mật khẩu bảo vệ link UI công khai do tunnel tạo ra.

**Cell 1 — clone repo và kiểm đúng source** (phiên mới, chạy một lần):

```python
%cd /kaggle/working
!git clone https://github.com/buidong941-ship-it/SudoCode.git SudoCode
%cd /kaggle/working/SudoCode

from pathlib import Path
for name in ('ui/dashboard.py', 'ui/assets/dashboard.css',
             'ui/assets/fonts/BeVietnamPro-Regular.ttf',
             '.streamlit/config.toml', 'kaggle/ui_dashboard.py'):
    assert Path(name).is_file(), f'Thiếu {name}: kiểm lại nhánh và việc push code.'
!git log -1 --oneline
```

Clone lấy nhánh mặc định của repo. Nếu bạn push lên nhánh khác, thêm `--branch <ten-nhanh>` sau `git clone`. Đối chiếu dòng commit in ra với bản vừa push. Repo riêng tư cần quyền đọc GitHub; không dán token vào cell hay URL clone lưu trong notebook.

**Cell 2 — nạp Secrets vào môi trường, chỉ in trạng thái:**

```python
import os
from kaggle_secrets import UserSecretsClient

client = UserSecretsClient()
for name in ('DEEPSEEK_API_KEY', 'TYPESAFE_API_KEY', 'UI_PASSWORD'):
    os.environ[name] = client.get_secret(name)
    assert os.environ[name], f'{name} đang trống; thêm và gắn lại secret.'
    print(name, 'đã nạp')
assert len(os.environ['UI_PASSWORD']) >= 8, 'UI_PASSWORD cần ít nhất 8 ký tự.'
```

Nếu cell báo thiếu/quyền truy cập secret, quay lại Add-ons → Secrets và tích gắn cho notebook này, rồi chạy lại **cell 2**. Không dùng `print(os.environ)` hoặc in giá trị các khóa. Launcher cũng có cơ chế đọc Secrets; cell này giúp phát hiện thiếu khóa trước khi chờ cài/tải model.

**Cell 3 — kiểm GPU:**

```python
!nvidia-smi -L
```

Cần thấy GPU T4. Nếu chưa có GPU, đổi Accelerator rồi Restart session và chạy lại từ cell 1; dữ liệu thư mục làm việc có thể không còn sau khi đổi phiên.

**Cell 4 — chọn profile và chạy dashboard:**

```python
%cd /kaggle/working/SudoCode
import os
os.environ['UI_PROFILE'] = 'b2_integ_tt'
os.environ['PYTHONIOENCODING'] = 'utf-8'
!python -u kaggle/ui_dashboard.py
```

**Không cần cell `pip install` riêng.** Launcher tự cài `requirements-ui.txt`, tạo venv vLLM riêng `/tmp/vllm-venv` (Python 3.12 theo `scripts/setup_env.sh`), tải Qwen3-4B và cloudflared, rồi bật UI. DeepSeek/Jev dùng khóa đã nạp từ Secrets; Qwen chạy nội bộ trên GPU. Lần đầu mỗi phiên có thể mất nhiều phút. **Giữ cell 4 chạy**, không Interrupt trong lúc dùng UI.

Khi sẵn sàng, output có:

```text
UI sẵn sàng nội bộ
UI mở được qua URL công khai (trang yêu cầu mật khẩu UI_PASSWORD)
================ MỞ UI ================
Link: https://<ngau-nhien>.trycloudflare.com
```

**Mở UI:** bấm **Link** trong output cell 4 trên trình duyệt máy cá nhân, nhập giá trị `UI_PASSWORD` bạn đã đặt trong Secrets. Không mở `localhost:8501` trên máy cá nhân cho cách này: UI đang nằm trên Kaggle. Chạy `kaggle/ui_tunnel.py` sẽ mở bản UI cũ; cần dùng đúng `kaggle/ui_dashboard.py`.

**Thử luồng chính:**

1. Kiểm thanh bên báo sẵn sàng, hai khóa API có, đúng profile; mở thông tin kỹ thuật để xem cảnh báo cấu hình/hash nếu có.
2. Nhập **Tên nhân viên**, **Khách demo**, chọn **Có bộ nhớ**. Với candidate, chọn **Tư vấn hai tầng (B2-TT)** trước khi mở cuộc gọi; để gói hướng dẫn tắt khi chưa có gói đã duyệt.
3. Tab **Cuộc gọi** → **Bắt đầu cuộc gọi mới** → nhập lời khách → **Kết thúc cuộc gọi**. Gọi lần hai cùng SĐT/namespace để xem **Call Brief**. Hoặc tab **Demo C.6** → **Chạy demo từ đầu**.
4. Clone sạch không có `runs/`, nên tab **Chỉ số** có thể trống. Cần report phù hợp để hiện số đo; dashboard không tự tạo số liệu thay thế.

**Lưu trước khi tắt:** kết thúc cuộc gọi đang mở, thanh bên → **Chuẩn bị gói dữ liệu UI để tải về** → **Tải ui_data.zip**. Dữ liệu ở `/kaggle/working/ui_data`; phiên mới không tự khôi phục dữ liệu phiên cũ. Chỉ chia sẻ link/mật khẩu cho người được phép thao tác dữ liệu demo chung.

**Cell 5 — dự phòng tải dữ liệu** (chỉ chạy sau khi đã dừng cell 4, nếu không tải được qua UI):

```python
import shutil
shutil.make_archive('/kaggle/working/ui_data', 'zip', '/kaggle/working/ui_data')
```

Tải `/kaggle/working/ui_data.zip` ở khung Output. Dừng cell launcher bằng **■ / Interrupt**, rồi **Stop session** để ngừng dùng GPU. Link chỉ sống trong phiên hiện tại; chạy lại có link mới.

**Lần chạy sau / cập nhật code:** phiên Kaggle mới thì chạy lại từ cell 1. Nếu repo vẫn còn, dừng launcher trước, chạy `!git -C /kaggle/working/SudoCode pull --ff-only`, kiểm commit rồi chạy lại cell 2–4. Sau khi đổi Secrets, chạy lại cell 2 và khởi động lại launcher; tiến trình UI đang chạy không tự nhận khóa mới.

**Lỗi thường gặp**

| Hiện tượng | Cách xử lý |
|---|---|
| Thiếu file dashboard / mở giao diện cũ | Kiểm commit/nhánh đã push và lệnh entrypoint ở cell 4 |
| `No module named streamlit` ở máy cá nhân | Cài `requirements-ui.txt` bằng đúng `venv\Scripts\python.exe` như mục 5.1 |
| Cổng 8501 đã dùng | Dừng Streamlit cũ hoặc đổi `--server.port=8502`, mở `http://localhost:8502` |
| Không thấy Secrets / thiếu khóa | Thêm đúng label và tích gắn; chạy lại cell 2 rồi khởi động lại cell 4 |
| `UI_PASSWORD` quá ngắn | Sửa secret thành ít nhất 8 ký tự rồi nạp/chạy lại |
| Nút mở cuộc gọi bị khóa / `code lệch freeze` | Dùng source, JSON profile và freeze cùng phiên bản; không bỏ kiểm hash hay chép freeze cũ vào source mới |
| Nhãn `chưa kiểm hash code` | Không có `code_sha256.txt` ở freeze mà JSON chỉ định; UI cho chạy nhưng chưa xác minh đúng code đã đo |
| Qwen timeout khi UI ở máy cá nhân | Cell Qwen phải còn chạy; đặt lại URL đuôi `/v1` và khóa mới, khởi động lại Streamlit |
| vLLM lỗi / không thấy GPU | Chọn GPU T4, bật Internet, Restart session; đọc log vLLM |
| UI trắng / Streamlit thoát / không có link | Xem log sau khi dừng cell 4 bằng cell bên dưới |
| Link hết hoạt động | Kiểm cell launcher và phiên Kaggle; chạy lại để lấy link mới |
| Lỗi tiếng Việt trên Windows | Đặt `PYTHONIOENCODING=utf-8` trước khi khởi động như lệnh mẫu |

**Cell xem log khi lỗi** (dừng cell launcher trước để có thể chạy cell khác):

```python
!tail -50 /kaggle/working/streamlit.log
!tail -50 /kaggle/working/vllm_tunnel.log
```


### 5.2. Kiểm khởi động (thanh bên trái)

Profile được chọn một lần cho cả tiến trình qua `UI_PROFILE`, không đổi giữa phiên. Lúc mở, UI kiểm:

- `ARCH=target` và `PLANNER_VARIANT=b2_jev`;
- model, ngân sách planner và các cờ hợp đồng khớp JSON của `UI_PROFILE` đã chọn;
- với `b2_v52n` hoặc `b2_integ_tt`, nếu có `code_sha256.txt` tại đường dẫn `freeze` trong JSON thì kiểm hash; lệch → từ chối. Thiếu tệp freeze → ghi nhãn chưa kiểm hash;
- nếu profile có snapshot đã đo trên máy, JSON phải khớp snapshot đó. `b2_v51a` chỉ cảnh báo khi lệch hash code theo hành vi cũ.

Lỗi kiểm cấu hình hoặc hash thuộc diện từ chối thì thanh bên báo đỏ và nút **Bắt đầu cuộc gọi mới** bị khóa.

Thanh bên còn có:

- **Chuẩn bị gói dữ liệu UI để tải về**: đóng `ui_data.zip` (bộ nhớ, feedback, trace, kho duyệt FAQ, trạng thái gói) để tải về;
- **Chế độ** `full` / `baseline_no_memory`: mỗi chế độ có engine, namespace (`ui:<profile>:<chế độ>:<tên>`) và phiên riêng;
- **Tên khách demo**: mỗi tên là một namespace bộ nhớ riêng;
- **Tên nhân viên / người duyệt**: bắt buộc trước khi like / dislike hay duyệt FAQ;
- **Gói FAQ đang kích hoạt**: chỉ áp dụng cho cuộc gọi mở sau, không đổi giữa cuộc.

### 5.3. Các tab

- **Cuộc gọi:**
  - Nhập SĐT mô phỏng, kênh (hotline / Zalo / fanpage) và ngày gọi (để trống thì lấy 2026-10-15). Bấm **Bắt đầu cuộc gọi mới**, gõ lời khách, rồi bấm **Kết thúc cuộc gọi** để lưu phiên. Lưu phiên chờ audit nền xong; câu đã phát thì hiện ngay từ trước đó.
  - Câu hiện trên màn hình chính là câu backend phát qua `on_emit`, đã qua guardrail. Không giả streaming: TTFT bằng Total.
  - Mỗi lượt có mã sự kiện, nên Streamlit chạy lại trang không gọi agent hay tool ghi lần hai.
  - Gọi lần hai với cùng SĐT thì **Call Brief** hiện ra.
  - Mỗi câu trả lời có:
    - "chi tiết lượt": goal, các bước B2, tool, FAQ đã dùng;
    - nút 👍 / 👎 kèm ghi chú. Feedback ghi theo từng câu vào `data/ui/feedback.jsonl` và là **nguồn feedback thứ hai** của C.5.
- **Demo C.6:** chọn chạy tới cuộc 1, 2 hoặc 3, rồi **Chạy demo từ đầu**.
  - Cuộc 1: tư vấn, báo giá kèm KM, khách hẹn hỏi người nhà.
  - Cuộc 2 (3 ngày sau): nhận ra khách, không hỏi lại, chốt đơn.
  - Cuộc 3 (M2): khách hỏi vận đơn.

  Lời khách nằm trong `ui/engine.py` (`DEMO_SCRIPT`), viết riêng cho demo, không lấy từ bộ test.
- **Bộ nhớ:** dòng thời gian gồm phiên, báo giá, fact (có nguồn, hạn dùng, `superseded → #id` khi bị thay) và kết quả hành động (đơn tạo / cập nhật, hẹn gọi lại, chuyển máy).
- **Chỉ số:** chỉ tin các report đã gắn nhãn phiên bản, bộ dữ liệu, backend và ngày đo. Report của dev50 ghi rõ là **số của v50**. Report chưa gắn nhãn bị cảnh báo, không dùng làm số hiện hành.
- **Cải tiến (C.5):** xem mục 6. Đặt `C5_ROOT=<thư mục kho duyệt>` để chọn kho, mặc định `runs/c5/review`.

### 5.4. Bộ nhớ và tệp của UI

- `data/ui/memory.db`: bộ nhớ khách của UI. Muốn dùng DB khác thì đặt `DATABASE_URL=sqlite:///<đường dẫn>` trước khi chạy.
- `data/ui/feedback.jsonl`, `data/ui/traces/*.jsonl`: feedback và trace của UI, đầu vào cho bước gom gap của C.5.
- `data/c5/active.json`, `data/c5/activation_log.jsonl`: gói FAQ đang kích hoạt và lịch sử kích hoạt / quay lui.
- Nút **Xoá bộ nhớ khách này** xoá namespace hiện tại và đặt lại mock. Nút bị khóa khi đang trong cuộc gọi.

### 5.5. Kiểm thử UI (chạy trên Kaggle CPU, không cần khóa)

Ở tab **Cải tiến → Tiếp nhận & nhập nháp**, sau khi gửi **Cần cải thiện**, bấm **Soạn hướng dẫn từ feedback**.
DeepSeek dùng feedback cùng trace để phân loại và tạo bản nháp hợp lệ trong hàng chờ. Khóa `DEEPSEEK_API_KEY`
phải có trong môi trường UI. Xem kết quả phân tích ngay bên dưới nếu chưa có nháp, rồi sang **Duyệt từng hướng dẫn**.
Sau khi duyệt, đóng gói và kích hoạt để áp dụng cho cuộc gọi mới. Mục **Nhập bản nháp JSON đã soạn sẵn** là lựa chọn
thủ công; cần chọn tệp và điền người soạn mới bật nút nhập.

```bash
python tests/ui_dashboard_check.py  # dashboard mới: mật khẩu, 5 tab, gọi lại, feedback, biểu đồ report
python tests/ui_feedback_flow_check.py  # feedback → DeepSeek giả → nháp thật, chưa duyệt/kích hoạt
python tests/ui_v2_check.py         # luồng UI v2 dùng chung với dashboard
python tests/ui_password_check.py   # cổng mật khẩu
python tests/ui_b2_check.py         # khởi động B2, namespace, nạp / đổi / quay lui gói FAQ
python tests/ui_check.py            # pipeline cũ legacy_offline
```

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

Chi tiết ở [docs/HAM-IMPROVE.md](docs/HAM-IMPROVE.md). Các lệnh trên là khung chung (pipeline cũ).

### 6.1. Knowledge Gap Loop trên B2 (C.5, `scripts/c5_loop.py`)

Với cấu hình chính (`ARCH=target`), cơ chế cải tiến **chỉ nạp FAQ**. Gói có loại khác (playbook, exemplar, cue…) bị từ chối ngay khi mở phiên. Vòng gồm các bước:

```bash
# 1. gom gap từ HAI nguồn: điểm chấm tự động (trace + report, CHỈ bộ dev) và like/dislike của nhân viên ở UI
python scripts/c5_loop.py gaps --root runs/c5/review --trace runs/<x>/dev/full.jsonl --report runs/<x>/report.json \
    --feedback data/ui/feedback.jsonl --ui-trace data/ui/traces/*.jsonl
# 2. bản nháp FAQ (cần DEEPSEEK_API_KEY; nhóm chạy trên Kaggle CPU)
python scripts/with_profile.py profiles/b2_v52n.json -- python scripts/c5_loop.py draft --root runs/c5/review --limit 30
# 3. người duyệt: tab Cải tiến của UI (C5_ROOT=runs/c5/review), hoặc
python -m improve review approve <id> --by "<tên>" --reason "đúng nguồn" --root runs/c5/review
# 4. đóng gói FAQ đã duyệt (hash + test hồi quy tự sinh), kích hoạt, quay lui
python scripts/c5_loop.py package  --root runs/c5/review --name r1 --by "<tên>" --out runs/c5/packages/r1
python scripts/c5_loop.py activate --pkg runs/c5/packages/r1 --by "<tên>" --reason "..."
python scripts/c5_loop.py rollback --by "<tên>" --reason "..."
python scripts/c5_loop.py status
```

- **Bản nháp có nguồn:**
  - DeepSeek chỉ **chọn câu policy theo ID** và đặt chủ đề / câu hỏi theo cách khách nói. Câu trả lời của FAQ là các câu **nguyên văn** của đúng một đoạn policy được trích.
  - Code kiểm lại từng câu với văn bản gốc. Đoạn nội bộ, hết hiệu lực, có số tiền hay SĐT đều bị chặn.
  - Không có nguồn phù hợp thì gap giữ nguyên "chưa trả lời được", không bịa chính sách.
- **Test hồi quy:** do code dựng từ template, gồm câu khách và cụm nguyên văn phải nói, đặt ở `runs/c5/packages/<gói>/regression/`. Đây là suite riêng, **không** trộn vào bộ đánh giá cố định của R0 / R1, và không được gọi là holdout.
- **Gói FAQ:**
  - `PACKAGE.json` ghi hash, nguồn của từng FAQ và người duyệt.
  - Gói không được sửa sau khi tạo: hash lệch thì từ chối kích hoạt.
  - Kích hoạt và quay lui đổi nguyên khối (`data/c5/active.json`, có nhật ký). UI chỉ nạp gói khi **mở cuộc gọi mới**.
- **Đo:** R0 chạy với `IMPROVE_DIR` rỗng; R1 thêm `IMPROVE_DIR=<thư mục gói>`. Hai vòng phải cùng code, cùng bộ đánh giá, cùng model, chỉ khác gói FAQ.
- **Trace:** mỗi lượt ghi `improve.retrieved` (FAQ được tra thấy) và `improve.used` (FAQ có câu thực sự vào câu trả lời cuối). Tra thấy không có nghĩa là đã dùng.
- Nếu FAQ lập từ gap của dev rồi đo lại trên dev, phải ghi rõ đó **không phải** phép đo độc lập.

## 7. Cờ cấu hình thêm từ 01–02/11/2026

| Cờ | Mặc định | Ý nghĩa |
|---|---|---|
| `JEV_DROP_POLICY` | `qwen` | Jev bỏ slot `address`/`payment` mà luật đã cắt được thì gọi Qwen làm trọng tài (`accept` = hành vi cũ) |
| `EXTRACTOR_CERT_VERSION` | `1` | `2` = CERT v2 (`docs/DE-XUAT-CERT-V2-2026-11-02.md`) |
| `PLANNER_BACKEND` / `PLANNER_JEV_MIN_CONF` | `rules` / `0.6` | Planner LLM có giới hạn, chỉ dùng ở nhánh fallback (`harness/planner_llm.py`) |
| `LEXICON_INCLUDE` | `approved` | Mức nạp lexicon slot (`harness/lexicon/slots.json`, duyệt bằng `scripts/lexicon_review.py`) |
| `IMPROVE_DIR` | (trống) | Nạp đề xuất đã duyệt của `improve/`. Với `ARCH=target` chỉ nhận gói FAQ (mục 6.1) |
| `UI_PROFILE` / `UI_QWEN` / `C5_ROOT` | `b2_v52n` (đối chiếu: `b2_v51a`) / `on` / `runs/c5/review` | UI: profile backend; tắt Qwen compose khi không có vLLM (ghi nhãn); kho duyệt FAQ |

## 8. Cấu hình đích M1 (chốt 10/11/2026, bản R0) — LỊCH SỬ

> **Lưu ý:** mục này là cấu hình cũ (planner rules, Jev giả lập), giữ lại để đối chiếu số đo lịch sử. Cấu hình chính hiện hành là **B2-v52n**, xem mục 2A.

Đường tham chiếu là planner rules; bộ hiểu mới chỉ chạy shadow. Biến môi trường dùng trong các lần đo 10/11:

```bash
PLANNER_SELECTOR=rules GOAL_CONTRACT=1 CONTRACT_V2=1          # CONTRACT_V2 mặc định bật từ 10/11 (D59)
EXTRACTOR_CONFIDENCE_GATE=1 EXTRACTOR_CERT_VERSION=2 EXTRACTOR_JEV_HYBRID=1 EXTRACTOR_LLM=qwen
PLANNER_BACKEND=rules PRODUCT_LEXICON=1 ORDER_QTY=1 LEXICON_INCLUDE=approved IMPROVE_DIR=
REPLY_STYLE=short LLM_MAX_TOKENS=160 LLM_TEMPERATURE=0 STRIP_QUESTIONS=1 QWEN_MODEL=Qwen/Qwen3-4B
python run_eval.py --scenarios <bộ> --config full --router jev --generator qwen --extractor hybrid --workers 2
```

- Không có API Jev thật thì thêm `JEV_SIMULATED=1`: mọi lời gọi Jev (router, nhãn slot/claim, phân loại câu hỏi) chuyển sang Qwen
  trên cùng vLLM và chặn client thật. Số đo khi đó phải ghi là "Jev giả lập". Cấu hình này không gọi DeepSeek.
- Quyền (D60): số điện thoại khách tự đọc chỉ là số liên hệ, không mở hay gộp hồ sơ CRM. Danh tính lấy theo caller ID/zalo_id/fb_id
  của kênh. Đây không phải xác thực mạnh: không có OTP.
- Reset trước demo: nút **Xoá bộ nhớ khách này** hoặc **Chạy demo từ đầu** trong `ui/dashboard.py` (mục 5). Khi chạy dòng lệnh, đặt
  `DATABASE_URL=sqlite:///<file mới>` để mỗi lần chạy có bộ nhớ riêng.
- Bản đóng băng: `runs/snapshots/20261110-target-r0/`. Gói C.5 (`IMPROVE_DIR=improve`) đã duyệt nhưng **tắt** vì đo R1 không hơn R0.
- Số đo V3 dev (Jev giả lập): baseline → đích RQR 69,6 → 0 (giảm 100%), TSR 70,4 → 98,8, HR giá&KM 10,3 → 8,9 (chưa đạt ≤ 5).
- Kết quả và giới hạn: `docs/PLAN/THUC-THI-FINAL-PROGRESS.md`.

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
