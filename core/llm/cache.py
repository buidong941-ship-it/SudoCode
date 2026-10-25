"""Cache kết quả LLM theo mã băm của request (model + messages + tham số), lưu SQLite.

Chỉ dùng cho lời gọi nhiệt độ 0 có đầu ra JSON (bộ trích, router `qwen`, tóm tắt): chạy lại cùng kịch bản → đọc lại đúng kết quả
cũ thay vì gọi model, nên số liệu tái lập được và đối chiếu tay được với đúng đầu ra đã chấm. Prompt đổi một chữ thì khóa đổi,
model được gọi lại. Lời thoại của generator (nhiệt độ 0,3, streaming để đo TTFT) KHÔNG đi qua cache.

Nhiều worker cùng ghi một file: SQLite tự khóa; lỗi cache không bao giờ làm hỏng lượt thoại (chỉ là không cache được).
`LLM_CACHE=off` để tắt.
"""
import hashlib
import json
import os
import sqlite3
import threading

from core.config import settings

_lock = threading.Lock()
_conn = {}


def _db():
    path = settings.llm_cache_path
    if path.lower() in ("off", "none", ""):
        return None
    key = (path, os.getpid())
    if key not in _conn:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        c = sqlite3.connect(path, timeout=30, check_same_thread=False)
        c.execute("CREATE TABLE IF NOT EXISTS llm_cache (k TEXT PRIMARY KEY, model TEXT, v TEXT)")
        _conn[key] = c
    return _conn[key]


def make_key(model, messages, **params):
    blob = json.dumps({"model": model, "messages": messages, **params}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def get(key):
    try:
        c = _db()
        if c is None:
            return None
        with _lock:
            r = c.execute("SELECT v FROM llm_cache WHERE k = ?", (key,)).fetchone()
        return json.loads(r[0]) if r else None
    except Exception:
        return None


def put(key, model, value):
    try:
        c = _db()
        if c is None:
            return
        with _lock:
            c.execute("INSERT OR REPLACE INTO llm_cache VALUES (?, ?, ?)", (key, model, json.dumps(value, ensure_ascii=False)))
            c.commit()
    except Exception:
        pass
