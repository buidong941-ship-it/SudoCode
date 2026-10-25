# Chạy đánh giá trên Kaggle hoặc server thuê

Một lệnh chạy trọn bộ là `scripts/run_suite.py`: bật vLLM nếu cần, chạy `run_eval.py` hai cấu hình trên từng bộ kịch bản, chấm bằng `eval/reference_eval.py` của BTC, ghi bảng tổng hợp. Lệnh này giống hệt nhau trên Kaggle, server thuê (SSH/Termius) và máy cá nhân. Khác biệt theo nơi chạy nằm trong một file profile:

| Profile | File | Dùng khi | GPU |
|---|---|---|---|
| `kaggle` | `profiles/kaggle.env` | Notebook Kaggle do `scripts/kaggle_job.py` đẩy lên | T4 x2: card 0 cho vLLM (Qwen), card 1 cho `bge-m3` |
| `server` | `profiles/server.env` | Máy thuê qua SSH/Termius | Mặc định 1 GPU dùng chung; máy 2 GPU sửa như `kaggle` |
| `local` | `profiles/local.env` | Máy cá nhân không GPU | Không: chỉ kiểm logic (router `rules`, generator `offline`, BM25) |

Chọn profile bằng biến `RUN_PROFILE`. Thứ tự ưu tiên: biến môi trường đặt tay > profile > `.env`. Khóa API không bao giờ nằm trong profile.

## 1. Các backend và cách bật

| Thành phần | Lựa chọn | Cờ / biến |
|---|---|---|
| Router | `jev` (API TypeSafe) · `llm` (DeepSeek) · `qwen` (local) · `rules` | `--router`, `ROUTER_BACKEND` |
| Generator | `deepseek` (API) · `qwen` (local) · `offline` (câu mẫu) | `--generator`, `GENERATOR_BACKEND` |
| Bộ trích questions/claims/slot | `rules` · `llm` · `hybrid` | `--extractor`, `EXTRACTOR_BACKEND`; LLM dùng `EXTRACTOR_LLM=qwen\|deepseek` |
| Tóm tắt phiên + handoff | `auto` (= LLM của generator) · `qwen` · `deepseek` · `template` | `SUMMARY_BACKEND` |
| Model local | Mặc định `Qwen/Qwen3-8B-AWQ`, tắt chế độ suy luận | `QWEN_MODEL`, `QWEN_BASE_URL`, `QWEN_THINKING` |

`--router qwen --generator qwen` là cấu hình **toàn bộ LLM chạy local** (điểm thưởng tiêu chí G). Baseline và hệ thống luôn chạy cùng backend và cùng model, như đề yêu cầu.

Mọi backend dùng Qwen gọi chung **một server vLLM**. Các worker gửi HTTP request tới server đó và vLLM tự gom batch, nên `--workers 4` không nạp bốn bản model. Thứ được nạp theo từng worker là `bge-m3` (~2,3 GB mỗi worker).

## 2. Kaggle

### 2.1. Một lần cho mỗi tài khoản

1. Tài khoản đã xác minh số điện thoại (bật được GPU và Internet).
2. Token API (Settings → API → Create New Token) lưu ở `C:\Users\admin\.kaggle\MidZid\kaggle (n).json`. Không dán vào chat, không đặt trong repo.
3. `pip install kaggle` trong venv của project.

Tài khoản đang dùng được (kiểm 14/10/2026): `midzid` (`kaggle (4).json`), `felicityabby` (`kaggle (2).json`), `carterbryleeaqul` (`kaggle (3).json`). File `kaggle (1).json` đã hết hiệu lực. Mỗi tài khoản 30 giờ GPU/tuần.

### 2.2. Mỗi lần chạy

```bash
CRED="C:\Users\admin\.kaggle\MidZid\kaggle (4).json"
python scripts/kaggle_job.py --cred "$CRED" quota
python scripts/kaggle_job.py --cred "$CRED" push --job qwen-dev --sets dev --router qwen --generator qwen --extractor hybrid
python scripts/kaggle_job.py --cred "$CRED" wait --job qwen-dev      # chờ xong rồi tự kéo kết quả → runs/kaggle/qwen-dev/
```

