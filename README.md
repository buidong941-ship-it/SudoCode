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

## 2A. Cấu hình chính hiện hành: B2-v52n (chốt 17/11/2026)

**R0 `integ-ui7c` đã có trong cây mã Git:** dùng `profiles/b2_integ_tt.json` để chạy đúng chế độ B2 hai tầng đã đo; profile mặc định vẫn là B2-v52n để không tự đổi hành vi khi nâng cấp. R0 để `PLANNER_GUIDANCE_DIR` và `IMPROVE_DIR` rỗng. Đường feedback → nháp DeepSeek Flash → người duyệt → gói guidance → đo R1 có trong `scripts/guidance_*.py`, `harness/guidance.py`, `improve/guidance_edit.py` và `ui/app_v2.py`; gói R1 chỉ nạp khi được chọn rõ, không tự kích hoạt.

```bash
python scripts/with_profile.py profiles/b2_integ_tt.json -- python run_eval.py --scenarios test_set/public_sample --config full --router rules --generator qwen --extractor hybrid --out runs/r0-integ/full.jsonl
UI_PROFILE=b2_integ_tt streamlit run ui/app_v2.py
```

Nguồn là snapshot `runs/freeze/20261118-integ-ui7c`; kiểm tra SHA-256 trong snapshot khớp 284/284 file lúc ghép. `runs/` không lên Git, nên bản clone cần bộ kịch bản/dữ liệu đánh giá riêng để tái lập số dev92. R0 là bản tham chiếu tương đối: H13 còn các ca tạo đơn trái ý khách.

**Cấu hình chính** là B2-v52n. Kiến trúc và env giống hệt B2-v51-A:
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

## 5. Giao diện demo (UI)

UI Streamlit ở `ui/app.py` phục vụ demo của đề bài (C.6) và vòng cải tiến (C.5). UI tách khỏi core: chỉ gọi `CallSession` giống `run_eval.py`, không ghi tool thay agent. Bộ nhớ, feedback và trace của UI nằm ở `data/ui/` (ngoài Git), riêng với DB đo.

### 5.1. Cài và mở

UI không tải model nào về máy: DeepSeek và Jev gọi qua API, RAG dùng BM25, tool là mock của BTC. Riêng Qwen cần vLLM; trên máy không có GPU thì đặt `UI_QWEN=off`.

PowerShell (Windows), tại thư mục repo:

```powershell
venv\Scripts\python.exe -m pip install -r requirements-ui.txt   # = requirements.txt + streamlit
$env:PYTHONIOENCODING = "utf-8"
$env:UI_PROFILE = "b2_v52n"          # backend chính B2-v52n (đọc profiles/b2_v52n.json); "b2_v51a" = đối chiếu
$env:UI_QWEN = "off"                 # máy không có vLLM → nhãn "khác cấu hình đo"
venv\Scripts\python.exe -m streamlit run ui/app.py           # mở http://localhost:8501
```

Bash (Linux / macOS / Git Bash):

```bash
pip install -r requirements-ui.txt
UI_PROFILE=b2_v52n UI_QWEN=off streamlit run ui/app.py
```

- Khóa `DEEPSEEK_API_KEY` và `TYPESAFE_API_KEY` đọc từ `.env`. Thanh bên chỉ hiện có hoặc THIẾU, không hiện giá trị.
- Máy có vLLM (đặt `QWEN_BASE_URL`) thì bỏ `UI_QWEN=off` để chạy đúng cấu hình đo. Không có GPU thì mượn GPU Kaggle cho Qwen, xem **mục 5.1b**.
- Chỉ muốn xem giao diện, không có khóa: `UI_PROFILE=legacy_offline`. Profile này chạy pipeline cũ (rules + câu mẫu), UI ghi rõ **không phải B2**.
- Chạy trên server: thêm `--server.address 0.0.0.0 --server.port 8501`, rồi chuyển cổng về máy (`ssh -L 8501:localhost:8501 <server>`).

### 5.1b. UI ở máy cá nhân, Qwen chạy trên GPU Kaggle (đúng cấu hình đo)

