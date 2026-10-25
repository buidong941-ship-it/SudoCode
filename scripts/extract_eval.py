"""Đo riêng bộ trích (rules | llm | hybrid) trên bộ câu gán nhãn tay tests/extract_eval/{agent,customer}.jsonl.

Câu lấy từ trace bộ dev (generator của nhóm + lời khách của kịch bản dev), không lấy từ bộ test.
- agent.jsonl: mỗi dòng một câu của agent; nhãn `ask` (slot câu hỏi hoặc null), `qtype`, `claims` [{field, value}].
- customer.jsonl: mỗi dòng một câu khách + câu agent ngay trước (`context`); nhãn `slots`; `skip` = slot nhãn mơ hồ, không chấm.
Chỉ số: precision / recall / F1 theo từng field claim, phát hiện câu hỏi, đúng slot câu hỏi, và theo từng slot của khách.

    python scripts/extract_eval.py --modes rules hybrid --out runs/extract_eval.json
"""
import argparse
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.config import settings  # noqa: E402
from harness import extractor  # noqa: E402
from harness.textnorm import fold  # noqa: E402
from harness.tools import find_color  # noqa: E402

TODAY = "2026-10-20"


def load(name):
    return [json.loads(l) for l in open(os.path.join(ROOT, "tests", "extract_eval", name), encoding="utf-8")]


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f}


def _addr(v):
    return re.sub(r"[^a-z0-9 ]", " ", fold(str(v))).split()


def same(slot, gold, pred):
    if slot == "address":
        g, p = _addr(gold), _addr(pred)
        return bool(g) and len(set(g) & set(p)) / len(set(g)) >= 0.8
    if slot == "color":
        return (find_color(str(gold)) or fold(str(gold))) == (find_color(str(pred)) or fold(str(pred)))
    if slot == "self_name":
        return fold(str(gold)) == fold(str(pred))
    return str(gold).upper() == str(pred).upper()


