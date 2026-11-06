#!/usr/bin/env python3
"""06/11: chuyển regex quyết định sang harness/lexicon/{router,cues,guardrails}.json — mọi mẫu phải GIỐNG HỆT bản cũ.

So từng hằng số (chuỗi regex + cờ của re, mô tả intent / cờ, thứ tự) giữa code hiện tại và một bản tham chiếu (code trước
khi chuyển), mỗi bên chạy trong tiến trình riêng với thư mục gốc của nó.

    python tests/lexicon_rx_parity.py --ref-root DIR      # so
    python tests/lexicon_rx_parity.py --dump              # in JSON các hằng số của cây hiện tại (dùng nội bộ)
"""
import argparse
import importlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMES = {
    "core.llm.router": ["INTENTS", "INTENTS_EN", "FLAGS", "FLAGS_EN", "FLAGS_Q", "_RULES", "_FLAG_RULES"],
    "harness.agent": ["GIFT_Q_RX", "PROMO_END_RX", "PRIOR_REF_RX", "REFUND_RX", "HYPO_RX", "DOC_REF_RX", "DUR_RX",
                      "PROXY_CLAIM_RX", "PROXY_INFO_RX", "REFUSE_INTERNAL_OK_RX", "REFUSE_INTERNAL_SENT", "OTHER_PII_RX",
                      "ATTR_ASK_RX", "CLOSE_ORDER_RX", "CLOSING_RX", "RETURN_RX", "QTY_RX"],
    "harness.planner_table": ["RETURN_CUE_RX", "PRESSURE_RX", "CANCEL_RX", "LATER_CLOSE_RX", "DECLINE_RX", "SHOP_CALLS_RX"],
    "harness.guardrails": ["HUMAN_RX", "COMPETITOR_RX", "PAST_RX", "REQUIRED", "PRICE_CUE_RX", "PROMO_NOUN_RX",
                           "PROMO_POS_RX", "PROMO_NEG_RX", "SHIP_ONLY_RX", "WARRANTY_RX"],
}
# mẫu mới tách từ regex viết thẳng trong hàm (bản cũ không có tên) → so với chuỗi cũ chép tay
INLINE = {("harness.guardrails", "INTERNAL_MENTION_RX"): r"(gia nhap|nha cung cap|gia von)\s+(la|khoang|chi)"}


def ser(o):
    if hasattr(o, "pattern") and hasattr(o, "flags"):
        return {"__rx__": o.pattern, "flags": o.flags}
    if isinstance(o, dict):
        return {"__dict__": [[k, ser(v)] for k, v in o.items()]}      # giữ thứ tự
    if isinstance(o, (list, tuple)):
        return [ser(v) for v in o]
    return o


def dump():
    sys.path.insert(0, os.getcwd())
    out = {}
    for mod, names in NAMES.items():
        m = importlib.import_module(mod)
        for n in names:
            out[f"{mod}.{n}"] = ser(getattr(m, n))
    print(json.dumps(out, ensure_ascii=False))


def run_dump(root):
    env = {**os.environ, "PYTHONPATH": root, "LLM_CACHE": "off", "IMPROVE_DIR": ""}
    p = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "lexicon_rx_parity.py"), "--dump"], cwd=root, env=env,
                       capture_output=True, text=True, encoding="utf-8")
    if p.returncode:
        sys.exit(f"dump lỗi ở {root}:\n{p.stderr[-2000:]}")
    return json.loads(p.stdout.strip().splitlines()[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref-root")
    ap.add_argument("--dump", action="store_true")
    a = ap.parse_args()
    if a.dump:
        return dump()
    new, ref = run_dump(ROOT), run_dump(os.path.abspath(a.ref_root))
    bad = [k for k in ref if new.get(k) != ref[k]]
    for k in bad:
        print("LỆCH", k, "\n  cũ:", json.dumps(ref[k], ensure_ascii=False)[:400], "\n  mới:", json.dumps(new.get(k), ensure_ascii=False)[:400])
    sys.path.insert(0, ROOT)
    for (mod, n), pat in INLINE.items():
        got = getattr(importlib.import_module(mod), n).pattern
        if got != pat:
            bad.append(f"{mod}.{n}")
            print("LỆCH", f"{mod}.{n}", got, "≠", pat)
    print(f"lexicon_rx_parity: {len(ref)} hằng số + {len(INLINE)} mẫu tách từ hàm, lệch {len(bad)}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
