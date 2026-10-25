# SUDO CODE Task

## 1. Clone repository và chuyển sang branch

```bash
git clone https://github.com/buidong941-ship-it/SUDOCODE_task.git
cd SUDOCODE_task

git checkout claude/sleepy-albattani-aqjrof
```

> Branch `claude/sleepy-albattani-aqjrof` chứa đầy đủ code harness.

---

## 2. Tạo môi trường Python và cài dependencies

### Linux / WSL / Git Bash

```bash
python -m venv .venv
source .venv/bin/activate
```

### Windows

Có thể sử dụng **WSL** hoặc **Git Bash** để chạy các lệnh trên.

Sau đó cài các thư viện:

```bash
pip install -r requirements.txt
```

Virtual environment giúp tách riêng Python packages của project khỏi môi trường Python hệ thống.

---

## 3. Bước 1 — Chạy smoke test offline

Kiểm tra hệ thống mà:

- Không cần Internet.
- Không cần API key.
- Sử dụng server API giả lập (mock server).

Chạy:

```bash
bash tests/smoke.sh
```

Nếu smoke test chạy thành công thì có thể tiếp tục các bước tiếp theo.

---

## 4. Bước 2 — Cấu hình API keys

Copy file cấu hình mẫu:

```bash
cp .env.example .env
```

Sau đó mở file `.env` và điền:

```env
TYPESAFE_API_KEY=your_typesafe_api_key
DEEPSEEK_API_KEY=your_deepseek_api_key
```

> Không commit file `.env` chứa API key thật lên Git.

---

## 5. Bước 3 — Chạy thử một scenario

Trước khi chạy toàn bộ dataset, chạy thử scenario `SAMPLE-01`:

```bash
python run_eval.py \
    --scenarios test_set/public_sample \
    --config full \
    --out runs/try.jsonl \
    --only SAMPLE-01
```

Kết quả sẽ được ghi vào:

```text
runs/try.jsonl
```

---

## 6. Bước 4 — Chạy đầy đủ hai cấu hình

### Chạy cấu hình `full`

```bash
python run_eval.py \
    --scenarios test_set/public_sample \
    --config full \
    --out runs/full.jsonl
```

### Chạy cấu hình `baseline_no_memory`

```bash
python run_eval.py \
    --scenarios test_set/public_sample \
    --config baseline_no_memory \
    --out runs/baseline.jsonl
```

Sau khi chạy xong sẽ có:

```text
runs/
├── try.jsonl
├── full.jsonl
└── baseline.jsonl
```

---

## 7. Chấm kết quả

Dùng `reference_eval.py` để đánh giá và so sánh hai kết quả:

```bash
python eval/reference_eval.py \
    --scenarios test_set/public_sample \
    --trace runs/full.jsonl \
    --baseline runs/baseline.jsonl
```

Trong đó:

| Tham số | Ý nghĩa |
|---|---|
| `--scenarios` | Thư mục chứa các scenario cần đánh giá |
| `--trace` | Kết quả của cấu hình `full` |
| `--baseline` | Kết quả của cấu hình `baseline_no_memory` |

---

## Tóm tắt toàn bộ quy trình

```text
Clone repository
       ↓
Checkout branch
       ↓
Tạo .venv
       ↓
pip install -r requirements.txt
       ↓
Smoke test offline
       ↓
Cấu hình API keys
       ↓
Chạy SAMPLE-01
       ↓
Chạy full
       ↓
Chạy baseline_no_memory
       ↓
reference_eval.py
       ↓
Kết quả đánh giá
```