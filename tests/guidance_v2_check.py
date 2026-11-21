"""18/11 DI17 (freeze integ-ui4): kiểm lọc truy hồi theo asks có kiểu + planner chính không nhận hướng dẫn tầng trong.
Không model, không API. Dùng khung tests/b2_round_f_check.py (như tests/guidance_check.py).

V1 store / schema: asks_any hợp lệ qua validate; nhãn lạ bị chặn; GUIDE_ASKS (improve) == harness.understanding.ASKS; schema có asks_any.
V2 truy hồi: asks giao asks_any → giữ; không giao (kể cả lượt không hỏi gì) → lọc asks_mismatch; hướng dẫn không khai asks_any không
   bị ảnh hưởng. Mutant: bỏ asks_any → câu không hỏi gì lại kéo hướng dẫn (test phát hiện được khác biệt).
V3 audience: context("main") bỏ inner, context("inner") / ("outer") như cũ; hướng dẫn inner điểm cao KHÔNG chiếm chỗ k của planner
   chính (chọn từ eligible theo audience); trần token áp theo từng audience.
V4 đường thật: gói đóng bằng guidance_loop giữ asks_any qua improve_hook (pin); phiên B2 một tầng: trace `selected` có hướng dẫn
   inner nhưng payload THỰC gửi planner chính (guidance_context) và supplied_to_planner KHÔNG có; mutant planner_b2 gọi context
   không audience → test phát hiện inner lọt vào payload.
V5 gói nháp thật (đối số 1, mặc định repo_extra/guidance/drafts_v2.json): regress ở MIN_SCORE 3.0 / CONTEXT_K 2 / MAX_TOKENS 800 đạt.
Dùng: python tests/guidance_v2_check.py [drafts_v2.json]"""
import json
import os
import sys
import tempfile
import types
from types import SimpleNamespace
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_fpath = os.path.join(ROOT, "tests", "b2_round_f_check.py")
F = types.ModuleType("b2_round_f_frame")
F.__file__ = _fpath
exec(compile(open(_fpath, encoding="utf-8").read().split("# ================================================================== H8")[0], _fpath, "exec"),
     F.__dict__)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import guidance_loop as GL  # noqa: E402
from harness import agent, guidance as G, improve_hook, understanding as U  # noqa: E402
from harness.memory import Memory  # noqa: E402
from harness.tools import ToolBox  # noqa: E402
from core.llm.generator import Generator  # noqa: E402
from core.llm.router import Router  # noqa: E402
from improve import store as S  # noqa: E402

ok, resp, Script, pick = F.ok, F.resp, F.Script, F.pick
DRAFTS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "repo_extra", "guidance", "drafts_v2.json")
tmp = tempfile.mkdtemp(prefix="gv2_")


def guide(gid, audience="both", asks_any=None, caps=(), title=None, examples=None, group=None):
    g = {"id": gid, "guide_id": gid, "version": 1, "title": title or f"Hướng dẫn {gid}", "audience": audience,
         "tags": ["mau_cu_the"], "applies_when": ["Khách hỏi giá hai mẫu máy lọc không khí cụ thể"],
         "guidance": ["Đọc giá từng mẫu khách nêu"], "examples": examples or ["Giá từng mẫu máy lọc không khí thế nào em"],
         "requires_capabilities": list(caps)}
    if asks_any is not None:
        g["asks_any"] = list(asks_any)
    if group:
        g["conflict_group"] = group
    return g


def prop(g):
    pl = {k: g[k] for k in GL.PAYLOAD_KEYS if k in g}
    pl["guide_id"] = g["guide_id"]
    return {"kind": "planner_guidance", "payload": pl}


# ---------------- V1 store / schema
ok("V1", "asks_any hợp lệ qua validate", S.validate(prop(guide("GUIDE-A", asks_any=["price", "compare"]))), [])
ok("V1", "asks_any nhãn lạ bị chặn", bool(S.validate(prop(guide("GUIDE-A", asks_any=["gia_ca"])))), True)
ok("V1", "GUIDE_ASKS == harness.understanding.ASKS", sorted(S.GUIDE_ASKS), sorted(U.ASKS))
sch = json.load(open(os.path.join(ROOT, "schemas", "planner_guidance.schema.json"), encoding="utf-8"))
ok("V1", "schema có asks_any đúng nhãn", sorted(sch["properties"]["asks_any"]["items"]["enum"]), sorted(U.ASKS))
ok("V1", "asks_any có trong PAYLOAD_KEYS / improve_hook / guidance_edit / ui.engine",
   all("asks_any" in open(os.path.join(ROOT, p), encoding="utf-8").read() for p in
       ("scripts/guidance_loop.py", "harness/improve_hook.py", "improve/guidance_edit.py", "ui/engine.py")), True)


