"""D2 + D3 + D5: kho đề xuất `pending/ → approved/ | rejected/`, nhật ký `log.jsonl`, ảnh chụp vòng và quay lui.

Một đề xuất (proposal) là một file JSON:
    {id, kind, title, payload{}, source_gaps[], author, created_at, status, review{by, at, reason}}

kind và payload:
    faq       {topic, question, answer, policy_refs[]}   bổ sung kiến thức (Knowledge Gap Loop), KHÔNG sửa policy/ của BTC
    playbook  {trigger, instruction}                     cách xử lý một tình huống
    exemplar  {customer_text, agent_text, goals[], source{scenario, call, turn}}   few-shot (Exemplar Bank)
    cue       {slot, pattern}                            cue lexicon cho extractor (regex)

Luật chặn ngay khi đề xuất (không cần người duyệt mới chặn):
- faq / playbook / exemplar không được chứa số tiền, phần trăm giảm giá hay số điện thoại: giá & KM chỉ lấy từ tool.
- exemplar không được là câu "hứa đại để chốt" (cam kết / đảm bảo / chắc chắn ...).
- cue phải là regex biên dịch được.
"""
import datetime as dt
import glob
import hashlib
import json
import os
import re
import shutil

from improve import root as _root

KINDS = {
    "faq": ("topic", "question", "answer"),
    "playbook": ("trigger", "instruction"),
    "exemplar": ("customer_text", "agent_text"),
    "cue": ("slot", "pattern"),
    # D52 (PLAN-2026-11-05-PLANNER-TABLE mục 8): thay đổi kỹ thuật suy ra từ một thẻ context, mỗi cái duyệt riêng
    "planner_rule": ("when", "do", "priority"),        # dòng bảng planner (origin=approved), chỉ handler an toàn
    "router_cue": ("target", "pattern"),               # target = intent:<tên> (router rules) | flag:<tên>
    "product_alias": ("brand", "forms"),               # cách đọc phiên âm thương hiệu cho tầng tra sản phẩm
}
# Loại kỹ thuật: duyệt xong chưa có hiệu lực ngay mà vào gated/, chỉ lên approved/ khi qua cổng hồi quy (python -m improve gate)
GATED_KINDS = ("planner_rule", "router_cue", "product_alias")
STATES = ("pending", "gated", "approved", "rejected")
# Bản sao danh sách handler an toàn của harness/planner_table.SAFE_HANDLERS (improve/ không được import harness;
# tests/improve_d52_check.py kiểm hai danh sách khớp nhau)
SAFE_PLANNER_HANDLERS = {"add_goal", "quote", "policy_answer", "order_status", "refuse_other_customer", "attr_check", "gift_status",
                         "cart_total", "defer_ack", "handoff_scope", "warranty_fact", "policy_peek", "order_updated_note",
                         "ask_repeat", "refund_amount", "defer_close", "handoff_reason"}
ROUTER_INTENTS = {"product_inquiry", "price_promo", "policy_question", "place_order", "order_change", "order_status", "callback",
                  "negotiate", "out_of_scope", "meta", "greeting_or_other"}
ROUTER_FLAGS = {"agrees_to_buy", "defers_decision", "asks_if_bot", "wants_data_deleted", "medical_question", "asks_internal_cost",
                "mentions_competitor"}
MONEY_RX = re.compile(
    r"\d[\d.,]*\s*(?:đ|đồng|vnd|vnđ|k|nghìn|ngàn|triệu|tr|củ|%)(?!\w)|"
    r"\b(?:một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|trăm)\s+(?:triệu|nghìn|ngàn|trăm nghìn)\b|"
    r"(?:giảm|bớt|chiết khấu)\s+\d", re.I)
PHONE_RX = re.compile(r"(?<!\d)0\d{9,10}(?!\d)")
PROMISE_RX = re.compile(r"cam kết|đảm bảo|bảo đảm|chắc chắn|100\s*%|hứa (?:với )?(?:anh|chị)", re.I)


class ProposalError(ValueError):
    pass


def now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def paths(root=None):
    r = _root(root)
    return {"root": r, "gaps": os.path.join(r, "gaps.jsonl"), "log": os.path.join(r, "log.jsonl"),
            "rounds": os.path.join(r, "rounds"), **{s: os.path.join(r, s) for s in STATES}}


def _ensure(root=None):
    p = paths(root)
    for s in STATES:
        os.makedirs(p[s], exist_ok=True)
    os.makedirs(p["rounds"], exist_ok=True)
    return p


