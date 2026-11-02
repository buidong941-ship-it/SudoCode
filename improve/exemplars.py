"""Mục E — Exemplar Bank: lọc lượt mẫu từ trace DEV đã chấm, đưa vào improve/pending/ (kind=exemplar) chờ duyệt.

Lượt được chọn khi đủ CẢ các điều kiện (PLAN-2026-11-01 mục E):
  - thuộc cuộc gọi ĐẠT TSR (không nằm trong failures của report);
  - guardrail không phải sinh lại / thay template, không có problems;
  - không có claim sai (không nằm trong ví dụ HR của report);
  - không phải câu "hứa đại để chốt" (store.PROMISE_RX) và không phải goal mở đầu / chào hỏi thuần;
  - generator là LLM thật (không lấy câu offline/template — câu mẫu phải là văn nói của model).
Số tiền, ngày, mã đơn, SĐT trong câu agent được thay bằng [GIÁ] / [NGÀY] / [MÃ_ĐƠN] / [SĐT] trước khi đề xuất, vì
exemplar chỉ để học cách nói (store.validate chặn mọi số tiền trong exemplar).

    python -m improve exemplars --trace runs/x/dev/full.jsonl --report runs/x/dev/report.json [--per-goal 3]
"""
import re

from improve import collect as C
from improve import store as S

SKIP_GOALS = {"greet", "closing", "opening_returning", "ask_repeat"}
MONEY = re.compile(r"\d[\d.,]*\s*(?:đ|đồng|vnd|vnđ|k|nghìn|ngàn|triệu|tr)(?!\w)|"
                   r"\b(?:một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|trăm)(?:\s+\w+){0,4}\s+(?:triệu|nghìn|ngàn|đồng)\b", re.I)
DATE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
ORDER = re.compile(r"\bOD\d{4,}\b")
PHONE = re.compile(r"(?<!\d)0\d{9,10}(?!\d)")
PCT = re.compile(r"\d+\s*%")


def mask(text):
    t = ORDER.sub("[MÃ_ĐƠN]", text or "")
    t = PHONE.sub("[SĐT]", t)
    t = MONEY.sub("[GIÁ]", t)
    t = PCT.sub("[GIẢM]", t)
    return DATE.sub("[NGÀY]", t)


def mine(trace, report, per_goal=3, generators=("qwen", "deepseek")):
    import json
    C.check_dev_only(trace, report)
    rows = C.load_trace(trace)
    rep = json.load(open(report, encoding="utf-8"))
    sysrep = rep.get("system", rep)
    failed = {(f["scenario"], f["call"]) for f in (sysrep.get("task_success_rate") or {}).get("failures") or []}
    wrong = {(e["scenario"], e["call"], e["turn"]) for e in (sysrep.get("hallucination_rate") or {}).get("examples") or []}
    picked, count = [], {}
    for r in rows:
        g = r.get("guardrail") or {}
        goals = r.get("goals") or []
        key = (r.get("scenario_id"), r.get("call"), r.get("turn"))
        if (key[0], key[1]) in failed or key in wrong:
            continue
        if g.get("problems") or g.get("action") in ("regenerated", "safe_template", "coverage_template", "llm_error_template"):
            continue
        if not goals or set(goals) <= SKIP_GOALS or (r.get("llm_usage") is None and "offline" not in generators):
            continue
        if S.PROMISE_RX.search(r.get("agent_text") or ""):
            continue
        main = next((x for x in goals if x not in SKIP_GOALS), goals[0])
        if count.get(main, 0) >= per_goal:
            continue
        prop = {"kind": "exemplar", "title": f"mẫu {main}",
                "payload": {"customer_text": mask(r.get("customer_text")), "agent_text": mask(r.get("agent_text")),
                            "goals": goals, "source": {"scenario": key[0], "call": key[1], "turn": key[2]}},
                "source_gaps": []}
        if S.validate(prop):
            continue
        count[main] = count.get(main, 0) + 1
        picked.append(prop)
    return picked