Máy cá nhân không chạy được vLLM. Cách này mượn GPU của Kaggle chỉ cho Qwen3-4B, còn UI, khóa DeepSeek / TypeSafe, bộ nhớ và feedback vẫn ở máy bạn. Script [kaggle/qwen_tunnel.py](kaggle/qwen_tunnel.py) làm các việc:
- bật vLLM với đúng model của `profiles/b2_v52n.json` (giống b2_v51a);
- khóa endpoint bằng một khóa ngẫu nhiên, mỗi lần chạy một khóa mới;
- mở **quick tunnel cloudflared** (không cần tài khoản) ra một URL `https://….trycloudflare.com`;
- kiểm gọi có khóa qua URL đó trả đúng model, gọi **không khóa** thì bị từ chối;
- in hai dòng để bạn đặt ở máy.

**Bước 1: trên Kaggle**
1. Tạo notebook mới. Settings → **Accelerator: GPU T4**, **Internet: On** (tài khoản Kaggle phải xác minh số điện thoại mới bật được Internet).
2. Đưa repo vào notebook bằng một trong hai cách:
   - **Dataset do `kaggle_job.py` đóng gói:**
     1. Ở máy, chạy `python scripts/kaggle_job.py --cred kaggle.json dataset`.
     2. Trong notebook: Add Input → dataset `<user>/sudocode-repo`.
     3. Chạy cell, sửa đường dẫn theo kết quả `!ls /kaggle/input` (một số tài khoản có thêm tầng `datasets/<user>/`):
        ```python
        !cp -r /kaggle/input/sudocode-repo/repo /kaggle/working/SudoCode
        ```
   - **`git clone`** nếu repo cho phép:
     ```python
     !git clone https://github.com/buidong941-ship-it/SudoCode.git /kaggle/working/SudoCode
     ```
3. Chạy cell sau và **để nguyên cho nó chạy**. Lần đầu của mỗi phiên mất vài phút để cài vLLM và tải model.
   ```python
   !cd /kaggle/working/SudoCode && python kaggle/qwen_tunnel.py
   ```
   Khi xong, cell in một khối "ĐẶT Ở MÁY CÁ NHÂN" gồm `QWEN_BASE_URL` (đuôi `/v1`) và `QWEN_API_KEY`.

**Bước 2: trên máy cá nhân.** Dán hai dòng vừa in vào PowerShell, rồi mở UI như mục 5.1 nhưng **không** đặt `UI_QWEN=off`:

```powershell
$env:QWEN_BASE_URL = "https://<…>.trycloudflare.com/v1"     # dán từ output Kaggle
$env:QWEN_API_KEY  = "<khóa in ra>"
$env:PYTHONIOENCODING = "utf-8"; $env:UI_PROFILE = "b2_v52n"
Remove-Item Env:UI_QWEN -ErrorAction SilentlyContinue
venv\Scripts\python.exe -m streamlit run ui/app.py
```

Thanh bên phải hiện **"B2-v52n (cấu hình chính 17/11), generator Qwen như cấu hình đo"** và dòng **"Code: freeze `runs/freeze/20261117-v52n-ui` · khớp 255 tệp"**. Code lệch freeze thì UI từ chối chạy.

**Lưu ý:**
- **Khóa:**
  - URL tunnel là công khai. Endpoint chỉ trả lời khi có khóa, và khóa chỉ hiện trong output của notebook.
  - Không để notebook ở chế độ Public, không chia sẻ output, không commit khóa.
  - Muốn tự chọn khóa thì đặt `QWEN_TUNNEL_KEY` trước khi chạy.
- **Vòng đời:**
  - Dừng cell (■) thì tắt cả tunnel lẫn vLLM.
  - Phiên Kaggle tắt (hết giờ, để không quá lâu, hết quota GPU) thì URL chết. Chạy lại cell sẽ được **URL và khóa mới**, phải đặt lại ở máy.
  - Quick tunnel của Cloudflare dành cho thử nghiệm, không cam kết thời gian sống.