`push` làm ba việc:
1. Đóng gói repo thành `repo.tar.gz`, bỏ `.git`, `venv`, `data`, `runs`, `dataset`, `.env`, `kaggle.json`. Gói được đẩy lên dataset **riêng tư** `<user>/sudocode-repo`: lần đầu tạo mới, các lần sau thêm version. Lệnh chờ Kaggle xử lý xong rồi mới đi tiếp.
2. Sinh kernel `<user>/sudocode-<job>` từ `kaggle/runner.py`, điền sẵn tham số của `run_suite.py`. Kernel chọn GPU T4 (`machine_shape: NvidiaTeslaT4`), bật Internet và để riêng tư.
3. Đẩy kernel. Trên Kaggle, `runner.py` chép repo vào `/tmp/repo`, nạp Secrets nếu có, kiểm GPU, chạy `scripts/setup_env.sh` rồi `scripts/run_suite.py`.

Kết quả nằm trong `/kaggle/working/out/<job>/` (trace, log, `report.json`, `summary.md`). Bộ nhớ SQLite và cache LLM ở `/kaggle/working/data/`. venv vLLM và cache model đặt ở `/tmp`, để lần kéo kết quả không tải theo vài GB model.

### 2.3. Khóa Jev / DeepSeek trên Kaggle

Kernel đẩy qua API **không tự gắn Secrets**. Job chỉ dùng `qwen` và `rules` thì không cần khóa nào. Job dùng `--router jev`, `--router llm` hoặc `--generator deepseek` thì:

1. Đẩy job một lần. Runner sẽ dừng ngay và báo thiếu secret nào.
2. Mở kernel trên kaggle.com → **Add-ons → Secrets** → bật `TYPESAFE_API_KEY` và/hoặc `DEEPSEEK_API_KEY` (đổi khóa mới trước, vì khóa cũ đã lộ hôm 08/10).
3. Bấm **Save Version** trên giao diện, hoặc đẩy lại job cùng tên `--job`.

### 2.4. Giới hạn

- vLLM cần GPU compute ≥ 7.0. P100 (6.0) không chạy được, nên runner dừng ngay nếu Kaggle cấp P100.
- T4 không hỗ trợ bf16 (profile đặt `VLLM_DTYPE=half`) và không có FlashAttention 2. vLLM 0.9.2 tự dùng engine V0 trên T4.
- Mỗi phiên tối đa 12 giờ. Ổ đĩa bị xóa sau phiên, chỉ `/kaggle/working` được giữ thành output.
- Chạy theo kiểu gửi đi rồi chờ kết quả. Muốn gỡ lỗi từng lượt thì chạy `--only <scenario_id>` hoặc dùng server.

## 3. Server thuê (SSH / Termius)

```bash
git clone https://github.com/buidong941-ship-it/SudoCode.git && cd SudoCode
python3 -m venv .venv && source .venv/bin/activate
cp .env.example .env                               # điền khóa nếu dùng Jev / DeepSeek
RUN_PROFILE=server bash scripts/setup_env.sh       # harness + venv vLLM riêng (.vllm-venv)
RUN_PROFILE=server python scripts/run_suite.py --sets sample dev test --router qwen --generator qwen --extractor hybrid
```

- Mạng chậm thì đặt `PIP_INDEX=https://mirrors.aliyun.com/pypi/simple/` (nhật ký 08/10, mục 1.1).
- Giữ vLLM chạy giữa các lệnh: `--keep-server`, hoặc tự bật/tắt bằng `RUN_PROFILE=server bash scripts/serve_llm.sh start|status|stop`.
- Dùng Qwen trên server từ máy cá nhân: `ssh -L 8000:127.0.0.1:8000 <server>`, rồi chạy ở máy với `RUN_PROFILE=local` (cổng `QWEN_BASE_URL` trùng cổng tunnel).
- Server tắt là mất ổ đĩa: chạy `bash scripts/data_pack.sh` và đưa `_upload/` lên Drive trước khi tắt (README mục 3.2).

## 4. Máy cá nhân (không GPU)

```bash
RUN_PROFILE=local python scripts/run_suite.py --sets sample --router rules --generator offline
bash tests/smoke.sh       # gồm cả đường Qwen qua server giả lập: kiểm nối dây trước khi tốn giờ GPU
python tests/llm_extract_check.py
```

## 5. Kết quả của một lần chạy

```
<out>/
  summary.md, summary.json      bảng A.6 rút gọn của từng bộ (Baseline / Hệ thống)
  suite.json, suite.log         lệnh, cấu hình, thời gian, mã thoát từng bước
  vllm.log                      log server vLLM (khi có dùng Qwen)
  <bộ>/full.jsonl, baseline_no_memory.jsonl, *.log, *.config.json, report.json, table.txt
```

