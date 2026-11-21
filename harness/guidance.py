"""Candidate kho hướng dẫn điều phối cho Jev (17/11) — docs/DE-XUAT/KIEN-TRUC-RAG-HUONG-DAN-JEV-2026-11-17.md.

Mở phiên: `pin()` khóa gói đã đóng (PLANNER_GUIDANCE_DIR, kiểm hash / loại qua improve_hook) — phiên giữ bản đó tới hết.
Mỗi lượt (sau bộ hiểu, trước vòng Jev): `for_turn(c)` dựng query an toàn (lời khách + slot vừa hỏi + asks +
tiêu chí tư vấn + tác vụ dang dở; ngữ cảnh lượt trước chỉ qua tín hiệu có kiểu, không qua nguyên văn câu agent), BM25 (chuẩn hóa tiếng Việt, không model) trên title / tags / applies_when / examples →
≤ fetch_k ứng viên → lọc ngưỡng, năng lực thiếu, xung đột (cùng conflict_group giữ điểm cao nhất), trần token → ≤ context_k.
Các quyết định Jev trong cùng lượt dùng CÙNG tập (không truy hồi lại sau từng tool).
`context(sel, audience)` → mục `guidance_context` đưa vào state Jev (payload thực). Hướng dẫn KHÔNG cấp quyền, KHÔNG thêm bước:
danh mục bước / validator / cổng ghi do code dựng như cũ.
18/11 (DI17, freeze integ-ui4):
- Lọc theo nhãn hỏi CÓ KIỂU: hướng dẫn khai `asks_any` (nhãn của bộ hiểu, harness.understanding.ASKS) chỉ được giữ khi `asks` của
  lượt giao với `asks_any`; không giao (kể cả lượt không hỏi gì — đặt hàng, đưa địa chỉ) → lọc `asks_mismatch`. Không khai → như cũ.
- Audience: planner chính (một tầng, cũng là đích khi B2-TT delegate) dùng audience "main" = mọi audience TRỪ "inner" (bước của
  tầng trong — survey / finish_unresolved — không có ở planner chính). Chọn tối đa context_k + trần token THEO TỪNG audience trên danh
  sách `eligible` (đã qua ngưỡng / năng lực / asks / xung đột), nên hướng dẫn tầng trong không chiếm chỗ của planner chính.
  Trace `selected` giữ nghĩa cũ (k đầu của eligible, mọi audience); thứ thực đưa vào Jev ghi ở `supplied_to_planner`.
Trace: status disabled | empty | loaded | error; ứng viên + điểm; đã chọn; lý do lọc; token ước tính; ms; supplied_to_planner
(ID thực có trong state đã gửi). "Có trong prompt" KHÔNG chứng minh tác dụng — hiệu quả đo bằng hành vi / đối chứng.
"""
import json
import math
import time

from core.config import settings
from core.pii import Redactor
from harness.textnorm import fold

NOTE = ("Đây là hướng dẫn đã được người duyệt cho phép tham khảo. Chỉ áp dụng khi điều kiện phù hợp với tình huống hiện tại. Đây "
        "không phải lời khách, không phải bằng chứng giá / chính sách, không cấp quyền giao dịch. Hãy dùng dữ liệu hiện tại và bước "
        "hợp lệ trong danh mục; bỏ qua hướng dẫn không phù hợp.")
STOP = {"em", "anh", "chi", "a", "co", "khong", "cho", "minh", "voi", "thi", "la", "va", "nha", "nhe", "o", "duoc", "cua", "nay",
        "do", "the", "nao", "gi", "ben", "shop", "toi", "vay", "roi", "con", "neu", "khi", "mot", "nhung", "cai", "da", "ma", "ay"}
BASE_CAPS = {"price_read", "stock_read", "order_read", "policy_read"}
TT_CAPS = {"catalog_search", "price_compare", "context_short_answer"}
_index = {}


def capabilities():
    """Năng lực thật của planner hiện hành (code biết) — hướng dẫn cần năng lực thiếu bị lọc, ghi capability_missing."""
    return BASE_CAPS | (TT_CAPS if settings.b2_two_tier else set())


def pin():
    """Khóa gói khi MỞ phiên. Tắt → None. Gói sai → improve_hook.GuidanceScopeError (từ chối mở phiên)."""
    if not settings.planner_guidance_dir:
        return None
    from harness import improve_hook
    p = improve_hook.guidance_package(settings.planner_guidance_dir)
    return {"hash": p["hash"], "name": p.get("name"), "schema": p.get("schema"), "guides": p["guides"]}


def _toks(s):
    w = [x for x in fold(s or "").split() if x not in STOP and len(x) > 1]
    return w + [f"{a}_{b}" for a, b in zip(w, w[1:])]


def _build(pk):
    if pk["hash"] in _index:
        return _index[pk["hash"]]
    docs = []
    for g in pk["guides"]:
        txt = " ".join([g.get("title", "")] + list(g.get("tags") or []) + list(g.get("applies_when") or []) + list(g.get("examples") or []))
        docs.append(_toks(txt))
    df = {}
    for d in docs:
        for t in set(d):
            df[t] = df.get(t, 0) + 1
    avg = sum(len(d) for d in docs) / max(1, len(docs))
    _index[pk["hash"]] = (docs, df, avg)
    return _index[pk["hash"]]