def ret(guides, text, asks=(), **over):
    pin = {"hash": "v2-" + str(abs(hash(json.dumps(guides, sort_keys=True, ensure_ascii=False)))), "guides": tuple(guides)}
    st = SimpleNamespace(guidance_pin=pin, u_turn={"asks": list(asks), "consult": {}}, last_q_slot=None, b2tt_task=None, history=[])
    with F.Ctx({"guidance_min_score": 0.5, "guidance_context_k": 2, "guidance_max_tokens": 800, "guidance_fetch_k": 15, **over}):
        r = G.for_turn(SimpleNamespace(s=st, text=text))
        return r, {a: [g["id"] for g in ((G.context(r, a) or {}).get("guides") or [])] for a in ("main", "inner", "outer")}


TXT = "Giá từng mẫu máy lọc không khí thế nào em"
# ---------------- V2 lọc asks
gA = guide("GUIDE-A", asks_any=["price", "compare"])
r, _ = ret([gA], TXT, asks=["price"])
ok("V2", "asks giao asks_any → giữ", r["trace"]["selected"], ["GUIDE-A"])
r, _ = ret([gA], TXT, asks=[])
ok("V2", "lượt không hỏi gì → lọc asks_mismatch", (r["trace"]["selected"], r["trace"]["filtered"].get("GUIDE-A")), ([], "asks_mismatch"))
r, _ = ret([gA], TXT, asks=["delivery_time"])
ok("V2", "asks không giao → lọc asks_mismatch", r["trace"]["filtered"].get("GUIDE-A"), "asks_mismatch")
gN = guide("GUIDE-N")
r, _ = ret([gN], TXT, asks=[])
ok("V2", "không khai asks_any → không bị lọc theo asks", r["trace"]["selected"], ["GUIDE-N"])
mut = dict(gA); mut.pop("asks_any")
r_m, _ = ret([mut], TXT, asks=[])
ok("V2", "mutant bỏ asks_any: kết quả khác (test bắt được)", r_m["trace"]["selected"] != [], True)

# ---------------- V3 audience
gI = guide("GUIDE-I", audience="inner", title="Hướng dẫn giá từng mẫu máy lọc không khí cụ thể",
           examples=["Giá từng mẫu máy lọc không khí thế nào em", "Giá từng mẫu máy lọc không khí cụ thể"])
gB = guide("GUIDE-B", audience="both")
gO = guide("GUIDE-O", audience="outer")
r, ctx = ret([gI, gB, gO], TXT, asks=["price"], guidance_context_k=1)
ok("V3", "tiền đề: inner điểm cao nhất, trace selected (k=1) là inner", r["trace"]["selected"], ["GUIDE-I"])
ok("V3", "main: không có inner, vẫn nhận 1 hướng dẫn không-inner (inner không chiếm chỗ)", (len(ctx["main"]), "GUIDE-I" in ctx["main"]), (1, False))
ok("V3", "inner: nhận inner", ctx["inner"], ["GUIDE-I"])
ok("V3", "outer: không có inner", "GUIDE-I" in ctx["outer"], False)
r, ctx = ret([gI, gB, gO], TXT, asks=["price"], guidance_context_k=3)
ok("V3", "main k=3: both + outer, không inner", sorted(ctx["main"]), ["GUIDE-B", "GUIDE-O"])
r, ctx = ret([gI, gB, gO], TXT, asks=["price"], guidance_context_k=3, guidance_max_tokens=60)
ok("V3", "trần token áp theo audience (main ≤ trần)", G._tokens([g for g in (gB, gO) if g["id"] in ctx["main"]]) <= 60, True)
legacy = {"selected": [gI, gB]}
ok("V3", "dữ liệu cũ chỉ có selected: main vẫn bỏ inner", [g["id"] for g in (G.context(legacy, "main") or {}).get("guides", [])], ["GUIDE-B"])

# ---------------- V4 đường thật: gói + phiên B2 một tầng
RV, PKG = os.path.join(tmp, "rv"), os.path.join(tmp, "pkg")
fx = [dict(gI, id=None), dict(gB, id=None, asks_any=["price", "compare"])]
dr = os.path.join(tmp, "fx.json")
json.dump([{k: v for k, v in g.items() if k != "id"} | {"id": g["guide_id"], "tests": []} for g in fx], open(dr, "w", encoding="utf-8"),
          ensure_ascii=False)