def log(event, root=None, **kw):
    p = _ensure(root)
    rec = {"at": now(), "event": event, **kw}
    with open(p["log"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def read_log(root=None):
    p = paths(root)
    if not os.path.exists(p["log"]):
        return []
    with open(p["log"], encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


# ---------- kiểm tra đề xuất ----------

def validate(prop):
    """Trả danh sách lỗi (rỗng = hợp lệ)."""
    errs = []
    kind = prop.get("kind")
    if kind not in KINDS:
        return [f"kind phải là một trong {sorted(KINDS)}"]
    pl = prop.get("payload") or {}
    for f in KINDS[kind]:
        if not str(pl.get(f) or "").strip():
            errs.append(f"payload.{f} trống")
    if kind in ("faq", "playbook", "exemplar"):
        fields = {"faq": ("question", "answer"), "playbook": ("trigger", "instruction"),
                  "exemplar": ("agent_text",)}[kind]
        for f in fields:
            txt = str(pl.get(f) or "")
            m = MONEY_RX.search(txt)
            if m:
                errs.append(f"payload.{f} chứa số tiền/KM '{m.group(0)}' — giá & KM chỉ được lấy từ tool")
            if PHONE_RX.search(txt):
                errs.append(f"payload.{f} chứa số điện thoại")
    if kind == "exemplar":
        m = PROMISE_RX.search(str(pl.get("agent_text") or ""))
        if m:
            errs.append(f"exemplar là câu hứa/cam kết '{m.group(0)}' — không lấy làm mẫu")
    if kind in ("cue", "router_cue"):
        try:
            re.compile(str(pl.get("pattern") or ""))
        except re.error as e:
            errs.append(f"payload.pattern không phải regex hợp lệ: {e}")
    if kind in GATED_KINDS:
        errs += _validate_technical(kind, pl)
    return errs


def _texts(x):
    if isinstance(x, str):
        return [x]
    if isinstance(x, dict):
        return [t for v in x.values() for t in _texts(v)]
    if isinstance(x, list):
        return [t for v in x for t in _texts(v)]
    return []


def _validate_technical(kind, pl):
    """D52: luật chặn cho planner_rule / router_cue / product_alias (trước khi người duyệt thấy)."""
    errs = []
    ex = pl.get("examples") or {}
    if kind != "product_alias" and (not ex.get("match") or not ex.get("no_match")):
        errs.append("phải có examples.match và examples.no_match (mỗi loại ≥ 1 câu)")
    for t in _texts(ex) + _texts(pl.get("forms") or []):
        if MONEY_RX.search(t) or PHONE_RX.search(t):
            errs.append(f"câu ví dụ / cách đọc chứa số tiền hoặc SĐT: '{t[:60]}'")
            break
    if kind == "planner_rule":
        w, do = pl.get("when") or {}, pl.get("do") or {}
        if not isinstance(w, dict) or not w:
            errs.append("when phải là object khác rỗng")
        elif set(w) - {"intent", "intent_not", "flags", "text", "any"}:
            errs.append(f"when chỉ được dùng intent / intent_not / flags / text / any, có {sorted(set(w) - {'intent', 'intent_not', 'flags', 'text', 'any'})}")
        for i in (w.get("intent") or []) + (w.get("intent_not") or []):
            if i not in ROUTER_INTENTS:
                errs.append(f"intent lạ '{i}'")
        for fl, cond in (w.get("flags") or {}).items():
            if fl not in ROUTER_FLAGS or not re.fullmatch(r"(>=|<)\d+(\.\d+)?", str(cond)):
                errs.append(f"điều kiện cờ sai '{fl}: {cond}'")
        if "text" in w:
            try:
                re.compile(w["text"])
            except (re.error, TypeError) as e:
                errs.append(f"when.text không phải regex hợp lệ: {e}")
        if do.get("handler") not in SAFE_PLANNER_HANDLERS:
            errs.append(f"handler '{do.get('handler')}' không nằm trong danh sách an toàn (không tạo / sửa đơn)")
        if not isinstance(pl.get("priority"), (int, float)) or not 1 <= pl["priority"] <= 899:
            errs.append("priority phải trong 1–899 (trước fallback)")
        if pl.get("mode", "add") not in ("add", "terminal"):
            errs.append("mode chỉ được add hoặc terminal")
    if kind == "router_cue":
        tgt = str(pl.get("target") or "")
        typ, _, name = tgt.partition(":")
        if not ((typ == "intent" and name in ROUTER_INTENTS) or (typ == "flag" and name in ROUTER_FLAGS)):
            errs.append(f"target phải là intent:<tên> hoặc flag:<tên> hợp lệ, có '{tgt}'")
    if kind == "product_alias":
        forms = pl.get("forms")
        if not isinstance(forms, list) or not forms or not all(isinstance(x, str) and len(x.strip()) >= 3 for x in forms):
            errs.append("forms phải là danh sách cách đọc (mỗi cách ≥ 3 ký tự)")
    return errs


def make_id(prop):
    body = json.dumps({"kind": prop.get("kind"), "payload": prop.get("payload")}, ensure_ascii=False, sort_keys=True)
    return f"P-{prop.get('kind')}-{hashlib.sha1(body.encode()).hexdigest()[:8]}"


# ---------- vòng đời ----------

def _file(state, pid, root=None):
    return os.path.join(paths(root)[state], f"{pid}.json")


def find(pid, root=None):
    for s in STATES:
        f = _file(s, pid, root)
        if os.path.exists(f):
            with open(f, encoding="utf-8") as fh:
                return s, json.load(fh)
    raise ProposalError(f"không thấy đề xuất {pid}")


def list_state(state="pending", root=None):
    out = []
    for f in sorted(glob.glob(os.path.join(paths(root)[state], "*.json"))):
        with open(f, encoding="utf-8") as fh:
            out.append(json.load(fh))
    return out


def _write(state, prop, root=None):
    p = _ensure(root)
    with open(os.path.join(p[state], f"{prop['id']}.json"), "w", encoding="utf-8") as fh:
        json.dump(prop, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def propose(prop, author="claude", root=None):
    """Đưa một đề xuất vào pending/. Trùng nội dung với một đề xuất đã có (ở bất kỳ trạng thái nào) thì bỏ qua."""
    prop = dict(prop)
    errs = validate(prop)
    if errs:
        raise ProposalError("; ".join(errs))
    prop["id"] = prop.get("id") or make_id(prop)
    for s in STATES:
        if os.path.exists(_file(s, prop["id"], root)):
            return s, prop["id"]
    prop.update({"author": prop.get("author") or author, "created_at": prop.get("created_at") or now(),
                 "status": "pending", "review": None, "source_gaps": prop.get("source_gaps") or []})
    prop.setdefault("title", prop["payload"].get("topic") or prop["payload"].get("trigger")
                    or prop["payload"].get("slot") or prop["kind"])
    _write("pending", prop, root)
    log("propose", root, id=prop["id"], kind=prop["kind"], author=prop["author"], source_gaps=prop["source_gaps"])
    return "pending", prop["id"]


def _move(pid, to, by, reason, root=None, event=None):
    if not (by or "").strip():
        raise ProposalError("phải ghi người duyệt (--by)")
    state, prop = find(pid, root)
    if state == to:
        return prop
    if to == "approved":
        errs = validate(prop)
        if errs:
            raise ProposalError("đề xuất không còn hợp lệ: " + "; ".join(errs))
    os.remove(_file(state, pid, root))
    prop["status"] = to
    prop["review"] = {"by": by, "at": now(), "reason": reason or "", "from": state}
    _write(to, prop, root)
    log(event or {"approved": "approve", "rejected": "reject", "pending": "reopen", "gated": "approve_gated"}[to], root,
        id=pid, by=by, reason=reason or "", from_state=state)
    return prop


def approve(pid, by, reason="", root=None):
    """Người duyệt đồng ý. Loại kỹ thuật (GATED_KINDS) vào gated/ — chưa có hiệu lực cho tới khi qua cổng hồi quy."""
    state, prop = find(pid, root)
    if prop.get("kind") in GATED_KINDS and state != "gated":
        return _move(pid, "gated", by, reason, root)
    return _move(pid, "approved", by, reason, root)


def gate_pass(pid, by, reason="", root=None):
    """Cổng hồi quy đạt → approved/ (agent được nạp)."""
    state, _ = find(pid, root)
    if state != "gated":
        raise ProposalError(f"{pid} không ở gated/ (đang {state})")
    return _move(pid, "approved", by, reason, root, event="gate_pass")


def gate_fail(pid, by, reason="", root=None):
    """Cổng hồi quy trượt → về pending/ kèm danh sách ca hỏng để người duyệt sửa hoặc loại."""
    state, _ = find(pid, root)
    if state != "gated":
        raise ProposalError(f"{pid} không ở gated/ (đang {state})")
    return _move(pid, "pending", by, reason, root, event="gate_fail")


def reject(pid, by, reason="", root=None):
    return _move(pid, "rejected", by, reason, root)


def reopen(pid, by, reason="", root=None):
    return _move(pid, "pending", by, reason, root)


def approved_hash(root=None):
    """Mã băm của bộ approved/ hiện tại — để ghi vào trace / job khi móc nạp được bật (mục E)."""
    h = hashlib.sha256()
    for prop in list_state("approved", root):
        h.update(json.dumps({"id": prop["id"], "payload": prop["payload"]}, ensure_ascii=False, sort_keys=True).encode())
    return h.hexdigest()[:16]


# ---------- vòng và quay lui (D5) ----------

def save_round(name, reports=(), by="", note="", root=None):
    """Chụp approved/ hiện tại + các report của vòng vào rounds/<name>/."""
    if not re.fullmatch(r"[\w.-]+", name or ""):
        raise ProposalError("tên vòng chỉ gồm chữ, số, '.', '-', '_'")
    p = _ensure(root)
    d = os.path.join(p["rounds"], name)
    if os.path.exists(d):
        raise ProposalError(f"vòng {name} đã tồn tại")
    os.makedirs(os.path.join(d, "reports"))
    shutil.copytree(p["approved"], os.path.join(d, "approved"))
    rep = {}
    for r in reports:
        label, _, path = r.partition("=") if "=" in r else (os.path.basename(os.path.dirname(r)) or "report", "", r)
        dst = os.path.join(d, "reports", f"{label}.json")
        shutil.copyfile(path, dst)
        rep[label] = os.path.relpath(dst, d)
    manifest = {"name": name, "at": now(), "by": by, "note": note, "approved_hash": approved_hash(root),
                "approved_ids": [x["id"] for x in list_state("approved", root)], "reports": rep}
    with open(os.path.join(d, "round.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    log("round_save", root, name=name, by=by, approved_hash=manifest["approved_hash"],
        n_approved=len(manifest["approved_ids"]), reports=sorted(rep))
    return manifest


def load_round(name, root=None):
    d = os.path.join(paths(root)["rounds"], name)
    with open(os.path.join(d, "round.json"), encoding="utf-8") as fh:
        m = json.load(fh)
    m["reports_data"] = {}
    for label, rel in m.get("reports", {}).items():
        with open(os.path.join(d, rel), encoding="utf-8") as fh:
            m["reports_data"][label] = json.load(fh)
    return m


def rounds(root=None):
    out = []
    for f in sorted(glob.glob(os.path.join(paths(root)["rounds"], "*", "round.json"))):
        with open(f, encoding="utf-8") as fh:
            out.append(json.load(fh))
    return sorted(out, key=lambda m: m["at"])


def metric(report, name):
    s = report.get("system", report)
    if name == "tsr":
        return (s.get("task_success_rate") or {}).get("value")
    if name == "hr":
        h = s.get("hallucination_rate") or {}
        return (h.get("price_promo_only") or {}).get("value", h.get("value"))
    if name == "rqr":
        return (s.get("repeat_question_rate") or {}).get("value")
    if name == "guardrail":
        g = s.get("guardrail_violations")
        return g.get("total", g.get("value")) if isinstance(g, dict) else g
    raise KeyError(name)


def rollback_decision(prev, cur, tsr_drop=3.0):
    """D5: quay lui khi TSR tụt quá `tsr_drop` điểm HOẶC HR tăng. prev/cur: {label: report}; xét từng bộ chung."""
    reasons = []
    for label in sorted(set(prev) & set(cur)):
        tp, tc = metric(prev[label], "tsr"), metric(cur[label], "tsr")
        hp, hc = metric(prev[label], "hr"), metric(cur[label], "hr")
        if tp is not None and tc is not None and tp - tc > tsr_drop:
            reasons.append(f"{label}: TSR {tp} → {tc} (tụt {tp - tc:.1f} > {tsr_drop} điểm)")
        if hp is not None and hc is not None and hc > hp:
            reasons.append(f"{label}: HR {hp} → {hc} (tăng)")
    missing = sorted(set(prev) ^ set(cur))
    return {"rollback": bool(reasons), "reasons": reasons, "compared": sorted(set(prev) & set(cur)),
            "unmatched_sets": missing}


def rollback(to, by, reason="", root=None):
    """Đưa approved/ về đúng ảnh chụp của vòng `to`. Đề xuất bị gỡ quay về pending/ (để duyệt lại), không bị xoá."""
    if not (by or "").strip():
        raise ProposalError("phải ghi người quyết định quay lui (--by)")
    p = _ensure(root)
    snap = os.path.join(p["rounds"], to, "approved")
    if not os.path.isdir(snap):
        raise ProposalError(f"không có ảnh chụp vòng {to}")
    keep = {os.path.basename(f)[:-5] for f in glob.glob(os.path.join(snap, "*.json"))}
    removed, restored = [], []
    for prop in list_state("approved", root):
        if prop["id"] not in keep:
            _move(prop["id"], "pending", by, f"rollback về {to}: {reason}", root, event="rollback_remove")
            removed.append(prop["id"])
    for f in glob.glob(os.path.join(snap, "*.json")):
        pid = os.path.basename(f)[:-5]
        if not os.path.exists(_file("approved", pid, root)):
            for s in ("pending", "rejected"):
                if os.path.exists(_file(s, pid, root)):
                    os.remove(_file(s, pid, root))
            shutil.copyfile(f, _file("approved", pid, root))
            restored.append(pid)
    log("rollback", root, to=to, by=by, reason=reason, removed=removed, restored=restored,
        approved_hash=approved_hash(root))
    return {"removed": removed, "restored": restored, "approved_hash": approved_hash(root)}