- **Độ trễ:** mỗi câu có Qwen đi thêm một vòng qua internet. TTFT trên UI kiểu này **không** so được với số đo trên Kaggle.
- **Kiểm không cần phiên tương tác:** đặt `QWEN_TUNNEL_SELFTEST=1` thì script cài vLLM, mở tunnel, kiểm có khóa / không khóa, chat thử một câu rồi tự dừng. Ở chế độ này script không in khóa và URL. Nhóm dùng chế độ này để kiểm script bằng job GPU theo lô.

### 5.1c. Chạy cả UI lẫn Qwen trên Kaggle, mở bằng link có mật khẩu (demo, quay video, người khác mở)

[kaggle/ui_tunnel.py](kaggle/ui_tunnel.py) chạy mọi thứ trên Kaggle. Qwen chỉ nghe ở cổng nội bộ của máy, không mở ra ngoài. Chỉ UI được mở qua tunnel, và **bắt buộc có mật khẩu**.

**Khi nào dùng cách nào:**

| | 5.1b: UI ở máy cá nhân | 5.1c: UI trên Kaggle |
|---|---|---|
| Cài đặt ở máy | Python + streamlit | Không cần gì, chỉ trình duyệt |
| Độ trễ Qwen | Thêm một vòng qua internet | Qwen cùng máy với agent, sát lúc đo hơn |
| Khóa API | `.env` ở máy bạn | Kaggle Secrets |
| Ai mở được | Chỉ máy bạn | Ai có link **và** mật khẩu |
| Dữ liệu UI (feedback, bộ nhớ, duyệt FAQ) | Giữ ở máy, dùng tiếp cho vòng C.5 | **Mất khi phiên tắt** nếu không tải về |

**Các bước, làm đúng thứ tự:**

**Bước 0: chuẩn bị (làm một lần)**
1. Tài khoản Kaggle đã **xác minh số điện thoại** (Settings → Phone verification). Chưa xác minh thì không bật được Internet và GPU cho notebook.
2. Đưa code lên Kaggle thành dataset. Chạy ở máy, tại thư mục repo:
   ```bash
   pip install kaggle
   # kaggle.json: Kaggle → Settings → API → Create New Token
   python scripts/kaggle_job.py --cred kaggle.json dataset      # tạo / cập nhật dataset riêng tư <user>/sudocode-repo
   ```
   Lệnh này đóng gói repo và bỏ `runs/`, `data/`, `.env`, khóa… Mỗi lần sửa code thì chạy lại để có version mới.

   Vì bỏ `runs/`, dataset tạo bằng lệnh này không có tệp freeze. UI vẫn chạy nhưng ghi nhãn **"chưa kiểm hash code"**. Muốn UI kiểm code đúng freeze v52n, dùng dataset do job kiểm UI đẩy lên: job `v52nui-check-1117` kèm `runs/freeze/20261117-v52n-ui/code_sha256.txt` và config snapshot (17/11: `midzed/sudocode-repo`). Nhãn khi đó là **"Code: … khớp 255 tệp"**.

   Repo GitHub cho phép clone thì có thể bỏ bước này và dùng `git clone` ở bước 3.

**Bước 1: tạo notebook**
1. Kaggle → **Create → New Notebook**.
2. Khung bên phải → **Session options**:
   - **Accelerator: GPU T4 x2** (hoặc T4);
   - **Internet: On**;
   - **Language: Python**.
3. **Add Input** (khung bên phải) → tab **Your Work / Datasets** → chọn `sudocode-repo`.

**Bước 2: gắn Secrets.** Menu **Add-ons → Secrets → Add Secret**, thêm ba secret, rồi **tích ô gắn (attach)** từng secret cho notebook này:

| Label | Value |
|---|---|
| `DEEPSEEK_API_KEY` | khóa DeepSeek |
| `TYPESAFE_API_KEY` | khóa TypeSafe (Jev) |
| `UI_PASSWORD` | mật khẩu mở UI, ít nhất 8 ký tự, tự đặt |

