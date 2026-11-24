"""Kaggle only. Cơ chế cải tiến C.5 trên code v6p15 (ARCH=target, cờ profile v6p15):
(A) IMPROVE_DIR=improve (41 exemplar + 3 playbook, không FAQ) → preflight phải từ chối (thiết kế 16/11: target chỉ nhận FAQ);
(B) gói hướng dẫn planner r1-ui7c-1119 nạp được, pin() khóa đúng hash, lọc năng lực theo planner hiện hành, dựng được
guidance_context cho từng audience; (C) các bộ kiểm cũ của vòng cải tiến chạy trên code v6p15."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = "repo_extra/guidance_pkg_r1"
V6P15 = {"ARCH": "target", "PLANNER_VARIANT": "b2_jev", "B2_TWO_TIER": "1", "JEV_WRITE_GATE": "1", "WRITE_PATH_GATE": "1",
         "PICK_BY_NAME": "1", "DOC_ANSWER": "1", "LINE_SKU_UPDATE": "1", "ORDER_EXT_TOOLS": "0", "DONE_NO_HANDOFF": "0",
         "LLM_CACHE": "off", "PYTHONIOENCODING": "utf-8"}
passed, failed = 0, []


def check(name, ok, detail=""):
    global passed
    print(("PASS " if ok else "FAIL ") + name + (f"  | {detail}" if detail else ""), flush=True)
    if ok:
        passed += 1
    else:
        failed.append(name)


def py(code, extra):
    env = {k: v for k, v in os.environ.items() if k not in ("IMPROVE_DIR", "PLANNER_GUIDANCE_DIR")}
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env={**env, **V6P15, **extra}, capture_output=True, text=True)


r = py("from harness import improve_hook as I; print(I.preflight())", {"IMPROVE_DIR": "improve"})
check("A: IMPROVE_DIR=improve (exemplar/playbook) bị từ chối ở ARCH=target", r.returncode != 0 and "ImproveScopeError" in r.stderr,
      (r.stderr.strip().splitlines() or [""])[-1][:200])
r = py("from harness import improve_hook as I; print(I.preflight())", {"IMPROVE_DIR": ""})
check("A: IMPROVE_DIR rỗng → tắt, không lỗi", r.returncode == 0 and r.stdout.strip() == "None", r.stdout.strip()[:80])

code_b = r'''
import json
from harness import guidance as G
p = G.pin()
caps = sorted(G.capabilities())
need = {g["id"]: sorted(set(g.get("requires") or g.get("capabilities") or [])) for g in p["guides"]}
miss = {k: sorted(set(v) - set(caps)) for k, v in need.items() if set(v) - set(caps)}
sel = {"eligible": p["guides"]}
ctx = {a: [g["id"] for g in (G.context(sel, a) or {}).get("guides") or []] for a in ("main", "outer", "inner")}
print(json.dumps({"name": p["name"], "hash": p["hash"], "n": len(p["guides"]), "caps": caps, "capability_missing": miss, "context": ctx,
                  "guides": [{"id": g["id"], "audience": g.get("audience"), "asks_any": g.get("asks_any"), "title": (g.get("title") or g.get("text") or "")[:90]} for g in p["guides"]]},
                 ensure_ascii=False))
'''
r = py(code_b, {"PLANNER_GUIDANCE_DIR": PKG})
ok = r.returncode == 0
check("B: gói r1-ui7c-1119 nạp được trên v6p15 (pin)", ok, (r.stderr.strip().splitlines() or [""])[-1][:200] if not ok else "")
if ok:
    info = json.loads(r.stdout.strip().splitlines()[-1])
    print(json.dumps(info, ensure_ascii=False, indent=1), flush=True)
    check("B: hash khớp PACKAGE.json", info["hash"] == json.loads((ROOT / PKG / "PACKAGE.json").read_text(encoding="utf-8"))["approved_hash"])
    check("B: có hướng dẫn cho planner chính", bool(info["context"]["main"]), str(info["context"]))
    print("capability_missing (hướng dẫn cần năng lực planner v6p15 không có):", info["capability_missing"], flush=True)

for t in ("tests/guidance_v3_check.py", "tests/improve_hook_check.py", "tests/c5_loop_check.py", "tests/ui_guidance_check_v1_1.py"):
    r = subprocess.run([sys.executable, t], cwd=ROOT, env={**os.environ, "PYTHONIOENCODING": "utf-8", "LLM_CACHE": "off"},
                       capture_output=True, text=True)
    tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
    check(f"C: {t} trên code v6p15", r.returncode == 0, " / ".join(tail)[:300])

print("c5 compat:", passed, "PASS,", len(failed), "FAIL", failed, flush=True)
assert not failed, failed
