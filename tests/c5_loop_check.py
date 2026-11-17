"""Kiểm C.5 Knowledge Gap Loop (16/11, không mạng, không model): kiểm nguồn FAQ, bản nháp (LLM giả), hai nguồn feedback,
đóng gói + hash + test hồi quy tự sinh, kích hoạt / quay lui nguyên khối, ARCH=target chỉ nạp FAQ.

Chạy: python tests/c5_loop_check.py   (ghi vào thư mục tạm; chạy trên Kaggle CPU)"""
import json
import os
import sys
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
tmp = tempfile.mkdtemp(prefix="c5check_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "m.db").replace("\\", "/")
os.environ.setdefault("RUN_PROFILE", "local")
os.environ.setdefault("RAG_MODE", "bm25")
os.environ["TOOL_TRANSPORT"] = "direct"

import c5_loop as L  # noqa: E402
from core.config import check_arch, settings  # noqa: E402
from harness import improve_hook, knowledge, rag  # noqa: E402
from improve import store as S  # noqa: E402

FAILS = []


def ok(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


chunks = L.allowed_chunks()
ok(len(chunks) > 5 and all(not (c["restricted"] or c["superseded"] or c["noise"]) for c in chunks.values()), "chunk được phép: loại nội bộ / hết hiệu lực / nhiễu")
restricted = next(c for c in rag.CHUNKS if c["restricted"] or c["superseded"])


def pick_sentence():
    for c in chunks.values():
        for s in L.sentences(c["text"]):
            if 30 <= len(s) <= 200 and not S.validate({"kind": "faq", "payload": {"topic": "t", "question": "q", "answer": s}}):
                return c, s
    raise SystemExit("không tìm được câu policy hợp lệ")


ch, sent = pick_sentence()


def payload(answer=None, chunk=None, must=None):
    a = answer or sent
    return {"topic": "chủ đề thử", "question": "câu hỏi thử của khách về chính sách", "answer": a,
            "source": {"chunk_id": (chunk or ch)["chunk_id"], "doc": (chunk or ch)["doc"]},
            "test": {"customer_text": "câu hỏi thử của khách về chính sách", "must_say_any": must or [L.must_phrase(a)]},
            "gap": {"id": "Gx", "type": "no_info", "feedback_source": "auto_eval"}}


# ---------- 1. kiểm nguồn FAQ (code) ----------
ok(L.verify_faq(payload(), chunks) == [], f"FAQ nguyên văn đúng chunk: hợp lệ ({ch['chunk_id']})")
ok(any("nguyên văn" in e for e in L.verify_faq(payload(answer=sent + " Bên em luôn hỗ trợ tận tình."), chunks)),
   "câu thêm không có trong nguồn → bị chặn")
ok(any("không tồn tại" in e for e in L.verify_faq(payload(chunk=restricted), chunks)), "chunk nội bộ / hết hiệu lực → bị chặn")
ok(any("must_say_any" in e for e in L.verify_faq(payload(must=["cụm không có trong câu trả lời"]), chunks)), "test phải khớp câu trả lời")
ok(S.validate({"kind": "faq", "payload": payload(answer="Phí đổi lần hai là 30.000đ.")}) != [], "FAQ có số tiền → store.validate chặn")


# ---------- 2. bản nháp: LLM giả chỉ CHỌN ID ----------
class FakeLLM:
    def __init__(self, out):
        self.out = out

    def json(self, prompt, **kw):
        self.prompt = prompt
        return self.out


gap = {"id": "G1", "type": "no_info", "customer_text": "câu khách", "agent_text": "Dạ em chưa có thông tin ạ.", "feedback_source": "auto_eval"}
idx = L.sentences(ch["text"]).index(sent) + 1
pl, why = L.draft_one(FakeLLM({"decision": "faq", "chunk_id": ch["chunk_id"], "sentence_ids": [f"{ch['chunk_id']}#{idx}"],
                               "topic": "t", "question": "q"}), gap, [ch])
ok(pl is not None and pl["answer"] == sent and L.verify_faq(pl, chunks) == [], f"draft hợp lệ → payload có nguồn ({why})")
pl2, why2 = L.draft_one(FakeLLM({"decision": "faq", "chunk_id": ch["chunk_id"], "sentence_ids": ["X#9"], "topic": "t", "question": "q"}), gap, [ch])
ok(pl2 is None and "không hợp lệ" in why2, "ID câu lạ → không tạo FAQ")
pl3, why3 = L.draft_one(FakeLLM({"decision": "unanswered", "chunk_id": "", "sentence_ids": [], "topic": "", "question": ""}), gap, [ch])
ok(pl3 is None and "unanswered" in why3, "model không thấy nguồn → gap giữ unanswered")

# ---------- 3. nguồn feedback 2: like / dislike nhân viên ----------
fb = os.path.join(tmp, "fb.jsonl")
tr = os.path.join(tmp, "ui_trace.jsonl")
with open(tr, "w", encoding="utf-8") as fh:
    fh.write(json.dumps({"session_id": "ui:s:call_1", "turn": 2, "customer_text": "khách hỏi", "agent_text": "agent đáp", "goals": ["no_info"]}) + "\n")
with open(fb, "w", encoding="utf-8") as fh:
    fh.write(json.dumps({"msg_id": "ui:s:call_1:2", "rating": -1, "note": "thiếu", "by": "NV1"}) + "\n")
    fh.write(json.dumps({"msg_id": "ui:s:call_1:2", "rating": 1, "by": "NV2"}) + "\n")
    fh.write(json.dumps({"msg_id": "ui:s:call_9:1", "rating": -1, "by": "NV1"}) + "\n")
sg = L.staff_gaps(fb, [tr])
ok(len(sg) == 2 and sg[0]["customer_text"] == "khách hỏi" and sg[0]["feedback_source"] == "staff_feedback" and sg[1].get("unmatched"),
   f"dislike gắn đúng lượt trace UI; like không thành gap; không khớp → đánh dấu unmatched: {[g.get('customer_text') for g in sg]}")

# ---------- 4. đóng gói + test hồi quy + kích hoạt / quay lui ----------
rv = os.path.join(tmp, "review")
st, pid = S.propose({"kind": "faq", "payload": payload(), "source_gaps": ["Gx"]}, author="deepseek-draft", root=rv)
S.approve(pid, "Người duyệt", "đúng nguồn", root=rv)
pk = os.path.join(tmp, "pkg", "r1")
L.main(["package", "--root", rv, "--name", "r1", "--by", "Người duyệt", "--out", pk])
man = json.load(open(os.path.join(pk, "PACKAGE.json"), encoding="utf-8"))
ok(man["kind"] == "faq_only" and man["approved_hash"] == S.approved_hash(pk) and len(man["faq"]) == 1
   and man["faq"][0]["reviewed_by"] == "Người duyệt", "gói: chỉ FAQ đã duyệt, hash khớp approved/, có người duyệt")
reg = json.load(open(os.path.join(pk, "regression", f"C5-{pid}.json"), encoding="utf-8"))
ok(reg["calls"]["call_1"]["success_if"]["must_say_any"] == payload()["test"]["must_say_any"] and reg["_meta"]["split"] == "c5_regression",
   "test hồi quy tự sinh từ template, suite riêng")
try:
    L.main(["package", "--root", rv, "--name", "r1", "--by", "x", "--out", pk])
    ok(False, "gói đã tồn tại phải bị từ chối")
except SystemExit:
    ok(True, "gói không được ghi đè")
bad_rv = os.path.join(tmp, "review_bad")
st, bid = S.propose({"kind": "faq", "payload": payload(), "source_gaps": []}, root=bad_rv)
S.approve(bid, "X", root=bad_rv)
fp = os.path.join(bad_rv, "approved", f"{bid}.json")
pr = json.load(open(fp, encoding="utf-8"))
pr["payload"]["answer"] = sent + " Câu sửa tay không có nguồn."
json.dump(pr, open(fp, "w", encoding="utf-8"), ensure_ascii=False)
try:
    L.main(["package", "--root", bad_rv, "--name", "bad", "--by", "x", "--out", os.path.join(tmp, "pkg", "bad")])
    ok(False, "FAQ sửa tay mất nguồn phải chặn đóng gói")
except SystemExit:
    ok(True, "FAQ đã duyệt bị sửa tay mất nguồn → chặn đóng gói")

state = os.path.join(tmp, "state")
pk2 = os.path.join(tmp, "pkg", "r2")
st, pid2 = S.propose({"kind": "faq", "payload": {**payload(), "topic": "chủ đề hai"}, "source_gaps": []}, root=rv)
S.approve(pid2, "Người duyệt", root=rv)
L.main(["package", "--root", rv, "--name", "r2", "--by", "Người duyệt", "--out", pk2])
L.main(["activate", "--pkg", pk, "--by", "A", "--reason", "r1", "--state", state])
L.main(["activate", "--pkg", pk2, "--by", "A", "--reason", "r2", "--state", state])
ok(L.active(state)["package"] == os.path.abspath(pk2), "kích hoạt r2")
L.main(["rollback", "--by", "A", "--reason", "hại", "--state", state])
ok(L.active(state)["package"] == os.path.abspath(pk), "quay lui → r1 nguyên khối")
log = L.load_jsonl(os.path.join(state, "activation_log.jsonl"))
ok([x["event"] for x in log] == ["activate", "activate", "rollback"] and all(x["by"] for x in log), "nhật ký kích hoạt có người / lý do")
tamper = os.path.join(pk2, "approved", f"{pid2}.json")
pr = json.load(open(tamper, encoding="utf-8"))
pr["payload"]["topic"] = "sửa sau khi đóng gói"
json.dump(pr, open(tamper, "w", encoding="utf-8"), ensure_ascii=False)
try:
    L.main(["activate", "--pkg", pk2, "--by", "A", "--state", state])
    ok(False, "gói bị sửa sau đóng gói phải bị từ chối kích hoạt")
except SystemExit:
    ok(True, "gói bị sửa sau đóng gói (hash lệch) → từ chối kích hoạt")

# ---------- 5. ARCH=target: chỉ FAQ ----------
with patch.object(settings, "arch", "target"), patch.object(settings, "improve_dir", pk), \
        patch.object(settings, "requests_backend", ""), patch.object(settings, "understanding", ""), \
        patch.object(settings, "planner_selector", "rules"), patch.object(settings, "planner_variant", "b2_jev"):
    info = check_arch(settings)
    ok(info.get("improve") == {"dir": pk, "scope": "faq_only"}, f"check_arch target + gói FAQ: cho phép, ghi phạm vi: {info.get('improve')}")
    improve_hook.reset()
    ok(improve_hook.preflight() == man["approved_hash"], "preflight: gói FAQ hợp lệ")
    q = payload()["question"]
    hits = knowledge.search(q, k=2)
    ok(any(h.get("chunk_id") == f"FAQ:{pid}" for h in hits), f"FAQ được tra thấy qua knowledge.search: {[h.get('chunk_id') for h in hits]}")
    ok(improve_hook.playbooks(q) == [] and improve_hook.exemplars(["quote"]) == [], "target: không playbook / exemplar")
    st_ = improve_hook.faq_stamp([pid], [])
    ok(st_["retrieved"] == [pid] and st_["used"] == [] and st_["scope"] == "faq_only", "stamp tách retrieved / used")
    mixed = os.path.join(tmp, "mixed")
    s1, x1 = S.propose({"kind": "faq", "payload": payload()}, root=mixed)
    S.approve(x1, "X", root=mixed)
    s2, x2 = S.propose({"kind": "playbook", "payload": {"trigger": "chờ", "instruction": "ghi nhận, hẹn gọi lại"}}, root=mixed)
    S.approve(x2, "X", root=mixed)
    with patch.object(settings, "improve_dir", mixed):
        improve_hook.reset()
        try:
            improve_hook.preflight()
            ok(False, "gói có playbook phải bị từ chối khi ARCH=target")
        except improve_hook.ImproveScopeError:
            ok(True, "ARCH=target + gói có loại khác FAQ → từ chối mở phiên")
improve_hook.reset()

print("TẤT CẢ OK" if not FAILS else f"{len(FAILS)} LỖI: {FAILS}")
sys.exit(1 if FAILS else 0)