def eval_agent(items):
    q = {"tp": 0, "fp": 0, "fn": 0, "slot_ok": 0, "type_ok": 0}
    fields, errors, ms = {}, [], []
    for it in items:
        meta = {}
        t0 = time.perf_counter()
        qs, cs = extractor.analyze_agent(it["sentence"], {}, meta=meta)
        ms.append((time.perf_counter() - t0) * 1000)
        pred_q = qs[0] if qs else None
        if it["ask"] and pred_q:
            q["tp"] += 1
            q["slot_ok"] += pred_q["slot"] == it["ask"]
            q["type_ok"] += pred_q["type"] == it["qtype"]
            if pred_q["slot"] != it["ask"]:
                errors.append({"id": it["id"], "kind": "question_slot", "gold": it["ask"], "pred": pred_q["slot"], "text": it["sentence"]})
        elif pred_q:
            q["fp"] += 1; errors.append({"id": it["id"], "kind": "question_fp", "pred": pred_q["slot"], "text": it["sentence"]})
        elif it["ask"]:
            q["fn"] += 1; errors.append({"id": it["id"], "kind": "question_fn", "gold": it["ask"], "text": it["sentence"]})
        gold = {(c["field"], json.dumps(c["value"])) for c in it["claims"]}
        pred = {(c["field"], json.dumps(c["value"])) for c in cs}
        for f, v in gold | pred:
            st = fields.setdefault(f, {"tp": 0, "fp": 0, "fn": 0})
            if (f, v) in gold and (f, v) in pred:
                st["tp"] += 1
            elif (f, v) in pred:
                st["fp"] += 1; errors.append({"id": it["id"], "kind": "claim_fp", "field": f, "pred": v, "text": it["sentence"]})
            else:
                st["fn"] += 1; errors.append({"id": it["id"], "kind": "claim_fn", "field": f, "gold": v, "text": it["sentence"]})
        if meta.get("fallback"):
            errors.append({"id": it["id"], "kind": "llm_fallback", "why": meta["fallback"]})
    tot = {k: sum(s[k] for s in fields.values()) for k in ("tp", "fp", "fn")}
    return {"questions": {**prf(q["tp"], q["fp"], q["fn"]), "slot_acc": q["slot_ok"] / q["tp"] if q["tp"] else None,
                          "type_acc": q["type_ok"] / q["tp"] if q["tp"] else None},
            "claims": {f: prf(**s) for f, s in sorted(fields.items())}, "claims_all": prf(**tot),
            "ms_p50": sorted(ms)[len(ms) // 2] if ms else None, "errors": errors}


def eval_customer(items):
    slots, errors, ms = {}, [], []
    for it in items:
        meta = {}
        t0 = time.perf_counter()
        pred = extractor.customer_slots(it["text"], TODAY, meta, it.get("context"))
        ms.append((time.perf_counter() - t0) * 1000)
        gold, skip = it["slots"], set(it.get("skip") or [])
        for k in (set(gold) | set(pred)) - skip:
            st = slots.setdefault(k, {"tp": 0, "fp": 0, "fn": 0})
            if k == "claimed_prices":
                g, p = set(gold.get(k) or []), set(pred.get(k) or [])
                st["tp"] += len(g & p); st["fp"] += len(p - g); st["fn"] += len(g - p)
                if g != p:
                    errors.append({"id": it["id"], "slot": k, "gold": sorted(g), "pred": sorted(p), "text": it["text"]})
            elif k in gold and k in pred and same(k, gold[k], pred[k]):
                st["tp"] += 1
            else:
                if k in pred:
                    st["fp"] += 1
                if k in gold:
                    st["fn"] += 1
                errors.append({"id": it["id"], "slot": k, "gold": gold.get(k), "pred": pred.get(k), "text": it["text"]})
        if meta.get("fallback"):
            errors.append({"id": it["id"], "kind": "llm_fallback", "why": meta["fallback"]})
    tot = {k: sum(s[k] for s in slots.values()) for k in ("tp", "fp", "fn")}
    return {"slots": {k: prf(**s) for k, s in sorted(slots.items())}, "slots_all": prf(**tot),
            "ms_p50": sorted(ms)[len(ms) // 2] if ms else None, "errors": errors}


def fmt(x):
    return "     -" if x is None else f"{100 * x:6.1f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modes", nargs="+", default=["rules"], choices=["rules", "llm", "hybrid"])
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "extract_eval.json"))
    a = ap.parse_args()
    agent_items, cust_items = load("agent.jsonl"), load("customer.jsonl")
    settings.extractor_async = False
    report = {"n_agent": len(agent_items), "n_customer": len(cust_items), "modes": {}}
    for mode in a.modes:
        os.environ["EXTRACTOR_BACKEND"] = settings.extractor_backend = mode
        r = {"agent": eval_agent(agent_items), "customer": eval_customer(cust_items)}
        report["modes"][mode] = r
        ag, cu = r["agent"], r["customer"]
        print(f"\n== {mode}  (agent {len(agent_items)} câu, khách {len(cust_items)} câu; ms p50 agent {ag['ms_p50']:.0f}, "
              f"khách {cu['ms_p50']:.0f})")
        print(f"{'':28}{'P':>6}{'R':>6}{'F1':>6}   tp/fp/fn")
        rows = [("câu hỏi (phát hiện)", ag["questions"])] + [(f"claim {k}", v) for k, v in ag["claims"].items()] + \
               [("claim (tất cả)", ag["claims_all"])] + [(f"khách {k}", v) for k, v in cu["slots"].items()] + \
               [("khách (tất cả)", cu["slots_all"])]
        for name, s in rows:
            print(f"{name:28}{fmt(s['precision'])}{fmt(s['recall'])}{fmt(s['f1'])}   {s['tp']}/{s['fp']}/{s['fn']}")
        print(f"đúng slot câu hỏi: {fmt(ag['questions']['slot_acc'])}%   đúng loại open/confirm: {fmt(ag['questions']['type_acc'])}%")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(report, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n→ {a.out}")


if __name__ == "__main__":
    main()
