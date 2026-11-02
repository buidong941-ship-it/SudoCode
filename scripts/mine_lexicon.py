"""D-1 / D-5: rút ỨNG VIÊN cue và bảng viết tắt để người duyệt (PLAN-2026-11-01 mục A-L, A-D).

Hai nguồn:
  ref    dữ liệu tham khảo CSConDa (hcmut-ura, CC BY-NC 4.0) — đọc thẳng từ thư mục ngoài repo (`--ref-dir` hoặc env
         LEXICON_REF_DIR), KHÔNG chép dữ liệu vào repo. Chỉ dùng câu hỏi của khách (`question`).
  synth  câu tự sinh `data/lexicon_corpus/synth/*.jsonl` — CHỈ phần split=mine (70%); phần eval (30%) để đo.

Ra (thư mục `data/lexicon_corpus/`, không commit):
  candidates_<nguồn>.jsonl   {slot, ngram, count, neg_count, examples[3 câu đã che PII]} — n-gram (1–3 từ, đã fold)
                             đứng quanh từ khóa slot (ref) hoặc ngay trước span giá trị (synth)
  abbrev_<nguồn>.jsonl       {token, count, examples} — token ngắn không dấu hay gặp, ứng viên viết tắt / teencode

Ứng viên KHÔNG tự vào lexicon: người duyệt chọn rồi thêm bằng `scripts/lexicon_review.py add` (status=proposed) → approve.

    python scripts/mine_lexicon.py ref --ref-dir "D:/.../dataset/data_reference/hcmut-ura"
    python scripts/mine_lexicon.py synth
Cần pandas + pyarrow (requirements-offline.txt).
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from harness.textnorm import TEEN, fold, mask_pii  # noqa: E402

OUT = os.path.join(ROOT, "data", "lexicon_corpus")
# từ khóa neo theo slot cho nguồn ref (fold). Dữ liệu ref là CSKH phần mềm B2B → chỉ các slot dưới đây có ý nghĩa.
REF_ANCHORS = {
    "payment": r"\b(thanh toan|chuyen khoan|ck|stk|so tai khoan|tien mat|cod|chuyen tien|momo|banking|hoa don)\b",
    "callback_requested": r"\b(goi lai|lien he lai|lien lac|nhan tin|inbox|phan hoi|bao lai|hen)\b",
    "self_name": r"\b(minh la|em la|anh la|chi la|toi la|ten (minh|em|toi) la|ten la)\b",
    "address": r"\b(dia chi|giao (hang|ve|den|toi)|ship|gui (ve|den|toi|ra)|van chuyen)\b",
    "blocker": r"\b(suy nghi|can nhac|hoi (sep|ke toan|y kien)|trao doi (them|voi)|de (em|minh|anh|chi) (xem|tinh))\b",
}
NAME_AFTER_RX = re.compile(r"\b((?:mình|em|anh|chị|tôi|tên mình|tên em|tên tôi) (?:là|tên là|tên)) ([A-ZĐ][\wÀ-ỹ]+(?: [A-ZĐ][\wÀ-ỹ]+){0,3})")
EMAIL_RX = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
URL_RX = re.compile(r"https?://\S+|www\.\S+")
TEEN_TOKENS = {x for pat, _ in TEEN for x in pat.replace("\\b", "").split("|")}


def mask(text):
    """Che PII trước khi bất kỳ câu nào được in / ghi: SĐT, STK, CCCD (mask_pii), email, URL, tên sau 'mình là…'."""
    t = mask_pii(text or "")
    t = EMAIL_RX.sub("[EMAIL]", t)
    t = URL_RX.sub("[URL]", t)
    return NAME_AFTER_RX.sub(lambda m: m.group(1) + " [TÊN]", t)


def ngrams(tokens, n_max=3):
    for n in range(1, n_max + 1):
        for i in range(len(tokens) - n + 1):
            yield " ".join(tokens[i:i + n])


def load_ref(ref_dir):
    import pandas as pd
    rows = []
    for f in sorted(glob.glob(os.path.join(ref_dir, "*.parquet"))):
        df = pd.read_parquet(f, columns=["question", "type"])
        for q, ty in zip(df["question"], df["type"]):
            rows.append({"text": str(q), "type": re.sub(r"\s+", " ", str(ty)).strip().lower(), "file": os.path.basename(f)})
    return rows


def mine_ref(ref_dir, window=3, min_count=3):
    rows = load_ref(ref_dir)
    cand, examples = collections.defaultdict(collections.Counter), collections.defaultdict(list)
    tok_count, tok_ex = collections.Counter(), collections.defaultdict(list)
    for r in rows:
        f = fold(r["text"])
        toks = re.findall(r"[a-z0-9đ]+", f)
        for t in set(toks):
            if 1 < len(t) <= 4 and not t.isdigit() and t not in TEEN_TOKENS and not re.search(r"[aeiouy]", t[1:] if len(t) > 2 else t):
                tok_count[t] += 1
                if len(tok_ex[t]) < 3:
                    tok_ex[t].append(mask(r["text"])[:160])
        for slot, rx in REF_ANCHORS.items():
            for m in re.finditer(rx, f):
                left = re.findall(r"[a-z0-9đ]+", f[:m.start()])[-window:]
                right = re.findall(r"[a-z0-9đ]+", f[m.end():])[:window]
                for g in set(ngrams(left + [m.group(0)] + right)):
                    if m.group(0) in g:
                        cand[slot][g] += 1
                        key = (slot, g)
                        if len(examples[key]) < 3:
                            examples[key].append(mask(r["text"])[:160])
    out = [{"slot": s, "ngram": g, "count": c, "examples": examples[(s, g)], "source": "ref:hcmut-ura"}
           for s, cnt in cand.items() for g, c in cnt.most_common(200) if c >= min_count]
    ab = [{"token": t, "count": c, "examples": tok_ex[t], "source": "ref:hcmut-ura"}
          for t, c in tok_count.most_common(150) if c >= min_count]
    return out, ab, len(rows)


def load_synth(split="mine"):
    rows = []
    for f in sorted(glob.glob(os.path.join(OUT, "synth", "*.jsonl"))):
        for l in open(f, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                if r.get("split") == split:
                    rows.append(r)
    return rows


def mine_synth(min_count=2):
    rows = load_synth("mine")
    pos, neg, ex = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter), collections.defaultdict(list)
    for r in rows:
        slot, f = r["slot"], fold(r["text"])
        span = fold(r.get("span") or "")
        if r["label"] == "positive" and span and span in f:
            left = re.findall(r"[a-z0-9đ]+", f[:f.index(span)])[-3:]
            for g in set(ngrams(left)):
                pos[slot][g] += 1
                if len(ex[(slot, g)]) < 3:
                    ex[(slot, g)].append(r["text"][:160])
        elif r["label"] == "hard_negative":
            for g in set(ngrams(re.findall(r"[a-z0-9đ]+", f))):
                neg[slot][g] += 1
    out = []
    for slot, cnt in pos.items():
        for g, c in cnt.most_common(150):
            if c >= min_count:
                out.append({"slot": slot, "ngram": g, "count": c, "neg_count": neg[slot][g],
                            "precision_hint": round(c / (c + neg[slot][g]), 2), "examples": ex[(slot, g)],
                            "source": "claude-synth"})
    return sorted(out, key=lambda x: (-x["precision_hint"], -x["count"])), len(rows)


def write(name, rows):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name)
    with open(p, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", choices=["ref", "synth"])
    ap.add_argument("--ref-dir", default=os.environ.get("LEXICON_REF_DIR"))
    ap.add_argument("--min-count", type=int, default=3)
    a = ap.parse_args()
    if a.source == "ref":
        if not a.ref_dir or not os.path.isdir(a.ref_dir):
            sys.exit("cần --ref-dir hoặc LEXICON_REF_DIR trỏ tới thư mục chứa *.parquet của hcmut-ura")
        cand, ab, n = mine_ref(a.ref_dir, min_count=a.min_count)
        print(f"{n} câu khách → {len(cand)} ứng viên cue → {write('candidates_ref.jsonl', cand)}")
        print(f"{len(ab)} ứng viên viết tắt → {write('abbrev_ref.jsonl', ab)}")
    else:
        cand, n = mine_synth(min_count=max(2, a.min_count - 1))
        print(f"{n} câu synth (split=mine) → {len(cand)} ứng viên → {write('candidates_synth.jsonl', cand)}")


if __name__ == "__main__":
    main()
