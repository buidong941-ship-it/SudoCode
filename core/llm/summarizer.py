"""Tóm tắt bằng LLM cho (1) episodic memory cuối phiên và (2) handoff brief khi chuyển máy.

LLM chỉ VIẾT câu tóm tắt và phân loại cảm xúc; dữ kiện (sản phẩm, giá, đơn, rào cản, lịch hẹn) do harness đưa vào dưới dạng
FACTS có cấu trúc. Kiểm tra sau khi sinh: mọi số tiền trong câu tóm tắt phải có trong FACTS (cùng tập số guardrail cho phép),
độ dài trong giới hạn schema — sai thì dùng câu ghép từ dữ liệu (`fallback`), nên bộ nhớ không bao giờ chứa giá bịa.

Backend (`SUMMARY_BACKEND`): auto = LLM của generator (câu mẫu khi generator offline) | qwen | deepseek | template.
Tóm tắt phiên chạy trong `end()` (precompute cho Call Brief lần sau, không tính vào độ trễ lượt).
"""
import json

from core import log as cclog
from core.config import settings

log = cclog.get("summary")
SENTIMENTS = ["binh_thuong", "hai_long", "kho_chiu", "gian"]
SCHEMA = {"type": "object", "required": ["summary", "sentiment", "open_questions"], "additionalProperties": False,
          "properties": {"summary": {"type": "string"}, "sentiment": {"type": "string", "enum": SENTIMENTS},
                         "open_questions": {"type": "array", "items": {"type": "string"}}}}


def backend(generator_backend):
    b = settings.summary_backend
    if b == "auto":
        return generator_backend if generator_backend in ("qwen", "deepseek") else "template"
    return b


def summarize(kind, facts, history, allowed_money, generator_backend, max_chars):
    b = backend(generator_backend)
    if kind == "handoff":
        h = settings.handoff_summary
        if h == "template" or (h == "auto" and b != "deepseek"):
            return None
    if b == "template":
        return None
    from core.llm.deepseek import LLM
    from core.pii import Redactor
    from harness.textnorm import find_money
    try:
        llm = LLM(b)
        convo = [f"{'Khách' if h['role'] == 'customer' else 'Nhân viên'}: {h['text']}" for h in history[-12:]]
        data = {"FACTS": facts, "HỘI_THOẠI": convo}
        red = Redactor() if llm.external else None
        if red:
            data = red.redact(json.loads(json.dumps(data, ensure_ascii=False, default=str)))
        task = ("Viết tóm tắt cuộc gọi 1–2 câu cho bộ nhớ khách hàng: khách cần gì, đã tư vấn gì kèm giá, kết quả, rào cản, hẹn gì."
                if kind == "session" else
                "Viết tóm tắt bàn giao 2–4 câu cho nhân viên nhận máy: khách cần gì, đã tư vấn gì kèm giá, đang ở bước nào, vì sao chuyển.")
        prompt = (f"{task}\nChỉ dùng con số có trong FACTS, viết tiền dạng 5.200.000đ, không đọc mã SKU.\n"
                  "sentiment: cảm xúc của khách ở cuối hội thoại. open_questions: câu khách hỏi mà nhân viên chưa trả lời được "
                  "(rỗng nếu không có).\n\n" + json.dumps(data, ensure_ascii=False, default=str))
        d = llm.json(prompt, max_tokens=400, schema=SCHEMA)
        text = (d.get("summary") or "").strip()
        if red:
            text = red.restore(text)
        bad = [v for _, _, v in find_money(text) if v not in allowed_money]
        if not text or len(text) < 20 or len(text) > max_chars or bad:
            log.warning("tóm tắt %s bị loại (dài %d, số tiền lạ %s) → dùng câu ghép", kind, len(text), bad)
            return None
        sentiment = d.get("sentiment") if d.get("sentiment") in SENTIMENTS else "binh_thuong"
        oq = [str(q)[:200] for q in (d.get("open_questions") or [])][:5]
        if red:
            oq = [red.restore(q) for q in oq]
        return {"summary": text, "sentiment": sentiment, "open_questions": oq, "source": b}
    except Exception as e:
        log.warning("tóm tắt %s lỗi → dùng câu ghép: %s: %s", kind, type(e).__name__, str(e)[:160])
        return None
