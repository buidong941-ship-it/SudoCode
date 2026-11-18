#!/usr/bin/env bash
# Job Kaggle CPU (13/11/2026): naturalize holdout H13 bằng lời viết lại tay của Claude rồi kiểm lại toàn bộ.
#   bash scripts/h1113_naturalize_job.sh <thư mục kết quả> [python]
# Bước: dựng claude_rewrites.json (kiểm mỏ neo từng lượt) → naturalize.py --backend claude --offline → không lượt nào bị
#       trả về câu gốc → validate final --strict (trace hoàn hảo PASS / rỗng FAIL) → khóa final (raw phải còn nguyên byte) →
#       index → suites → audit h13@r1 trên final (trùng 3 lớp, lineage, coverage, canary đúng/rỗng/sai) → suite guarded vẫn bị chặn.
# Không chạy agent nào trên H13. Không gọi model, không cần secret.
set -u
OUT="${1:?thiếu thư mục kết quả}"
PY="${2:-python}"
REL=datagen/datasets/releases/h1113
mkdir -p "$OUT"
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1 RAG_MODE=bm25 LLM_CACHE=off
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

rm -rf "$REL/final"
step 01_rewrites "$PY" "$REL/naturalize/h13_claude_rewrites.py" || status=1
step 02_naturalize "$PY" datagen/naturalize.py --src "$REL/raw" --out "$REL/final" --splits holdout \
     --backend claude --offline --import-claude "$REL/final/claude_rewrites.json" || status=1
step 03_naturalize_clean "$PY" -c "
import json, sys
r = json.load(open('$REL/final/naturalize_report.json', encoding='utf-8'))
print({k: v for k, v in r.items() if k != 'rejected'})
for x in r['rejected']: print('  giữ câu gốc:', x)
sys.exit(1 if r['kept_original_after_check'] or r['scenarios'] != 84 else 0)
" || status=1
step 04_validate "$PY" datagen/validate.py "$REL/final/holdout" --strict --report "$REL/validate_final.json" || status=1
if [ $status -eq 0 ]; then
  step 05_freeze "$PY" datagen/generate_btc_like_benchmark.py --out "$REL" --freeze final || status=1
else
  echo "05_freeze skipped (bước trước lỗi)" | tee -a "$OUT/steps.txt"
fi
step 06_index "$PY" scripts/dataset_registry.py index || status=1
step 07_suites "$PY" scripts/dataset_registry.py suites || status=1
step 08_audit "$PY" scripts/dataset_registry.py audit --release h13@r1 --out "$OUT/audit" || status=1
rm -rf /tmp/suite_guard
if "$PY" scripts/dataset_registry.py materialize --suite holdout_h13 --out /tmp/suite_guard > "$OUT/09_guard.log" 2>&1; then
  echo "09_guard rc=0 (SAI: suite guarded bị materialize không cần duyệt)" | tee -a "$OUT/steps.txt"; status=1
else
  echo "09_guard rc=blocked (đúng)" | tee -a "$OUT/steps.txt"
fi

# Kết quả mang về: final (kịch bản, rewrites, report), manifest, validate, registry lock/index, suite đã giải
mkdir -p "$OUT/datasets/h1113"
cp -r "$REL/final" "$OUT/datasets/h1113/final" 2>/dev/null
cp "$REL/manifest.json" "$REL/validate_final.json" "$OUT/datasets/h1113/" 2>/dev/null
cp datagen/datasets/registry.lock.json datagen/datasets/index.jsonl "$OUT/datasets/" 2>/dev/null
cp -r datagen/datasets/suites/resolved "$OUT/datasets/resolved" 2>/dev/null
echo "status=$status" | tee -a "$OUT/steps.txt"
exit $status
