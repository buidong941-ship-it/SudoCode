#!/usr/bin/env bash
# Cài môi trường chạy trên máy Linux có GPU (Kaggle hoặc server thuê). Chạy từ gốc repo:
#   RUN_PROFILE=kaggle bash scripts/setup_env.sh          # Kaggle: cài vào python hệ thống (đã có torch CUDA)
#   RUN_PROFILE=server bash scripts/setup_env.sh          # server: nên kích hoạt venv của harness trước (source .venv/bin/activate)
# Biến:
#   SETUP_HARNESS=1   cài requirements.txt + sentence-transformers (RAG) + faster-whisper (ASR) cho python đang dùng
#   SETUP_VLLM=1      tạo venv riêng $VLLM_VENV và cài $VLLM_SPEC — tách khỏi harness để torch/transformers không đụng nhau
#   VLLM_SPEC         mặc định "vllm==0.9.2 transformers>=4.51,<4.54" (có Qwen3 + AWQ; trên T4 tự dùng engine V0 vì T4 là
#                     compute 7.5). Ghim transformers: bản ≥ 4.54 đã có config "aimv2" trùng tên vLLM 0.9.2 đăng ký → vLLM
#                     chết lúc import (ValueError: 'aimv2' is already used, đo 15/10). Qwen3 cần transformers ≥ 4.51.
#   PIP_INDEX         mirror pip nếu PyPI chậm (vd https://mirrors.aliyun.com/pypi/simple/ — xem docs/NHAT-KY-2026-10-08.md)
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/_profile.sh
SETUP_HARNESS="${SETUP_HARNESS:-1}"; SETUP_VLLM="${SETUP_VLLM:-1}"
VLLM_SPEC="${VLLM_SPEC:-vllm==0.9.2 transformers>=4.51,<4.54}"; VLLM_VENV="${VLLM_VENV:-.vllm-venv}"
read -r -a VLLM_PKGS <<< "$VLLM_SPEC"                  # nhiều gói cách nhau bằng dấu cách
PIP_ARGS=(-q); [ -n "${PIP_INDEX:-}" ] && PIP_ARGS+=(-i "$PIP_INDEX")
[ -f BUILD_INFO.json ] && echo "[setup] code: $(cat BUILD_INFO.json)"      # do scripts/kaggle_job.py ghi khi đóng gói

if [ "$SETUP_HARNESS" = 1 ]; then
  echo "[setup] harness: $(python --version 2>&1) ($(command -v python))"
  python -m pip install "${PIP_ARGS[@]}" -r requirements.txt sentence-transformers numpy faster-whisper
  python -c "import torch; print('[setup] torch', torch.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.device_count(), 'GPU')" || true
  # model embedding (mặc định bge-m3): harness chỉ nạp model ĐÃ có trên máy (rag.py, local_files_only) — máy mới chưa tải thì
  # RAG âm thầm lùi về BM25 và số liệu không so được với lần đo bằng bge-m3 → tải một lần ở đây
  if [ "${RAG_MODE:-auto}" != "bm25" ]; then
    python run_rag_eval.py --download || echo "[setup] CẢNH BÁO: không tải được model embedding → RAG sẽ dùng BM25"
  fi
  # router `laya`: tải checkpoint một lần (multilingual ~650 MB) để lượt đầu không phải chờ tải
  if [ "${SETUP_LAYA:-1}" = 1 ]; then
    python -c "import laya; laya.load('${LAYA_MODEL:-convaiinnovations/laya}', subfolder='${LAYA_SUBFOLDER:-multilingual}', device='cpu'); print('[setup] laya ok')" \
      || echo "[setup] CẢNH BÁO: không tải được Laya → router laya sẽ lỗi và lùi về luật"
  fi
fi

if [ "$SETUP_VLLM" = 1 ]; then
  if [ -x "$VLLM_VENV/bin/python" ] && "$VLLM_VENV/bin/python" -c "import vllm" 2>/dev/null; then
    echo "[setup] vLLM đã có ở $VLLM_VENV: $("$VLLM_VENV/bin/python" -c 'import vllm; print(vllm.__version__)')"
  else
    # venv vLLM dùng Python riêng (VLLM_PYTHON, mặc định 3.12) do uv tự tải: Kaggle đã lên Python 3.13 (15/10/2026) nhưng
    # vllm 0.9.2 — bản còn engine V0 chạy được trên T4 — chỉ có cho Python < 3.13. Harness vẫn chạy bằng python của máy.
    echo "[setup] tạo $VLLM_VENV (Python ${VLLM_PYTHON:-3.12}, qua uv) và cài $VLLM_SPEC (vài phút)"
    python -m pip install -q uv
    python -m uv venv --python "${VLLM_PYTHON:-3.12}" "$VLLM_VENV"
    UV_ARGS=(); [ -n "${PIP_INDEX:-}" ] && UV_ARGS+=(--index-url "$PIP_INDEX")
    python -m uv pip install --python "$VLLM_VENV/bin/python" "${UV_ARGS[@]}" "${VLLM_PKGS[@]}"
    # import luôn module server: lỗi tương thích (vd transformers quá mới) lộ ra ở đây chứ không phải lúc bật server
    "$VLLM_VENV/bin/python" -c "import vllm, torch, transformers, vllm.entrypoints.openai.api_server; print('[setup] vLLM', vllm.__version__, 'torch', torch.__version__, 'transformers', transformers.__version__)"
  fi
fi
nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader 2>/dev/null | sed 's/^/[setup] GPU /' || echo "[setup] không thấy nvidia-smi"
