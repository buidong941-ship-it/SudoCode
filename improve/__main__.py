"""CLI khung cơ chế cải tiến.

    python -m improve collect --trace runs/x/dev/full.jsonl --report runs/x/dev/report.json [--append]
    python -m improve gaps [--type no_info]                 # xem gaps.jsonl
    python -m improve propose de_xuat.json                  # 1 đề xuất hoặc danh sách → pending/
    python -m improve review                                # liệt kê pending
    python -m improve review show P-faq-1a2b3c4d
    python -m improve review approve P-faq-1a2b3c4d --by "Đồng" --reason "khớp chính sách 03-02"
    python -m improve review reject  P-faq-1a2b3c4d --by "Đồng" --reason "trùng FAQ đã có"
    python -m improve review -i --by "Đồng"                 # duyệt lần lượt từng đề xuất (hỏi y/n/s)
    python -m improve round save r0 --report dev=runs/x/dev/report.json --by "Đồng"
    python -m improve check --prev r0 --report dev=runs/y/dev/report.json [--apply --by "Đồng"]
    python -m improve rollback --to r0 --by "Đồng" --reason "TSR tụt"
    python -m improve status

Mọi lệnh nhận `--root DIR` (mặc định thư mục improve/, hoặc env IMPROVE_ROOT).
"""
import argparse
import json
import sys

from improve import collect as C
from improve import store as S


def _p(*a):
    print(*a, flush=True)


def _reports(specs):
    out = {}
    for s in specs or []:
        # report holdout được phép ở đây: đo vòng (E) dùng cả dev và holdout, chỉ collect (feedback) bị giới hạn dev
        label, _, path = s.partition("=") if "=" in s else ("dev", "", s)
        with open(path, encoding="utf-8") as fh:
            out[label] = json.load(fh)
    return out


def cmd_collect(a):
    gaps = C.collect(a.trace, a.report, a.scenarios, a.config)
    path = S.paths(a.root)["gaps"]
    n = C.write(gaps, path, append=a.append)
    S.log("collect", a.root, trace=a.trace, report=a.report, n_found=len(gaps), n_written=n)
    _p(f"{len(gaps)} gap ({n} mới) → {path}")
    for row in C.summary(gaps):
        _p(f"  {row['n']:>4}  {row['type']}" + (f" / {row['subtype']}" if row["subtype"] else ""))


def cmd_gaps(a):
    gaps = C.load(S.paths(a.root)["gaps"])
    if a.type:
        gaps = [g for g in gaps if g["type"] == a.type]
    for g in gaps[: a.limit]:
        _p(f"{g['id']}  {g['type']:<16} {g['scenario']}/{g['call']}/t{g['turn']}  "
           f"{(g.get('customer_text') or '')[:70]!r}  {json.dumps(g.get('detail'), ensure_ascii=False)[:120]}")
    _p(f"({len(gaps)} gap)")


def cmd_propose(a):
    with open(a.file, encoding="utf-8") as fh:
        data = json.load(fh)
    bad = 0
    for prop in data if isinstance(data, list) else [data]:
        try:
            state, pid = S.propose(prop, author=a.author, root=a.root)
            _p(f"{pid}: {'→ pending' if state == 'pending' else 'đã có ở ' + state}")
        except S.ProposalError as e:
            bad += 1
            _p(f"BỊ CHẶN ({prop.get('kind')}, {prop.get('title') or ''}): {e}")
    sys.exit(1 if bad else 0)


def _show(prop):
    _p(f"── {prop['id']}  [{prop['kind']}]  {prop.get('title', '')}")
    _p(f"   tác giả {prop.get('author')} · {prop.get('created_at')} · gap: {', '.join(prop.get('source_gaps') or []) or '—'}")
    for k, v in prop["payload"].items():
        _p(f"   {k}: {v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)}")
    if prop.get("review"):
        r = prop["review"]
        _p(f"   duyệt: {r['by']} · {r['at']} · {r.get('reason')}")


def cmd_review(a):
    if a.action == "show":
        _show(S.find(a.id, a.root)[1])
    elif a.action in ("approve", "reject", "reopen"):
        prop = getattr(S, a.action)(a.id, a.by, a.reason, a.root)
        _p(f"{prop['id']} → {prop['status']}")
    elif a.interactive:
        if not a.by:
            sys.exit("cần --by khi duyệt")
        for prop in S.list_state("pending", a.root):
            _show(prop)
            ans = input("   duyệt? [y]es / [n]o / [s]kip / [q]uit: ").strip().lower()
            if ans == "q":
                break
            if ans in ("y", "n"):
                reason = input("   lý do: ").strip()
                (S.approve if ans == "y" else S.reject)(prop["id"], a.by, reason, a.root)
    else:
        state = a.state or "pending"
        props = S.list_state(state, a.root)
        for prop in props:
            _p(f"{prop['id']}  [{prop['kind']}]  {prop.get('title', '')[:70]}")
        _p(f"({len(props)} đề xuất ở {state}/)")


