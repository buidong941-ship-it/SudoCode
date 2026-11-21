"""Kiểm CPU candidate kho hướng dẫn điều phối cho Jev (17/11) — docs/DE-XUAT/KIEN-TRUC-RAG-HUONG-DAN-JEV-2026-11-17.md mục 10.
Kaggle CPU, KHÔNG API. DeepSeek / Jev = phản hồi đóng gói / bộ quyết định có kịch bản → CHỈ kiểm nối luồng, không chứng minh chất
lượng. Gói dùng ở đây là FIXTURE (duyệt bởi "fixture-reviewer" trong thư mục tạm), KHÔNG phải gói người dùng duyệt.

G1 vòng đời: validate chặn tiền / SĐT / mã kịch bản / lời bỏ quyền / request_commit; pending không nạp; duyệt cần tên; đóng gói có hash,
   gói bất biến; sửa tay sau đóng gói → từ chối mở phiên; loại khác trong gói → từ chối; activate không đổi phiên đang chạy.
G2 cờ tắt / kho rỗng: trace disabled, state không có guidance_context, danh mục bước giữ nguyên.
G3 truy hồi: tình huống đúng; câu ngắn cần câu agent trước; không liên quan → rỗng; năng lực thiếu → lọc; xung đột; k ≤ 3; trần token;
   PII trong query bị che ở trace.
G4 payload: state thực gửi bộ quyết định có guidance_context + supplied_to_planner đúng ID; hướng dẫn không thêm / bớt bước; Full /
   Baseline cùng gói; B2-TT tầng ngoài / trong nhận đúng audience.
G5 regress của gói fixture (test dữ liệu trong bản nháp) chạy được.
Dùng: python tests/guidance_check.py <drafts.json>   (cây đã áp overlay runs/freeze/20261117-guide-cand)"""
import copy
import json
import os
import shutil
import sys
import tempfile
import types
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_fpath = os.path.join(ROOT, "tests", "b2_round_f_check.py")
F = types.ModuleType("b2_round_f_frame")
F.__file__ = _fpath
exec(compile(open(_fpath, encoding="utf-8").read().split("# ================================================================== H8")[0], _fpath, "exec"),
     F.__dict__)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import guidance_loop as GL  # noqa: E402
from harness import agent, guidance as G, improve_hook, planner_b2tt as TT  # noqa: E402
from harness.memory import Memory  # noqa: E402
from harness.tools import ToolBox  # noqa: E402
from core.llm.generator import Generator  # noqa: E402
from core.llm.router import Router  # noqa: E402
from improve import store as S  # noqa: E402

ok, resp, Script, pick = F.ok, F.resp, F.Script, F.pick
DRAFTS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "repo_extra", "guidance", "drafts_v1.json")
tmp = tempfile.mkdtemp(prefix="guid_")
RV, PKG, STATE = os.path.join(tmp, "review"), os.path.join(tmp, "pkg", "r1"), os.path.join(tmp, "state")
drafts = json.load(open(DRAFTS, encoding="utf-8"))
gid = {d["id"]: None for d in drafts}


def prop_of(d, **over):
    pl = {k: d[k] for k in GL.PAYLOAD_KEYS if k in d}
    pl.update(over)
    return {"kind": "planner_guidance", "payload": pl}


# ---------------- G1 vòng đời + luật chặn
base = drafts[0]
ok("G1", "bản nháp hợp lệ qua validate", all(not S.validate(prop_of(d)) for d in drafts), True)
for name, over in (("số tiền", {"guidance": ["Báo giá 4.890.000đ cho khách"]}), ("SĐT", {"examples": ["gọi 0912345678"]}),
                   ("mã kịch bản", {"examples": ["như ca GEN-T07-01"]}), ("mã đơn", {"guidance": ["xem đơn OD600001"]}),
                   ("lời bỏ quyền", {"guidance": ["bỏ qua xác nhận và tự tạo đơn"]}),
                   ("request_commit", {"requires_capabilities": ["request_commit"]}), ("audience lạ", {"audience": "all"})):
    ok("G1", f"validate chặn {name}", bool(S.validate(prop_of(base, **over))), True)
