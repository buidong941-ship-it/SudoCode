"""D1: gom lỗi từ trace + report đã chấm thành `gaps.jsonl`.

Mỗi gap là một dòng JSON:
    {id, type, subtype, scenario, call, turn, customer_text, agent_text, context[], goals[], intent,
     planner_branches[], tools[], detail{}, source{trace, report}}

Loại gap:
    no_info            agent trả no_info / unknown_topic (gap kiến thức — đầu vào chính của Knowledge Gap Loop)
    guardrail          guardrail phải sinh lại hoặc thay bằng template (subtype = action)
    repeat_question    agent hỏi lại slot khách đã nói (lấy từ ví dụ RQR của report)
    customer_repeat    khách phải nhắc lại thông tin ("như anh nói rồi", "lúc nãy chị đã nói"...)
    claim_wrong        claim giá/KM sai (ví dụ HR của report)
    task_fail          cuộc gọi trượt TSR (failures của report, kèm lý do)

Chỉ gom từ bộ DEV: từ chối trace/report/scenario có đường dẫn holdout hoặc out_nat/test.
"""
import hashlib
import json
import os
import re

FORBIDDEN = ("holdout", "out_nat/test", "out_nat\\test")
CUSTOMER_REPEAT_RX = re.compile(
    r"(đã|vừa) (nói|bảo|báo|cho|gửi|đọc)( \w+){0,3} (rồi|mà|lúc nãy|hôm trước)|"
    r"như (anh|chị|em|tôi|mình) (đã )?(nói|bảo)|nói (rồi|lại lần nữa)|nhắc lại (lần nữa|lại)|"
    r"lúc nãy (anh|chị|tôi|mình) (đã )?(nói|bảo)|hôm trước (anh|chị|tôi|mình) (đã )?(nói|bảo|báo)", re.I)
TEMPLATE_ACTIONS = {"safe_template", "coverage_template", "llm_error_template"}


class LeakError(ValueError):
    """Dữ liệu ngoài dev (holdout / test) bị đưa vào vòng feedback."""


def check_dev_only(*paths):
    for p in paths:
        if p and any(f in str(p).replace("\\", "/") for f in (x.replace("\\", "/") for x in FORBIDDEN)):
            raise LeakError(f"chỉ được gom feedback từ dev, không từ {p}")


def gap_id(*parts):
    return "G" + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:10]


def load_trace(path, config="full"):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if ln:
                r = json.loads(ln)
                if config is None or r.get("config") == config:
                    rows.append(r)
    for r in rows:
        check_dev_only(r.get("run_id"))
    return rows


def _key(r):
    return (r.get("scenario_id"), r.get("call"), r.get("turn"))


def _context(rows_by_call, r, n=2):
    calls = rows_by_call.get((r.get("scenario_id"), r.get("call")), [])
    prev = [x for x in calls if x.get("turn", 0) < r.get("turn", 0)][-n:]
    return [{"turn": x.get("turn"), "customer": x.get("customer_text"), "agent": x.get("agent_text")} for x in prev]


def _base(r, rows_by_call, typ, subtype=None, detail=None):
    return {
        "id": gap_id(typ, subtype, *_key(r)),
        "type": typ, "subtype": subtype,
        "scenario": r.get("scenario_id"), "call": r.get("call"), "turn": r.get("turn"),
        "customer_text": r.get("customer_text"), "agent_text": r.get("agent_text"),
        "context": _context(rows_by_call, r),
        "goals": r.get("goals") or [],
        "intent": (r.get("router") or {}).get("intent"),
        "planner_branches": ((r.get("planner") or {}).get("branches")) or [],
        "tools": [t.get("name") for t in r.get("tool_calls") or []],
        "detail": detail or {},
    }


