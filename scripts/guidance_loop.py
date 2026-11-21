"""Vòng đời kho hướng dẫn điều phối cho Jev (17/11 candidate) — tái dùng improve/store (pending → approved → gói → activate).

    python scripts/guidance_loop.py import   --root R --drafts drafts.json --author "Claude (Opus 5.5)"   # bản nháp → pending/
    python scripts/guidance_loop.py approve  --root R --id P-... --by "Tên" [--reason ...]               # NGƯỜI duyệt (không tự động)
    python scripts/guidance_loop.py reject   --root R --id P-... --by "Tên" [--reason ...]
    python scripts/guidance_loop.py package  --root R --name r1 --by "Tên" --out runs/c5/guidance_packages/r1
    python scripts/guidance_loop.py regress  --pkg runs/c5/guidance_packages/r1                            # kiểm truy hồi (code, không model)
    python scripts/guidance_loop.py activate --pkg ... --by "Tên" [--reason ...] [--state data/c5/guidance]
    python scripts/guidance_loop.py rollback --by "Tên" [--reason ...] [--state ...]
    python scripts/guidance_loop.py status   [--state ...]

- Bản nháp có thể kèm `tests` (dữ liệu, không code): [{"name", "customer_text", "agent_last"?, "asked_slot"?, "asks"?, "expect":
  "selected" | "not_selected"}]. Gói xuất tests vào regression/; `regress` chạy truy hồi thật (harness.guidance) trên gói.
- Gói = root store chỉ chứa approved/ loại planner_guidance + PACKAGE.json (kind, approved_hash, schema) + regression/.
  Bất biến sau khi đóng: sửa nội dung → hash mới → gói mới. Không tự activate. Eval truyền PLANNER_GUIDANCE_DIR tường minh;
  active.json chỉ cho UI / phiên mở sau.
"""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from improve import guidance_edit as GE  # noqa: E402
from improve import store as S  # noqa: E402

SCHEMA = "planner_guidance/1"
STATE_DIR = os.path.join(ROOT, "data", "c5", "guidance")
PAYLOAD_KEYS = ("version", "title", "audience", "tags", "applies_when", "exceptions", "guidance", "avoid", "examples",
                "counterexamples", "requires_capabilities", "conflict_group", "asks_any")


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def cmd_import(a):
    drafts = json.load(open(a.drafts, encoding="utf-8"))
    res = {"pending": [], "invalid": []}
    for d in drafts:
        pl = {k: d[k] for k in PAYLOAD_KEYS if k in d}
        pl["guide_id"] = d.get("id")
        prop = {"kind": "planner_guidance", "payload": pl, "source_gaps": list(d.get("source_refs") or []),
                "title": d.get("title"), "tests": d.get("tests") or [], "classification": d.get("classification")}
        errs = S.validate(prop)
        if errs:
            res["invalid"].append({"id": d.get("id"), "errors": errs[:5]})
            continue
        st, pid = S.propose(prop, author=a.author, root=a.root)
        res["pending"].append({"guide": d.get("id"), "id": pid, "state": st})
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 1 if res["invalid"] else 0


def cmd_review(a, approve):
    sup = []
    if approve:
        _, sup = GE.approve(a.id, a.by, a.reason or "", root=a.root)     # 18/11: bản đã duyệt cũ cùng guide_id → rejected (supersede)
    else:
        S.reject(a.id, a.by, a.reason or "", root=a.root)
    print(json.dumps({"id": a.id, "state": "approved" if approve else "rejected", "by": a.by, "superseded": sup}, ensure_ascii=False))


