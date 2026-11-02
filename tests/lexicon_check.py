"""Kiểm harness/lexicon/slots.json (PLAN-2026-11-01 A-L, quy trình rút cue bước 4).

- cấu trúc hợp lệ (lexicon.validate): id duy nhất, kind/status hợp lệ, pattern dạng fold(), có nguồn, ≥2 câu ví dụ;
- MỌI entry (kể cả proposed) chạy đúng ví dụ của nó qua customer_slots_rules: `expect` {slot: giá trị | null | "*"};
  ví dụ `hit` kiểm cue scanner;
- entry approved không làm đổi kết quả các câu nhãn tay trong tests/extract_eval/customer.jsonl theo hướng sai
  (slot luật trích khớp nhãn trước khi áp lexicon thì sau khi áp vẫn phải khớp);
- viết tắt không đụng số tiền (500k) và không lặp bảng TEEN có sẵn.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["LEXICON_INCLUDE"] = "all"

from harness import extractor, lexicon  # noqa: E402
from harness.textnorm import TEEN, fold  # noqa: E402

FAILS = []
TODAY = "2026-10-15"


def ok(c, m):
    if not c:
        FAILS.append(m); print("FAIL:", m)


data = lexicon.load_raw()
for e in lexicon.validate(data):
    ok(False, f"cấu trúc: {e}")

lexicon.reload()
for slot, spec in data["slots"].items():
    for e in spec["entries"]:
        for ex in e.get("examples") or []:
            if "hit" in ex:
                got = lexicon.cue_hit(fold(ex["text"])) is not None
                ok(got == ex["hit"], f"{e['id']}: cue_hit({ex['text']!r}) = {got}, cần {ex['hit']}")
                continue
            out = extractor.customer_slots_rules(ex["text"], TODAY)
            for k, want in ex["expect"].items():
                have = out.get(k)
                good = (have is None) if want is None else (have is not None) if want == "*" else (have == want)
                ok(good, f"{e['id']}: {ex['text']!r} → {k}={have!r}, cần {want!r}")

# entry approved không làm hỏng câu nhãn tay
os.environ["LEXICON_INCLUDE"] = "approved"
lexicon.reload()
path = os.path.join(ROOT, "tests", "extract_eval", "customer.jsonl")
rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
SLOTS = {k for s in data["slots"] for k in [s]}
broken = []
for r in rows:
    gold = r.get("slots") or {}
    out = extractor.customer_slots_rules(r["text"], TODAY)
    for k in SLOTS:
        if k in r.get("skip", []):
            continue
        if (k in gold) != (k in out) or (k in gold and gold[k] != out[k]):
            broken.append((r["id"], k, gold.get(k), out.get(k)))
# baseline: tắt hẳn lexicon → so xem lexicon approved có làm TĂNG số lỗi trên câu nhãn tay không
base_fail = set()
saved = lexicon._compiled
lexicon._compiled = lambda path, include: {"entries": [], "abbrev": []}
for r in rows:
    gold = r.get("slots") or {}
    out = extractor.customer_slots_rules(r["text"], TODAY)
    for k in SLOTS:
        if k in r.get("skip", []):
            continue
        if (k in gold) != (k in out) or (k in gold and gold[k] != out[k]):
            base_fail.add((r["id"], k))
lexicon._compiled = saved
lexicon.reload()
new = [b for b in broken if (b[0], b[1]) not in base_fail]
ok(not new, f"lexicon approved làm sai thêm câu nhãn tay: {new}")
print(f"extract_eval/customer: lỗi slot trước lexicon {len(base_fail)}, sau {len(broken)} (mới sai {len(new)})")

# viết tắt
norm = lexicon.normalize("Cho mình xin stk với sdt, giá 500k ntn vs bên kia?")
ok("số tài khoản" in norm and "số điện thoại" in norm and "500k" in norm and "như thế nào" in norm, f"normalize: {norm!r}")
teen_from = {x for pat, _ in TEEN for x in pat.replace("\\b", "").split("|")}
for a in data.get("abbreviations") or []:
    ok(a["from"] not in teen_from, f"viết tắt {a['from']} đã có trong TEEN (harness/textnorm.py)")
ok(all(a["from"] != "ck" for a in data.get("abbreviations") or []), "'ck' mơ hồ (chuyển khoản / chồng) — không được thêm")

print("TẤT CẢ OK" if not FAILS else f"{len(FAILS)} LỖI")
sys.exit(1 if FAILS else 0)
