"""B-H (PLAN-2026-11-01): planner hybrid CÓ GIỚI HẠN — LLM chỉ đề xuất goal khi planner bằng code bế tắc.

Đường chính vẫn là `CallSession._plan()`. Module này chỉ được gọi ở nhánh fallback (không nhánh code nào khớp lời khách),
khi `PLANNER_BACKEND` khác `rules` (mặc định `rules` → không gọi gì, trace y hệt trước).

LLM được làm gì: chọn MỘT goal trong danh sách đóng các goal hợp lệ ở trạng thái hiện tại (`allowed_goals`), hoặc `none`.
LLM KHÔNG được: gọi tool, chọn tạo/sửa đơn (order.create / order.update không có trong danh sách), thấy đáp án scenario.
Mọi goal LLM chọn đều qua code kiểm điều kiện ở `CallSession._apply_llm_goal` trước khi thực thi.

Backend: `jev` (Choice, có độ tin cậy) làm chính; Jev lỗi → `qwen` (JSON Schema enum, nhiệt độ 0, cache như router).
Jev trả điểm dưới `PLANNER_JEV_MIN_CONF` → abstain (quay về nhánh code), KHÔNG gọi Qwen. `PLANNER_BACKEND=qwen` → chỉ Qwen.
PII được che bằng core.pii.Redactor trước khi gửi.
"""
import time

from core.config import settings
from core.pii import Redactor

# mô tả goal cho LLM (tiếng Việt, ngắn). Chỉ các goal an toàn, không có tạo / sửa đơn.
GOALS = {
    "quote": "báo lại giá / khuyến mãi của sản phẩm đang tư vấn (khách hỏi giá, hỏi KM, hỏi còn ưu đãi không)",
    "policy_answer": "trả lời theo chính sách / tài liệu của shop (đổi trả, bảo hành, giao hàng, thanh toán)",
    "order_status": "tra tình trạng đơn hàng khách đã đặt (đơn tới đâu, bao giờ giao, mã đơn)",
    "defer_ack": "khách muốn suy nghĩ / hỏi người nhà / để sau: ghi nhận và hẹn liên hệ lại",
    "ask_product": "khách chưa nói cần sản phẩm gì: hỏi khách cần tư vấn sản phẩm nào",
    "ask_repeat": "câu khách không rõ nghĩa / bị cắt: xin khách nói lại",
    "closing": "khách cảm ơn / chào / kết thúc cuộc gọi",
    "none": "không goal nào ở trên phù hợp",
}


def allowed_goals(state):
    """Danh sách đóng theo trạng thái cuộc gọi. state: {focus, has_orders, turn_no}."""
    g = ["policy_answer", "defer_ack", "ask_repeat", "closing", "none"]
    if state.get("focus"):
        g.insert(0, "quote")
    else:
        g.insert(0, "ask_product")
    if state.get("has_orders"):
        g.insert(0, "order_status")
    return g


def _jev(text, recent, goals):
    from typesafe_sdk import Choice
    from harness.question_classifiers.jev_slots import _client
    state = Redactor().redact({"customer_said": text, "recent_dialogue": recent[-4:]})
    q = {"goal": Choice(instructions="Nhân viên bán hàng nên làm gì tiếp với câu khách vừa nói?",
                        criteria={k: GOALS[k] for k in goals})}
    r = _client().system_one(state=state, questions=q, model=settings.jev_model)
    ch = r.choices["goal"]
    return ch.choice, float(ch.confidence)


def _qwen(text, recent, goals):
    import json
    from core.llm.deepseek import LLM
    schema = {"type": "object", "required": ["goal"], "additionalProperties": False,
              "properties": {"goal": {"type": "string", "enum": goals}}}
    prompt = ("Bạn chọn bước tiếp theo cho nhân viên bán hàng qua điện thoại. Chỉ chọn MỘT goal trong danh sách, "
              "trả JSON {\"goal\": <goal>}.\n" + "\n".join(f"- {k}: {GOALS[k]}" for k in goals)
              + f"\n\nHội thoại gần đây: {json.dumps(recent[-4:], ensure_ascii=False)}\nCâu khách: {text}")
    d = LLM("qwen").json(prompt, schema=schema)
    g = d.get("goal")
    return (g if g in goals else "none"), None


def suggest(text, recent, state, backend=None):
    """→ {"goal", "confidence", "backend", "fallback", "ms", "allowed"}; goal None = abstain."""
    backend = backend or settings.planner_backend
    goals = allowed_goals(state)
    t0 = time.perf_counter()
    out = {"goal": None, "confidence": None, "backend": backend, "fallback": None, "allowed": goals}
    if backend == "rules":
        return out
    try:
        if backend == "jev":
            try:
                g, conf = _jev(text, recent, goals)
            except Exception as e:                              # Jev lỗi → Qwen
                out["fallback"] = f"jev {type(e).__name__}: {str(e)[:120]}"
                out["backend"] = "qwen"
                g, conf = _qwen(text, recent, goals)
            else:
                if conf < settings.planner_jev_min_conf:      # dưới ngưỡng → abstain, KHÔNG gọi Qwen
                    out.update(confidence=conf, abstain=f"jev conf {conf:.2f} < {settings.planner_jev_min_conf}")
                    out["ms"] = int((time.perf_counter() - t0) * 1000)
                    return out
        else:
            g, conf = _qwen(text, recent, goals)
    except Exception as e:
        out["fallback"] = (out["fallback"] + " | " if out["fallback"] else "") + f"{type(e).__name__}: {str(e)[:120]}"
        out["ms"] = int((time.perf_counter() - t0) * 1000)
        return out
    out.update(goal=None if g == "none" else g, confidence=conf, ms=int((time.perf_counter() - t0) * 1000))
    return out
