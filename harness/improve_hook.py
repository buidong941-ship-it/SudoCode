"""Mục E (PLAN-2026-11-01): ĐIỂM NỐI DUY NHẤT giữa agent và cơ chế cải tiến `improve/`.

Tắt mặc định: `IMPROVE_DIR` rỗng → mọi hàm trả rỗng, agent và trace y hệt khi không có module này.
Bật (`IMPROVE_DIR=improve` hoặc thư mục vòng khác): chỉ đọc đề xuất ĐÃ DUYỆT (`improve.loader.load_approved`, kiểm lại luật
chặn số tiền / SĐT / câu hứa khi nạp) và đưa vào agent theo 4 loại:
    faq       thêm vào kết quả tra chính sách (chunk_id "FAQ:<id>") khi câu khách khớp câu hỏi / chủ đề FAQ
    playbook  plan["PLAYBOOK"] = hướng dẫn khi câu khách khớp trigger (generator có luật 16 đi kèm)
    exemplar  plan["EXEMPLARS"] = tối đa 2 câu mẫu có goal trùng goal lượt này (chỉ tham khảo văn phong)
    cue       cue extractor bổ sung (harness/lexicon.cue_hit) → chặn chứng nhận rỗng, mở cổng LLM
Trace ghi `improve: {approved_hash, used[]}` khi bật, để biết lượt nào dùng đề xuất nào (so vòng, quay lui).
"""
import re

from core.config import settings
from harness.textnorm import fold

_cache = {"dir": None, "data": None}
STOP = {"em", "anh", "chi", "a", "co", "khong", "cho", "minh", "voi", "thi", "la", "va", "nha", "nhe", "o", "duoc", "cua",
        "nay", "do", "the", "nao", "gi", "ben", "shop", "toi", "vay", "roi", "con", "neu", "khi", "mot", "nhung", "cai"}


def enabled():
    return bool(settings.improve_dir)


def approved():
    if not enabled():
        return None
    if _cache["dir"] != settings.improve_dir:
        from improve.loader import load_approved
        _cache.update(dir=settings.improve_dir, data=load_approved(settings.improve_dir))
    return _cache["data"]


def reset():
    _cache.update(dir=None, data=None)


def _toks(s):
    return {t for t in re.findall(r"[a-z0-9]+", fold(s)) if t not in STOP and len(t) > 1}


def faq_hits(text, k=2, min_overlap=0.5):
    a = approved()
    if not a:
        return []
    q = _toks(text)
    scored = []
    for it in a["items"]["faq"]:
        ref = _toks(it.get("question", "")) | _toks(it.get("topic", ""))
        if not ref or not q:
            continue
        ov = len(q & ref) / len(ref)
        if ov >= min_overlap and len(q & ref) >= 2:
            scored.append((ov, it))
    scored.sort(key=lambda x: -x[0])
    return [{"chunk_id": f"FAQ:{it['id']}", "text": it["answer"], "source": "improve"} for _, it in scored[:k]]


def playbooks(text):
    a = approved()
    if not a:
        return []
    f, out = fold(text), []
    for it in a["items"]["playbook"]:
        trig = it.get("trigger", "")
        if trig.startswith("re:"):
            try:
                hit = re.search(trig[3:], f)
            except re.error:
                hit = None
        else:
            need = _toks(trig)
            hit = need and need <= _toks(text)
        if hit:
            out.append(it)
    return out


def exemplars(goals, k=2):
    a = approved()
    if not a or not goals:
        return []
    g = set(goals)
    scored = sorted(((len(g & set(it.get("goals") or [])), it) for it in a["items"]["exemplar"]), key=lambda x: -x[0])
    return [it for n, it in scored[:k] if n]


def cue_patterns():
    a = approved()
    if not a:
        return []
    out = []
    for it in a["items"]["cue"]:
        try:
            out.append((it["id"], it["slot"], re.compile(it["pattern"])))
        except re.error:
            continue
    return out


def planner_rows():
    """D50/D52: dòng bảng planner đã duyệt (loại `planner_rule`) → origin=approved. Tắt hoặc chưa có loại này → []."""
    a = approved()
    if not a:
        return []
    return [{**{k: v for k, v in it.items() if k != "id"}, "id": f"IMP:{it['id']}", "origin": "approved"}
            for it in a["items"].get("planner_rule", [])]


def router_cues():
    """D52: cue router đã duyệt → [(id, kiểu 'intent'|'flag', tên, regex)]. Tắt → []."""
    a = approved()
    if not a:
        return []
    out = []
    for it in a["items"].get("router_cue", []):
        typ, _, name = str(it.get("target", "")).partition(":")
        try:
            out.append((it["id"], typ, name, re.compile(it["pattern"])))
        except re.error:
            continue
    return out


# cờ an toàn: cue đã duyệt được nâng cờ cả khi router là Jev (lưới an toàn); cờ khác và intent chỉ áp cho router rules
SAFETY_FLAGS = {"asks_internal_cost", "medical_question", "wants_data_deleted", "asks_if_bot"}


def apply_router_cues(text, out, backend):
    """Áp cue router đã duyệt lên kết quả router (tại chỗ). → danh sách id đã dùng."""
    cues = router_cues()
    if not cues:
        return []
    f, used = fold(text), []
    for pid, typ, name, rx in cues:
        if not rx.search(f):
            continue
        if typ == "flag" and (backend == "rules" or name in SAFETY_FLAGS):
            out.setdefault("flags", {})[name] = max(out["flags"].get(name, 0), 0.95); used.append(pid)
        elif typ == "intent" and backend == "rules" and (out.get("intent") == "greeting_or_other" or out.get("confidence", 0) < 0.8):
            out.update(intent=name, confidence=0.85); used.append(pid)
    return used


def product_aliases():
    """D52: cách đọc thương hiệu đã duyệt → [{brand, forms}] (tầng tra SP, khi PRODUCT_LEXICON=1). Tắt → []."""
    a = approved()
    if not a:
        return []
    return [{"brand": it["brand"], "forms": list(it.get("forms") or []), "id": it["id"]} for it in a["items"].get("product_alias", [])]


def apply_to_plan(plan, text, goals):
    """Gắn PLAYBOOK / EXEMPLARS vào plan của generator. → danh sách id đề xuất đã dùng (rỗng khi tắt)."""
    if not enabled():
        return []
    used = []
    pb = playbooks(text)
    if pb:
        plan["PLAYBOOK"] = [p["instruction"] for p in pb]
        used += [p["id"] for p in pb]
    ex = exemplars(goals)
    if ex:
        plan["EXEMPLARS"] = [{"khach": e["customer_text"], "nhan_vien": e["agent_text"]} for e in ex]
        used += [e["id"] for e in ex]
    return used


def stamp(used):
    a = approved()
    return {"approved_hash": a["hash"], "used": used} if a else None