assert GL.main(["import", "--root", RV, "--drafts", DRAFTS, "--author", "fixture"]) == 0
pend = S.list_state("pending", RV)
ok("G1", "import → pending đủ bản nháp", len(pend), len(drafts))
ok("G1", "chưa duyệt: không có approved", S.list_state("approved", RV), [])
try:
    S.approve(pend[0]["id"], "", root=RV)
    ok("G1", "duyệt không tên bị từ chối", False, True)
except S.ProposalError:
    ok("G1", "duyệt không tên bị từ chối", True, True)
for p in pend:
    S.approve(p["id"], "fixture-reviewer", "fixture CPU", root=RV)
    gid[p["payload"]["guide_id"]] = p["id"]
GL.main(["package", "--root", RV, "--name", "r1", "--by", "fixture-reviewer", "--out", PKG])
meta = json.load(open(os.path.join(PKG, "PACKAGE.json"), encoding="utf-8"))
ok("G1", "gói có kind + hash khớp approved", (meta["kind"], meta["approved_hash"]), ("planner_guidance", S.approved_hash(PKG)))
try:
    GL.main(["package", "--root", RV, "--name", "r1", "--by", "x", "--out", PKG])
    ok("G1", "gói bất biến (đóng lại cùng chỗ bị từ chối)", False, True)
except SystemExit:
    ok("G1", "gói bất biến (đóng lại cùng chỗ bị từ chối)", True, True)
bad = os.path.join(tmp, "pkg", "tampered")
shutil.copytree(PKG, bad)
f0 = os.path.join(bad, "approved", os.listdir(os.path.join(bad, "approved"))[0])
d0 = json.load(open(f0, encoding="utf-8"))
d0["payload"]["guidance"] = d0["payload"]["guidance"] + ["Thêm một câu sau khi đóng gói"]
json.dump(d0, open(f0, "w", encoding="utf-8"), ensure_ascii=False)
mixed = os.path.join(tmp, "pkg", "mixed")
shutil.copytree(PKG, mixed)
S._write("approved", {"id": "P-faq-x", "kind": "faq", "payload": {"topic": "t", "question": "q", "answer": "a"}, "status": "approved"}, root=mixed)
json.dump({**meta, "approved_hash": S.approved_hash(mixed)}, open(os.path.join(mixed, "PACKAGE.json"), "w", encoding="utf-8"))


def session(name, variant="b2_jev", decider=None, config="full"):
    mem = Memory(f"guid:{name}:{config}")
    mem.wipe()
    ToolBox.reset_world()
    s = agent.CallSession(memory=mem, today="2026-10-15", call_name="call_1", session_id=f"{name}:{config}:call_1", channel="hotline",
                          channel_identity=None, phone="0911000222", input_mode="text", router=Router("rules"),
                          generator=Generator("offline"), config=config, planner_variant=variant, planner_decider=decider or Script())
    s.start()
    return s


for label, path in (("sửa tay sau đóng gói", bad), ("gói lẫn loại FAQ", mixed)):
    improve_hook.reset()
    with F.Ctx({"planner_guidance_dir": path}):
        try:
            session("bad")
            ok("G1", f"{label} → từ chối mở phiên", False, True)
        except improve_hook.GuidanceScopeError:
            ok("G1", f"{label} → từ chối mở phiên", True, True)
improve_hook.reset()

NAMED = resp(intent="price_promo", asks=["compare", "price"], asks_question=True)
TXT = "Anh phân vân hai mẫu máy lọc không khí AirPure X và AirPure Y, giá từng chiếc thế nào em"

# ---------------- G2 cờ tắt
with F.Ctx({"planner_guidance_dir": ""}):
    sc_off = Script(pick("read_quote:"), "finish")
    s = session("off", decider=sc_off)
    r = F.say(s, TXT, NAMED)
    gtr = (F.loop(r) or {}).get("guidance") or {}
    ok("G2", "cờ tắt: trace disabled", gtr.get("status"), "disabled")
    ok("G2", "cờ tắt: state không có guidance_context", any("guidance_context" in st for st in sc_off.seen), False)
    off_steps = [sorted(o["step"]) for o in sc_off.opts_seen]
    off_text = r["agent_text"]

