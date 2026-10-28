#!/usr/bin/env bash
# Kiểm thử nhanh không cần mạng/khóa API:
#  1) offline: router=rules, generator=offline trên 7 kịch bản mẫu, cả 2 cấu hình, chấm bằng reference_eval.py
#  2) tích hợp: Jev SDK + DeepSeek client gọi server giả lập (kiểm định dạng request/response thật)
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=${OUT:-/tmp/smoke}; mkdir -p "$OUT"
export DATABASE_URL="sqlite:///$OUT/memory.db"
for c in full baseline_no_memory; do
  python run_eval.py --scenarios test_set/public_sample --config $c --out "$OUT/$c.jsonl" --router rules --generator offline --run-id smoke
done
(cd "$OUT" && python "$OLDPWD/eval/reference_eval.py" --scenarios "$OLDPWD/test_set/public_sample" --trace full.jsonl --baseline baseline_no_memory.jsonl | sed -n '/Chỉ số/,/Vi phạm/p')
python tests/fake_api_server.py 8765 & PID=$!; trap "kill $PID" EXIT; sleep 1
TYPESAFE_API_KEY=test-key-123 TYPESAFE_BASE_URL=http://127.0.0.1:8765 DEEPSEEK_API_KEY=test-key-123 DEEPSEEK_BASE_URL=http://127.0.0.1:8765 \
  python run_eval.py --scenarios test_set/public_sample --config full --out "$OUT/live.jsonl" --router jev --generator deepseek --run-id smoke-live
python - "$OUT/live.jsonl" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
fb = [r["router"]["fallback"] for r in rows if r["router"]["fallback"]]
assert rows and not fb, f"router fallback: {fb[:3]}"
assert all(r["router"]["backend"] == "jev" for r in rows)
print(f"tích hợp OK: {len(rows)} lượt, Jev + DeepSeek (giả lập) không lỗi")
PY
# log từng lượt phải có cho mọi kịch bản; lần chạy không lỗi thì không có file errors
test "$(grep -c '^.* === ' "$OUT/live.log")" -eq 7 && test ! -e "$OUT/live.errors.jsonl" && echo "log OK: $OUT/live.log"
# đường model local: router + generator + bộ trích + tóm tắt qua API kiểu vLLM (giả lập) — kiểm nối dây, không kiểm chất lượng
QWEN_BASE_URL=http://127.0.0.1:8765 LLM_CACHE=off \
  python run_eval.py --scenarios test_set/public_sample --config full --out "$OUT/qwen.jsonl" --router qwen --generator qwen --extractor hybrid --run-id smoke-qwen
python - "$OUT/qwen.jsonl" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
assert rows and all(r["router"]["backend"] == "qwen" and not r["router"]["fallback"] for r in rows), "router qwen fallback"
assert all(r["extractor"]["backend"].startswith("hybrid") and not r["extractor"]["fallback"] for r in rows), "bộ trích LLM fallback"
print(f"qwen OK: {len(rows)} lượt, router + generator + bộ trích hybrid qua API kiểu vLLM (giả lập)")
PY
python tests/llm_extract_check.py | tail -1
python tests/question_detection_check.py | tail -1
python tests/coverage_check.py | tail -1
python tests/placeholder_check.py | tail -1
python tests/generator_parallel_check.py
python tests/logprobs_check.py

# MCP: 2 server đúng giao thức + trace qua MCP == gọi trực tiếp
python tests/mcp_check.py | tail -1
python tests/mcp_parity.py --out-dir "$OUT/parity" | tail -1
# PII không ra ngoài / không vào log (7 kịch bản mẫu)
GEN_PLACEHOLDERS=0 python tests/pii_check.py --scenarios test_set/public_sample | tail -1
# hậu xử lý ASR (không cần audio)
python asr/transcribe.py --from-ground-truth --out "$OUT/hypotheses.json" | sed -n 2,3p