**Bước 3: đưa repo vào thư mục làm việc** (cell 1). Kaggle tự giải nén `repo.tar.gz` của dataset thành thư mục `repo`. Đường dẫn cụ thể khác nhau theo tài khoản, nên cell tự tìm:

```python
import glob, os, shutil
src = sorted(p for p in glob.glob("/kaggle/input/**/repo", recursive=True) if os.path.isfile(os.path.join(p, "run_eval.py")))
assert src, "không thấy repo trong /kaggle/input — đã Add Input dataset sudocode-repo chưa?"
shutil.copytree(src[0], "/kaggle/working/SudoCode", dirs_exist_ok=True)
print("repo:", src[0], "→ /kaggle/working/SudoCode")
```

Nếu dùng GitHub thay dataset:

```python
!git clone https://github.com/buidong941-ship-it/SudoCode.git /kaggle/working/SudoCode
```

**Bước 4: kiểm GPU và Secrets** (cell 2; chỉ in có / thiếu, không in giá trị):

```python
!nvidia-smi -L
from kaggle_secrets import UserSecretsClient
s = UserSecretsClient()
for k in ("DEEPSEEK_API_KEY", "TYPESAFE_API_KEY", "UI_PASSWORD"):
    try:
        print(k, "có" if s.get_secret(k) else "THIẾU")
    except Exception:
        print(k, "THIẾU — chưa thêm hoặc chưa tích gắn cho notebook này")
```

Cần thấy ít nhất một dòng `GPU 0: Tesla T4` và cả ba secret đều **có**.

**Bước 5: chạy UI** (cell 3). **Không cần cell cài đặt riêng.** Script tự làm, theo thứ tự:
1. `pip install -r requirements-ui.txt` (đã gồm `requirements.txt` + streamlit);
2. cài vLLM vào venv riêng `/tmp/vllm-venv`;
3. vLLM tự tải trọng số `Qwen/Qwen3-4B` từ Hugging Face (khoảng 8 GB, không cần token) rồi nạp lên GPU;
4. tự tải cloudflared.

Vì vậy notebook bắt buộc phải bật **Internet**. Cell này **chạy liên tục**, đừng dừng trong lúc dùng UI:

```python
!cd /kaggle/working/SudoCode && python kaggle/ui_tunnel.py
```

Thứ tự các dòng sẽ thấy (lần đầu của mỗi phiên mất khoảng 5–7 phút):

```text
[qwen_tunnel …] khóa API: DEEPSEEK_API_KEY có, TYPESAFE_API_KEY có
[qwen_tunnel …] $ python -m pip install -q -r requirements-ui.txt
[qwen_tunnel …] model Qwen/Qwen3-4B (theo profiles/b2_v52n.json), cổng 8000, khóa không (chỉ nội bộ)
[qwen_tunnel …] $ SETUP_HARNESS=0 SETUP_VLLM=1 bash scripts/setup_env.sh      ← cài vLLM, ~1–2 phút
[qwen_tunnel …] $ bash scripts/serve_llm.sh start                             ← nạp Qwen3-4B, ~2 phút
[qwen_tunnel …] vLLM sẵn sàng
[qwen_tunnel …] UI sẵn sàng nội bộ
[qwen_tunnel …] UI mở được qua URL công khai (trang yêu cầu mật khẩu UI_PASSWORD)

================ MỞ UI ================
Link: https://<ngẫu-nhiên>.trycloudflare.com
```

**Bước 6: dùng UI**
1. Mở **Link** bằng trình duyệt, ở máy nào cũng được, rồi nhập mật khẩu `UI_PASSWORD`.
2. Kiểm thanh bên: ô xanh **"B2-v52n (cấu hình chính 17/11), generator Qwen như cấu hình đo"**, dòng code **khớp 255 tệp**, cả hai khóa API đều **có**.
3. Nhập **Tên nhân viên / người duyệt** ở thanh bên (bắt buộc để like / dislike và duyệt FAQ).
4. Demo nhanh: tab **Demo C.6** → chọn **2** → **Chạy demo từ đầu**. Hoặc tự gọi: tab **Cuộc gọi** → **Bắt đầu cuộc gọi mới** → gõ lời khách → **Kết thúc cuộc gọi** → gọi lần hai cùng SĐT để xem Call Brief.

