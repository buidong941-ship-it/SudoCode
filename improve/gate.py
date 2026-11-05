"""D52: cổng hồi quy tự động trước khi một mục kỹ thuật (gated/) có hiệu lực.

Với từng mục ở gated/: chạy offline (router rules, generator offline, extractor rules, PLANNER_TABLE=1) trên các bộ dev
hai lần — A: chỉ approved/ hiện tại; B: approved/ + mục đó — rồi so:
  1. kịch bản đang QUA ở A mà TRƯỢT ở B → trượt cổng;
  2. lượt KHÔNG dùng mục đó mà goal đổi giữa A và B → trượt cổng (ngưỡng mặc định 0 lượt).
Đạt → approved/ (store.gate_pass); trượt → pending/ kèm danh sách ca hỏng (store.gate_fail).

Chỉ gọi run_eval.py và eval/reference_eval.py qua tiến trình con (improve/ không import core). Không dùng holdout.
Chạy trên Kaggle CPU (máy cá nhân chỉ lưu file):  python -m improve gate --sets test_set/public_sample datagen/out_nat/dev --by "gate"
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

from improve import collect as C
from improve import store as S

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SETS = ["test_set/public_sample", "datagen/out_nat/dev", "datagen/out_btc_like_final_v1_1/final/dev",
                "datagen/out_btc_like_final_v2_1/final/dev", "datagen/out_btc_like_d7/final/dev", "datagen/out_v3/final/dev"]


def _root_with(approved_props, tmp):
    """Thư mục improve tạm chỉ có approved/ = danh sách đề xuất cho trước."""
    d = os.path.join(tmp, "approved")
    os.makedirs(d, exist_ok=True)
    for p in approved_props:
        q = dict(p, status="approved")
        with open(os.path.join(d, f"{p['id']}.json"), "w", encoding="utf-8") as fh:
            json.dump(q, fh, ensure_ascii=False)
    return tmp


def _run(scen, improve_root, out, python):
    env = {**os.environ, "IMPROVE_DIR": improve_root, "IMPROVE_ROOT": improve_root, "PLANNER_TABLE": "1",
           "PRODUCT_LEXICON": "1", "LLM_CACHE": "off", "DATABASE_URL": f"sqlite:///{out}.db", "PLANNER_BACKEND": "rules"}
    subprocess.run([python, os.path.join(PROJECT, "run_eval.py"), "--scenarios", os.path.join(PROJECT, scen), "--config", "full",
                    "--out", out, "--router", "rules", "--generator", "offline", "--extractor", "rules", "--transport", "direct",
                    "--run-id", "gate"], check=True, env=env, cwd=PROJECT, stderr=subprocess.DEVNULL)
    # đạt / trượt từng kịch bản bằng check_call của reference_eval (bản BTC), chạy ở tiến trình con; report.json chỉ giữ 40 ca trượt
    code = ("import json,sys; sys.path.insert(0,'eval'); import reference_eval as R; s=R.load_scenarios(sys.argv[1]); "
            "t=R.load_trace(sys.argv[2]); out=[]\n"
            "for sid,sc in s.items():\n"
            " r=[R.check_call(sp,t.get((sid,c),[]))[0] for c,sp in sc['calls'].items()]; r=[x for x in r if x is not None]\n"
            " out.append(sid) if r and not all(r) else None\n"
            "print(json.dumps(out))")
    res = subprocess.run([python, "-c", code, os.path.join(PROJECT, scen), out], check=True, cwd=PROJECT,
                         capture_output=True, text=True, encoding="utf-8")
    rows = [json.loads(l) for l in open(out, encoding="utf-8") if l.strip()]
    return rows, set(json.loads(res.stdout.strip().splitlines()[-1]))


def _uses(row, prop):
    pid = prop["id"]
    if f"IMP:{pid}" in ((row.get("planner") or {}).get("table") or []):
        return True
    if pid in ((row.get("improve") or {}).get("used") or []) or pid in ((row.get("router") or {}).get("improve") or []):
        return True
    if prop["kind"] == "product_alias":
        txt = (row.get("customer_text") or "").lower()
        return any(f.lower() in txt for f in prop["payload"].get("forms") or [])
    return False


def compare(a_rows, a_fail, b_rows, b_fail, prop, max_unrelated=0):
    """→ (đạt?, lý do[]). Thuần, test được không cần chạy agent."""
    scen = {r["scenario_id"] for r in a_rows}
    broke = sorted(s for s in scen if s not in a_fail and s in b_fail)
    key = lambda r: (r["scenario_id"], r["call"], r["turn"])
    bm = {key(r): r for r in b_rows}
    unrelated = []
    for r in a_rows:
        b = bm.get(key(r))
        if b is None or _uses(b, prop):
            continue
        if (r.get("goals") or []) != (b.get("goals") or []):
            unrelated.append(f"{key(r)}: {r.get('goals')} → {b.get('goals')}")
    reasons = [f"làm trượt kịch bản đang qua: {', '.join(broke)}"] if broke else []
    if len(unrelated) > max_unrelated:
        reasons.append(f"đổi goal ở {len(unrelated)} lượt không dùng mục này: " + "; ".join(unrelated[:5]))
    return not reasons, reasons


def run(sets=None, by="gate", root=None, python=None, max_unrelated=0, apply=True):
    python = python or sys.executable
    sets = [s for s in (sets or DEFAULT_SETS) if os.path.isdir(os.path.join(PROJECT, s))]
    for s in sets:
        C.check_dev_only(s)
    gated = S.list_state("gated", root)
    approved = S.list_state("approved", root)
    results = []
    tmp = tempfile.mkdtemp(prefix="improve_gate_")
    base_root = _root_with(approved, os.path.join(tmp, "base"))
    base = {s: _run(s, base_root, os.path.join(tmp, f"base-{s.replace('/', '_')}.jsonl"), python) for s in sets}
    for prop in gated:
        cand_root = _root_with(approved + [prop], os.path.join(tmp, prop["id"]))
        ok_all, reasons = True, []
        for s in sets:
            b_rows, b_fail = _run(s, cand_root, os.path.join(tmp, f"{prop['id']}-{s.replace('/', '_')}.jsonl"), python)
            ok, why = compare(*base[s], b_rows, b_fail, prop, max_unrelated)
            if not ok:
                ok_all = False
                reasons += [f"[{s}] {w}" for w in why]
        results.append({"id": prop["id"], "kind": prop["kind"], "pass": ok_all, "reasons": reasons})
        if apply:
            (S.gate_pass if ok_all else S.gate_fail)(prop["id"], by, "; ".join(reasons)[:2000] or f"qua cổng trên {len(sets)} bộ", root)
    S.log("gate_run", root, sets=sets, results=results)
    shutil.rmtree(tmp, ignore_errors=True)
    return results
