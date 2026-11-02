"""D-4 (ràng buộc 2): chống trùng giữa dữ liệu tự sinh và các bộ ĐO (holdout BTC-like, out_nat/test, public_sample).

So n-gram (mặc định 8 từ, sau fold()) giữa câu tự sinh và lời KHÁCH của các bộ đo. Câu nào có ít nhất một n-gram chung
thì bị loại. Script CHỈ IN SỐ ĐẾM, không bao giờ in câu của bộ đo (giữ nguyên tắc không mở holdout trước đóng băng).

    python scripts/check_overlap.py --synth-tsv datagen/synth_slots/b1.tsv
    python scripts/check_overlap.py --jsonl data/lexicon_corpus/synth/address.jsonl
Dùng như thư viện: `overlapping(list_câu) -> set(chỉ số câu trùng)` (datagen/synth_slot_sentences.py gọi).
"""
import argparse
import csv
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from harness.textnorm import fold  # noqa: E402

GUARDED = [os.path.join("datagen", "out_btc_like_final_v1", "final", "holdout"),
           os.path.join("datagen", "out_btc_like_final_v1_1", "final", "holdout"),
           os.path.join("datagen", "out_nat", "test"),
           os.path.join("test_set", "public_sample")]


def grams(text, n):
    toks = re.findall(r"[a-z0-9]+", fold(text))
    return {" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1)}


def _customer_turns(obj):
    calls = obj.get("calls") or {}
    for c in (calls.values() if isinstance(calls, dict) else calls):
        for t in (c.get("customer_turns") or []) + (c.get("customer_turns_asr") or []):
            yield t if isinstance(t, str) else json.dumps(t, ensure_ascii=False)


def guarded_grams(n=8):
    out = set()
    for d in GUARDED:
        for f in glob.glob(os.path.join(ROOT, d, "*.json")):
            try:
                obj = json.load(open(f, encoding="utf-8"))
            except ValueError:
                continue
            for t in _customer_turns(obj):
                out |= grams(t, n)
    return out


def overlapping(texts, n=8):
    g = guarded_grams(n)
    return {i for i, t in enumerate(texts) if grams(t, n) & g}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--synth-tsv", nargs="*", default=[])
    ap.add_argument("--jsonl", nargs="*", default=[])
    ap.add_argument("-n", type=int, default=8)
    a = ap.parse_args()
    texts = []
    for p in a.synth_tsv:
        with open(p, encoding="utf-8", newline="") as fh:
            texts += [r["text"] for r in csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)]
    for p in a.jsonl:
        texts += [json.loads(l)["text"] for l in open(p, encoding="utf-8") if l.strip()]
    bad = overlapping(texts, a.n)
    print(f"{len(texts)} câu kiểm, {len(bad)} câu trùng {a.n}-gram với bộ đo (không in nội dung bộ đo)")
    for i in sorted(bad):
        print("  trùng:", texts[i][:100])
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