Mỗi dòng trace có thêm trường `extractor`: `{backend, ms, fallback, dropped_spans}`. Trường này cho biết bộ trích LLM có phải dùng luật dự phòng không, và đã loại bao nhiêu đoạn trích bịa. Số liệu báo cáo phải ghi rõ backend và model lấy từ `suite.json`.

## 6. Sổ đăng ký tài nguyên Kaggle (cập nhật mỗi lần tạo dataset / kernel mới)

### 6.1. Tài khoản

| Tài khoản | File token (`C:\Users\admin\.kaggle\MidZid\`) | Ghi chú |
|---|---|---|
| `midzid` | `kaggle (4).json` | Mặc định; cấu hình B (Jev) chạy ở đây |
| `felicityabby` | `kaggle (2).json` | |
| `carterbryleeaqul` | `kaggle (3).json` | `kaggle (1).json` cùng tài khoản nhưng token đã hết hiệu lực |

### 6.2. Dataset (tất cả riêng tư)

Dataset riêng tư của tài khoản này không đọc được từ tài khoản khác, nên **mỗi tài khoản có dataset code riêng**, cùng tên `sudocode-repo`. `push` tự đóng gói và thêm version mới mỗi lần chạy; muốn dùng lại version đang có mà không upload thì thêm `--dataset <user>/sudocode-repo`.

| Dataset | Nội dung | Trên Kaggle (khi chạy) |
|---|---|---|
| `midzid/sudocode-repo` | `repo.tar.gz` = code + kịch bản + dữ liệu BTC (không có `.env`, `data/`, `runs/`, `dataset/`) | `/kaggle/input/**/repo.tar.gz` → giải nén ra `/tmp/repo` |
| `felicityabby/sudocode-repo` | như trên | như trên |
| `carterbryleeaqul/sudocode-repo` | như trên | như trên |

Chưa upload: `dataset/audio` + `dataset/asr` (đo ASR). Khi cần thì tạo dataset riêng `<user>/sudocode-audio` để mỗi lần sửa code không phải upload lại audio.

### 6.3. Kernel (job) đã chạy

Tên kernel luôn là `<user>/sudocode-<job>`. Kết quả kéo về `runs/kaggle/<job>/` (thư mục `runs/` không commit; giữ bản trên Drive theo README mục 3.2).

| Ngày | Job | Tài khoản | Cấu hình (router + generator + bộ trích) | Bộ kịch bản | Secret cần gắn | Kết quả |
|---|---|---|---|---|---|---|
| 14/10 | `probe-qwen` v1 | `midzid` | rules + qwen + hybrid, kèm smoke | sample | không | Chạy hơn 2 giờ không xong (cờ `-t 7200` không có tác dụng), bị hủy tay lúc 23:32; Kaggle không lưu log/output của kernel bị hủy → chưa rõ treo ở bước nào |
| 14/10 | `probe-qwen` v2 | `midzid` | rules + qwen + hybrid, không smoke | sample | không | Cũng kết thúc CANCEL, log rỗng. **Nguyên nhân cả v1 và v2** (tìm ra 15/10): `kaggle_job.py` chèn tham số job dạng JSON thô (`true`) vào `runner.py` → `NameError` ở dòng 20, code chưa hề chạy; phiên GPU vẫn hiện RUNNING tới khi bị hủy. Đã sửa (chèn qua `json.loads`) và thêm bước chạy thử runner tại máy trước khi đẩy |
| 15/10 | `eval-b` v1–v2 | `midzid` | jev + qwen + rules | sample, dev, test | `TYPESAFE_API_KEY` | Đẩy trên CPU (`--accelerator none`) chỉ để tạo kernel và gắn secret. v2: runner chạy đúng, dừng có chủ đích vì không có GPU; secrets nạp được: chưa có |
| 15/10 | `eval-b` v3 | `midzid` | jev + qwen + rules | sample, dev, test | `TYPESAFE_API_KEY` | Đẩy qua API lên T4: secret **không** được giữ → dừng ngay. Kernel đẩy qua API làm mất phần gắn secret |
| 15/10 | `eval-b` (chạy từ giao diện, 3 lần) | `midzid` | như trên | sample, dev, test | `TYPESAFE_API_KEY` | Lần 1: vLLM 0.9.2 không có cho Python 3.13 → venv Python 3.12 qua uv. Lần 2: `transformers` ≥ 4.54 xung đột (`aimv2`) → ghim < 4.54. Lần 3 (dataset 13:31): **COMPLETE, 50 phút, 0 lượt lỗi LLM** → `runs/kaggle/eval-b/out/eval-b/` |
| 15/10 | `eval-c` v1–v2 | `felicityabby` | qwen + qwen + hybrid | sample, dev, test | không | v1: vLLM sập vì prefix caching trên T4 → tắt. v2: JSON ép schema bị cắt (khoảng trắng) và bộ trích quá giờ → **hủy tay**, số liệu không dùng |
| 15/10 | `eval-d` v1–v2 | `carterbryleeaqul` | qwen + qwen + rules | sample, dev, test | không | Như `eval-c` (router Qwen dính lỗi JSON) → **hủy tay** |

| 15/10 | `speed-awq8` / `speed-fp16-4b` / `speed-fp16-8b-tp2` v2 | midzid / felicityabby / carterbryleeaqul | rules + qwen + rules, RAG BM25, chỉ `full` | dev | không | Đo tốc độ 3 cách chạy Qwen trên T4 (v1 chết vì cờ `--guided-decoding-disable-any-whitespace` thiếu `--guided-decoding-backend xgrammar`). Kernel **xếp hàng ~1 giờ** chờ T4 (đẩy 15:22, chạy 16:25; trạng thái vẫn hiện RUNNING, log rỗng). Kết quả: [SO-SANH-2026-10-15.md](SO-SANH-2026-10-15.md) mục 6 |
| 15/10 | `eval-b` v7 | `midzid` | jev + qwen + rules, 2 biến thể nối tiếp: `eval-b-4b` (Qwen3-4B fp16, card 0; bge-m3 card 1), `eval-b-8b-tp2` (Qwen3-8B fp16 chia 2 card; bge-m3 trên CPU) | sample, dev, test | `TYPESAFE_API_KEY` | Kernel có runner mới (đọc `kaggle/jobs/eval-b.json` trong dataset) → từ nay đổi cấu hình bằng `push --dataset-only`, không mất secret. Kết quả: `runs/kaggle/eval-b/out/eval-b/eval-b-4b/`, `.../eval-b-8b-tp2/` |

| 15/10 | `speed2-w1` / `speed2-ngram-short` / `speed2-rep2` | felicityabby / carterbryleeaqul / midzid | rules + qwen (Qwen3-4B fp16) + rules, RAG BM25, chỉ `full` | dev | không | Thử 1 worker, speculative n-gram, trả lời ngắn, 2 bản Qwen. Không phải xếp hàng (chạy ngay sau khi đẩy). N-gram làm vLLM 0.9.2 sập trên T4. Kết quả: [SO-SANH-2026-10-15.md](SO-SANH-2026-10-15.md) mục 7 |
| 15/10 | `eval-b` v8 (chạy từ giao diện), biến thể `eval-b-4b-short-w1` | `midzid` | jev + qwen (Qwen3-4B fp16, `REPLY_STYLE=short`, `LLM_MAX_TOKENS=160`) + rules, 1 worker, `bge-m3` card 1 | sample, dev, test | `TYPESAFE_API_KEY` | `push --dataset-only --variant …`; truyền một `--variant` để ghi đè 2 biến thể cũ còn trong runner nhúng của kernel (runner **gộp** `kaggle/jobs/<job>.json` vào JOB cũ). Chạy ngay, 84 phút, 0 lượt lỗi. Kết quả: [SO-SANH-2026-10-15.md](SO-SANH-2026-10-15.md) mục 7.1 |

| 23/10 | `laya-agree` v1 | `felicityabby` | `--pre-only`: `scripts/router_agreement.py` chạy Laya trên 435 lượt đã có nhãn Jev | sample, dev, test (nhãn từ `eval-b-4b-short-w1`) | không | 6 phút. Khớp intent 18%, cờ bật gần như mọi lượt → Laya không thay được Jev ([NHAT-KY-2026-10-23.md](NHAT-KY-2026-10-23.md) mục 2) |
| 23/10 | `laya-b` v1 | `felicityabby` | laya + qwen (Qwen3-4B fp16, câu ngắn, 160 token) + rules, 1 worker, code đã sửa | sample, dev, test | không | NHAT-KY-2026-10-23 mục 3 |
| 23/10 | `eval-b` (dataset-only, chạy từ giao diện) | `midzid` | jev + qwen, 2 biến thể `eval-b-fix-rules`, `eval-b-fix-hybrid` (`SUITE_EXTRACTOR=hybrid`), code đã sửa | sample, dev, test | `TYPESAFE_API_KEY` | Dừng ở 3 giờ (lỗi `DEADLINE` của runner, đã sửa). fix-rules đủ 3 bộ: TSR dev 100 / test 95,5, total p95 ~3,4 s. fix-hybrid chỉ có sample + dev full: 60 vi phạm `claims_human`, chậm gấp đôi → giữ luật (NHAT-KY-2026-10-23 mục 5) |
| 23/10 | `eval-b` v2 (dataset-only, chạy từ giao diện) | `midzid` | jev + qwen, biến thể `eval-b-hyb2`: hybrid sửa lại (trích phía khách chạy nền, lọc và kiểm claim phía agent) | sample, dev, test | `TYPESAFE_API_KEY` | ~2,6 giờ. TSR dev 100 / test 95,5; CCR test 76,3 (luật 68,4); HR test 0; TTFT p95 1,35 s; 0 vi phạm → chọn hybrid mới (NHAT-KY-2026-10-23 mục 6) |
| 24/10 | `eval-b` v3 (dataset-only, chạy từ giao diện) | `midzid` (token mới: `D:\User\Documents\kaggle_api_key\midzid.json`) | jev + qwen, biến thể `eval-b-hyb3`: bộ trích phân loại từng câu + vai trò con số + ngữ cảnh; `SUITE_EXTRACT_EVAL=1` chấm bộ trích rules/llm/hybrid trên `tests/extract_eval/` | sample, dev, test | `TYPESAFE_API_KEY` | Đủ 3 bộ, ~2,6 giờ, 0 lượt lỗi LLM; kết quả ở `runs/kaggle/eval-b-hyb3/`. RQR sample hết lỗi; HR giá dev/test tăng (3,2 / 4,1) do lọc claim, đã sửa sau đó (NHAT-KY-2026-10-24 mục 5) |

**Kernel đẩy lên có thể xếp hàng chờ GPU T4 khá lâu** mà trạng thái vẫn là RUNNING; nhìn dòng `[runner HH:MM:SS] repo → …` (giờ UTC) trong log để biết lúc thật sự bắt đầu chạy.

**Chạy job cần secret (Jev/DeepSeek):** đẩy qua API một lần để tạo kernel, gắn secret trên giao diện, rồi cập nhật code bằng `python scripts/kaggle_job.py --cred ... dataset` (chỉ đẩy dataset, không đẩy kernel) và chạy lại từ giao diện (Edit → Input → cập nhật `sudocode-repo` lên version mới nhất → Save Version → Save & Run All). Log có dòng `[setup] code: {... "packed_at": ...}` để biết đúng bản code. Job không cần secret thì dùng `push` như bình thường.

Model của mọi job ở trên: `Qwen/Qwen3-8B-AWQ` (thinking tắt), vLLM 0.9.2, GPU T4 x2, 4 worker, transport MCP. Bảng so sánh với số liệu 08/10: [SO-SANH-2026-10-15.md](SO-SANH-2026-10-15.md).

### 6.4. Chạy lại một job

```bash
# cùng tên --job = cùng kernel (thêm version mới, giữ secret đã gắn); code được đóng gói lại từ máy
python scripts/kaggle_job.py --cred "C:\Users\admin\.kaggle\MidZid\kaggle (4).json" push --job eval-b \
  --sets sample dev test --router jev --generator qwen --extractor rules
python scripts/kaggle_job.py --cred "C:\Users\admin\.kaggle\MidZid\kaggle (2).json" push --job eval-c \
  --sets sample dev test --router qwen --generator qwen --extractor hybrid
python scripts/kaggle_job.py --cred "C:\Users\admin\.kaggle\MidZid\kaggle (3).json" push --job eval-d \
  --sets sample dev test --router qwen --generator qwen --extractor rules
python scripts/kaggle_job.py --cred "<file token>" wait --job <job>      # chờ xong → runs/kaggle/<job>/
```

Gắn secret cho kernel dùng Jev/DeepSeek: đăng nhập kaggle.com bằng **đúng tài khoản trong bảng 6.3** → mở `https://www.kaggle.com/code/<user>/sudocode-<job>` → Edit → Add-ons → Secrets → bật secret → Save Version.

## 7. Khi không dùng nữa

Kaggle → Settings → API → **Expire API Token**, rồi xóa file token tương ứng trong `C:\Users\admin\.kaggle\MidZid\`.