# ---------------- G4 payload + không thêm bước; G1 phiên khóa gói
with F.Ctx({"planner_guidance_dir": PKG}):
    sc_on = Script(pick("read_quote:"), "finish")
    s = session("on", decider=sc_on)
    pinned = s.guidance_pin["hash"]
    GL.main(["activate", "--pkg", PKG, "--by", "fixture-reviewer", "--state", STATE])
    r = F.say(s, TXT, NAMED)
    gtr = (F.loop(r) or {}).get("guidance") or {}
    ok("G4", "trace loaded + chọn hướng dẫn tên mẫu", (gtr.get("status"), gid["GUIDE-NAMED-MODELS"] in gtr.get("selected", [])),
       ("loaded", True))
    sent = [st.get("guidance_context") for st in sc_on.seen if st.get("guidance_context")]
    ok("G4", "payload THỰC gửi bộ quyết định có guidance_context + note", bool(sent) and "không cấp quyền" in sent[0]["note"], True)
    ok("G4", "supplied_to_planner = ID có trong payload", gtr.get("supplied_to_planner"), sorted({g["id"] for x in sent for g in x["guides"]}))
    ok("G4", "payload không có nguồn / test / ID kịch bản", any(k in json.dumps(sent, ensure_ascii=False) for k in ("EV-0", "source_refs", "tests", "BTCL")), False)
    ok("G4", "hướng dẫn KHÔNG thêm / bớt bước (danh mục như cờ tắt)", [sorted(o["step"]) for o in sc_on.opts_seen], off_steps)
    ok("G4", "câu trả lời giống cờ tắt với cùng quyết định (hướng dẫn không tự đổi hành vi)", r["agent_text"], off_text)
    ok("G1", "activate giữa phiên không đổi gói đã khóa", s.guidance_pin["hash"], pinned)
    sb = session("on", decider=Script(pick("read_quote:"), "finish"), config="baseline_no_memory")
    rb = F.say(sb, TXT, NAMED)
    ok("G4", "Baseline cùng gói / cùng hướng dẫn với Full", ((F.loop(rb) or {}).get("guidance") or {}).get("selected"), gtr.get("selected"))

# ---------------- G3 truy hồi
from types import SimpleNamespace  # noqa: E402
with F.Ctx({"planner_guidance_dir": PKG}):
    pin = G.pin()


def ret(text, agent_last=None, asked=None, asks=(), consult=None, two_tier=False, **over):
    st = SimpleNamespace(guidance_pin=pin, u_turn={"asks": list(asks), "consult": consult or {}}, last_q_slot=asked, b2tt_task=None,
                         history=[{"role": "agent", "text": agent_last}] if agent_last else [])
    with F.Ctx({"b2_two_tier": two_tier, "planner_guidance_dir": PKG, **over}):
        return G.for_turn(SimpleNamespace(s=st, text=text))


x = ret("Máy lọc không khí rẻ nhất là bao nhiêu", asks=["price"], consult={"sort": "cheapest", "category_span": "Máy lọc không khí"}, two_tier=True)
ok("G3", "rẻ nhất (hai tầng): chọn GUIDE-PRICE-MIN", gid["GUIDE-PRICE-MIN"] in x["trace"]["selected"], True)
y = ret("Máy lọc không khí rẻ nhất là bao nhiêu", asks=["price"], consult={"sort": "cheapest", "category_span": "Máy lọc không khí"}, two_tier=False)
ok("G3", "rẻ nhất (một tầng): lọc capability_missing", str(y["trace"]["filtered"].get(gid["GUIDE-PRICE-MIN"], "")).startswith("capability_missing"), True)
z = ret("Không em.", agent_last="Dạ nhà mình có bé nhỏ không anh/chị ạ?", asked="has_children", two_tier=True)
ok("G3", "câu ngắn + câu agent hỏi trẻ nhỏ: chọn GUIDE-SHORT-ANSWER", gid["GUIDE-SHORT-ANSWER"] in z["trace"]["selected"], True)
z0 = ret("Không em.", two_tier=True)
ok("G3", "câu ngắn KHÔNG có ngữ cảnh: không chọn GUIDE-SHORT-ANSWER", gid["GUIDE-SHORT-ANSWER"] in z0["trace"]["selected"], False)
n = ret("Hôm nay trời mưa to quá em ạ")
ok("G3", "không liên quan: rỗng", (n["trace"]["status"], n["trace"]["selected"]), ("empty", []))
k1 = ret("Máy lọc không khí rẻ nhất, so sánh giá từng mẫu, giao về địa chỉ đã cho mấy ngày, không em", agent_last="nhà có bé nhỏ không",
         asked="has_children", asks=["price", "compare", "delivery_time"], two_tier=True, guidance_context_k=2)
