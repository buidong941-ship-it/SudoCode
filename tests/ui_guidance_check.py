"""Kiểm UI candidate tích hợp B2-TT + hướng dẫn điều phối (17/11, freeze 20261117-integ-ui). Kaggle CPU, KHÔNG API, không model thật.

A. Engine (DeepSeek / Jev giả theo khung tests/b2_round_f_check.py; tool mock BTC thật):
   profile b2_integ_tt + kiểm hash code theo freeze; FAQ không nạp; nhập nháp → duyệt từng cái → đóng gói → regress → kích hoạt;
   phiên khóa gói khi mở, không đổi giữa phiên; hai cờ độc lập cho đủ 4 chế độ; quay lui; gói bị sửa → từ chối mở phiên;
   một lượt B2-TT thật qua engine UI; trace / feedback ghi chế độ + hash gói; thử truy hồi; xuất dữ liệu có kho / gói / trạng thái.
B. Giao diện (Streamlit AppTest, ui/app_v2.py): thanh bên có hai cờ; tab Cải tiến 4 bước mở được; nhập nháp; duyệt / loại TỪNG
   hướng dẫn (loại cần lý do); chạy test của hướng dẫn; đóng gói + regress; kích hoạt / quay lui; thử truy hồi; luồng FAQ cũ vẫn mở.
Gói ở đây là FIXTURE do "fixture-reviewer" duyệt chỉ để kiểm — không phải gói thật.

Chạy: python tests/ui_guidance_check.py [drafts.json]   (cây đã áp overlay runs/freeze/20261117-integ-ui; cần streamlit)"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import zipfile
import io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tmp = tempfile.mkdtemp(prefix="uiguide_")
os.environ["UI_PROFILE"] = "b2_integ_tt"
os.environ["UI_QWEN"] = "off"
os.environ["UI_DATA_DIR"] = os.path.join(tmp, "ui")
os.environ["C5_STATE_DIR"] = os.path.join(tmp, "c5_state")
os.environ["C5_ROOT"] = os.path.join(tmp, "c5_review")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "ui.db").replace("\\", "/")
os.environ["LLM_CACHE"] = "off"
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


# ================================================================== A. engine
ok(E.CANDIDATE and E.PROFILE_INFO["profile"] == "b2_integ_tt", "profile candidate b2_integ_tt")
ok(E.GUIDE_ROOT.startswith(os.environ["UI_DATA_DIR"]) and E.GUIDE_STATE.startswith(os.environ["UI_DATA_DIR"]),
   "kho / trạng thái hướng dẫn nằm cạnh dữ liệu UI (tải về được)")
info = E.startup_check()
ok(info["ok"] and info["code"]["status"] == "ok" and info["code"]["freeze"] == "runs/freeze/20261117-integ-ui",
   f"startup_check: code khớp freeze integ-ui ({info.get('code')}; {info.get('mismatch')})")
ok("Candidate" in info["label"], f"nhãn nêu candidate: {info['label']}")

_fpath = os.path.join(ROOT, "tests", "b2_round_f_check.py")
F = types.ModuleType("b2_round_f_frame")
F.__file__ = _fpath
exec(compile(open(_fpath, encoding="utf-8").read().split("# ================================================================== H8")[0], _fpath, "exec"),
     F.__dict__)
from core.config import settings  # noqa: E402
from harness import improve_hook, planner_b2tt as TT  # noqa: E402
from improve import store as S  # noqa: E402


def policy_inner(state, opts):
    for pre in ("survey:", "answer", "ask_customer_category", "finish_unresolved"):
        hit = next((k for k in opts if k.startswith(pre)), None)
        if hit:
            return {"pick": hit, "backend": "script", "ms": 0}


CHEAP = F.resp(intent="price_promo", asks=["price"], asks_question=True,
               consult={"sort": "cheapest", "scope": "category", "category_span": "Máy lọc không khí", "budget_span": None, "area_span": None})

# --- nhập → duyệt TỪNG cái → đóng gói → regress → kích hoạt (dòng lệnh UI gọi)
rc, out = cmd("import", "--root", E.GUIDE_ROOT, "--drafts", DRAFTS, "--author", "fixture-author")
pend = E.guidance_props("pending")
ok(rc == 0 and len(pend) == 4, f"nhập nháp → 4 chờ duyệt ({rc}; {out[-300:]})")
gid = {p["payload"]["guide_id"]: p["id"] for p in pend}
ok(not E.guidance_props("approved"), "chưa duyệt: không có gì ở approved")
for g in ("GUIDE-NAMED-MODELS", "GUIDE-DELIVERY-NO-ORDER"):
    S.approve(gid[g], "fixture-reviewer", "kiểm UI", root=E.GUIDE_ROOT)
try:
    S.approve(gid["GUIDE-PRICE-MIN"], "", root=E.GUIDE_ROOT)
    ok(False, "duyệt không tên phải bị từ chối")
except S.ProposalError:
    ok(True, "duyệt không tên bị từ chối")
pk = os.path.join(E.GUIDE_PKGS, "r1")
rc, out = cmd("package", "--root", E.GUIDE_ROOT, "--name", "r1", "--by", "fixture-reviewer", "--out", pk)
meta = json.load(open(os.path.join(pk, "PACKAGE.json"), encoding="utf-8")) if rc == 0 else {}
ok(rc == 0 and meta.get("n") == 2 and set(meta.get("ids") or []) == {gid["GUIDE-NAMED-MODELS"], gid["GUIDE-DELIVERY-NO-ORDER"]},
   f"đóng gói đúng 2 hướng dẫn đã duyệt ({out[-200:]})")
rc, out = cmd("regress", "--pkg", pk)
ok(rc == 0, f"regress gói r1 đạt: {out[-300:]}")
ok([p["name"] for p in E.guidance_packages()] == ["r1"] and len(E.package_guides(pk)) == 2, "UI liệt kê gói + nạp được hướng dẫn trong gói")

# --- FAQ không nạp trên candidate
os.makedirs(os.environ["C5_STATE_DIR"], exist_ok=True)
with open(os.path.join(os.environ["C5_STATE_DIR"], "active.json"), "w", encoding="utf-8") as fh:
    json.dump({"package": os.path.join(tmp, "faq_pkg"), "approved_hash": "x"}, fh)

with F.Ctx({"improve_dir": "", "b2tt_max_tool_calls": 18, "b2tt_max_decisions": 4}):
    TT.DECIDERS.update(inner=policy_inner, outer=None)
    eng = E.Engine("uig")
    eng.reset()
    ok(eng.two_tier is True and eng.use_guidance is True, "mặc định candidate: B2-TT bật, dùng gói đang kích hoạt")

    # chế độ tt: chưa kích hoạt gói nào
    eng.start_call("0911777888", "hotline", "2026-10-15")
    ok(eng.calls[-1]["mode"] == "tt" and settings.b2_two_tier is True and settings.planner_guidance_dir == ""
       and eng.sess.guidance_pin is None, f"chưa kích hoạt gói → chế độ tt (kho rỗng): {eng.calls[-1]['mode']}")
    ok(settings.improve_dir == "" and eng.calls[-1]["package_hash"] is None, "candidate KHÔNG nạp gói FAQ dù FAQ đang kích hoạt")
    rc, out = cmd("activate", "--pkg", pk, "--by", "fixture-reviewer", "--reason", "kiểm UI", "--state", E.GUIDE_STATE)
    ok(rc == 0 and E.guidance_active().get("package") == os.path.abspath(pk), "kích hoạt gói r1")
    try:
        eng._load_mode()
        ok(False, "đổi chế độ / gói giữa phiên phải bị từ chối")
    except RuntimeError:
        ok(True, "đổi chế độ / gói giữa phiên bị từ chối")
    ok(settings.planner_guidance_dir == "" and eng.sess.guidance_pin is None, "kích hoạt KHÔNG đổi phiên đang mở")
    eng.end_call()

    # chế độ ttg: phiên mới khóa gói; một lượt B2-TT thật qua engine UI
    eng.start_call("0911777888", "hotline", "2026-10-16")
    h = meta.get("approved_hash")
    ok(eng.calls[-1]["mode"] == "ttg" and eng.sess.guidance_pin and eng.sess.guidance_pin["hash"] == h
       and eng.calls[-1]["guidance_hash"] == h, f"phiên mới khóa gói r1 → ttg ({eng.calls[-1]['mode']}, {eng.calls[-1]['guidance_hash']})")
    F.QUEUE[:] = [CHEAP]
    r = eng.say("Máy lọc không khí rẻ nhất là bao nhiêu?", event_id="g1")
    lp = (r.get("planner") or {}).get("loop") or {}
    ok("ask_need" not in (r.get("goals") or []) and "thấp nhất" in (r.get("agent_text") or ""),
       f"B2-TT qua UI: trả lời giá thấp nhất, không hỏi trẻ nhỏ: {r.get('agent_text')}")
    gtr = lp.get("guidance") or {}
    ok(gtr.get("status") in ("loaded", "empty") and gtr.get("package_hash") == h, f"trace hướng dẫn có hash gói: {gtr.get('status')}")
    ok(set(gtr.get("supplied_to_planner") or []) <= set(gtr.get("selected") or []), "supplied_to_planner ⊆ selected")
    ok(r["ui"]["mode"] == "ttg" and r["ui"]["guidance_hash"] == h, "row UI ghi chế độ + hash gói")
    fb = eng.feedback(r, -1, "thử", "NV1")
    ok(fb["mode"] == "ttg" and fb["guidance_hash"] == h, "feedback ghi chế độ + hash gói")
    tl = [json.loads(l) for l in open(os.path.join(E.TRACES, f"{eng.ns.replace(':', '_')}.jsonl"), encoding="utf-8")]
    ok(tl[-1]["mode"] == "ttg" and tl[-1]["guidance_hash"] == h and (tl[-1].get("guidance") or {}).get("status") == gtr.get("status"),
       "trace UI ghi chế độ + hash + trạng thái hướng dẫn")
    eng.end_call()

    # đủ 4 chế độ bằng hai cờ độc lập
    for tt_on, g_on, want in ((False, False, "off"), (False, True, "g"), (True, False, "tt"), (True, True, "ttg")):
        eng.two_tier, eng.use_guidance = tt_on, g_on
        eng.start_call("0911777888", "hotline", "2026-10-17")
        ok(eng.calls[-1]["mode"] == want and settings.b2_two_tier is tt_on
           and (settings.planner_guidance_dir == os.path.abspath(pk)) is g_on and bool(eng.sess.guidance_pin) is g_on,
           f"cờ B2-TT={tt_on}, hướng dẫn={g_on} → {want} (được {eng.calls[-1]['mode']})")
        eng.end_call()

    # quay lui → phiên mới kho rỗng
    rc, out = cmd("rollback", "--by", "fixture-reviewer", "--reason", "kiểm quay lui", "--state", E.GUIDE_STATE)
    eng.start_call("0911777888", "hotline", "2026-10-18")
    ok(rc == 0 and eng.calls[-1]["mode"] == "tt" and eng.sess.guidance_pin is None, "quay lui: phiên mới không nạp gói (tt)")
    eng.end_call()

    # gói bị sửa sau khi đóng → từ chối mở phiên
    bad = os.path.join(tmp, "pk_bad")
    shutil.copytree(pk, bad)
    f0 = os.path.join(bad, "approved", sorted(os.listdir(os.path.join(bad, "approved")))[0])
    pr = json.load(open(f0, encoding="utf-8"))
    pr["payload"]["guidance"] = pr["payload"]["guidance"] + ["Thêm một câu sửa tay"]
    json.dump(pr, open(f0, "w", encoding="utf-8"), ensure_ascii=False)
    with open(os.path.join(E.GUIDE_STATE, "active.json"), "w", encoding="utf-8") as fh:
        json.dump({"package": bad, "approved_hash": meta.get("approved_hash")}, fh)
    try:
        eng.start_call("0911777888", "hotline", "2026-10-19")
        ok(False, "gói bị sửa phải bị từ chối khi mở phiên")
    except improve_hook.GuidanceScopeError:
        ok(True, "gói bị sửa → từ chối mở phiên")
    ok(eng.sess is None, "mở phiên lỗi không để lại phiên dở dang")
    os.remove(os.path.join(E.GUIDE_STATE, "active.json"))
    TT.DECIDERS.update(inner=None, outer=None)
improve_hook.reset()

# --- thử truy hồi (ngoài cuộc gọi) + test của từng hướng dẫn
guides = E.package_guides(pk)
tt0 = settings.b2_two_tier
x = E.try_retrieval(guides, "Anh phân vân hai mẫu máy lọc không khí, giá từng chiếc thế nào em", asks=["compare", "price"], two_tier=False)
ok(gid["GUIDE-NAMED-MODELS"] in x["trace"]["selected"], f"thử truy hồi: câu so hai mẫu chọn NAMED-MODELS ({x['trace']['selected']})")
y = E.try_retrieval(guides, "Không em.", two_tier=True)
ok(y["trace"]["selected"] == [], f"thử truy hồi: 'Không em.' không ngữ cảnh → rỗng ({y['trace']['selected']})")
ok(settings.b2_two_tier == tt0, "thử truy hồi trả lại settings.b2_two_tier")
allp = [E.guide_dto(p) for p in E.guidance_props("pending") + E.guidance_props("approved")]
res = E.run_guide_tests(gid["GUIDE-NAMED-MODELS"], allp, next(p for p in E.guidance_props("approved")
                                                              if p["id"] == gid["GUIDE-NAMED-MODELS"])["tests"])
ok(res and all(r["pass"] for r in res), f"test của NAMED-MODELS đạt trên kho: {[(r['test'], r['pass']) for r in res]}")
z = zipfile.ZipFile(io.BytesIO(E.export_ui_data()))
names = z.namelist()
ok(any(n.startswith("guidance_packages/r1/") for n in names) and any(n.startswith("guidance_review/approved/") for n in names)
   and any(n.startswith("guidance_state/") for n in names), "ui_data.zip có kho / gói / trạng thái hướng dẫn")

# ================================================================== B. giao diện
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = os.path.join(ROOT, "ui", "app_v2.py")
T = 300
E.GUIDE_ROOT, E.GUIDE_PKGS, E.GUIDE_STATE = (os.path.join(tmp, "b", x) for x in ("review", "pkgs", "state"))
os.makedirs(E.GUIDE_ROOT)
shutil.copyfile(DRAFTS, os.path.join(E.GUIDE_ROOT, "drafts_ui.json"))


def btn(at, label):
    b = [x for x in at.button if x.label == label]
    return b[0] if b else None


def errs(at):
    return [e.value for e in at.exception]


at = AppTest.from_file(APP, default_timeout=T).run()
ok(not at.exception and len(at.tabs) == 5, f"mở app_v2 (candidate): 5 tab, không lỗi {errs(at)}")
labels = {c.label for c in at.checkbox}
ok({"Tư vấn hai tầng (B2-TT)", "Dùng gói hướng dẫn đang kích hoạt"} <= labels, f"thanh bên có hai cờ: {labels}")
ok(any("không nạp" in c.value for c in at.caption if "Gói FAQ" in c.value), "thanh bên: FAQ không nạp trên candidate")
for s in at.radio(key="g_step").options:
    at.radio(key="g_step").set_value(s).run()
    ok(not at.exception, f"bước '{s}' mở không lỗi: {errs(at)}")

at.radio(key="g_step").set_value("1 · Tiếp nhận & nhập nháp").run()
at.selectbox(key="g_pick").set_value("drafts_ui.json").run()
at.text_input(key="g_author").input("fixture-author").run()
btn(at, "Nhập vào hàng chờ duyệt").click().run()
ok(not at.exception and len(E.guidance_props("pending")) == 4, f"UI nhập nháp → 4 chờ duyệt ({len(E.guidance_props('pending'))}; {errs(at)})")

at.radio(key="g_step").set_value("2 · Duyệt từng hướng dẫn").run()
[t for t in at.text_input if t.label == "Tên nhân viên"][0].input("NV-duyet").run()
ok(any(m.value.startswith("#### ") for m in at.markdown), "duyệt: hiện nội dung đầy đủ từng hướng dẫn")
p0 = E.guidance_props("pending")[0]
at.button(key=f"run-{p0['id']}").click().run()
ok(not at.exception and (at.success or at.warning), f"chạy test của một hướng dẫn: {errs(at)}")
at.button(key=f"ga-{p0['id']}").click().run()
appr = E.guidance_props("approved")
ok(not at.exception and [p["id"] for p in appr] == [p0["id"]] and appr[0]["review"]["by"] == "NV-duyet",
   f"duyệt MỘT hướng dẫn, đúng người ({[p['id'] for p in appr]}; {errs(at)})")
p1 = E.guidance_props("pending")[0]
at.button(key=f"gx-{p1['id']}").click().run()
ok(not E.guidance_props("rejected"), "loại KHÔNG ghi lý do → không loại")
at.text_input(key=f"gr-{p1['id']}").input("không phù hợp lúc này").run()
at.button(key=f"gx-{p1['id']}").click().run()
rj = E.guidance_props("rejected")
ok(len(rj) == 1 and rj[0]["review"]["reason"] == "không phù hợp lúc này", f"loại có lý do ({errs(at)})")

at.radio(key="g_step").set_value("3 · Đóng gói & kích hoạt").run()
at.text_input(key="g_pkg_name").input("rUI").run()
btn(at, "Đóng gói hướng dẫn đã duyệt").click().run()
pm = os.path.join(E.GUIDE_PKGS, "rUI", "PACKAGE.json")
ok(os.path.exists(pm) and json.load(open(pm, encoding="utf-8"))["n"] == 1, f"UI đóng gói 1 hướng dẫn đã duyệt ({errs(at)})")
ok(any("regress đạt" in s.value for s in at.success), "đóng gói xong tự chạy regress và hiện kết quả")
btn(at, "Kích hoạt cho cuộc gọi mở sau").click().run()
ok(E.guidance_active().get("package") == os.path.abspath(os.path.join(E.GUIDE_PKGS, "rUI")), f"UI kích hoạt gói ({errs(at)})")
btn(at, "Quay lui gói trước").click().run()
ok(not E.guidance_active().get("package"), "UI quay lui → không còn gói")

at.radio(key="g_step").set_value("4 · Thử truy hồi").run()
at.text_input(key="g_try_text").input("Giao về địa chỉ chị đã đưa thì mấy ngày nhận được em").run()
btn(at, "Thử truy hồi").click().run()
ok(not at.exception and not at.error and any("Trạng thái" in m.value for m in at.markdown), f"thử truy hồi trên UI: {errs(at)}")

[c for c in at.checkbox if c.label == "Xem luồng FAQ cũ (đã dừng mở rộng)"][0].check().run()
ok(not at.exception and any(r.key == "c5_step" for r in at.radio), f"luồng FAQ cũ vẫn mở được (chỉ xem): {errs(at)}")

print("TẤT CẢ OK" if not FAILS else f"{len(FAILS)} LỖI: {FAILS}")
sys.exit(1 if FAILS else 0)