assert GL.main(["import", "--root", RV, "--drafts", dr, "--author", "fixture"]) == 0
ids = {}
for p in S.list_state("pending", RV):
    S.approve(p["id"], "fixture-reviewer", "fixture CPU", root=RV)
    ids[p["payload"]["guide_id"]] = p["id"]
GL.main(["package", "--root", RV, "--name", "v2fx", "--by", "fixture-reviewer", "--out", PKG])
improve_hook.reset()
with F.Ctx({"planner_guidance_dir": PKG}):
    pin = G.pin()
ok("V4", "gói qua improve_hook giữ asks_any", [g.get("asks_any") for g in pin["guides"] if g["guide_id"] == "GUIDE-B"], [["price", "compare"]])


def session(name, decider):
    mem = Memory(f"gv2:{name}:full")
    mem.wipe()
    ToolBox.reset_world()
    s = agent.CallSession(memory=mem, today="2026-10-15", call_name="call_1", session_id=f"{name}:full:call_1", channel="hotline",
                          channel_identity=None, phone="0911000333", input_mode="text", router=Router("rules"),
                          generator=Generator("offline"), config="full", planner_variant="b2_jev", planner_decider=decider)
    s.start()
    return s


NAMED = resp(intent="price_promo", asks=["compare", "price"], asks_question=True)
TXT2 = "Anh phân vân hai mẫu máy lọc không khí AirPure X và AirPure Y, giá từng mẫu máy lọc không khí cụ thể thế nào em"


def run_main(tag):
    sc = Script(pick("read_quote:"), "finish")
    with F.Ctx({"planner_guidance_dir": PKG, "b2_two_tier": False, "guidance_min_score": 0.5, "guidance_context_k": 2}):
        improve_hook.reset()
        s = session(tag, sc)
        r = F.say(s, TXT2, NAMED)
    gtr = (F.loop(r) or {}).get("guidance") or {}
    sent = [st["guidance_context"] for st in sc.seen if "guidance_context" in st]
    return gtr, sent


gtr, sent = run_main("main")
sent_ids = sorted({g["id"] for x in sent for g in x["guides"]})
ok("V4", "tiền đề: trace selected có hướng dẫn inner", ids["GUIDE-I"] in (gtr.get("selected") or []), True)
ok("V4", "payload THỰC gửi planner chính không có inner", ids["GUIDE-I"] in sent_ids, False)
ok("V4", "payload planner chính có hướng dẫn both", ids["GUIDE-B"] in sent_ids, True)
ok("V4", "supplied_to_planner = ID trong payload, không inner", (gtr.get("supplied_to_planner"), ids["GUIDE-I"] in (gtr.get("supplied_to_planner") or [])),
   (sent_ids, False))
_orig = G.context
with patch.object(G, "context", lambda sel, audience=None: _orig(sel, None)):
    _, sent_m = run_main("mutant")
ok("V4", "mutant planner_b2 bỏ audience: inner lọt vào payload (test bắt được)", ids["GUIDE-I"] in {g["id"] for x in sent_m for g in x["guides"]}, True)

# ---------------- V5 gói nháp thật ở cấu hình chốt
if os.path.exists(DRAFTS):
    RV2, PKG2 = os.path.join(tmp, "rv2"), os.path.join(tmp, "pkg2")
    assert GL.main(["import", "--root", RV2, "--drafts", DRAFTS, "--author", "fixture"]) == 0
    for p in S.list_state("pending", RV2):
        S.approve(p["id"], "fixture-reviewer", "fixture CPU", root=RV2)
    GL.main(["package", "--root", RV2, "--name", "v2real", "--by", "fixture-reviewer", "--out", PKG2])
    with F.Ctx({"guidance_min_score": 3.0, "guidance_context_k": 2, "guidance_max_tokens": 800, "guidance_fetch_k": 15}):
        improve_hook.reset()
        nreg, fails = GL.regress(PKG2)
    ok("V5", f"regress drafts_v2 ở 3.0 / K=2 ({nreg} test)", fails, [])
    ok("V5", "mọi nháp khai asks_any", all(d.get("asks_any") for d in json.load(open(DRAFTS, encoding="utf-8"))), True)
else:
    ok("V5", "có tệp drafts_v2", False, True)

print(f"\n{F.PASS[0]} OK, {len(F.FAIL)} FAIL")
for g, n_ in F.FAIL:
    print("FAIL", g, n_)
sys.exit(1 if F.FAIL else 0)
