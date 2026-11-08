"""Bộ hiểu ý đa hành động; chỉ trả tên trong hợp đồng đóng, không sinh tham số tool."""
import json
from pathlib import Path

from core.llm.deepseek import LLM

_DOC = json.loads((Path(__file__).with_name("planner_actions.json")).read_text(encoding="utf-8"))
ACTIONS = _DOC["actions"]


def select(text, previous_agent, state):
    names = [n for n, spec in ACTIONS.items()
             if "order" not in spec.get("requires", ()) or state.has_order]
    options = "\n".join(f"- {name}: {ACTIONS[name]['description']}" for name in names)
    prompt = (f"{_DOC['instruction']}\n\nHành động hợp lệ:\n{options}\n\n"
              f"Giai đoạn: {state.stage}; sản phẩm đang bàn: {state.focus or '(chưa có)'}; "
              f"giỏ: {', '.join(state.cart) or '(trống)'}; đơn đã có: {', '.join(state.order_ids) or '(chưa có)'}.\n"
              f"Nhân viên vừa nói: {previous_agent or '(đầu cuộc gọi)'}\nKhách: {text}\n"
              'Trả JSON {"actions": ["tên hành động", ...]}.')
    schema = {"type": "object", "required": ["actions"], "additionalProperties": False,
              "properties": {"actions": {"type": "array", "minItems": 1, "maxItems": 3,
                                         "items": {"type": "string", "enum": names}}}}
    result = LLM("qwen", role="planner").json(prompt, schema=schema, max_tokens=80, cache=False)
    actions = []
    for name in result.get("actions") or []:
        if name in names and name not in actions:
            actions.append(name)
    return actions
