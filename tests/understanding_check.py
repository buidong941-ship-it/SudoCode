"""Kiểm bộ hiểu thống nhất (harness/understanding.py) với phản hồi DeepSeek giả lập — không gọi API.

- intent / flags / safety → route của planner; slot qua kiểm dẫn chứng (span phải có trong câu) + chuẩn hóa bằng code
- span không có trong câu → bỏ, ghi lý do
- API lỗi hai lần → ném lỗi (agent xin nói lại, KHÔNG quay về pipeline cũ)
- planner_table: route có `understanding` thì asking/takes theo bộ hiểu, không theo regex
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import settings  # noqa: E402
from core.llm import deepseek  # noqa: E402
from harness import understanding as U  # noqa: E402

fails = []


def check(name, cond, got=None):
    print(("OK   " if cond else "FAIL ") + name + ("" if cond else f"  → {got}"))
    if not cond:
        fails.append(name)


TEXT = "Giao về 12 Lê Lợi, Quận 1, TP HCM, chị trả COD nhé"
CANNED = {"intent": "place_order", "flags": ["agrees_to_buy", "bogus_flag"],
          "observations": [{"slot": "address", "span": "12 Lê Lợi, Quận 1, TP HCM"}, {"slot": "payment", "span": "COD", "label": "COD"},
                           {"slot": "size", "span": "size 99"}, {"slot": "not_a_slot", "span": "x"}],
          "requests": [{"kind": "place_order", "evidence": "Giao về"}, {"kind": "launch_rocket", "evidence": "Giao về"}],
          "withdrawn": [], "response_to_agent": {"act": "none"}, "asks": [], "refs": {},
          "safety": ["proxy_claim"], "asks_question": False, "ambiguity": {"level": "none"}}

with patch.object(settings, "understanding", "deepseek"), patch.object(settings, "deepseek_api_key", "test-key"):
    seen = {}

    def fake_json(self, prompt, **kw):
        seen["prompt"] = prompt
        return CANNED
    with patch.object(deepseek.LLM, "json", fake_json):
        u = U.understand(TEXT, "2026-10-15", [{"role": "agent", "text": "Dạ anh/chị cho em xin địa chỉ ạ?"}], "", "address")
    check("intent → route", u["route"]["intent"] == "place_order", u["route"])
    check("cờ hợp lệ bật, cờ lạ bỏ", u["route"]["flags"].get("agrees_to_buy") == 1.0 and "bogus_flag" not in u["route"]["flags"], u["route"]["flags"])
    check("slot address có dẫn chứng", u["slots"].get("address") == "12 Lê Lợi, Quận 1, TP HCM", u["slots"])
    check("slot payment chuẩn hóa bằng code", u["slots"].get("payment") == "COD", u["slots"])
    check("span không có trong câu → bỏ", "size" not in u["slots"] and any(d.get("why") == "span_not_in_text" for d in u["meta"]["dropped"]), u["meta"])
    check("slot lạ → bỏ", "not_a_slot" not in u["slots"], u["slots"])
    check("yêu cầu lạ → bỏ", u["requests"] == ["place_order"], u["requests"])
    check("safety proxy_claim giữ", u["safety"] == ["proxy_claim"], u["safety"])
    check("planner nhận understanding trong route", u["route"]["understanding"]["requests"] == ["place_order"], u["route"])
    check("địa chỉ bị che trước khi gửi API", "12 Lê Lợi" not in seen["prompt"], seen["prompt"][-300:])
    check("không đưa đáp án kịch bản vào prompt", not any(k in seen["prompt"] for k in ("success_if", "ground_truth", "_meta")))

    def boom(self, prompt, **kw):
        raise TimeoutError("api down")
    with patch.object(deepseek.LLM, "json", boom):
        try:
            U.understand("alo em", "2026-10-15", [], "", None)
            check("API lỗi → ném lỗi", False, "không ném")
        except RuntimeError as e:
            check("API lỗi → ném lỗi sau 2 lần", "after 2 attempts" in str(e), str(e))

# planner: asking / takes theo bộ hiểu
from harness import planner_table  # noqa: E402


class _S:
    focus, focus_by, discussed, cart = None, None, [], []

    def _cart_add(self, x):
        self.cart.append(x)


c = planner_table.Ctx(_S(), "ok để mình tính", {}, {"intent": "callback", "flags": {},
                                                     "understanding": {"asks_question": False, "requests": []}})
planner_table._prepare(c)
check("planner: không yêu cầu → takes False", c.takes is False and c.asking is False, (c.takes, c.asking))
c = planner_table.Ctx(_S(), "giá bao nhiêu", {}, {"intent": "price_promo", "flags": {}, "understanding": {"asks_question": True, "requests": []}})
planner_table._prepare(c)
check("planner: asks_question → asking True", c.asking is True, c.asking)

print(f"\n{'TẤT CẢ OK' if not fails else f'{len(fails)} lỗi: {fails}'}")
sys.exit(1 if fails else 0)
