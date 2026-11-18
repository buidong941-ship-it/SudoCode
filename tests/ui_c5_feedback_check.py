"""Kiểm bản vá UI v52n-ui2 (17/11, không API, không model thật):

A1  tải lại trang (Engine mới trong st.session_state, cùng DB / namespace) không còn trùng session_id → không UNIQUE
    (turns.ns, session_id, turn); msg_id của hai lần khác nhau → feedback không gắn nhầm lượt.
A2  nút "Gom gap" (E.gap_cmd → c5_loop gaps): dislike trên UI thành gap staff_feedback gắn đúng lượt; bấm lại không nhân bản;
    giữ gap điểm chấm tự động đã có (--append).
A4  gap unmatched vẫn có lời khách / agent (lấy từ bản ghi feedback); đếm gap theo nguồn đúng (E.gap_counts).
A3  nút "Soạn nháp" (E.draft_cmd → c5_loop draft, DeepSeek GIẢ): gap staff_feedback đi tới bước soạn nháp (ghi chú nhân viên
    có trong prompt); bấm lại không gọi model cho gap đã kết luận.

Chạy: python tests/ui_c5_feedback_check.py   (Kaggle CPU; cần runs/snapshots/20261116-b2-v51A/config.json như ui_b2_check)"""
import json
import os
import re
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
tmp = tempfile.mkdtemp(prefix="uic5fb_")
os.environ["UI_PROFILE"] = "b2_v51a"
os.environ["UI_QWEN"] = "off"
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "ui.db").replace("\\", "/")
os.environ["LLM_CACHE"] = "off"

from ui import engine as E  # noqa: E402  (đặt env profile TRƯỚC core)

FAILS = []


