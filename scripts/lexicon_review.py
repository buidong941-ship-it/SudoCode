"""Duyệt entry của harness/lexicon/slots.json (PLAN-2026-11-01 A-L, quy trình rút cue bước 3).

    python scripts/lexicon_review.py                       # liệt kê entry proposed
    python scripts/lexicon_review.py --all                 # liệt kê tất cả
    python scripts/lexicon_review.py approve size.neg.so_nha --by "Đồng"
    python scripts/lexicon_review.py reject ab.vk --by "Đồng" --reason "..."
    python scripts/lexicon_review.py add candidates.json   # thêm ứng viên (từ mine_lexicon.py) vào slots.json, status=proposed

Sau khi duyệt, chạy tests/lexicon_check.py (trên Kaggle) để chắc ví dụ của entry vẫn đúng.
"""
import argparse
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from harness import lexicon  # noqa: E402


def _all(data):
    for slot, spec in data["slots"].items():
        for e in spec["entries"]:
            yield slot, e
    for a in data.get("abbreviations") or []:
        yield "abbrev", a


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", nargs="?", choices=["approve", "reject", "add"])
    ap.add_argument("target", nargs="?", help="id entry, hoặc file JSON ứng viên khi add")
    ap.add_argument("--by", default="")
    ap.add_argument("--reason", default="")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    data = lexicon.load_raw()
    if not a.action:
        for slot, e in _all(data):
            if a.all or e.get("status") == "proposed":
                what = e.get("pattern") or f"{e.get('from')} → {e.get('to')}"
                print(f"[{e.get('status'):<8}] {e['id']:<34} {slot:<20} {e.get('kind', 'abbrev'):<8} {what}  ({e.get('source')})")
        return
    if a.action in ("approve", "reject"):
        if not a.by.strip():
            sys.exit("cần --by (người duyệt)")
        hit = [e for _, e in _all(data) if e["id"] == a.target]
        if not hit:
            sys.exit(f"không thấy {a.target}")
        e = hit[0]
        e["status"] = "approved" if a.action == "approve" else "rejected"
        e["reviewed_by"] = f"{a.by} ({dt.date.today().isoformat()})"
        if a.reason:
            e["review_reason"] = a.reason
    else:
        cands = json.load(open(a.target, encoding="utf-8"))
        have = {e["id"] for _, e in _all(data)}
        n = 0
        for c in cands if isinstance(cands, list) else [cands]:
            slot = c.pop("slot")
            if c["id"] in have:
                continue
            c.update(status="proposed", reviewed_by=None, added=c.get("added") or dt.date.today().isoformat(),
                     added_by=c.get("added_by") or "claude")
            data["slots"].setdefault(slot, {"description": "", "entries": []})["entries"].append(c)
            n += 1
        print(f"thêm {n} ứng viên (proposed)")
    errs = lexicon.validate(data)
    if errs:
        sys.exit("slots.json không hợp lệ sau thay đổi, không ghi:\n  " + "\n  ".join(errs))
    with open(lexicon.PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("đã ghi", lexicon.PATH)


if __name__ == "__main__":
    main()
