#!/usr/bin/env python3
"""06/11: harness/lexicon/{router,cues,guardrails}.json — mọi mẫu biên dịch được, ví dụ khớp / không khớp đúng, router đủ trường.

    python tests/lexicon_rx_check.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.lexicon import rx as L  # noqa: E402
from harness.textnorm import fold  # noqa: E402


def main():
    bad, n_rx, n_ex = [], 0, 0
    for name in ("cues", "guardrails"):
        doc = L.load(name)
        for key, e in doc["patterns"].items():
            try:
                r = L.rx(name, key)
                n_rx += 1
            except ValueError as err:
                bad.append(str(err))
                continue
            if "@" in L.pattern(name, key):
                bad.append(f"{name}.{key}: còn @TÊN@ chưa thay (thiếu trong defs?)")
            if e.get("goal") and not e.get("message"):
                bad.append(f"{name}.{key}: mẫu bắt buộc theo goal thiếu message")
            ex = e.get("examples") or {}
            for t in ex.get("match", []):
                n_ex += 1
                if not r.search(fold(t)):
                    bad.append(f"{name}.{key}: phải khớp '{t}'")
            for t in ex.get("no_match", []):
                n_ex += 1
                if r.search(fold(t)):
                    bad.append(f"{name}.{key}: không được khớp '{t}'")
    R = L.load("router")
    for k, v in R["flags"].items():
        miss = {"yes", "no", "yes_en", "no_en", "q_vi", "q_en"} - set(v)
        if miss:
            bad.append(f"router.flags.{k}: thiếu {sorted(miss)}")
    for k, v in R["intents"].items():
        if not v.get("vi") or not v.get("en"):
            bad.append(f"router.intents.{k}: thiếu vi / en")
    if set(R["flag_rules"]) != set(R["flags"]):
        bad.append(f"router: flag_rules {sorted(R['flag_rules'])} khác flags {sorted(R['flags'])}")
    for r_ in R["intent_rules"]:
        if r_["intent"] not in R["intents"]:
            bad.append(f"router.intent_rules: intent lạ {r_['intent']}")
    for p in [r_["pattern"] for r_ in R["intent_rules"]] + list(R["flag_rules"].values()):
        try:
            re.compile(L.join(p))
            n_rx += 1
        except re.error as err:
            bad.append(f"router: mẫu sai cú pháp {L.join(p)[:60]}: {err}")
    for b in bad:
        print("LỖI", b)
    print(f"lexicon_rx_check: {n_rx} mẫu, {n_ex} ví dụ — {'OK' if not bad else str(len(bad)) + ' lỗi'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
