"""D52 (PLAN-2026-11-05-PLANNER-TABLE mục 8): context lạ → thẻ context → đề xuất DUYỆT TÁCH từng mục.

1. find_unusual(rows): đánh dấu lượt "lạ" từ trace dev (chỉ dựa trên trace, KHÔNG dựa trên report chấm điểm):
   chỉ rơi vào fallback (R36 / branch fallback), router không chắc / dự phòng, guardrail phải sinh lại / dùng câu mẫu,
   agent xin nhắc lại, khách phải nhắc lại ý.
2. context_view(): thứ DUY NHẤT gửi cho LLM — lời khách, lời agent, intent / cờ router, goal, tên tool. Không bao giờ có
   success_if / ground_truth / _meta / lý do chấm của kịch bản (kiểm bằng ALLOWED_KEYS).
3. LLM (HTTP OpenAI-compatible, không import core): trả thẻ {summary, handling, items[]}. Mỗi item là MỘT đề xuất
   (playbook / exemplar / planner_rule / router_cue / cue / product_alias) → pending/ với cùng context_id.
   Hoặc nạp thẻ đã viết sẵn từ file (--cards), ví dụ do người / trợ lý soạn trong phiên.

Chạy ngoài cuộc gọi, theo lô. Chỉ từ bộ DEV (collect.check_dev_only).
"""
import hashlib
import json
import os
import re
import urllib.request

from improve import collect as C
from improve import store as S

ALLOWED_KEYS = {"scenario", "call", "turn", "signals", "customer_text", "agent_text", "intent", "flags", "goals", "tools", "context"}
SIGNALS = ("fallback", "router_unsure", "guardrail", "ask_repeat", "customer_repeat")
TEMPLATE_ACTIONS = {"safe_template", "coverage_template", "llm_error_template", "regenerated"}


def signals_of(r):
    out = []
    pl = r.get("planner") or {}
    branches = [b.get("branch") for b in pl.get("branches") or []]
    if "fallback" in branches or (pl.get("table") or [])[-1:] == ["R36"]:
        out.append("fallback")
    ro = r.get("router") or {}
    if ro.get("fallback") or (ro.get("confidence") is not None and ro.get("confidence") < 0.6):
        out.append("router_unsure")
    if (r.get("guardrail") or {}).get("action") in TEMPLATE_ACTIONS:
        out.append("guardrail")
    if "ask_repeat" in (r.get("goals") or []):
        out.append("ask_repeat")
    if C.CUSTOMER_REPEAT_RX.search(r.get("customer_text") or ""):
        out.append("customer_repeat")
    return out


def find_unusual(rows):
    by_call = {}
    for r in sorted(rows, key=lambda x: (x.get("scenario_id"), x.get("call"), x.get("turn", 0))):
        by_call.setdefault((r.get("scenario_id"), r.get("call")), []).append(r)
    out = []
    for r in rows:
        sig = signals_of(r)
        if sig:
            out.append(context_view(r, sig, by_call))
    return out


def context_view(r, sig, by_call):
    prev = [x for x in by_call.get((r.get("scenario_id"), r.get("call")), []) if x.get("turn", 0) < r.get("turn", 0)][-2:]
    v = {"scenario": r.get("scenario_id"), "call": r.get("call"), "turn": r.get("turn"), "signals": sig,
         "customer_text": r.get("customer_text"), "agent_text": r.get("agent_text"),
         "intent": (r.get("router") or {}).get("intent"),
         "flags": {k: round(x, 2) for k, x in ((r.get("router") or {}).get("flags") or {}).items() if x >= 0.3},
         "goals": r.get("goals") or [], "tools": [t.get("name") for t in r.get("tool_calls") or []],
         "context": [{"customer": x.get("customer_text"), "agent": x.get("agent_text")} for x in prev]}
    assert set(v) <= ALLOWED_KEYS
    return v


def context_id(v):
    return "CTX-" + hashlib.sha1(f"{v['scenario']}|{v['call']}|{v['turn']}|{v['customer_text']}".encode()).hexdigest()[:8]


