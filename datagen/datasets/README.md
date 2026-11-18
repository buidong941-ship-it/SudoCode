# Danh mục dataset (đầu mối tra cứu, từ 13/11/2026)

Thư mục này là **đầu mối** quản lý dữ liệu của nhóm: danh mục phiên bản, vai trò, exposure, và cách chọn bộ chạy.
Dữ liệu gốc **không bị di chuyển hay sửa**: các `datagen/out_*`, `test_set/`, `tests/extract_eval/`… vẫn nằm ở chỗ cũ, nên
report/snapshot cũ vẫn đọc được. Bàn giao gốc: `docs/PLAN/BAN-GIAO-TO-CHUC-DATASET-VA-TEMPLATE-MOI-2026-11-13.md`.

> Đặt ở `datagen/datasets/` chứ không phải `data/datasets/` như bàn giao gợi ý, vì `data/` bị `.gitignore` và bị
> `scripts/kaggle_job.py` loại khỏi gói Kaggle (mọi kiểm thử chạy trên Kaggle).

```text
datagen/datasets/
  registry.json          viết tay: dataset_id@version, path, vai trò, lineage, exposure, ghi chú
  registry.lock.json     sinh bởi `index`: số file, số kịch bản, sha256 từng phần, tổng kịch bản độc lập
  index.jsonl            sinh bởi `index`: mỗi kịch bản một dòng (khóa dataset_id, version, scenario_id; sha256; template; khung diễn biến)
  suites/*.json          suite khai báo theo luật chọn; suites/resolved/*.json = danh sách đã giải, có sha256
  releases/h1113/        release holdout mới H13
    final/holdout/       ← BỘ CHẠY: 84 kịch bản đã naturalize, đóng băng (manifest.json → frozen)
    raw/holdout/         bản trước naturalize (cùng kịch bản, đáp án; manifest.json → frozen_raw)
    templates/, naturalize/   nguồn sinh lại (template, lời viết lại tay của Claude); không commit
```

## Chọn bộ nào

| Suite | Dùng khi | Nội dung |
|---|---|---|
| `dev` | phát triển, đọc lỗi, sửa | đại diện theo template từ gen@nat-v1/dev, btcl@v1_1/dev, btcl_d7, v3/dev (1 ca/template) + toàn bộ red-team, JEV1108 |
| `regression` | kiểm nhanh sau mỗi sửa | **tập con của dev**: red-team + mỗi loại ca khó một ca + vài ca thường làm đối chứng. Không tính là mẫu độc lập với dev |
| `observed_v3` | đối chiếu lịch sử | V3 holdout 77 ca; đã đo và đọc lỗi nhiều lần → observed, không còn là holdout |
| `observed_other` | đối chiếu lịch sử | gen@nat-v1/test (22) + btcl@v2_1/holdout (40) |
| `btc_sample` | báo riêng | 7 mẫu BTC, không trộn với dữ liệu nhóm |
| `holdout_h13` | **chỉ khi người dùng duyệt đo** | holdout mới H13, `guarded` |
| `component_checks` | kiểm thành phần | extractor/claim, câu đơn slot, function probe, ASR/RAG của BTC; không materialize thành kịch bản |

Số kịch bản thực tế của mỗi suite nằm ở `suites/resolved/<suite>.json` (trường `n`, `by_dataset`).

## Lệnh

Theo quy ước dự án, các lệnh dưới đây chạy trên Kaggle (`scripts/kaggle_job.py ... --pre`), không chạy trên máy cá nhân.

```bash
python scripts/dataset_registry.py index        # cập nhật registry.lock.json + index.jsonl sau khi thêm/sửa dữ liệu
python scripts/dataset_registry.py suites       # giải suite → suites/resolved/
python scripts/dataset_registry.py materialize --suite regression --out /tmp/suites/regression
python run_eval.py --scenarios /tmp/suites/regression --config full --out runs/x/full.jsonl ...
python run_eval.py --scenarios /tmp/suites/regression --config baseline_no_memory --out runs/x/base.jsonl ...
python eval/reference_eval.py --scenarios /tmp/suites/regression --trace runs/x/full.jsonl --baseline runs/x/base.jsonl
# hoặc: RUN_PROFILE=server python scripts/run_suite.py --sets /tmp/suites/regression ...
python scripts/dataset_registry.py audit --release h13@r1 --out <dir>    # trùng 3 lớp + lineage + coverage + canary
```

- **Runner chưa đọc suite manifest trực tiếp.** `materialize` chép đúng các file của suite (kiểm sha256 với index,
  chặn trùng `scenario_id`) vào một thư mục staging kèm `_suite_manifest.json` (loader bỏ qua file bắt đầu `_`).
  Default của `run_suite.py` (`sample/dev/test`) không đổi.
- Suite `guarded` (holdout mới) bị từ chối nếu không có `--allow-guarded`. Chỉ thêm cờ này khi người dùng đã duyệt đo,
  và ghi exposure `evaluated` vào `registry.json` cùng ngày.
- Tái tạo release H13: xem đầu `releases/h1113/templates/build_h1113.py`; sinh + kiểm raw ở `scripts/h1113_dataset_job.sh`,
  naturalize + kiểm final ở `scripts/h1113_naturalize_job.sh`.

## Quy ước

- **Khóa kịch bản** là `(dataset_id, version, scenario_id)`. `BTCL-001` ở v1, v1_1, v2, v2_1 là bốn file khác nhau
  nhưng **một** kịch bản độc lập (cùng `lineage_group`). Không sửa `scenario_id` trong file gốc.
- **Không cộng** raw/final, bản vá, bản viết lại lời thành dữ liệu mới. `registry.lock.json → summary` báo riêng tổng
  file và tổng kịch bản độc lập.
- **Bản chuẩn:** gen@nat-v1 (bản chạy của gen@out-v1); btcl@v1_1 cho dev BTC-like; btcl@v2_1/holdout là bản BTC-like
  holdout đã đo (v1_1/holdout cùng 40 kịch bản, chưa mở chữ nhưng không còn độc lập); btcl@v1 và @v2 là superseded,
  giữ để tái lập report cũ.
- **Exposure:** `generated` / `reviewed-for-data-quality` / `used-for-development` / `evaluated` / `inspected-after-evaluation`,
  kèm ngày và người/agent. Khi đã dùng lỗi của một bộ để sửa thì đổi vai trò sang observed, không "làm mới" bằng đổi seed
  hay paraphrase.
- **Holdout mới:** phiên/model sửa agent không đọc `releases/h1113/templates/`, `releases/h1113/raw/` hay phần H13 của
  `index.jsonl`/`audit` trước khi người dùng cho đo. Người viết H13 là Claude, cùng trợ lý từng sửa hệ thống (khác phiên),
  phải nêu khi báo số.
- Không lưu credential hay PII thật ở đây. SĐT trong index chỉ lưu băm 12 ký tự.
