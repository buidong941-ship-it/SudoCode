"""C.5 Knowledge Gap Loop (16/11) — nối improve/ (kho đề xuất, duyệt, vòng) với nguồn policy và DeepSeek.

improve/ không được import core/harness (tests/improve_check.py), nên phần cần cả hai phía nằm ở đây.

    python scripts/c5_loop.py gaps     --root R --trace T.jsonl --report report.json [--feedback F.jsonl --ui-trace U.jsonl ...]
    python scripts/c5_loop.py draft    --root R [--limit 20] [--types no_info,staff_dislike]      # cần DEEPSEEK_API_KEY
    python scripts/c5_loop.py package  --root R --name r1 --by "Tên" --out runs/c5/packages/r1
    python scripts/c5_loop.py activate --pkg runs/c5/packages/r1 --by "Tên" --reason "..."  [--state data/c5]
    python scripts/c5_loop.py rollback --by "Tên" --reason "..." [--state data/c5]
    python scripts/c5_loop.py status   [--state data/c5]

Luật (bản giao 16/11):
- HAI nguồn feedback độc lập: điểm chấm tự động (trace + report của eval/reference_eval.py, CHỈ bộ dev) và like/dislike của
  nhân viên trên từng câu trả lời ở UI (data/ui/feedback.jsonl + trace UI). Gap ghi `feedback_source` = auto_eval | staff_feedback.
- DeepSeek chỉ soạn BẢN NHÁP vào pending/ (không activate, không ghi approved/). FAQ phải có nguồn: câu trả lời gồm các câu
  CHÉP NGUYÊN VĂN từ đúng MỘT chunk policy được trích (không nội bộ / hết hiệu lực / nhiễu); code kiểm lại từng câu. Không có
  nguồn phù hợp → gap giữ unanswered (ghi lý do), không bịa chính sách.
- Test hồi quy đi kèm được CODE dựng từ template (kịch bản một cuộc gọi, must_say_any = cụm nguyên văn của câu trả lời đã
  duyệt); không chạy code do model sinh.
- package: chỉ FAQ đã duyệt → thư mục gói (approved/ + PACKAGE.json có hash + regression/ suite riêng). Gói là root của store
  nên IMPROVE_DIR=<gói> nạp được qua improve.loader; ARCH=target từ chối gói có loại khác FAQ (harness/improve_hook).
- activate / rollback đổi con trỏ gói NGUYÊN KHỐI (data/c5/active.json) + nhật ký; runtime đọc con trỏ khi MỞ phiên / run mới.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import sys
import unicodedata
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from improve import collect as C  # noqa: E402
from improve import store as S  # noqa: E402

DRAFT_TYPES = ("no_info", "staff_dislike", "task_fail")
STATE_DIR = os.path.join(ROOT, "data", "c5")


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def fold(s):
    s = unicodedata.normalize("NFD", str(s or "")).replace("đ", "d").replace("Đ", "D")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w%]+", " ", s)).strip()


SENT_RX = re.compile(r"(?<=[.!?;])\s+|\n+")


def sentences(text):
    out = []
    for s in SENT_RX.split(text or ""):
        s = re.sub(r"\*\*|__|^#+\s*", "", s).strip(" -•*\t>")
        if len(s) >= 12:
            out.append(s)
    return out


# ------------------------------------------------------------------ nguồn 2: feedback nhân viên (UI)

def load_jsonl(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def staff_gaps(feedback_path, ui_traces):
    """dislike của nhân viên trên MỘT câu trả lời (msg_id = session_id:turn) → gap staff_dislike gắn đúng lượt trace UI."""
    rows = {}
    for p in ui_traces or []:
        for r in load_jsonl(p):
            rows[f"{r.get('session_id') or r.get('run_id')}:{r.get('turn')}"] = r
    gaps = []
    for fb in load_jsonl(feedback_path):
        if fb.get("rating") != -1:
            continue
        r = rows.get(fb.get("msg_id"))
        if r is None:
            gaps.append({"id": C.gap_id("staff", fb.get("msg_id")), "type": "staff_dislike", "feedback_source": "staff_feedback",
                         "unmatched": True, "feedback": fb})
            continue
        gaps.append({"id": C.gap_id("staff", fb["msg_id"]), "type": "staff_dislike", "subtype": "dislike", "feedback_source": "staff_feedback",
                     "scenario": r.get("scenario_id") or fb.get("ns"), "call": r.get("call"), "turn": r.get("turn"),
                     "customer_text": r.get("customer_text"), "agent_text": r.get("agent_text"), "goals": r.get("goals"),
                     "detail": {"note": fb.get("note"), "by": fb.get("by"), "at": fb.get("at"), "msg_id": fb["msg_id"],
                                "package_hash": fb.get("package_hash")}})
    return gaps


def cmd_gaps(a):
    gaps = []
    if a.trace:
        for g in C.collect(a.trace, a.report):                  # collect tự từ chối đường dẫn holdout / out_nat/test
            g["feedback_source"] = "auto_eval"
            gaps.append(g)
    gaps += staff_gaps(a.feedback, a.ui_trace)
    seen, out = set(), []
    for g in gaps:                                          # dedupe có nguồn: cùng id → giữ bản đầu, ghi thêm nguồn
        if g["id"] in seen:
            continue
        seen.add(g["id"])
        out.append(g)
    p = S.paths(a.root)
    os.makedirs(p["root"], exist_ok=True)
    C.write(out, p["gaps"], append=a.append)
    by = {}
    for g in out:
        by[(g.get("feedback_source"), g["type"])] = by.get((g.get("feedback_source"), g["type"]), 0) + 1
    print(json.dumps({"gaps": len(out), "by_source_type": {f"{k[0]}:{k[1]}": v for k, v in sorted(by.items())}}, ensure_ascii=False))


# ------------------------------------------------------------------ kiểm nguồn FAQ (code, không model)

def allowed_chunks():
    from harness import rag
    return {c["chunk_id"]: c for c in rag.CHUNKS if not (c["restricted"] or c["superseded"] or c["noise"])}


def verify_faq(payload, chunks=None):
    """→ danh sách lỗi. Câu trả lời = các câu NGUYÊN VĂN của đúng chunk nguồn; test do code dựng phải khớp câu trả lời."""
    chunks = chunks if chunks is not None else allowed_chunks()
    errs = []
    src = payload.get("source") or {}
    ch = chunks.get(src.get("chunk_id"))
    if ch is None:
        return [f"nguồn {src.get('chunk_id')!r} không tồn tại hoặc thuộc tài liệu nội bộ / hết hiệu lực / nhiễu"]
    if src.get("doc") and src["doc"] != ch["doc"]:
        errs.append(f"source.doc {src['doc']!r} ≠ tài liệu của chunk {ch['doc']!r}")
    body = fold(ch["text"])
    sents = sentences(payload.get("answer") or "")
    if not sents:
        errs.append("answer rỗng")
    for s in sents:
        if fold(s) not in body:
            errs.append(f"câu không có nguyên văn trong {ch['chunk_id']}: {s[:80]!r}")
    t = payload.get("test") or {}
    if not str(t.get("customer_text") or "").strip():
        errs.append("test.customer_text trống")
    must = t.get("must_say_any") or []
    if not must or not all(fold(m) in fold(payload.get("answer")) for m in must):
        errs.append("test.must_say_any phải là cụm nguyên văn của answer")
    return errs


def must_phrase(answer, n=8):
    """Cụm kiểm cho test: n từ đầu của câu đầu (renderer đọc câu policy nguyên văn)."""
    first = (sentences(answer) or [answer])[0]
    return " ".join(first.split()[:n])


# ------------------------------------------------------------------ DeepSeek soạn nháp

DRAFT_SCHEMA = {"type": "object", "required": ["decision", "chunk_id", "sentence_ids", "topic", "question"],
                "properties": {"decision": {"type": "string", "enum": ["faq", "unanswered"]},
                               "chunk_id": {"type": "string"}, "sentence_ids": {"type": "array", "items": {"type": "string"}},
                               "topic": {"type": "string"}, "question": {"type": "string"}, "why": {"type": "string"}}}


def draft_one(llm, gap, cands):
    """DeepSeek CHỌN chunk + câu (theo ID) và đặt topic / question theo cách khách hỏi; KHÔNG viết câu trả lời. → payload | (None, lý do)."""
    menu, ids = [], {}
    for c in cands:
        for i, s in enumerate(sentences(c["text"])):
            sid = f"{c['chunk_id']}#{i + 1}"
            ids[sid] = (c, s)
            menu.append(f"[{sid}] {s}")
    if not menu:
        return None, "không có chunk policy phù hợp"
    prompt = ("Bạn soạn BẢN NHÁP FAQ cho tổng đài bán hàng. Câu khách mà agent chưa trả lời được:\n"
              f"KHÁCH: {gap.get('customer_text')}\nAGENT ĐÃ NÓI: {gap.get('agent_text')}\n\n"
              "Các câu chính sách được phép dùng (chỉ chọn theo ID, không viết lại):\n" + "\n".join(menu[:40]) +
              "\n\nNếu các câu trên trả lời ĐÚNG điều khách hỏi: decision=faq, chunk_id = chunk chứa các câu, sentence_ids = 1-3 ID "
              "câu cùng chunk đó, topic = chủ đề ngắn, question = câu hỏi chuẩn hóa theo cách khách nói. Nếu không câu nào trả lời "
              "đúng: decision=unanswered (không đoán, không bịa chính sách).")
    d = llm.json(prompt, max_tokens=300, schema=DRAFT_SCHEMA, cache=False)
    if not isinstance(d, dict) or d.get("decision") != "faq":
        return None, f"model: unanswered ({(d or {}).get('why') if isinstance(d, dict) else d})"
    picked = [ids[s] for s in d.get("sentence_ids") or [] if s in ids]
    if not picked or len({c["chunk_id"] for c, _ in picked}) != 1 or picked[0][0]["chunk_id"] != d.get("chunk_id"):
        return None, f"model chọn câu không hợp lệ {d.get('sentence_ids')} / chunk {d.get('chunk_id')}"
    ch = picked[0][0]
    answer = " ".join(s for _, s in picked)
    payload = {"topic": d["topic"].strip(), "question": d["question"].strip(), "answer": answer,
               "source": {"chunk_id": ch["chunk_id"], "doc": ch["doc"], "title": ch.get("title")},
               "test": {"customer_text": gap.get("customer_text"), "must_say_any": [must_phrase(answer)]},
               "gap": {"id": gap["id"], "type": gap["type"], "feedback_source": gap.get("feedback_source")}}
    return payload, None


def cmd_draft(a):
    from core.llm.deepseek import DeepSeek
    from harness import rag
    llm = DeepSeek()
    chunks = allowed_chunks()
    p = S.paths(a.root)
    gaps = [g for g in C.load(p["gaps"]) if g["type"] in a.types.split(",") and g.get("customer_text")][: a.limit]
    res = {"drafted": [], "unanswered": [], "invalid": []}
    for g in gaps:
        cands = [h for h in rag.search(g["customer_text"], k=4) if h.get("chunk_id") in chunks]
        cands = [chunks[h["chunk_id"]] for h in cands]
        payload, why = draft_one(llm, g, cands)
        if payload is None:
            res["unanswered"].append({"gap": g["id"], "why": why})
            continue
        errs = verify_faq(payload, chunks)
        prop = {"kind": "faq", "payload": payload, "source_gaps": [g["id"]], "author": "deepseek-draft"}
        errs += S.validate(prop)
        if errs:
            res["invalid"].append({"gap": g["id"], "errors": errs[:4]})
            continue
        state, pid = S.propose(prop, author="deepseek-draft", root=a.root)
        res["drafted"].append({"gap": g["id"], "id": pid, "state": state, "chunk": payload["source"]["chunk_id"]})
    S.log("c5_draft", a.root, **{k: len(v) for k, v in res.items()})
    with open(os.path.join(p["root"], "draft_result.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    print(json.dumps({k: len(v) for k, v in res.items()}, ensure_ascii=False))


# ------------------------------------------------------------------ đóng gói + test hồi quy tự sinh

def regression_scenario(prop):
    pl = prop["payload"]
    sid = f"C5-{prop['id']}"
    return {"scenario_id": sid, "level": "M1", "persona": "c5_regression", "hard_case": "knowledge_gap",
            "customer_phone": "0900000501", "customer_name": None, "honorific": "anh/chị",
            "notes": f"Tự sinh từ FAQ {prop['id']} (nguồn {pl['source']['chunk_id']}, gap {pl.get('gap', {}).get('id')}). Suite hồi quy "
                     "riêng của C.5 — KHÔNG thuộc bộ evaluation cố định R0/R1, không là holdout độc lập.",
            "calls": {"call_1": {"call_date": "2026-10-15", "customer_goal": "hoi_chinh_sach",
                                 "customer_turns": [pl["test"]["customer_text"]],
                                 "success_if": {"must_say_any": list(pl["test"]["must_say_any"])}}},
            "_meta": {"split": "c5_regression", "faq_id": prop["id"], "source_chunk": pl["source"]["chunk_id"]}}


def cmd_package(a):
    out = os.path.abspath(a.out)
    if os.path.exists(out):
        sys.exit(f"gói {out} đã tồn tại — gói không được sửa sau khi tạo; dùng tên mới")
    chunks = allowed_chunks()
    faqs, bad = [], []
    for prop in S.list_state("approved", a.root):
        if prop["kind"] != "faq":
            continue
        errs = verify_faq(prop["payload"], chunks) + S.validate(prop)
        (bad if errs else faqs).append((prop, errs))
    if bad:
        sys.exit("FAQ đã duyệt không qua kiểm nguồn: " + json.dumps([(p["id"], e[:2]) for p, e in bad], ensure_ascii=False))
    os.makedirs(os.path.join(out, "approved"))
    os.makedirs(os.path.join(out, "regression"))
    for prop, _ in faqs:
        with open(os.path.join(out, "approved", f"{prop['id']}.json"), "w", encoding="utf-8") as fh:
            json.dump(prop, fh, ensure_ascii=False, indent=1)
        with open(os.path.join(out, "regression", f"C5-{prop['id']}.json"), "w", encoding="utf-8") as fh:
            json.dump(regression_scenario(prop), fh, ensure_ascii=False, indent=1)
    reg = sorted(glob.glob(os.path.join(out, "regression", "*.json")))
    man = {"name": a.name, "created_at": now(), "by": a.by, "kind": "faq_only", "approved_hash": S.approved_hash(out),
           "faq": [{"id": p["id"], "topic": p["payload"]["topic"], "source": p["payload"]["source"], "reviewed_by": (p.get("review") or {}).get("by"),
                    "gap": p["payload"].get("gap")} for p, _ in faqs],
           "regression_suite": {"n": len(reg), "sha256": hashlib.sha256(b"".join(open(f, "rb").read() for f in reg)).hexdigest()[:16],
                                "note": "suite hồi quy riêng của C.5, không trộn vào evaluation R0/R1"},
           "review_root": os.path.relpath(os.path.abspath(a.root), ROOT)}
    with open(os.path.join(out, "PACKAGE.json"), "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=1)
    S.log("c5_package", a.root, name=a.name, out=os.path.relpath(out, ROOT), approved_hash=man["approved_hash"], n=len(faqs))
    print(json.dumps({"package": os.path.relpath(out, ROOT), "faq": len(faqs), "approved_hash": man["approved_hash"],
                      "regression": len(reg)}, ensure_ascii=False))


# ------------------------------------------------------------------ kích hoạt / quay lui NGUYÊN KHỐI

def _state(a):
    d = os.path.abspath(a.state)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "active.json"), os.path.join(d, "activation_log.jsonl")


def active(state_dir=STATE_DIR):
    p = os.path.join(state_dir, "active.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"package": "", "approved_hash": None}


def _set(a, pkg, event):
    cur_p, log_p = _state(a)
    prev = active(os.path.dirname(cur_p))
    rec = {"package": pkg, "approved_hash": S.approved_hash(pkg) if pkg else None, "at": now(), "by": a.by, "reason": a.reason,
           "event": event, "previous": prev.get("package")}
    with open(cur_p, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=1)
    with open(log_p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(rec, ensure_ascii=False))


def cmd_activate(a):
    pkg = os.path.abspath(a.pkg)
    man = json.load(open(os.path.join(pkg, "PACKAGE.json"), encoding="utf-8"))
    if man.get("kind") != "faq_only" or S.approved_hash(pkg) != man["approved_hash"]:
        sys.exit("gói không phải faq_only hoặc hash approved/ đã đổi so với PACKAGE.json — không kích hoạt")
    _set(a, pkg, "activate")


def cmd_rollback(a):
    _, log_p = _state(a)
    hist = load_jsonl(log_p)
    cur = hist[-1]["package"] if hist else ""
    prev = next((h["package"] for h in reversed(hist[:-1]) if h["package"] != cur), "") if hist else ""
    _set(a, prev, "rollback")


def cmd_status(a):
    cur_p, log_p = _state(a)
    print(json.dumps({"active": active(os.path.dirname(cur_p)), "history": load_jsonl(log_p)[-5:]}, ensure_ascii=False, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("gaps"); p.add_argument("--root", required=True); p.add_argument("--trace"); p.add_argument("--report")
    p.add_argument("--feedback"); p.add_argument("--ui-trace", nargs="*", default=[]); p.add_argument("--append", action="store_true")
    p = sub.add_parser("draft"); p.add_argument("--root", required=True); p.add_argument("--limit", type=int, default=20)
    p.add_argument("--types", default=",".join(DRAFT_TYPES))
    p = sub.add_parser("package"); p.add_argument("--root", required=True); p.add_argument("--name", required=True)
    p.add_argument("--by", required=True); p.add_argument("--out", required=True)
    for name in ("activate", "rollback", "status"):
        p = sub.add_parser(name); p.add_argument("--state", default=STATE_DIR)
        if name != "status":
            p.add_argument("--by", required=True); p.add_argument("--reason", default="")
        if name == "activate":
            p.add_argument("--pkg", required=True)
    a = ap.parse_args(argv)
    {"gaps": cmd_gaps, "draft": cmd_draft, "package": cmd_package, "activate": cmd_activate, "rollback": cmd_rollback,
     "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    main()