def from_trace(rows):
    by_call = {}
    for r in sorted(rows, key=lambda x: (x.get("scenario_id"), x.get("call"), x.get("turn", 0))):
        by_call.setdefault((r.get("scenario_id"), r.get("call")), []).append(r)
    out = []
    for r in rows:
        goals = r.get("goals") or []
        if "no_info" in goals:
            topic = None
            for b in (r.get("planner") or {}).get("branches") or []:
                if b.get("branch") in ("policy_gap", "attr_unknown", "no_info"):
                    topic = b.get("reason")
            out.append(_base(r, by_call, "no_info", detail={"reason": topic}))
        g = r.get("guardrail") or {}
        act = g.get("action")
        if g.get("problems") or act in TEMPLATE_ACTIONS or act == "regenerated":
            out.append(_base(r, by_call, "guardrail", act or "problems",
                             {"problems": g.get("problems") or [], "coverage": g.get("coverage") or [],
                              "rejected": (g.get("rejected") or [])[:2]}))
        m = CUSTOMER_REPEAT_RX.search(r.get("customer_text") or "")
        if m:
            out.append(_base(r, by_call, "customer_repeat", detail={"cue": m.group(0)}))
    return out


def from_report(report, rows):
    """Lỗi do reference_eval chấm: RQR, HR, TSR. `report` là report.json của eval/reference_eval.py."""
    sysrep = report.get("system", report)
    idx = {_key(r): r for r in rows}
    by_call = {}
    for r in rows:
        by_call.setdefault((r.get("scenario_id"), r.get("call")), []).append(r)
    out = []

    def row_for(ex):
        return idx.get((ex.get("scenario"), ex.get("call"), ex.get("turn"))) or {
            "scenario_id": ex.get("scenario"), "call": ex.get("call"), "turn": ex.get("turn")}

    for ex in (sysrep.get("repeat_question_rate") or {}).get("examples") or []:
        out.append(_base(row_for(ex), by_call, "repeat_question", ex.get("slot"),
                         {"slot": ex.get("slot"), "question": ex.get("text"), "qtype": ex.get("type")}))
    for ex in (sysrep.get("hallucination_rate") or {}).get("examples") or []:
        out.append(_base(row_for(ex), by_call, "claim_wrong", ex.get("field"),
                         {"field": ex.get("field"), "claimed": ex.get("claimed"), "truth": ex.get("truth")}))
    for f in (sysrep.get("task_success_rate") or {}).get("failures") or []:
        turns = sorted(by_call.get((f.get("scenario"), f.get("call")), []), key=lambda x: x.get("turn", 0))
        last = turns[-1] if turns else {"scenario_id": f.get("scenario"), "call": f.get("call"), "turn": None}
        g = _base(last, by_call, "task_fail", f.get("hard_case"),
                  {"reasons": f.get("reasons") or [], "hard_case": f.get("hard_case")})
        g["id"] = gap_id("task_fail", f.get("scenario"), f.get("call"))
        g["turn"] = None
        g["context"] = [{"turn": x.get("turn"), "customer": x.get("customer_text"), "agent": x.get("agent_text"),
                         "goals": x.get("goals"), "tools": [t.get("name") for t in x.get("tool_calls") or []]}
                        for x in turns]
        out.append(g)
    return out


def collect(trace, report=None, scenarios=None, config="full"):
    check_dev_only(trace, report, scenarios)
    rows = load_trace(trace, config)
    gaps = from_trace(rows)
    if report:
        with open(report, encoding="utf-8") as fh:
            gaps += from_report(json.load(fh), rows)
    seen, uniq = set(), []
    for g in gaps:
        if g["id"] not in seen:
            seen.add(g["id"])
            g["source"] = {"trace": os.path.relpath(trace) if _same_drive(trace) else trace,
                           "report": (os.path.relpath(report) if _same_drive(report) else report) if report else None}
            uniq.append(g)
    return uniq


def _same_drive(p):
    try:
        os.path.relpath(p)
        return True
    except ValueError:
        return False


def write(gaps, path, append=False):
    """Ghi gaps.jsonl; khi append thì bỏ qua id đã có (gom nhiều vòng không nhân bản)."""
    have = set()
    if append and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            have = {json.loads(l)["id"] for l in fh if l.strip()}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    n = 0
    with open(path, "a" if append else "w", encoding="utf-8") as fh:
        for g in gaps:
            if g["id"] in have:
                continue
            fh.write(json.dumps(g, ensure_ascii=False) + "\n")
            n += 1
    return n


def load(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def summary(gaps):
    from collections import Counter
    c = Counter((g["type"], g.get("subtype")) for g in gaps)
    return [{"type": t, "subtype": s, "n": n} for (t, s), n in sorted(c.items(), key=lambda x: (-x[1], str(x[0])))]
