#!/usr/bin/env python3
"""Tạo suite con từ một suite đã materialize: chép đúng các kịch bản có scenario_id trong danh sách (13/11, vòng F).

    python scripts/subset_suite.py --src /tmp/suites/dev --ids fixtures/set57_1113.json --dst /tmp/suites/set57

Thoát mã 3 nếu thiếu kịch bản nào trong danh sách (không chấm trên bộ thiếu)."""
import argparse
import glob
import json
import os
import shutil


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--ids", required=True)
    ap.add_argument("--dst", required=True)
    a = ap.parse_args()
    want = set(json.load(open(a.ids, encoding="utf-8")))
    os.makedirs(a.dst, exist_ok=True)
    got = set()
    for f in glob.glob(os.path.join(a.src, "*.json")):
        sid = (json.load(open(f, encoding="utf-8")) or {}).get("scenario_id")
        if sid in want:
            shutil.copy(f, os.path.join(a.dst, os.path.basename(f)))
            got.add(sid)
    miss = sorted(want - got)
    print(json.dumps({"want": len(want), "copied": len(got), "missing": miss}, ensure_ascii=False))
    if miss:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
