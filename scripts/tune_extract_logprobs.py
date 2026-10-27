#!/usr/bin/env python3
import argparse
import json
import re


FIELDS = ("is_human", "promo_active", "objection", "blocker", "competitor_price_vnd")


def tune(section, min_precision=0.95):
    thresholds = {}
    reports = {}
    for field in FIELDS:
        samples = [x for x in section.get("logprob_samples", []) if x.get("field") == field]
        parity = lambda x: int(re.sub(r"\D", "", x.get("id", "0")) or 0) % 2
        train = [x for x in samples if parity(x) == 0]
        held = [x for x in samples if parity(x) == 1]
        confident = [x for x in train if isinstance(x.get("confidence"), (int, float))]
        if len(confident) < 5 or len(held) < 5:
            continue

        def fn_count(ids):
            n = 0
            for err in section.get("errors", []):
                if err.get("id") not in ids:
                    continue
                if err.get("kind") == "claim_fn" and err.get("field") == field:
                    n += 1
                elif err.get("slot") == field and err.get("gold") is not None:
                    n += 1
            return n

        train_ids, held_ids = {x["id"] for x in train}, {x["id"] for x in held}
        candidates = sorted({0.0, 1.0, *(x["confidence"] for x in confident)})
        best = None
        for tau in candidates:
            kept = [x for x in train if x.get("confidence") is None or x["confidence"] >= tau]
            tp = sum(x["correct"] for x in kept)
            fp = len(kept) - tp
            dropped_tp = sum(x["correct"] for x in train if x.get("confidence") is not None and x["confidence"] < tau)
            fn = fn_count(train_ids) + dropped_tp
            p = tp / (tp + fp) if tp + fp else 1.0
            r = tp / (tp + fn) if tp + fn else 1.0
            rank = (r, p, -tau)
            if p >= min_precision and (best is None or rank > best[0]):
                best = (rank, tau, {"precision": p, "recall": r, "tp": tp, "fp": fp, "fn": fn})
        if best:
            thresholds[field] = best[1]
            kept = [x for x in held if x.get("confidence") is None or x["confidence"] >= best[1]]
            tp = sum(x["correct"] for x in kept)
            fp = len(kept) - tp
            dropped_tp = sum(x["correct"] for x in held if x.get("confidence") is not None and x["confidence"] < best[1])
            fn = fn_count(held_ids) + dropped_tp
            reports[field] = {"threshold": best[1], "calibration": best[2],
                              "holdout": {"precision": tp / (tp + fp) if tp + fp else None,
                                          "recall": tp / (tp + fn) if tp + fn else None,
                                          "tp": tp, "fp": fp, "fn": fn},
                              "calibration_n": len(train), "holdout_n": len(held)}
    return thresholds, reports


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--mode", default="llm")
    ap.add_argument("--min-precision", type=float, default=0.95)
    args = ap.parse_args()
    report = json.load(open(args.report, encoding="utf-8"))["modes"][args.mode]
    thresholds, details = {}, {}
    for part, section in (("agent", report["agent"]), ("customer", report["customer"])):
        chosen, scored = tune(section, args.min_precision)
        thresholds.update(chosen); details[part] = scored
    print(json.dumps({"thresholds": thresholds, "details": details}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
