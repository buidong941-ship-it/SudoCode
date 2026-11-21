"""18/11 (freeze integ-ui5): hướng dẫn inner / outer / both được đưa ĐÚNG NƠI trên đường chạy thật; finish_unresolved (chưa survey)
chuyển lượt về luồng chính và luồng chính tiếp tục chạy với đúng tập hướng dẫn. Không model, không API.
A1 hàm thật planner_b2tt._with_guidance: tầng outer nhận outer + both (không inner); tầng inner nhận inner + both (không outer).
A2 context("main") (planner chính) nhận outer + both, không inner.
A3 phiên B2-TT thật (bộ quyết định có kịch bản): tầng trong chọn finish_unresolved trước survey → outcome unresolved_delegated →
   planner chính VẪN được gọi (luồng tiếp tục) và payload THỰC của nó không có hướng dẫn inner, có both; payload tầng trong có
   inner + both, không outer. supplied_to_planner = hợp ID thực đã gửi.
Dùng: python tests/guidance_v3_check.py"""
import json
import os
import sys
import tempfile
import types
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_fpath = os.path.join(ROOT, "tests", "b2_round_f_check.py")
F = types.ModuleType("b2_round_f_frame")
F.__file__ = _fpath
exec(compile(open(_fpath, encoding="utf-8").read().split("# ================================================================== H8")[0], _fpath, "exec"),
     F.__dict__)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import guidance_loop as GL  # noqa: E402
from harness import guidance as G, improve_hook, planner_b2tt as TT  # noqa: E402
from improve import store as S  # noqa: E402

ok, resp, Script, pick = F.ok, F.resp, F.Script, F.pick
tmp = tempfile.mkdtemp(prefix="gv3_")
TXT = "Máy lọc không khí rẻ nhất là bao nhiêu?"


def guide(gid, audience):
    return {"id": gid, "guide_id": gid, "version": 1, "title": f"Máy lọc không khí rẻ nhất {audience}", "audience": audience,
            "tags": ["re_nhat"], "applies_when": ["Khách hỏi máy lọc không khí rẻ nhất"], "guidance": ["Đọc giá các mẫu trong nhóm"],
            "examples": ["Máy lọc không khí rẻ nhất là bao nhiêu"], "requires_capabilities": [], "tests": []}


GI, GO, GB = guide("GUIDE-AI", "inner"), guide("GUIDE-AO", "outer"), guide("GUIDE-AB", "both")
pin = {"hash": "v3-aud", "guides": tuple({k: v for k, v in g.items() if k != "tests"} for g in (GI, GO, GB))}
with F.Ctx({"guidance_min_score": 0.1, "guidance_context_k": 3, "guidance_max_tokens": 800, "guidance_fetch_k": 15, "b2_two_tier": True}):
    st = SimpleNamespace(guidance_pin=pin, u_turn={"asks": ["price"], "consult": {}}, last_q_slot=None, b2tt_task=None, history=[])
    sel = G.for_turn(SimpleNamespace(s=st, text=TXT))
    t = SimpleNamespace(guidance=sel, guidance_supplied=set())
    outer = [g["id"] for g in (TT._with_guidance({}, t, "outer").get("guidance_context") or {}).get("guides", [])]
    inner = [g["id"] for g in (TT._with_guidance({}, t, "inner").get("guidance_context") or {}).get("guides", [])]
    main = [g["id"] for g in (G.context(sel, "main") or {}).get("guides", [])]
ok("A1", "tiền đề: cả 3 hướng dẫn đủ điều kiện", sorted(sel["trace"]["eligible"]), ["GUIDE-AB", "GUIDE-AI", "GUIDE-AO"])
ok("A1", "outer nhận outer + both, không inner", sorted(outer), ["GUIDE-AB", "GUIDE-AO"])
ok("A1", "inner nhận inner + both, không outer", sorted(inner), ["GUIDE-AB", "GUIDE-AI"])
ok("A2", "main nhận outer + both, không inner", sorted(main), ["GUIDE-AB", "GUIDE-AO"])

# ---------------- A3 phiên B2-TT thật
RV, PKG = os.path.join(tmp, "rv"), os.path.join(tmp, "pkg")
dr = os.path.join(tmp, "d.json")
json.dump([dict(g) for g in (GI, GB)], open(dr, "w", encoding="utf-8"), ensure_ascii=False)
assert GL.main(["import", "--root", RV, "--drafts", dr, "--author", "fixture"]) == 0
ids = {}
for p in S.list_state("pending", RV):
    S.approve(p["id"], "fixture-reviewer", "fixture CPU", root=RV)
    ids[p["payload"]["guide_id"]] = p["id"]
GL.main(["package", "--root", RV, "--name", "aud", "--by", "fixture-reviewer", "--out", PKG])
seen_inner = []


def inner_dec(state, opts):
    seen_inner.append((state, dict(opts)))
    return {"pick": "finish_unresolved", "backend": "script", "ms": 0}


main_dec = Script(pick("read_quote:", "answer_ask:"), "finish")
with F.Ctx({"planner_guidance_dir": PKG, "b2_two_tier": True, "b2tt_max_tool_calls": 18, "b2tt_max_decisions": 4,
            "guidance_min_score": 0.1, "guidance_context_k": 2}):
    improve_hook.reset()
    TT.DECIDERS.update(inner=inner_dec, outer=None)
    try:
        s = F.session("aud", decider=main_dec)
        r = F.say(s, TXT, resp(intent="price_promo", asks=["price"], asks_question=True,
                               consult={"sort": "cheapest", "scope": "category", "category_span": "Máy lọc không khí"}))
    finally:
        TT.DECIDERS.update(inner=None, outer=None)
lp = F.loop(r) or {}
tt = lp.get("two_tier") or {}
ok("A3", "tiền đề: tầng trong được gọi và thấy finish_unresolved", bool(seen_inner) and "finish_unresolved" in seen_inner[0][1], True)
ok("A3", "finish_unresolved trước survey → unresolved_delegated", tt.get("outcome"), "unresolved_delegated")
ok("A3", "luồng chính vẫn chạy sau delegate (planner chính được gọi)", len(main_dec.seen) >= 1, True)
inner_ids = {g["id"] for st_, _ in seen_inner for g in (st_.get("guidance_context") or {}).get("guides", [])}
main_ids = {g["id"] for st_ in main_dec.seen for g in (st_.get("guidance_context") or {}).get("guides", [])}
ok("A3", "payload tầng trong: có inner + both", inner_ids, {ids["GUIDE-AI"], ids["GUIDE-AB"]})
ok("A3", "payload planner chính: có both, không inner", main_ids, {ids["GUIDE-AB"]})
ok("A3", "supplied_to_planner = hợp ID thực đã gửi", sorted((lp.get("guidance") or {}).get("supplied_to_planner") or []), sorted(inner_ids | main_ids))

print(f"\n{F.PASS[0]} OK, {len(F.FAIL)} FAIL")
for g, n_ in F.FAIL:
    print("FAIL", g, n_)
sys.exit(1 if F.FAIL else 0)