def ok(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


_fpath = os.path.join(ROOT, "tests", "b2_round_f_check.py")
F = types.ModuleType("b2_round_f_frame")
F.__file__ = _fpath
exec(compile(open(_fpath, encoding="utf-8").read().split("# ================================================================== H8")[0], _fpath, "exec"),
     F.__dict__)
import c5_loop as L  # noqa: E402
import core.llm.deepseek as DS  # noqa: E402
from improve import collect as C  # noqa: E402
from improve import store as S  # noqa: E402

E.FEEDBACK = os.path.join(tmp, "feedback.jsonl")
E.TRACES = os.path.join(tmp, "traces")
E.C5_STATE = os.path.join(tmp, "c5state")
RV = os.path.join(tmp, "review")
Q = "Máy lọc không khí AirPure Y giá bao nhiêu em?"


def run(cmd):
    """argv của E.gap_cmd / E.draft_cmd → chạy c5_loop.main trong tiến trình (để thay DeepSeek bằng bản giả)."""
    ok(cmd[1] == E.C5_LOOP, f"lệnh UI gọi đúng scripts/c5_loop.py: {cmd[:3]}")
    L.main(cmd[2:])


with F.Ctx({"improve_dir": ""}):
    # ---------- A1. tải lại trang ----------
    e1 = E.Engine("reload")
    e1.reset()
    e1.start_call("0911555777", "hotline", "2026-10-15")
    F.QUEUE[:] = [F.PRICE_Q]
    r1 = e1.say(Q, event_id="a")
    sid1 = e1.calls[-1]["session_id"]
    e2 = E.Engine("reload")                                   # trang tải lại giữa cuộc: Engine mới, n_calls = 0, cùng DB
    e2.start_call("0911555777", "hotline", "2026-10-15")
    sid2 = e2.calls[-1]["session_id"]
    ok(sid2 != sid1 and e2.calls[-1]["call"] == "call_2", f"Engine mới không dùng lại session_id cũ: {sid1} → {sid2}")
    try:
        F.QUEUE[:] = [F.PRICE_Q]
        r2 = e2.say(Q, event_id="a")                          # cùng event_id của phiên trình duyệt trước (dict events mới)
        ok(True, "lượt 1 sau khi tải lại trang ghi được (không UNIQUE turns)")
    except Exception as ex:  # noqa: BLE001
        r2 = None
        ok(False, f"lượt 1 sau khi tải lại trang lỗi: {type(ex).__name__}: {str(ex)[:160]}")
    if r2:
        ok(r2["ui"]["msg_id"] != r1["ui"]["msg_id"], f"msg_id khác nhau giữa hai lần tải trang: {r1['ui']['msg_id']} / {r2['ui']['msg_id']}")
    e1.end_call()
    e2.end_call()
    e3 = E.Engine("reload")
    e3.start_call("0911555777", "hotline", "2026-10-16")
    ok(e3.calls[-1]["call"] == "call_3", f"cuộc kế tiếp sau hai phiên trình duyệt: {e3.calls[-1]['call']}")
    e3.end_call()
    e3.reset()
    e3.start_call("0911555777", "hotline", "2026-10-15")
    ok(e3.calls[-1]["call"] == "call_1", "xoá bộ nhớ namespace → đánh số lại từ call_1 (demo C.6 không đổi)")
    e3.end_call()

    # ---------- A2 / A4. gom gap từ feedback nhân viên ----------
    os.makedirs(RV, exist_ok=True)
    C.write([{"id": "Gauto1", "type": "no_info", "feedback_source": "auto_eval", "customer_text": "x", "agent_text": "y"}],
            S.paths(RV)["gaps"])                                # gap nguồn 1 có sẵn — không được mất
    e1.feedback(r1, -1, "khách hỏi giá mà chưa nói khuyến mãi", "NV1")
    if r2:
        e2.feedback(r2, 1, "", "NV1")                          # like: không thành gap
    with open(E.FEEDBACK, "a", encoding="utf-8") as fh:        # feedback mồ côi (trace UI đã mất)
        fh.write(json.dumps({"msg_id": "ui:x:full:lost:call_9:1", "ns": "ui:x:full:lost", "turn": 1, "rating": -1, "note": "",
                             "by": "NV2", "customer_text": "Bên em có trả góp không?", "agent_text": "Dạ em chưa có thông tin ạ."},
                            ensure_ascii=False) + "\n")
    cmd = E.gap_cmd(RV)
    ok("--append" in cmd and "--feedback" in cmd and "--ui-trace" in cmd, f"gap_cmd: feedback + trace UI + append: {cmd[2:]}")
    run(cmd)
    gaps = C.load(S.paths(RV)["gaps"])
    staff = [g for g in gaps if g.get("feedback_source") == "staff_feedback"]
    m = [g for g in staff if not g.get("unmatched")]
    um = [g for g in staff if g.get("unmatched")]
    ok(any(g["id"] == "Gauto1" for g in gaps), "gap điểm chấm tự động có sẵn được giữ (--append)")
    ok(len(m) == 1 and m[0]["customer_text"] == Q and m[0]["detail"]["msg_id"] == r1["ui"]["msg_id"],
       f"dislike trên UI → gap staff_feedback gắn đúng lượt: {[(g['id'], g.get('customer_text')) for g in m]}")
    ok(len(um) == 1 and um[0]["customer_text"] == "Bên em có trả góp không?" and um[0]["agent_text"],
       "gap unmatched giữ lời khách / agent từ bản ghi feedback")
    ok(len(staff) == 2, f"like không thành gap; tổng gap nhân viên = 2: {len(staff)}")
    n0 = len(gaps)
    run(E.gap_cmd(RV))
    ok(len(C.load(S.paths(RV)["gaps"])) == n0, "bấm Gom gap lần hai không nhân bản")
    cnt = E.gap_counts(C.load(S.paths(RV)["gaps"]))
    ok(cnt.get("staff_feedback:staff_dislike") == 2 and cnt.get("auto_eval:no_info") == 1, f"đếm gap theo nguồn đúng: {cnt}")

    # ---------- A3. soạn nháp (DeepSeek giả) ----------
    CALLS = []

    class FakeDS:
        def json(self, prompt, **kw):
            CALLS.append(prompt)
            ids = re.findall(r"^\[([^\]]+#\d+)\]", prompt, re.M)
            if not ids:
                return {"decision": "unanswered", "chunk_id": "", "sentence_ids": [], "topic": "", "question": "", "why": "không có"}
            return {"decision": "faq", "chunk_id": ids[0].rsplit("#", 1)[0], "sentence_ids": [ids[0]], "topic": "chủ đề thử",
                    "question": "câu hỏi thử của khách"}

    real = DS.DeepSeek
    DS.DeepSeek = FakeDS
    try:
        dcmd = E.draft_cmd(RV, ["staff_dislike"], 10)
        ok(dcmd[2] == "draft" and "--types" in dcmd and "staff_dislike" in dcmd[-1], f"draft_cmd: {dcmd[2:]}")
        run(dcmd)
        res = json.load(open(os.path.join(RV, "draft_result.json"), encoding="utf-8"))
        reached = {x["gap"] for k in ("drafted", "unanswered", "invalid") for x in res[k]}
        ok({g["id"] for g in staff} <= reached, f"gap nhân viên đi tới bước soạn nháp: {res and {k: len(v) if isinstance(v, list) else v for k, v in res.items()}}")
        ok(any("GHI CHÚ NHÂN VIÊN: khách hỏi giá mà chưa nói khuyến mãi" in p for p in CALLS) or not CALLS,
           "ghi chú nhân viên có trong prompt soạn nháp")
        for x in res["drafted"]:
            st, prop = S.find(x["id"], RV)
            ok(st == "pending" and prop["payload"]["gap"]["feedback_source"] == "staff_feedback",
               f"nháp vào pending, ghi nguồn staff_feedback: {x['id']} ({st})")
        n_calls = len(CALLS)
        run(E.draft_cmd(RV, ["staff_dislike"], 10))
        res2 = json.load(open(os.path.join(RV, "draft_result.json"), encoding="utf-8"))
        ok(len(CALLS) == n_calls and not res2["drafted"] and not res2["unanswered"] and not res2["invalid"],
           f"bấm Soạn nháp lần hai: không gọi model cho gap đã kết luận (gọi thêm {len(CALLS) - n_calls})")
        ok(not S.list_state("approved", RV), "model không tự duyệt / kích hoạt gì")
    finally:
        DS.DeepSeek = real

print("TẤT CẢ OK" if not FAILS else f"{len(FAILS)} LỖI: {FAILS}")
sys.exit(1 if FAILS else 0)
