"""Kiểm UI nối B2-v51-A (16/11, FORCED-LABEL, không API): profile nạp đúng config snapshot + kiểm khởi động, câu hiện = câu
phát qua on_emit, event_id chống gọi lại khi Streamlit rerun, Full / Baseline namespace riêng, feedback nhân viên + trace UI
(nguồn feedback 2 của C.5), gói FAQ chỉ nạp khi MỞ phiên, không đổi giữa phiên, quay lui, gói sai phạm vi bị từ chối.

Chạy: python tests/ui_b2_check.py   (Kaggle CPU; cần runs/snapshots/20261116-b2-v51A/config.json)"""
import json
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
tmp = tempfile.mkdtemp(prefix="uib2_")
os.environ["UI_PROFILE"] = "b2_v51a"
os.environ["UI_QWEN"] = "off"                                # không có vLLM trên CPU: nhãn "khác cấu hình đo"
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "ui.db").replace("\\", "/")
os.environ["LLM_CACHE"] = "off"

from ui import engine as E  # noqa: E402  (đặt env profile TRƯỚC core)

FAILS = []


def ok(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


# ---------- 1. khởi động: settings khớp config snapshot ----------
info = E.startup_check()
ok(info["ok"] and info["arch"] == "target" and info["planner_variant"] == "b2_jev", f"startup_check B2: {info}")
ok("khác cấu hình đo" in info["label"], "UI_QWEN=off phải ghi nhãn khác cấu hình đo")
ok(set(info["keys_present"]) == {"DEEPSEEK_API_KEY", "TYPESAFE_API_KEY"} and all(isinstance(v, bool) for v in info["keys_present"].values()),
   "chỉ báo có / không key, không giá trị")
os.environ["PLANNER_B2_MAX_DECISIONS"] = "99"
bad = E.startup_check()
ok(not bad["ok"] and any("PLANNER_B2_MAX_DECISIONS" in m for m in bad["mismatch"]), "env lệch snapshot → từ chối")
os.environ["PLANNER_B2_MAX_DECISIONS"] = E.PROFILE_INFO["config_env"]["PLANNER_B2_MAX_DECISIONS"]

_fpath = os.path.join(ROOT, "tests", "b2_round_f_check.py")
F = types.ModuleType("b2_round_f_frame")
F.__file__ = _fpath
exec(compile(open(_fpath, encoding="utf-8").read().split("# ================================================================== H8")[0], _fpath, "exec"),
     F.__dict__)
import c5_loop as L  # noqa: E402
from core.config import settings  # noqa: E402
from harness import improve_hook  # noqa: E402
from improve import store as S  # noqa: E402

E.FEEDBACK = os.path.join(tmp, "feedback.jsonl")
E.TRACES = os.path.join(tmp, "traces")
E.C5_STATE = os.path.join(tmp, "c5state")
Q = "Máy lọc không khí AirPure Y giá bao nhiêu em?"

with F.Ctx({"improve_dir": ""}):
    ok(E.Engine("x", "full").ns != E.Engine("x", "baseline_no_memory").ns, "Full / Baseline: namespace riêng")
    eng = E.Engine("uib2")
    eng.reset()
    eng.start_call("0911555666", "hotline", "2026-10-15")
    F.QUEUE[:] = [F.PRICE_Q]
    r1 = eng.say(Q, event_id="e1")
    n_turn, n_emit = eng.sess.turn_no, len(eng.emitted)
    F.QUEUE[:] = [F.PRICE_Q]
    r1b = eng.say(Q, event_id="e1")                         # Streamlit rerun cùng event
    ok(r1b is r1 and eng.sess.turn_no == n_turn and len(eng.emitted) == n_emit and len(eng.calls[-1]["turns"]) == 1,
       "rerun cùng event_id: không gọi agent / tool lần hai")
    ok(r1["ui"]["n_emit"] == 1 and r1["ui"]["emitted_text"] == r1["agent_text"] and r1["ui"]["emitted_text"],
       f"câu hiện = câu phát qua on_emit: {r1['ui']}")
    ok(r1["ui"]["turn"] == 1 and r1["ui"]["msg_id"] == f"{eng.calls[-1]['session_id']}:1", f"msg_id theo session:turn: {r1['ui']['msg_id']}")
    F.QUEUE[:] = [F.PRICE_Q]
    r1c = eng.say("Thế còn AirPure X thì giá sao em?", event_id="e1c")
    ok(r1c["ui"]["turn"] == 2 and r1c["ui"]["msg_id"] != r1["ui"]["msg_id"], "hai lượt trong cùng cuộc gọi có msg_id khác nhau")
    fb = eng.feedback(r1, -1, "chưa nói đủ", "NV1")
    ok(fb["msg_id"] == r1["ui"]["msg_id"] and fb["rating"] == -1 and fb["by"] == "NV1", "feedback ghi theo message")
    tfile = os.path.join(E.TRACES, f"{eng.ns.replace(':', '_')}.jsonl")
    sg = L.staff_gaps(E.FEEDBACK, [tfile])
    ok(len(sg) == 1 and sg[0]["customer_text"] == Q and not sg[0].get("unmatched"), "collector gắn dislike với đúng lượt trace UI")
    try:
        eng.feedback(r1, 0)
        ok(False, "rating ngoài ±1 phải bị từ chối")
    except ValueError:
        ok(True, "rating ngoài ±1 bị từ chối")

    # ---------- 2. gói FAQ: nạp khi mở phiên, không đổi giữa phiên ----------
    chunks = L.allowed_chunks()
    ch, sent = next((c, s) for c in chunks.values() for s in L.sentences(c["text"])
                    if 30 <= len(s) <= 200 and not S.validate({"kind": "faq", "payload": {"topic": "t", "question": "q", "answer": s}}))
    rv = os.path.join(tmp, "review")
    st, pid = S.propose({"kind": "faq", "payload": {"topic": "chủ đề thử", "question": "câu hỏi thử của khách về chính sách",
                                                    "answer": sent, "source": {"chunk_id": ch["chunk_id"], "doc": ch["doc"]},
                                                    "test": {"customer_text": "câu hỏi thử", "must_say_any": [L.must_phrase(sent)]}}},
                        root=rv)
    S.approve(pid, "Người duyệt", root=rv)
    pk = os.path.join(tmp, "pkg", "r1")
    L.main(["package", "--root", rv, "--name", "r1", "--by", "Người duyệt", "--out", pk])
    L.main(["activate", "--pkg", pk, "--by", "Người duyệt", "--reason", "thử", "--state", E.C5_STATE])
    ok(settings.improve_dir == "", "kích hoạt KHÔNG đổi phiên đang mở")
    try:
        eng._load_package()
        ok(False, "đổi gói giữa phiên phải bị từ chối")
    except RuntimeError:
        ok(True, "đổi gói giữa phiên bị từ chối")
    eng.end_call()
    eng.start_call("0911555666", "hotline", "2026-10-16")
    h = S.approved_hash(pk)
    ok(settings.improve_dir == os.path.abspath(pk) and eng.calls[-1]["package_hash"] == h, "phiên mới nạp gói đang kích hoạt")
    F.QUEUE[:] = [F.PRICE_Q]
    r2 = eng.say(Q, event_id="e2")
    imp = r2.get("improve") or {}
    ok(imp.get("approved_hash") == h and imp.get("scope") == "faq_only" and "used" in imp and "retrieved" in imp,
       f"trace có approved_hash + retrieved / used: {imp}")
    ok(r2["ui"]["package_hash"] == h, "feedback / trace UI ghi hash gói")
    eng.end_call()
    L.main(["rollback", "--by", "Người duyệt", "--reason", "thử quay lui", "--state", E.C5_STATE])
    eng.start_call("0911555666", "hotline", "2026-10-17")
    ok(settings.improve_dir == "" and eng.calls[-1]["package_hash"] is None, "quay lui: phiên mới không nạp gói")
    eng.end_call()

    # ---------- 3. gói sai phạm vi bị từ chối khi mở phiên ----------
    mixed = os.path.join(tmp, "mixed")
    s2, x2 = S.propose({"kind": "playbook", "payload": {"trigger": "chờ", "instruction": "ghi nhận, hẹn gọi lại"}}, root=mixed)
    S.approve(x2, "X", root=mixed)
    with open(os.path.join(E.C5_STATE, "active.json"), "w", encoding="utf-8") as fh:
        json.dump({"package": mixed, "approved_hash": S.approved_hash(mixed)}, fh)
    try:
        eng.start_call("0911555666", "hotline", "2026-10-18")
        ok(False, "gói có playbook phải bị từ chối khi mở phiên B2")
    except improve_hook.ImproveScopeError:
        ok(True, "gói sai phạm vi → từ chối mở phiên")
    ok(eng.sess is None, "mở phiên lỗi không để lại phiên dở dang")
improve_hook.reset()

print("TẤT CẢ OK" if not FAILS else f"{len(FAILS)} LỖI: {FAILS}")
sys.exit(1 if FAILS else 0)
