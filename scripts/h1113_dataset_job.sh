#!/usr/bin/env bash
# Job Kaggle CPU duy nhất (13/11/2026) cho bàn giao tổ chức dataset + release H13. Không gọi model, không cần secret.
#   bash scripts/h1113_dataset_job.sh <thư mục kết quả> [python]
# Bước: dựng template → sinh 84 kịch bản → validate (trace hoàn hảo PASS / rỗng FAIL) → đóng băng raw →
#       index registry → giải suite → audit (trùng 3 lớp, lineage, coverage, canary đúng/rỗng/sai) →
#       materialize suite regression + chặn suite guarded → smoke run_eval offline trên regression (KHÔNG chạy H13).
set -u
OUT="${1:?thiếu thư mục kết quả}"
PY="${2:-python}"
REL=datagen/datasets/releases/h1113
mkdir -p "$OUT"
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1
: > "$OUT/steps.txt"
status=0
step() {
  local name=$1; shift
  echo "=== $name: $*"
  "$@" > "$OUT/$name.log" 2>&1
  local rc=$?
  echo "$name rc=$rc" | tee -a "$OUT/steps.txt"
  tail -60 "$OUT/$name.log"
  return $rc
}

step 01_build "$PY" "$REL/templates/build_h1113.py" || status=1
step 02_generate "$PY" datagen/generate_btc_like_benchmark.py --templates "$REL/templates" --out "$REL" \
     --prefix H13 --seed 20261113 --crm-first || status=1
step 03_validate "$PY" datagen/validate.py "$REL/raw/holdout" --strict --report "$REL/validate_raw.json" || status=1
if [ $status -eq 0 ]; then
  step 04_freeze "$PY" datagen/generate_btc_like_benchmark.py --out "$REL" --freeze raw || status=1
else
  echo "04_freeze skipped (bước trước lỗi)" | tee -a "$OUT/steps.txt"
fi
step 05_index "$PY" scripts/dataset_registry.py index || status=1
step 06_suites "$PY" scripts/dataset_registry.py suites || status=1
step 07_audit "$PY" scripts/dataset_registry.py audit --release h13@r1 --out "$OUT/audit" || status=1
rm -rf /tmp/suite_regression /tmp/suite_guard
step 08_materialize "$PY" scripts/dataset_registry.py materialize --suite regression --out /tmp/suite_regression || status=1
if "$PY" scripts/dataset_registry.py materialize --suite holdout_h13 --out /tmp/suite_guard > "$OUT/09_guard.log" 2>&1; then
  echo "09_guard rc=0 (SAI: suite guarded bị materialize không cần duyệt)" | tee -a "$OUT/steps.txt"; status=1
else
  echo "09_guard rc=blocked (đúng)" | tee -a "$OUT/steps.txt"
fi
mkdir -p "$OUT/smoke"
if [ -d /tmp/suite_regression ]; then
  export DATABASE_URL="sqlite:////tmp/h1113_smoke.db" RAG_MODE=bm25 LLM_CACHE=off
  step 10_run_eval_full "$PY" run_eval.py --scenarios /tmp/suite_regression --config full --out "$OUT/smoke/full.jsonl" \
       --router rules --generator offline --extractor rules --transport direct --workers 2 || status=1
  step 11_run_eval_base "$PY" run_eval.py --scenarios /tmp/suite_regression --config baseline_no_memory --out "$OUT/smoke/base.jsonl" \
       --router rules --generator offline --extractor rules --transport direct --workers 2 || status=1
  step 12_reference_eval "$PY" eval/reference_eval.py --scenarios /tmp/suite_regression --trace "$OUT/smoke/full.jsonl" \
       --baseline "$OUT/smoke/base.jsonl" --out "$OUT/smoke/report.json" || status=1
fi

# Kết quả mang về: release (template json, raw, manifest, validate), registry lock/index, suite đã giải
mkdir -p "$OUT/datasets"
cp -r "$REL" "$OUT/datasets/h1113" 2>/dev/null
cp datagen/datasets/registry.lock.json datagen/datasets/index.jsonl "$OUT/datasets/" 2>/dev/null
cp -r datagen/datasets/suites/resolved "$OUT/datasets/resolved" 2>/dev/null
echo "status=$status" | tee -a "$OUT/steps.txt"
exit $status