def cmd_round(a):
    m = S.save_round(a.name, a.report, a.by, a.note, a.root)
    _p(f"vòng {m['name']}: {len(m['approved_ids'])} đề xuất approved, hash {m['approved_hash']}, report {sorted(m['reports'])}")


def cmd_check(a):
    prev = S.load_round(a.prev, a.root)["reports_data"]
    cur = _reports(a.report)
    dec = S.rollback_decision(prev, cur, a.tsr_drop)
    _p(json.dumps(dec, ensure_ascii=False, indent=2))
    if dec["rollback"] and a.apply:
        res = S.rollback(a.prev, a.by, "; ".join(dec["reasons"]), a.root)
        _p(f"đã quay lui về {a.prev}: gỡ {res['removed']}, khôi phục {res['restored']}")
    sys.exit(2 if dec["rollback"] else 0)


def cmd_rollback(a):
    res = S.rollback(a.to, a.by, a.reason, a.root)
    _p(json.dumps(res, ensure_ascii=False))


def cmd_status(a):
    p = S.paths(a.root)
    _p(f"thư mục: {p['root']}")
    _p(f"gaps: {len(C.load(p['gaps']))}")
    for s in S.STATES:
        _p(f"{s}: {len(S.list_state(s, a.root))}")
    _p(f"approved hash: {S.approved_hash(a.root)}")
    for m in S.rounds(a.root):
        _p(f"vòng {m['name']} ({m['at']}, {m.get('by')}): {len(m['approved_ids'])} approved, hash {m['approved_hash']}")
    for rec in S.read_log(a.root)[-5:]:
        _p(f"  log {rec['at']} {rec['event']} {rec.get('id') or rec.get('name') or rec.get('to') or ''}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m improve", description="Khung cơ chế cải tiến (tách biệt core)")
    ap.add_argument("--root", help="thư mục dữ liệu (mặc định improve/ hoặc env IMPROVE_ROOT)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("collect", help="D1: gom lỗi từ trace + report dev → gaps.jsonl")
    p.add_argument("--trace", required=True)
    p.add_argument("--report", help="report.json của eval/reference_eval.py (RQR/HR/TSR)")
    p.add_argument("--scenarios", help="chỉ để kiểm tra không phải holdout/test")
    p.add_argument("--config", default="full")
    p.add_argument("--append", action="store_true", help="giữ gap cũ, chỉ thêm id mới")
    p.set_defaults(fn=cmd_collect)

    p = sub.add_parser("gaps", help="xem gaps.jsonl")
    p.add_argument("--type")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(fn=cmd_gaps)

    p = sub.add_parser("propose", help="D2: thêm đề xuất (file JSON, 1 hoặc danh sách) vào pending/")
    p.add_argument("file")
    p.add_argument("--author", default="claude")
    p.set_defaults(fn=cmd_propose)

    p = sub.add_parser("review", help="D3: liệt kê / xem / duyệt / loại đề xuất")
    p.add_argument("action", nargs="?", choices=["show", "approve", "reject", "reopen"])
    p.add_argument("id", nargs="?")
    p.add_argument("--by", help="người duyệt (bắt buộc khi approve/reject)")
    p.add_argument("--reason", default="")
    p.add_argument("--state", choices=S.STATES)
    p.add_argument("-i", "--interactive", action="store_true")
    p.set_defaults(fn=cmd_review)

    p = sub.add_parser("round", help="D5: chụp approved/ + report của một vòng")
    p.add_argument("op", choices=["save"])
    p.add_argument("name")
    p.add_argument("--report", action="append", default=[], help="bộ=report.json (lặp lại)")
    p.add_argument("--by", default="")
    p.add_argument("--note", default="")
    p.set_defaults(fn=cmd_round)

    p = sub.add_parser("check", help="D5: so report mới với vòng trước, quyết định quay lui (mã thoát 2 = nên quay lui)")
    p.add_argument("--prev", required=True, help="tên vòng trước")
    p.add_argument("--report", action="append", required=True, help="bộ=report.json của vòng hiện tại")
    p.add_argument("--tsr-drop", type=float, default=3.0)
    p.add_argument("--apply", action="store_true", help="tự quay lui nếu vượt ngưỡng")
    p.add_argument("--by", default="")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("rollback", help="D5: đưa approved/ về ảnh chụp của một vòng")
    p.add_argument("--to", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--reason", default="")
    p.set_defaults(fn=cmd_rollback)

    p = sub.add_parser("status")
    p.set_defaults(fn=cmd_status)

    a = ap.parse_args(argv)
    if a.cmd == "review" and a.action in ("show", "approve", "reject", "reopen") and not a.id:
        ap.error("cần id đề xuất")
    if a.cmd == "check" and a.apply and not a.by:
        ap.error("--apply cần --by")
    try:
        a.fn(a)
    except (S.ProposalError, C.LeakError) as e:
        sys.exit(f"lỗi: {e}")


if __name__ == "__main__":
    main()
