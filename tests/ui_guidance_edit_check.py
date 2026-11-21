"""Kiểm 18/11 (freeze 20261118-integ-ui3): sửa hướng dẫn thành phiên bản mới + so sánh trước / sau với Jev thật. Kaggle CPU, KHÔNG API.

A. Sửa (improve/guidance_edit + scripts/guidance_loop): bản chờ duyệt sửa → bản mới v+1 ở chờ duyệt, bản cũ sang Đã loại (thay thế),
   nội dung bản cũ không đổi; lỗi (không tên / không lý do / không thay đổi / có số tiền / xin quyền ghi / trường lạ / sửa bản đã loại)
   → không lưu gì; bản ĐÃ DUYỆT sửa → bản mới chờ duyệt, bản đã duyệt + gói đã đóng + gói đang kích hoạt KHÔNG đổi; hai bản cùng
   guide_id ở approved → đóng gói từ chối; duyệt bản mới (UI / CLI) → bản cũ sang Đã loại; gói mới chỉ chứa bản mới; log revise / supersede.
B. So sánh trước / sau (scripts/guidance_sandbox.run_spec, DeepSeek / Jev giả theo khung tests/b2_round_f_check.py, tool mock BTC):
   trước không có bản nháp, sau có (khóa vào phiên thử, đưa vào payload Jev); cả hai trả lời; settings + trace UI trả lại; kết quả lưu;
   tập "sau" thay bản cùng guide_id; tiến trình thử từ chối chạy khi thiếu khóa (không chạy backend dự phòng), không ghi kết quả;
   mutant bỏ bản nháp khỏi tập "sau" bị phát hiện.
C. Giao diện (AppTest ui/app_v2.py): nút Chỉnh sửa → form; lưu bị vô hiệu khi chưa có lý do; nội dung sai không lưu; lưu → bản mới;
   sửa bản đã duyệt → bản mới, bản đã duyệt giữ nguyên; duyệt bản mới → bản cũ sang Đã loại; khung so sánh: nút chạy bị vô hiệu khi
   thiếu khóa; hiện kết quả thử đã lưu (bảng Trước / Sau); mutant ghi đè tại chỗ bản đã duyệt bị phát hiện.

Chạy: python tests/ui_guidance_edit_check.py [drafts.json]   (cây đã áp overlay runs/freeze/20261118-integ-ui3; cần streamlit)"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tmp = tempfile.mkdtemp(prefix="uiguide_edit_")
os.environ["UI_PROFILE"] = "b2_integ_tt"
os.environ["UI_QWEN"] = "off"
os.environ["UI_DATA_DIR"] = os.path.join(tmp, "ui")
os.environ["C5_STATE_DIR"] = os.path.join(tmp, "c5_state")
os.environ["C5_ROOT"] = os.path.join(tmp, "c5_review")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "ui.db").replace("\\", "/")
os.environ["LLM_CACHE"] = "off"
for _k in ("DEEPSEEK_API_KEY", "TYPESAFE_API_KEY"):     # bảo đảm không gọi API thật kể cả khi máy có .env
    os.environ[_k] = ""
DRAFTS = next(p for p in ([sys.argv[1]] if len(sys.argv) > 1 else []) + [os.path.join(ROOT, "repo_extra", "guidance", "drafts_v1.json"),
                                                                          os.path.join(ROOT, "runs", "c5", "guidance_review", "drafts_v1.json")]
              if os.path.exists(p))

from ui import engine as E  # noqa: E402  (đặt env profile TRƯỚC core)

FAILS = []


def ok(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


def cmd(*args):
    r = subprocess.run(E.guidance_cmd(*args), capture_output=True, text=True, cwd=ROOT, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return r.returncode, r.stdout + r.stderr


def raises(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return False
    except S.ProposalError:
        return True


info = E.startup_check()
ok(info["code"]["status"] == "ok" and info["code"]["freeze"] == "runs/freeze/20261118-integ-ui3",
   f"startup_check: code khớp freeze integ-ui3 ({info.get('code')}; {info.get('mismatch')})")

from improve import guidance_edit as GE  # noqa: E402
from improve import store as S  # noqa: E402

# ================================================================== A. sửa thành phiên bản mới
R = E.GUIDE_ROOT
rc, out = cmd("import", "--root", R, "--drafts", DRAFTS, "--author", "fixture-author")
pend = E.guidance_props("pending")
ok(rc == 0 and len(pend) == 4, f"nhập nháp → 4 chờ duyệt ({rc})")
gid = {p["payload"]["guide_id"]: p["id"] for p in pend}
old_id = gid["GUIDE-NAMED-MODELS"]
_, old = S.find(old_id, R)
n_pend = len(pend)
for bad, why in ((dict(guidance=old["payload"]["guidance"] + ["Báo giá giảm 500k cho khách"]), "có số tiền"),
                 (dict(requires_capabilities=["price_read", "request_commit"]), "xin quyền ghi"),
                 (dict(guide_id="GUIDE-KHAC"), "trường không được sửa"),
                 (dict(title=old["payload"]["title"]), "không có thay đổi"),
                 (dict(applies_when=[]), "trường bắt buộc để trống")):
    ok(raises(GE.revise, old_id, bad, "NV-sua", "thử lỗi", root=R) and len(E.guidance_props("pending")) == n_pend,
       f"sửa bị từ chối, không lưu gì: {why}")
ok(raises(GE.revise, old_id, dict(title="Tiêu đề mới"), "", "lý do", root=R), "sửa không tên bị từ chối")
ok(raises(GE.revise, old_id, dict(title="Tiêu đề mới"), "NV-sua", " ", root=R), "sửa không lý do bị từ chối")
new_aw = old["payload"]["applies_when"] + ["Khách nêu tên hai mẫu cụ thể và hỏi giá hoặc tồn kho từng mẫu"]
nid = GE.revise(old_id, {"applies_when": new_aw}, "NV-sua", "rõ điều kiện hai mẫu", root=R)
st_new, new = S.find(nid, R)
st_old, old2 = S.find(old_id, R)
ok(nid != old_id and st_new == "pending" and new["payload"]["version"] == (old["payload"].get("version") or 1) + 1
   and new["payload"]["guide_id"] == "GUIDE-NAMED-MODELS" and new["revision_of"] == old_id and new["tests"] == old["tests"]
   and new["payload"]["applies_when"] == new_aw and new["author"] == "NV-sua",
   f"sửa bản chờ duyệt → bản mới v{new['payload']['version']} chờ duyệt, cùng guide_id, giữ test")
ok(st_old == "rejected" and nid in old2["review"]["reason"] and old2["payload"] == old["payload"],
   "bản chờ duyệt cũ → Đã loại (thay bằng bản mới), nội dung không bị ghi đè")
ok(raises(GE.revise, old_id, dict(title="X mới"), "NV-sua", "sửa bản đã loại", root=R), "không sửa bản đã loại")

# bản ĐÃ DUYỆT + gói đã đóng + gói đang kích hoạt không đổi khi sửa
d_id = gid["GUIDE-DELIVERY-NO-ORDER"]
GE.approve(d_id, "NV-duyet", "duyệt v1", root=R)
p1 = os.path.join(E.GUIDE_PKGS, "p1")
rc, out = cmd("package", "--root", R, "--name", "p1", "--by", "NV-duyet", "--out", p1)
h1 = json.load(open(os.path.join(p1, "PACKAGE.json"), encoding="utf-8"))["approved_hash"] if rc == 0 else None
rc2, _ = cmd("activate", "--pkg", p1, "--by", "NV-duyet", "--reason", "thử", "--state", E.GUIDE_STATE)
act0 = json.load(open(os.path.join(E.GUIDE_STATE, "active.json"), encoding="utf-8")) if rc2 == 0 else {}
_, d_old = S.find(d_id, R)
d2 = GE.revise(d_id, {"guidance": d_old["payload"]["guidance"] + ["Nói rõ đây là thời gian giao ước tính theo chính sách"]},
               "NV-sua", "phân biệt ước tính", root=R)
st_d, d_now = S.find(d_id, R)
ok(rc == 0 and st_d == "approved" and d_now["payload"] == d_old["payload"] and S.find(d2, R)[0] == "pending",
   "sửa bản ĐÃ DUYỆT → bản mới chờ duyệt; bản đã duyệt giữ nguyên ở approved")
rc3, out3 = cmd("regress", "--pkg", p1)
ok(S.approved_hash(p1) == h1 and rc3 == 0, "gói p1 đã đóng không đổi (hash khớp, regress đạt)")
ok(json.load(open(os.path.join(E.GUIDE_STATE, "active.json"), encoding="utf-8")) == act0, "gói đang kích hoạt không đổi khi sửa")
S.approve(d2, "NV-duyet", "duyệt thẳng qua store (không thay thế)", root=R)
ok(set(GE.approved_duplicates(R).get("GUIDE-DELIVERY-NO-ORDER") or []) == {d_id, d2}, "phát hiện hai bản cùng guide_id ở approved")
rc, out = cmd("package", "--root", R, "--name", "pdup", "--by", "NV-duyet", "--out", os.path.join(E.GUIDE_PKGS, "pdup"))
ok(rc != 0 and not os.path.exists(os.path.join(E.GUIDE_PKGS, "pdup", "PACKAGE.json")), f"đóng gói từ chối khi trùng guide_id: {out[-160:]}")
S.reopen(d2, "NV-duyet", "duyệt lại qua CLI", root=R)
rc, out = cmd("approve", "--root", R, "--id", d2, "--by", "NV-duyet", "--reason", "bản mới")
ok(rc == 0 and S.find(d2, R)[0] == "approved" and S.find(d_id, R)[0] == "rejected" and d2 in S.find(d_id, R)[1]["review"]["reason"]
   and not GE.approved_duplicates(R), f"CLI duyệt bản mới → bản cũ sang Đã loại (thay thế): {out[-200:]}")
p2 = os.path.join(E.GUIDE_PKGS, "p2")
rc, out = cmd("package", "--root", R, "--name", "p2", "--by", "NV-duyet", "--out", p2)
ids2 = json.load(open(os.path.join(p2, "PACKAGE.json"), encoding="utf-8"))["ids"] if rc == 0 else []
ok(ids2 == [d2] and S.approved_hash(p1) == h1, f"gói mới chỉ chứa bản mới; gói cũ vẫn nguyên ({ids2})")
evs = [r["event"] for r in S.read_log(R)]
ok("revise" in evs and evs.count("supersede") >= 2, f"log có revise + supersede ({evs.count('revise')} / {evs.count('supersede')})")

# ================================================================== B. so sánh trước / sau (model giả)
import importlib.util  # noqa: E402

_gs = importlib.util.spec_from_file_location("guidance_sandbox", os.path.join(ROOT, "scripts", "guidance_sandbox.py"))
GS = importlib.util.module_from_spec(_gs)
_gs.loader.exec_module(GS)
_fpath = os.path.join(ROOT, "tests", "b2_round_f_check.py")
F = types.ModuleType("b2_round_f_frame")
F.__file__ = _fpath
exec(compile(open(_fpath, encoding="utf-8").read().split("# ================================================================== H8")[0], _fpath, "exec"),
     F.__dict__)
from core.config import settings  # noqa: E402
from harness import improve_hook, planner_b2tt as TT  # noqa: E402
from harness.tools import mt  # noqa: E402


def policy_inner(state, opts):
    for pre in ("survey:", "answer", "ask_customer_category", "finish_unresolved"):
        hit = next((k for k in opts if k.startswith(pre)), None)
        if hit:
            return {"pick": hit, "backend": "script", "ms": 0}


CHEAP = F.resp(intent="price_promo", asks=["price"], asks_question=True,
               consult={"sort": "cheapest", "scope": "category", "category_span": "Máy lọc không khí", "budget_span": None, "area_span": None})
pm_id = gid["GUIDE-PRICE-MIN"]
_, pm = S.find(pm_id, R)
spec = E.sandbox_spec(pm, "empty", ["Máy lọc không khí rẻ nhất là bao nhiêu?", " "], [], True, "NV-thu")
ok(spec["trials"] == ["Máy lọc không khí rẻ nhất là bao nhiêu?"] and spec["base_guides"] == [] and spec["draft"]["id"] == pm_id,
   "spec: bỏ câu trống, nền rỗng, bản nháp đúng")
b, a = GS.sides(spec)
ok(b == [] and [g["id"] for g in a] == [pm_id], "nền rỗng: trước = rỗng, sau = bản nháp")
spec_ap = E.sandbox_spec(S.find(d2, R)[1], "approved", ["x"], [], True, "NV")
fake_v1 = {**E.guide_dto(S.find(d_id, R)[1]), "id": "P-old-same-guide"}
spec_ap["base_guides"] = spec_ap["base_guides"] + [fake_v1]
b, a = GS.sides(spec_ap)
ok("P-old-same-guide" in [g["id"] for g in b] and "P-old-same-guide" not in [g["id"] for g in a] and d2 in [g["id"] for g in a]
   and d2 not in [g["id"] for g in b], "nền đã duyệt: sau thay bản cùng guide_id bằng bản nháp; trước không có bản nháp")


def sandbox_ok(res, draft_id):
    t = res["trials"][0]
    lb, la = t["before"]["turns"][-1], t["after"]["turns"][-1]
    return (draft_id not in t["before"]["guides"] and draft_id in t["after"]["guides"]
            and draft_id not in (lb["guidance"].get("supplied_to_planner") or [])
            and draft_id in (la["guidance"].get("supplied_to_planner") or [])
            and t["before"]["mode"] == "tt" and t["after"]["mode"] == "ttg"
            and not t["before"]["error"] and not t["after"]["error"])


keep = (settings.b2_two_tier, settings.planner_guidance_dir, E.TRACES)
sb_out = os.path.join(E.sandbox_dir(pm_id), "20261118-000000-test")
mt._ORDERS["OD-ui-that"] = {"note": "đơn của cuộc gọi UI (trong cùng tiến trình chỉ để kiểm reset)"}
with F.Ctx({"improve_dir": "", "b2tt_max_tool_calls": 18, "b2tt_max_decisions": 4}):
    TT.DECIDERS.update(inner=policy_inner, outer=None)
    F.QUEUE[:] = [CHEAP, CHEAP]
    res = GS.run_spec(spec, sb_out, E=E, require_keys=False)
    TT.DECIDERS.update(inner=None, outer=None)
t0 = res["trials"][0]
ok(sandbox_ok(res, pm_id), f"trước không có / sau có bản nháp trong phiên + payload Jev; chế độ tt / ttg "
                           f"({t0['before']['turns'][-1]['guidance']}, {t0['after']['turns'][-1]['guidance']})")
ok(all("thấp nhất" in (t0[s]["turns"][-1]["agent_text"] or "") for s in ("before", "after")),
   f"cả hai phiên trả lời: {[t0[s]['turns'][-1]['agent_text'] for s in ('before', 'after')]}")
ok(all(t0[s]["turns"][-1]["actions"] and t0[s]["turns"][-1]["tools"] and t0[s]["turns"][-1]["latency_ms"] is not None
       for s in ("before", "after")), "kết quả có hành động Jev, tool, thời gian")
ok((settings.b2_two_tier, settings.planner_guidance_dir, E.TRACES) == keep, "settings + đường trace UI được trả lại sau phiên thử")
ok(not os.path.isdir(E.TRACES) or not any("sandbox" in f for f in os.listdir(E.TRACES)), "phiên thử không ghi vào trace UI (không vào vòng gap)")
ok(os.path.exists(os.path.join(sb_out, "result.json")) and E.sandbox_history(pm_id)[0]["draft_prop"] == pm_id
   and E.sandbox_history(pm_id)[0]["draft_payload_sha"] == E.payload_sha(pm), "kết quả thử lưu cạnh kho, gắn đúng bản nháp + payload")
ok(not mt._ORDERS, "mock reset trước mỗi phiên thử (vì vậy UI chạy thử ở TIẾN TRÌNH RIÊNG)")
ok(not os.path.exists(os.path.join(E.GUIDE_STATE, "active.json")) or
   json.load(open(os.path.join(E.GUIDE_STATE, "active.json"), encoding="utf-8")) == act0, "phiên thử không đổi gói đang kích hoạt")
real_sides = GS.sides
GS.sides = lambda sp: (real_sides(sp)[0], real_sides(sp)[0])           # mutant: tập "sau" quên bản nháp
with F.Ctx({"improve_dir": "", "b2tt_max_tool_calls": 18, "b2tt_max_decisions": 4}):
    TT.DECIDERS.update(inner=policy_inner, outer=None)
    F.QUEUE[:] = [CHEAP, CHEAP]
    mres = GS.run_spec(spec, os.path.join(tmp, "mutant_sb"), E=E, require_keys=False)
    TT.DECIDERS.update(inner=None, outer=None)
GS.sides = real_sides
ok(not sandbox_ok(mres, pm_id), "mutant (sau quên bản nháp) bị PHÁT HIỆN")
improve_hook.reset()

# tiến trình thử thật (subprocess) khi thiếu khóa: từ chối, không ghi kết quả
rc, log, r_none, sbdir = E.sandbox_run(spec, timeout=600)
ok(rc != 0 and r_none is None and "thiếu khóa" in log and not os.path.exists(os.path.join(sbdir, "result.json")),
   f"tiến trình thử từ chối khi thiếu khóa (rc {rc}): {log[-200:]}")
ok(os.path.exists(os.path.join(sbdir, "spec.json")), "spec của lần thử lưu cạnh kết quả (hồ sơ duyệt)")

# ================================================================== C. giao diện
from streamlit.testing.v1 import AppTest  # noqa: E402
from streamlit.testing.v1.errors import AppTestError  # noqa: E402

APP = os.path.join(ROOT, "ui", "app_v2.py")
T = 300


def clickable(at, key):
    try:
        at.button(key=key).click().run()
        return True
    except AppTestError:
        return False


def errs(at):
    return [e.value for e in at.exception]


def open_step2(app_file):
    at = AppTest.from_file(app_file, default_timeout=T).run()
    [t for t in at.text_input if t.label == "Tên nhân viên"][0].input("NV-ui").run()
    at.radio(key="g_step").set_value("2 · Duyệt từng hướng dẫn").run()
    return at


E.GUIDE_ROOT, E.GUIDE_PKGS, E.GUIDE_STATE = (os.path.join(tmp, "c", x) for x in ("review", "pkgs", "state"))
os.makedirs(E.GUIDE_ROOT)
cmd("import", "--root", E.GUIDE_ROOT, "--drafts", DRAFTS, "--author", "fixture-author")
RU = E.GUIDE_ROOT
u_gid = {p["payload"]["guide_id"]: p["id"] for p in E.guidance_props("pending")}
q = u_gid["GUIDE-NAMED-MODELS"]
at = open_step2(APP)
ok(not at.exception, f"mở bước 2 không lỗi {errs(at)}")
at.button(key=f"ged-{q}").click().run()
ok(not at.exception and any(t.key == f"ed-{q}-guidance" for t in at.text_area), f"bấm Chỉnh sửa → form sửa ({errs(at)})")
ok(not clickable(at, f"edsave-{q}"), "lưu khi CHƯA có lý do sửa: nút bị vô hiệu")
_, q0 = S.find(q, RU)
at.text_area(key=f"ed-{q}-guidance").input("\n".join(q0["payload"]["guidance"] + ["Báo khách giá 2 triệu"])).run()
at.text_input(key=f"ed-{q}-note").input("thêm bước").run()
ok(any("chưa hợp lệ" in w.value for w in at.warning), "form báo trước nội dung không hợp lệ")
at.button(key=f"edsave-{q}").click().run()
ok(len(E.guidance_props("pending")) == 4 and S.find(q, RU)[0] == "pending" and at.error, "nội dung có số tiền → không lưu, báo lỗi")
at.text_area(key=f"ed-{q}-guidance").input("\n".join(q0["payload"]["guidance"] + ["Đọc giá từng mẫu bằng công cụ rồi so sánh"])).run()
at.button(key=f"edsave-{q}").click().run()
qn = [p for p in E.guidance_props("pending") if p.get("revision_of") == q]
ok(not at.exception and len(qn) == 1 and S.find(q, RU)[0] == "rejected" and qn[0]["payload"]["version"] == (q0["payload"].get("version") or 1) + 1
   and any("Đã lưu" in s.value for s in at.success), f"UI lưu → bản mới chờ duyệt, bản cũ Đã loại ({errs(at)})")
q2 = qn[0]["id"]
at.button(key=f"ga-{q2}").click().run()
ok(S.find(q2, RU)[0] == "approved", f"UI duyệt bản mới ({errs(at)})")
at.button(key=f"ged-{q2}").click().run()
at.text_input(key=f"ed-{q2}-title").input("Báo giá / tồn kho từng mẫu khi khách nêu tên hai mẫu").run()
at.text_input(key=f"ed-{q2}-note").input("đổi tiêu đề").run()
at.button(key=f"edsave-{q2}").click().run()
q3 = [p for p in E.guidance_props("pending") if p.get("revision_of") == q2]
_, q2now = S.find(q2, RU)
ok(len(q3) == 1 and S.find(q2, RU)[0] == "approved" and q2now["payload"]["title"] != "Báo giá / tồn kho từng mẫu khi khách nêu tên hai mẫu",
   f"UI sửa bản ĐÃ DUYỆT → bản mới chờ duyệt, bản đã duyệt giữ nguyên ({errs(at)})")
at.button(key=f"ga-{q3[0]['id']}").click().run()
ok(S.find(q3[0]["id"], RU)[0] == "approved" and S.find(q2, RU)[0] == "rejected" and not GE.approved_duplicates(RU),
   f"UI duyệt bản sửa → bản cũ sang Đã loại, không trùng ({errs(at)})")

# khung so sánh: thiếu khóa → nút chạy vô hiệu; kết quả đã lưu hiện bảng Trước / Sau
pmu = u_gid["GUIDE-PRICE-MIN"]
dst = os.path.join(E.sandbox_dir(pmu), "20261118-000000-test")
os.makedirs(dst)
json.dump({**res, "draft_prop": pmu}, open(os.path.join(dst, "result.json"), "w", encoding="utf-8"), ensure_ascii=False)
at.checkbox(key=f"sbopen-{pmu}").check().run()
ok(not at.exception and any("Cần khóa" in w.value for w in at.warning), f"mở khung so sánh; báo thiếu khóa ({errs(at)})")
ok(not clickable(at, f"sbrun-{pmu}"), "thiếu khóa API: nút So sánh trước / sau bị vô hiệu")
rows = [r for tb in at.table for r in tb.value.to_dict("records")]
ok(any(r.get("Cần xem") == "Câu trả lời cho khách" for r in rows) and any(r.get("Cần xem") == "Đưa vào Jev" for r in rows),
   f"hiện kết quả thử đã lưu: bảng Trước / Sau ({len(rows)} dòng)")

# mutant: lưu ghi đè TẠI CHỖ (không tạo bản mới) → test phải phát hiện
src = open(APP, encoding="utf-8").read()
OLD = "nid = GE.revise(pid, ch, by, note, root=root)"
ok(src.count(OLD) == 1, "mutant: tìm đúng một chỗ lưu bản sửa")
mut = os.path.join(tmp, "app_v2_mutant.py")
open(mut, "w", encoding="utf-8").write(src.replace(OLD, 'nid = (S._write(p["status"], {**p, "payload": {**pl, **ch}}, root), pid)[1]'))
E.GUIDE_ROOT, E.GUIDE_PKGS, E.GUIDE_STATE = (os.path.join(tmp, "m", x) for x in ("review", "pkgs", "state"))
os.makedirs(E.GUIDE_ROOT)
cmd("import", "--root", E.GUIDE_ROOT, "--drafts", DRAFTS, "--author", "fixture-author")
mq = {p["payload"]["guide_id"]: p["id"] for p in E.guidance_props("pending")}["GUIDE-DELIVERY-NO-ORDER"]
GE.approve(mq, "NV", "v1", root=E.GUIDE_ROOT)
_, mq0 = S.find(mq, E.GUIDE_ROOT)
am = open_step2(mut)
am.button(key=f"ged-{mq}").click().run()
am.text_input(key=f"ed-{mq}-title").input("Tiêu đề sửa tại chỗ").run()
am.text_input(key=f"ed-{mq}-note").input("mutant").run()
am.button(key=f"edsave-{mq}").click().run()
_, mq1 = S.find(mq, E.GUIDE_ROOT)
detected = mq1["payload"] != mq0["payload"] or not any(p.get("revision_of") == mq for p in E.guidance_props("pending"))
ok(detected, "mutant ghi đè tại chỗ bản đã duyệt bị PHÁT HIỆN")

print("TẤT CẢ OK" if not FAILS else f"{len(FAILS)} LỖI: {FAILS}")
sys.exit(1 if FAILS else 0)
