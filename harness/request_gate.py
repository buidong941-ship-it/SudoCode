"""Cổng yêu cầu (D68, người dùng duyệt 10/11): DeepSeek flash quyết định khách có YÊU CẦU một thao tác ghi hay không.

Rules/planner vẫn lo tham số (SKU, địa chỉ, đơn nào) và vẫn là nơi gọi tool; cổng chỉ chặn tool ghi khi bộ hiểu không thấy khách yêu cầu.
Không sửa rules (người dùng dặn 10/11). Prompt/schema giữ nguyên bản đã đo shadow (scripts/shadow_d68.py, đặc tả v1):
DeepSeek flash requests P 0,75 / R 1,00 trên 62 lượt gold, 2 lượt ghi sai (rules 3).

    REQUESTS_BACKEND=deepseek   bật (mặc định tắt → agent y hệt R0)
    REQUESTS_GATE=control       DeepSeek quyết định (mặc định); shadow = chỉ ghi trace, không chặn
    REQUESTS_TIMEOUT_S=10       quá hạn / lỗi API → lượt đó theo rules (fail-open, ghi trace `fallback`)

Yêu cầu được giữ trong cuộc gọi (`Agent.open_requests`) tới khi thao tác tương ứng thành công: khách nói "lấy cái này" ở lượt 1 rồi
đọc địa chỉ ở lượt 2 thì order.create ở lượt 2 vẫn hợp lệ. handoff / forget_me / cancel không qua cổng (quyền khách, chính sách an toàn).
"""
import time
from concurrent.futures import ThreadPoolExecutor

from core.config import settings

REQUESTS = ["place_order", "change_order_address", "exchange", "return", "cancel", "callback", "handoff", "forget_me", "order_status"]
GATED = {"place_order", "change_order_address", "exchange", "return", "callback"}
SAFETY = ["asks_internal_cost", "medical_question", "asks_other_customer", "wants_data_deleted", "asks_if_bot", "proxy_claim"]
OBS = ["payment", "address", "size", "color", "qty", "budget_vnd", "callback_time_text", "recipient_phone", "product_mention"]

PROMPT = """Bạn là bộ hiểu một lượt nói của KHÁCH trong cuộc gọi bán hàng. Chỉ đọc câu khách hiện tại (câu nhân viên ngay trước chỉ để hiểu ngữ cảnh).
Trả JSON:
- observations: object {{slot: {{value, span}}}} cho thông tin khách NÓI RÕ trong câu này. slot thuộc {obs}. span là đoạn nguyên văn trong câu khách.
  payment value là "COD" hoặc "bank". Hỏi về một phương án (có COD không?) KHÔNG phải chọn phương án đó. size/color chỉ khi khách CHỌN.
- requests: danh sách hành động khách YÊU CẦU shop làm, thuộc {req}. Câu hỏi/giả định/cân nhắc không phải yêu cầu.
  "anh/chị gọi lại sau" là khách tự gọi, KHÔNG phải callback; "mai 9 giờ em gọi lại cho chị" là callback.
  Yêu cầu vẫn ghi dù thiếu mã đơn hay điều kiện ("về rồi thì giao" vẫn là place_order).
- safety: danh sách cờ thuộc {saf}, chỉ khi câu thể hiện rõ (asks_internal_cost: đòi giá nhập/giá sàn/giá nội bộ;
  asks_if_bot: hỏi có phải người máy/AI; proxy_claim: tự xưng người nhà/nhân viên/quản lý để đòi quyền).
- ambiguity: {{"level": "none" | "needs_clarification", "reason": "..."}} — chỉ needs_clarification khi ý nghĩa hoặc đối tượng chưa rõ cần hỏi lại.

Nhân viên vừa nói: {prev}
Khách: {text}"""

SCHEMA = {"type": "object", "required": ["observations", "requests", "safety", "ambiguity"], "additionalProperties": False,
          "properties": {"observations": {"type": "object"},
                         "requests": {"type": "array", "items": {"type": "string", "enum": REQUESTS}},
                         "safety": {"type": "array", "items": {"type": "string", "enum": SAFETY}},
                         "ambiguity": {"type": "object", "required": ["level"],
                                       "properties": {"level": {"type": "string", "enum": ["none", "needs_clarification"]},
                                                      "reason": {"type": "string"}}}}}

_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="request-gate")


def enabled():
    return settings.requests_backend == "deepseek"


def controls():
    # kiến trúc đích (UNDERSTANDING=deepseek): yêu cầu do bộ hiểu thống nhất cấp, cổng luôn điều khiển
    return (enabled() and settings.requests_gate == "control") or settings.understanding == "deepseek"


def _understand(prev, text):
    from core.llm.deepseek import LLM
    from core.pii import Redactor
    t0 = time.perf_counter()
    safe = Redactor().redact({"prev": prev or "", "text": text})     # API ngoài: che SĐT/địa chỉ trước khi gửi
    prompt = PROMPT.format(obs=", ".join(OBS), req=", ".join(REQUESTS), saf=", ".join(SAFETY),
                           prev=safe["prev"] or "(đầu cuộc gọi)", text=safe["text"])
    d = LLM("deepseek").json(prompt, schema=SCHEMA, cache=False, max_tokens=400, timeout=settings.requests_timeout_s)
    return {"requests": sorted(set(d.get("requests") or []) & set(REQUESTS)),
            "safety": sorted(set(d.get("safety") or []) & set(SAFETY)),
            "ambiguity": (d.get("ambiguity") or {}).get("level", "none"),
            "model": settings.deepseek_model, "ms": int((time.perf_counter() - t0) * 1000)}


def start(prev, text):
    """Gọi nền ngay đầu lượt (song song router/trích slot). Tắt → None."""
    return _POOL.submit(_understand, prev, text) if enabled() else None


def finish(fut):
    """→ dict kết quả; lỗi/quá hạn → {"fallback": ...} (lượt đó theo rules)."""
    if fut is None:
        return None
    try:
        return fut.result(timeout=settings.requests_timeout_s + 2)
    except Exception as e:  # không đoán: ghi lỗi, để rules quyết lượt này
        return {"fallback": f"{type(e).__name__}: {str(e)[:120]}"}