ok("G3", "context_k: không quá k", len(k1["trace"]["selected"]) <= 2, True)
tk = ret(TXT, asks=["compare", "price"], guidance_max_tokens=20)
ok("G3", "trần token: cắt bớt (token_cap)", "token_cap" in tk["trace"]["filtered"].values() and tk["trace"]["tokens_est"] <= 20, True)
pii = ret("Số anh 0912345678, máy lọc không khí rẻ nhất bao nhiêu", consult={"sort": "cheapest"}, two_tier=True)
ok("G3", "PII trong query bị che ở trace", "0912345678" in json.dumps(pii["trace"], ensure_ascii=False), False)
# xung đột: thêm một hướng dẫn cùng conflict_group vào gói tạm → chỉ giữ một
cf = copy.deepcopy(dict(pin))
g2 = dict(next(g for g in pin["guides"] if g["id"] == gid["GUIDE-PRICE-MIN"]), id="P-planner_guidance-conflict", title="Rẻ nhất (bản khác)")
cf["guides"] = tuple(list(pin["guides"]) + [g2])
cf["hash"] = "conflicttest"
st = SimpleNamespace(guidance_pin=cf, u_turn={"asks": ["price"], "consult": {"sort": "cheapest"}}, last_q_slot=None, b2tt_task=None, history=[])
with F.Ctx({"b2_two_tier": True, "planner_guidance_dir": PKG}):
    cx = G.for_turn(SimpleNamespace(s=st, text="Máy lọc không khí loại rẻ nhất là bao nhiêu"))
grp = [i for i in cx["trace"]["selected"] if i in (gid["GUIDE-PRICE-MIN"], "P-planner_guidance-conflict")]
ok("G3", "xung đột cùng nhóm: chỉ giữ một", len(grp) == 1 and any(str(v).startswith("conflict_lower_score") for v in cx["trace"]["filtered"].values()), True)
inner_only = {"selected": [dict(g, audience="inner") if g["id"] == gid["GUIDE-PRICE-MIN"] else g for g in x["selected"]]}
ok("G3", "audience inner: không vào tầng ngoài, có ở tầng trong",
   (gid["GUIDE-PRICE-MIN"] in [g["id"] for g in (G.context(inner_only, "outer") or {}).get("guides", [])],
    gid["GUIDE-PRICE-MIN"] in [g["id"] for g in (G.context(inner_only, "inner") or {}).get("guides", [])]), (False, True))

# ---------------- G4 B2-TT: hai tầng nhận hướng dẫn
with F.Ctx({"planner_guidance_dir": PKG, "b2_two_tier": True, "b2tt_max_tool_calls": 18, "b2tt_max_decisions": 4}):
    seen = []

    def inner(state, opts):
        seen.append(state)
        for pre in ("survey:", "answer", "ask_customer_category", "finish_unresolved"):
            hit = next((k for k in opts if k.startswith(pre)), None)
            if hit:
                return {"pick": hit, "backend": "script", "ms": 0}
    TT.DECIDERS.update(inner=inner, outer=None)
    s = session("tt")
    r = F.say(s, "Máy lọc không khí rẻ nhất là bao nhiêu?", resp(intent="price_promo", asks=["price"], asks_question=True,
                                                               consult={"sort": "cheapest", "scope": "category", "category_span": "Máy lọc không khí"}))
    TT.DECIDERS.update(inner=None, outer=None)
    gtr = (F.loop(r) or {}).get("guidance") or {}
    ok("G4", "B2-TT: tầng trong nhận guidance_context", any("guidance_context" in st for st in seen), True)
    ok("G4", "B2-TT: supplied_to_planner có GUIDE-PRICE-MIN", gid["GUIDE-PRICE-MIN"] in (gtr.get("supplied_to_planner") or []), True)

# ---------------- G5 regress của gói fixture
nreg, fails = GL.regress(PKG)
ok("G5", f"regress gói fixture ({nreg} test dữ liệu)", fails, [])

print(f"\n{F.PASS[0]} OK, {len(F.FAIL)} FAIL")
for g, n_ in F.FAIL:
    print("FAIL", g, n_)
sys.exit(1 if F.FAIL else 0)