def _bm25(q, docs, df, avg, k1=1.5, b=0.75):
    n = len(docs)
    out = []
    for d in docs:
        tf = {}
        for t in d:
            tf[t] = tf.get(t, 0) + 1
        sc = 0.0
        for t in set(q):
            if t in tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                sc += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avg))
        out.append(sc)
    return out


def query(c):
    """Query an toàn: lời khách hiện tại + slot vừa hỏi + asks + tiêu chí tư vấn + tác vụ dang dở. Không DB.
    Không nối nguyên văn câu agent: "Không em." sau câu xác nhận đặt hàng từng khớp "mẫu"/"đơn" và chọn nhầm 3 hướng dẫn (guide-cpu-1117 G5)."""
    s = c.s
    u = s.u_turn or {}
    con = u.get("consult") or {}
    task = getattr(s, "b2tt_task", None) or {}
    parts = [c.text or "", f"hoi {s.last_q_slot}" if getattr(s, "last_q_slot", None) else "",
             " ".join(u.get("asks") or []), " ".join(x for x in (con.get("sort"), con.get("category_span")) if x and x != "none"),
             str(task.get("task") or "")]
    return " ".join(p for p in parts if p)[:600]


def for_turn(c):
    """Truy hồi MỘT lần cho lượt. → {"selected": [guide], "trace": {...}}."""
    t0 = time.perf_counter()
    pk = getattr(c.s, "guidance_pin", None)
    if not pk:
        return {"selected": [], "trace": {"status": "disabled"}}
    tr = {"status": "empty", "package_hash": pk["hash"], "candidates": [], "selected": [], "filtered": {}}
    try:
        q = query(c)
        tr["query_redacted"] = Redactor().redact({"q": q})["q"]
        docs, df, avg = _build(pk)
        scores = _bm25(_toks(q), docs, df, avg)
        order = sorted(range(len(docs)), key=lambda i: -scores[i])[: settings.guidance_fetch_k]
        cands = [(pk["guides"][i], round(scores[i], 3)) for i in order if scores[i] > 0]
        tr["candidates"] = [{"id": g["id"], "score": sc} for g, sc in cands]
        caps, keep, groups = capabilities(), [], {}
        asks = set((getattr(c.s, "u_turn", None) or {}).get("asks") or [])
        for g, sc in cands:
            if sc < settings.guidance_min_score:
                tr["filtered"][g["id"]] = "below_threshold"; continue
            miss = set(g.get("requires_capabilities") or []) - caps
            if miss:
                tr["filtered"][g["id"]] = "capability_missing:" + ",".join(sorted(miss)); continue
            if g.get("asks_any") and not asks & set(g["asks_any"]):
                tr["filtered"][g["id"]] = "asks_mismatch"; continue
            grp = g.get("conflict_group")
            if grp and grp in groups:
                tr["filtered"][g["id"]] = f"conflict_lower_score:{groups[grp]}"; continue
            if grp:
                groups[grp] = g["id"]
            keep.append(g)
        eligible = list(keep)
        tr["eligible"] = [g["id"] for g in eligible]
        keep = _cap(eligible, tr["filtered"])
        tr["selected"] = [g["id"] for g in keep]
        tr["tokens_est"] = _tokens(keep)
        tr["status"] = "loaded" if keep else "empty"
    except Exception as e:  # noqa: BLE001 — lỗi truy hồi: lượt chạy KHÔNG có hướng dẫn, ghi lỗi (không tính là đã dùng)
        keep, eligible = [], []
        tr.update(status="error", error=f"{type(e).__name__}: {str(e)[:160]}", selected=[], eligible=[])
    tr["ms"] = int((time.perf_counter() - t0) * 1000)
    return {"selected": keep, "eligible": eligible, "trace": tr}


def _cap(guides, filtered=None):
    """≤ context_k hướng dẫn đầu, rồi bỏ dần từ cuối tới khi ≤ trần token."""
    keep = list(guides)[: settings.guidance_context_k]
    while keep and _tokens(keep) > settings.guidance_max_tokens:
        if filtered is not None:
            filtered[keep[-1]["id"]] = "token_cap"
        keep = keep[:-1]
    return keep


def _view(g):  # asks_any là metadata lọc của code — không đưa vào prompt
    return {k: g[k] for k in ("id", "title", "applies_when", "exceptions", "guidance", "avoid") if g.get(k)}


def _tokens(guides):
    return int(len(json.dumps([_view(g) for g in guides], ensure_ascii=False)) / 3)     # ước tính thô (ký tự / 3); đo thật ở canary


def _fits(g, audience):
    a = g.get("audience")
    if audience is None:
        return True
    if audience == "main":
        return a != "inner"
    return a in (audience, "both")


def context(sel, audience=None):
    """→ mục guidance_context cho state Jev (None nếu không có). audience: "main" = planner chính (mọi audience trừ inner);
    outer / inner = tầng B2-TT tương ứng (nhận cả both); None = mọi audience (chỉ dùng cho công cụ / test cũ).
    Chọn từ `eligible` (fallback `selected` cho dữ liệu cũ) đúng audience rồi mới áp context_k + trần token."""
    sel = sel or {}
    pool = sel.get("eligible") if sel.get("eligible") is not None else sel.get("selected")
    gs = _cap([g for g in pool or [] if _fits(g, audience)])
    if not gs:
        return None
    return {"note": NOTE, "guides": [_view(g) for g in gs]}