def cmd_package(a):
    appr = [p for p in S.list_state("approved", a.root) if p["kind"] == "planner_guidance"]
    if not appr:
        sys.exit("không có hướng dẫn đã duyệt")
    dup = GE.approved_duplicates(a.root)
    if dup:
        sys.exit(f"nhiều phiên bản cùng hướng dẫn đang ở 'đã duyệt' {dup} — đưa bản cũ về chờ duyệt / loại trước khi đóng gói")
    if os.path.exists(a.out):
        sys.exit(f"{a.out} đã có — gói bất biến, đặt tên mới")
    os.makedirs(os.path.join(a.out, "approved"))
    os.makedirs(os.path.join(a.out, "regression"))
    for p in appr:
        with open(os.path.join(a.out, "approved", f"{p['id']}.json"), "w", encoding="utf-8") as fh:
            json.dump(p, fh, ensure_ascii=False, indent=1)
        for i, tcase in enumerate(p.get("tests") or []):
            with open(os.path.join(a.out, "regression", f"{p['id']}_{i}.json"), "w", encoding="utf-8") as fh:
                json.dump({"guide": p["id"], **tcase}, fh, ensure_ascii=False, indent=1)
    h = S.approved_hash(a.out)
    meta = {"kind": "planner_guidance", "schema": SCHEMA, "name": a.name, "approved_hash": h, "n": len(appr), "by": a.by, "at": now(),
            "ids": [p["id"] for p in appr]}
    with open(os.path.join(a.out, "PACKAGE.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=1)
    print(json.dumps(meta, ensure_ascii=False))


def regress(pkg):
    """Chạy truy hồi THẬT (harness.guidance) trên từng test của gói. → (ok, fails)."""
    from types import SimpleNamespace
    from core.config import settings
    from harness import guidance as G, improve_hook
    old = settings.planner_guidance_dir
    settings.planner_guidance_dir = pkg
    improve_hook.reset()
    try:
        pin = G.pin()
    finally:
        settings.planner_guidance_dir = old
    fails, n = [], 0
    for f in sorted(os.listdir(os.path.join(pkg, "regression"))):
        tc = json.load(open(os.path.join(pkg, "regression", f), encoding="utf-8"))
        hist = [{"role": "agent", "text": tc["agent_last"]}] if tc.get("agent_last") else []
        s = SimpleNamespace(guidance_pin=pin, u_turn={"asks": tc.get("asks") or [], "consult": tc.get("consult") or {}}, history=hist,
                            last_q_slot=tc.get("asked_slot"), b2tt_task=None)
        tt0 = settings.b2_two_tier
        settings.b2_two_tier = bool(tc.get("two_tier"))      # năng lực của planner mà test giả định (một tầng / B2-TT)
        try:
            sel = G.for_turn(SimpleNamespace(s=s, text=tc["customer_text"]))
        finally:
            settings.b2_two_tier = tt0
        hit = tc["guide"] in [g["id"] for g in sel["selected"]]
        want = tc["expect"] == "selected"
        n += 1
        if hit != want:
            fails.append({"test": f, "expect": tc["expect"], "selected": sel["trace"]["selected"], "candidates": sel["trace"]["candidates"]})
    return n, fails


def cmd_regress(a):
    n, fails = regress(a.pkg)
    print(json.dumps({"tests": n, "fails": fails}, ensure_ascii=False, indent=1))
    return 1 if fails else 0


def _state(a):
    os.makedirs(a.state, exist_ok=True)
    return os.path.join(a.state, "active.json"), os.path.join(a.state, "activation_log.jsonl")


def cmd_activate(a):
    meta = json.load(open(os.path.join(a.pkg, "PACKAGE.json"), encoding="utf-8"))
    if meta.get("kind") != "planner_guidance" or S.approved_hash(a.pkg) != meta.get("approved_hash"):
        sys.exit("gói sai loại / hash không khớp — không kích hoạt")
    act, log = _state(a)
    prev = json.load(open(act, encoding="utf-8")) if os.path.exists(act) else {"package": "", "approved_hash": None}
    cur = {"package": os.path.abspath(a.pkg), "approved_hash": meta["approved_hash"], "prev": prev, "by": a.by, "at": now(), "reason": a.reason}
    json.dump(cur, open(act, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "activate", **{k: cur[k] for k in ("package", "approved_hash", "by", "at", "reason")}}, ensure_ascii=False) + "\n")
    print(json.dumps({k: cur[k] for k in ("package", "approved_hash")}, ensure_ascii=False))


def cmd_rollback(a):
    act, log = _state(a)
    cur = json.load(open(act, encoding="utf-8")) if os.path.exists(act) else {}
    prev = cur.get("prev") or {"package": "", "approved_hash": None}
    new = {**prev, "by": a.by, "at": now(), "reason": a.reason}
    json.dump(new, open(act, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "rollback", "package": new.get("package"), "approved_hash": new.get("approved_hash"),
                             "by": a.by, "at": new["at"], "reason": a.reason}, ensure_ascii=False) + "\n")
    print(json.dumps({"package": new.get("package"), "approved_hash": new.get("approved_hash")}, ensure_ascii=False))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("import"); p.add_argument("--root", required=True); p.add_argument("--drafts", required=True)
    p.add_argument("--author", required=True)
    for n in ("approve", "reject"):
        p = sub.add_parser(n); p.add_argument("--root", required=True); p.add_argument("--id", required=True)
        p.add_argument("--by", required=True); p.add_argument("--reason", default="")
    p = sub.add_parser("package"); p.add_argument("--root", required=True); p.add_argument("--name", required=True)
    p.add_argument("--by", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("regress"); p.add_argument("--pkg", required=True)
    p = sub.add_parser("activate"); p.add_argument("--pkg", required=True); p.add_argument("--by", required=True)
    p.add_argument("--reason", default=""); p.add_argument("--state", default=STATE_DIR)
    p = sub.add_parser("rollback"); p.add_argument("--by", required=True); p.add_argument("--reason", default="")
    p.add_argument("--state", default=STATE_DIR)
    p = sub.add_parser("status"); p.add_argument("--state", default=STATE_DIR)
    a = ap.parse_args(argv)
    if a.cmd == "status":
        act, _ = _state(a)
        print(open(act, encoding="utf-8").read() if os.path.exists(act) else "{}")
        return 0
    rc = {"import": cmd_import, "approve": lambda x: cmd_review(x, True), "reject": lambda x: cmd_review(x, False),
          "package": cmd_package, "regress": cmd_regress, "activate": cmd_activate, "rollback": cmd_rollback}[a.cmd](a)
    return rc or 0


if __name__ == "__main__":
    sys.exit(main())