PROMPT = """Bạn hỗ trợ đội sale cải tiến một agent bán hàng qua điện thoại (tiếng Việt). Dưới đây là MỘT lượt agent xử lý chưa tốt
(tín hiệu: {signals}). Hãy viết THẺ CONTEXT dạng JSON:
{{"summary": "<tình huống, 1–2 câu>", "handling": "<cách sale nên xử lý, lời thường>",
  "items": [<0–4 đề xuất, mỗi cái là một trong các dạng dưới>]}}

Dạng đề xuất (chỉ dùng khi thật cần; KHÔNG ghi số tiền, phần trăm, số điện thoại, KHÔNG hứa / cam kết):
- {{"kind": "playbook", "payload": {{"trigger": "<từ khóa>", "instruction": "<hướng dẫn>"}}}}
- {{"kind": "exemplar", "payload": {{"customer_text": "...", "agent_text": "...", "goals": ["..."]}}}}
- {{"kind": "router_cue", "payload": {{"target": "intent:<một trong {intents}> | flag:<một trong {flags}>",
   "pattern": "<regex trên câu đã bỏ dấu, chữ thường>", "examples": {{"match": ["..."], "no_match": ["..."]}}}}}}
- {{"kind": "cue", "payload": {{"slot": "<tên slot>", "pattern": "<regex bỏ dấu>"}}}}
- {{"kind": "product_alias", "payload": {{"brand": "<tên thương hiệu như catalog>", "forms": ["<cách đọc>"]}}}}
- {{"kind": "planner_rule", "payload": {{"when": {{"intent": ["..."], "text": "<regex bỏ dấu>"}}, "do": {{"handler": "<một trong {handlers}>",
   "goals": ["..."]}}, "priority": <1–899>, "mode": "add", "examples": {{"match": ["..."], "no_match": ["..."]}}}}}}
Chỉ trả JSON.

Lượt cần xem:
{view}"""


def build_prompt(v):
    assert set(v) <= ALLOWED_KEYS, f"khóa không được phép gửi LLM: {set(v) - ALLOWED_KEYS}"
    return PROMPT.format(signals=", ".join(v["signals"]), intents=", ".join(sorted(S.ROUTER_INTENTS)),
                         flags=", ".join(sorted(S.ROUTER_FLAGS)), handlers=", ".join(sorted(S.SAFE_PLANNER_HANDLERS)),
                         view=json.dumps(v, ensure_ascii=False, indent=1))


def llm_card(v, base_url=None, model=None, api_key=None, timeout=120):
    """Gọi LLM OpenAI-compatible (Qwen qua vLLM hoặc DeepSeek). Cấu hình: IMPROVE_LLM_BASE_URL / IMPROVE_LLM_MODEL / IMPROVE_LLM_API_KEY."""
    base_url = (base_url or os.environ.get("IMPROVE_LLM_BASE_URL") or os.environ.get("QWEN_BASE_URL") or "").rstrip("/")
    model = model or os.environ.get("IMPROVE_LLM_MODEL") or os.environ.get("QWEN_MODEL")
    if not base_url or not model:
        raise RuntimeError("chưa cấu hình IMPROVE_LLM_BASE_URL / IMPROVE_LLM_MODEL")
    body = json.dumps({"model": model, "temperature": 0, "messages": [{"role": "user", "content": build_prompt(v)}],
                       "response_format": {"type": "json_object"}}).encode()
    req = urllib.request.Request(base_url + "/chat/completions", data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {api_key or os.environ.get('IMPROVE_LLM_API_KEY', 'EMPTY')}"})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        txt = json.loads(fh.read())["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", txt, re.S)
    return json.loads(m.group(0) if m else txt)


def card_to_proposals(card, v, author="llm", root=None):
    """Mỗi item của thẻ → một đề xuất riêng trong pending/ (duyệt tách). Item sai luật chặn bị ghi lỗi, không vào kho."""
    cid = context_id(v)
    ctx = {"id": cid, "summary": card.get("summary", ""), "handling": card.get("handling", ""),
           "scenario": v["scenario"], "call": v["call"], "turn": v["turn"], "signals": v["signals"],
           "customer_text": v["customer_text"], "agent_text": v["agent_text"]}
    made, errors = [], []
    items = list(card.get("items") or [])
    if card.get("handling") and not any(i.get("kind") == "playbook" for i in items):
        items.insert(0, {"kind": "playbook", "payload": {"trigger": " ".join(re.findall(r"\w+", v["customer_text"] or ""))[:60],
                                                         "instruction": card["handling"]}})
    for it in items:
        prop = {"kind": it.get("kind"), "payload": it.get("payload") or {}, "title": it.get("title"),
                "context": ctx, "source_gaps": [cid]}
        try:
            state, pid = S.propose(prop, author=author, root=root)
            made.append((state, pid, prop["kind"]))
        except S.ProposalError as e:
            errors.append({"kind": it.get("kind"), "error": str(e)})
    S.log("context_card", root, context_id=cid, made=[m[1] for m in made], errors=errors)
    return cid, made, errors


def run(trace, root=None, cards=None, limit=20, config="full", author="llm"):
    """Gom lượt lạ từ trace dev → thẻ context (LLM hoặc file --cards {context_id|scenario:call:turn → thẻ})."""
    C.check_dev_only(trace)
    rows = C.load_trace(trace, config)
    views = find_unusual(rows)[:limit]
    given = json.load(open(cards, encoding="utf-8")) if cards else None
    out = []
    for v in views:
        key = f"{v['scenario']}:{v['call']}:{v['turn']}"
        if given is not None:
            card = given.get(context_id(v)) or given.get(key)
            if not card:
                continue
        else:
            card = llm_card(v)
        out.append(card_to_proposals(card, v, author=author, root=root))
    return views, out