**Bước 7: lưu dữ liệu rồi tắt** (làm trước khi đóng tab Kaggle)
1. Trong UI: thanh bên → **Chuẩn bị gói dữ liệu UI để tải về** → **Tải ui_data.zip**.

   Hoặc, sau khi dừng cell 3, chạy một cell mới, rồi tải `ui_data.zip` ở khung **Output** (`/kaggle/working`):
   ```python
   import shutil; shutil.make_archive("/kaggle/working/ui_data", "zip", "/kaggle/working/ui_data")
   ```
2. Dừng cell 3 (nút ■ / Interrupt). Script tắt tunnel, UI và vLLM.
3. **Session options → Stop session** để không tốn quota GPU.

**Khi có lỗi**

| Thông báo | Cách xử lý |
|---|---|
| `thiếu UI_PASSWORD (≥ 8 ký tự)` / `thiếu khóa API` | Bước 2: thêm secret **và tích gắn** cho notebook, rồi chạy lại cell 3 |
| `không thấy GPU` | Session options → Accelerator GPU, rồi **Restart session** |
| `cloudflared không cấp được URL` | Internet của notebook chưa bật (cần xác minh SĐT) |
| `Streamlit đã thoát` / UI trắng | Xem `/kaggle/working/streamlit.log` |
| `vLLM đã thoát` / `vLLM chưa sẵn sàng` | Xem `/kaggle/working/vllm_tunnel.log` |
| Link không mở được sau một thời gian | Phiên Kaggle đã tắt hoặc tunnel đã dừng: chạy lại cell 3 để có link mới |

Xem log ngay trong notebook bằng `!tail -50 /kaggle/working/streamlit.log`, đổi tên tệp theo log cần xem.

**Lưu ý:**
- Link công khai: ai có link mà thiếu mật khẩu thì không thấy gì ngoài ô nhập mật khẩu. Đừng gửi mật khẩu chung với link, và đổi mật khẩu sau buổi demo.
- Dừng cell (■) thì tắt UI, tunnel và vLLM. Phiên Kaggle tắt thì link chết; chạy lại sẽ có link mới.
- Kiểm bằng job theo lô: đặt `UI_TUNNEL_SELFTEST=1`, script dùng mật khẩu ngẫu nhiên, không cần khóa API, không in link hay mật khẩu. Cổng mật khẩu có test riêng: `tests/ui_password_check.py`.

### 5.2. Kiểm khởi động (thanh bên trái)

Profile được chọn một lần cho cả tiến trình qua `UI_PROFILE`, không đổi giữa phiên. Lúc mở, UI kiểm:
- `ARCH=target` và `PLANNER_VARIANT=b2_jev`;
- model, ngân sách planner và các cờ hợp đồng khớp `profiles/b2_v52n.json`;
- code khớp freeze `runs/freeze/20261117-v52n-ui` (có tệp freeze thì kiểm; lệch → từ chối);
- nếu máy có snapshot `runs/snapshots/20261117-b2-v52n/config.json`, profile phải khớp snapshot.

Lệch ở bất kỳ điểm nào thì thanh bên báo đỏ và nút **Bắt đầu cuộc gọi mới** bị khóa.

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

```bash
python tests/ui_b2_check.py   # B2: kiểm khởi động, on_emit, chống gọi lại, namespace, feedback, nạp / đổi / quay lui gói FAQ
python tests/ui_check.py      # pipeline cũ (legacy_offline): kịch bản C.6 + AppTest (nếu đã cài streamlit)
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
- Reset trước demo: nút **Xoá bộ nhớ khách này** hoặc **Chạy demo từ đầu** trong `ui/app.py` (mục 5). Khi chạy dòng lệnh, đặt
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
