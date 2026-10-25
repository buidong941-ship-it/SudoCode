#!/usr/bin/env bash
# Bật/tắt server vLLM phục vụ Qwen (API tương thích OpenAI) cho mọi worker của run_eval.py.
#   RUN_PROFILE=kaggle bash scripts/serve_llm.sh start     # chờ tới khi /v1/models trả đúng model (tối đa VLLM_WAIT giây)
#   bash scripts/serve_llm.sh status | stop
# Cấu hình (profiles/*.env): QWEN_MODEL, QWEN_BASE_URL, VLLM_GPUS (CUDA_VISIBLE_DEVICES), VLLM_TP (tensor parallel),
#   VLLM_DTYPE, VLLM_MAX_MODEL_LEN, VLLM_GPU_MEM, VLLM_SPECULATIVE (off|ngram), VLLM_EXTRA (cờ thêm), VLLM_VENV, VLLM_LOG.
# Nhiều bản (replica): QWEN_BASE_URL là danh sách cách nhau bằng dấu phẩy (vd cổng 8000,8001) → mỗi URL một server,
#   server thứ i chạy trên GPU thứ i của VLLM_GPUS (VLLM_TP phải là 1). Client chia worker cho các server theo PID.
# Tên model khi phục vụ = QWEN_MODEL (--served-model-name), kể cả khi QWEN_MODEL_PATH trỏ tới thư mục model tải sẵn.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/_profile.sh
CMD="${1:-start}"
QWEN_MODEL="${QWEN_MODEL:-Qwen/Qwen3-8B-AWQ}"
QWEN_BASE_URL="${QWEN_BASE_URL:-http://127.0.0.1:8000/v1}"
VLLM_VENV="${VLLM_VENV:-.vllm-venv}"; VLLM_LOG="${VLLM_LOG:-${RUN_OUT:-runs/suite}/vllm.log}"
PIDF="${VLLM_PIDFILE:-/tmp/sudocode-vllm.pid}"
PORTS=()
IFS=',' read -r -a URLS <<< "$QWEN_BASE_URL"
for u in "${URLS[@]}"; do p="$(echo "$u" | sed -E 's#.*:([0-9]+).*#\1#')"; [[ "$p" =~ ^[0-9]+$ ]] || p=8000; PORTS+=("$p"); done
IFS=',' read -r -a GPU_LIST <<< "${VLLM_GPUS:-0}"
N=${#PORTS[@]}

ready_one() { curl -sf -m 5 "http://127.0.0.1:$1/v1/models" 2>/dev/null | grep -q "\"$QWEN_MODEL\""; }
ready() { for p in "${PORTS[@]}"; do ready_one "$p" || return 1; done; }

case "$CMD" in
  status)
    if ready; then echo "vLLM sẵn sàng ở cổng ${PORTS[*]}: $QWEN_MODEL"; else echo "vLLM chưa chạy (đủ) ở cổng ${PORTS[*]}"; exit 1; fi ;;
  stop)
    for f in "$PIDF".*; do [ -f "$f" ] && { kill "$(cat "$f")" 2>/dev/null || true; rm -f "$f"; }; done
    # engine V0 chạy tiến trình con riêng: dọn hết để VRAM được trả trước khi bật lại
    pkill -f "vllm.entrypoints.openai.api_server" 2>/dev/null || true
    for i in $(seq 1 30); do pgrep -f "vllm.entrypoints.openai.api_server" >/dev/null || break; sleep 1; done
    pkill -9 -f "vllm.entrypoints.openai.api_server" 2>/dev/null || true
    echo "đã dừng vLLM" ;;
  start)
    if ready; then echo "vLLM đã chạy sẵn ở cổng ${PORTS[*]} ($QWEN_MODEL)"; exit 0; fi
    [ -x "$VLLM_VENV/bin/python" ] || { echo "chưa có $VLLM_VENV — chạy: SETUP_HARNESS=0 bash scripts/setup_env.sh" >&2; exit 1; }
    if [ "$N" -gt 1 ] && { [ "${VLLM_TP:-1}" != 1 ] || [ "${#GPU_LIST[@]}" -lt "$N" ]; }; then
      echo "$N bản cần VLLM_TP=1 và ≥ $N GPU trong VLLM_GPUS (đang: TP=${VLLM_TP:-1}, GPU=${VLLM_GPUS:-0})" >&2; exit 1
    fi
    mkdir -p "$(dirname "$VLLM_LOG")"
    # prefix caching TẮT mặc định: trên T4 (compute 7.5, engine V0) request trùng tiền tố prompt chạy kernel Triton
    # prefix_prefill không biên dịch được ("LLVM ERROR: Unsupported rounding mode") → engine sập giữa chừng (đo 15/10).
    # GPU đời mới (Ampere trở lên) bật bằng VLLM_PREFIX_CACHING=1. Không truyền cờ = mặc định của engine V0 (tắt).
    PREFIX_FLAG=(); [ "${VLLM_PREFIX_CACHING:-0}" = 1 ] && PREFIX_FLAG=(--enable-prefix-caching)
    # JSON ép theo schema: mặc định grammar cho phép khoảng trắng tùy ý → Qwen sinh hàng trăm dòng trắng tới khi đầy
    # max_tokens, JSON bị cắt (router qwen: JSONDecodeError "line 139"; bộ trích: quá giờ — đo 15/10). Tắt khoảng trắng tự do
    # nếu bản vLLM có cờ này (kiểm qua --help, không đoán); cờ chỉ hợp lệ với backend xgrammar/guidance.
    GUIDED_FLAG=()
    if "$VLLM_VENV/bin/python" -m vllm.entrypoints.openai.api_server --help 2>/dev/null | grep -q -- "--guided-decoding-disable-any-whitespace"; then
      GUIDED_FLAG=(--guided-decoding-backend xgrammar --guided-decoding-disable-any-whitespace)
    fi
    # speculative decoding kiểu n-gram (không cần model phụ): câu trả lời hay chép lại tên SP / giá / ngày có sẵn trong prompt
    SPEC_FLAG=()
    if [ "${VLLM_SPECULATIVE:-off}" = ngram ]; then
      SPEC_FLAG=(--speculative-config "{\"method\": \"ngram\", \"num_speculative_tokens\": ${VLLM_SPEC_TOKENS:-4}, \"prompt_lookup_max\": 4, \"prompt_lookup_min\": 2}")
    fi
    echo "cờ: ${GUIDED_FLAG[*]:-} ${SPEC_FLAG[*]:-} ${PREFIX_FLAG[*]:-}"
    for i in $(seq 0 $((N - 1))); do
      if [ "$N" -gt 1 ]; then GPUS="${GPU_LIST[$i]}"; LOG="${VLLM_LOG%.log}.$i.log"; else GPUS="${VLLM_GPUS:-0}"; LOG="$VLLM_LOG"; fi
      echo "khởi động vLLM #$i: $QWEN_MODEL trên GPU $GPUS (tp=${VLLM_TP:-1}) cổng ${PORTS[$i]}, log $LOG"
      # shellcheck disable=SC2086
      CUDA_VISIBLE_DEVICES="$GPUS" nohup "$VLLM_VENV/bin/python" -m vllm.entrypoints.openai.api_server \
        --model "${QWEN_MODEL_PATH:-$QWEN_MODEL}" --served-model-name "$QWEN_MODEL" \
        --host 127.0.0.1 --port "${PORTS[$i]}" --dtype "${VLLM_DTYPE:-auto}" \
        --max-model-len "${VLLM_MAX_MODEL_LEN:-8192}" --gpu-memory-utilization "${VLLM_GPU_MEM:-0.88}" \
        --tensor-parallel-size "${VLLM_TP:-1}" "${PREFIX_FLAG[@]}" "${GUIDED_FLAG[@]}" "${SPEC_FLAG[@]}" ${VLLM_EXTRA:-} \
        > "$LOG" 2>&1 &
      echo $! > "$PIDF.$i"
    done
    for s in $(seq 1 "${VLLM_WAIT:-1200}"); do
      if ready; then echo "vLLM sẵn sàng sau ${s}s ($N bản)"; exit 0; fi
      for i in $(seq 0 $((N - 1))); do
        if ! kill -0 "$(cat "$PIDF.$i")" 2>/dev/null; then
          LOG="$VLLM_LOG"; [ "$N" -gt 1 ] && LOG="${VLLM_LOG%.log}.$i.log"
          echo "vLLM đã thoát (#$i) — 40 dòng cuối log:" >&2; tail -40 "$LOG" >&2; exit 1
        fi
      done
      sleep 1
    done
    echo "vLLM chưa sẵn sàng sau ${VLLM_WAIT:-1200}s — xem $VLLM_LOG" >&2; exit 1 ;;
  *) echo "dùng: serve_llm.sh start|status|stop" >&2; exit 2 ;;
esac
