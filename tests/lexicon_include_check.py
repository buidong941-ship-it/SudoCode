"""D40: LEXICON_INCLUDE=none phải tắt hẳn lexicon (trước đây giá trị lạ nạp cả entry rejected).

- none → 0 entry, 0 viết tắt, cue_hit luôn None, normalize không đổi câu;
- approved ⊂ proposed ⊂ all, đúng theo status;
- giá trị lạ → ValueError (không âm thầm nạp hết).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from harness import lexicon  # noqa: E402
from harness.textnorm import fold  # noqa: E402

FAILS = []


def ok(c, m):
    if not c:
        FAILS.append(m)
        print("FAIL:", m)


def load(mode):
    os.environ["LEXICON_INCLUDE"] = mode
    lexicon.reload()
    return lexicon.compiled()


data = lexicon.load_raw()
by_status = {}
for spec in (data.get("slots") or {}).values():
    for e in spec.get("entries") or []:
        by_status[e["status"]] = by_status.get(e["status"], 0) + 1
n_abbrev = {s: sum(1 for a in data.get("abbreviations") or [] if a.get("status") == s) for s in lexicon.STATUSES}

none = load("none")
ok(none["entries"] == [] and none["abbrev"] == [], f"none còn nạp {len(none['entries'])} entry, {len(none['abbrev'])} viết tắt")
ok(lexicon.cue_hit(fold("ck trước nha em, ship về nhà anh")) is None, "none: cue_hit phải là None")
ok(lexicon.normalize("ko ck đc") == "ko ck đc", "none: normalize không được đổi câu")

expect = {"approved": {"approved"}, "proposed": {"approved", "proposed"}, "all": {"approved", "proposed", "rejected"}}
for mode, statuses in expect.items():
    c = load(mode)
    ok(len(c["entries"]) == sum(by_status.get(s, 0) for s in statuses), f"{mode}: số entry sai ({len(c['entries'])})")
    ok({e["status"] for e in c["entries"]} <= statuses, f"{mode}: nạp entry ngoài {statuses}")
    ok(len(c["abbrev"]) == sum(n_abbrev[s] for s in statuses), f"{mode}: số viết tắt sai ({len(c['abbrev'])})")
ok(len(load("approved")["entries"]) > 0, "approved phải có ít nhất 1 entry (nếu không, phép so none/approved vô nghĩa)")

for bad in ("off", "rejected", "xyz"):
    os.environ["LEXICON_INCLUDE"] = bad
    lexicon.reload()
    try:
        lexicon.compiled()
        ok(False, f"LEXICON_INCLUDE={bad} phải báo ValueError")
    except ValueError:
        pass

os.environ["LEXICON_INCLUDE"] = "approved"
lexicon.reload()
print(f"lexicon_include_check: {'OK' if not FAILS else f'{len(FAILS)} lỗi'} (entry theo status: {by_status})")
sys.exit(1 if FAILS else 0)
