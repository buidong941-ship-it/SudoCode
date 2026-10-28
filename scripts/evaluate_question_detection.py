#!/usr/bin/env python3
"""Evaluate rule and pretrained Jev question detection without fitting a model."""

import argparse
import csv
import hashlib
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("RAG_MODE", "bm25")

from harness import extractor  # noqa: E402
from harness.question_classifiers.jev import JevQuestionClassifier  # noqa: E402
from core.config import settings  # noqa: E402


def metrics(predicted, expected):
    tp = sum(bool(p) and bool(g) for p, g in zip(predicted, expected))
    fp = sum(bool(p) and not bool(g) for p, g in zip(predicted, expected))
    fn = sum(not bool(p) and bool(g) for p, g in zip(predicted, expected))
    tn = len(expected) - tp - fp - fn
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            "accuracy": (tp + tn) / len(expected) if expected else None}


def percentile(values, fraction):
    values = sorted(values)
    return values[int(fraction * (len(values) - 1))] if values else None


def read_labels(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows or any(row.get("human_label_0_or_1", "").strip() not in ("0", "1") for row in rows):
        raise SystemExit("CSV phải có nhãn người kiểm 0/1 cho mọi câu.")
    if len({row["sample_id"] for row in rows}) != len(rows):
        raise SystemExit("CSV có sample_id trùng.")
    return rows


def load_checkpoint(path):
    cached = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    item = json.loads(line)
                    cached[(item["sample_id"], item["text_sha256"])] = item
                except (ValueError, KeyError):
                    continue
    return cached


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default=os.path.join(ROOT, "docs", "REVIEW-QUESTION-CLF-200.csv"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--threshold", type=float, default=0.75)
    ap.add_argument("--max-calls", type=int, default=0, help="0 = đánh giá toàn bộ CSV; số dương = giới hạn API call mới")
    args = ap.parse_args()
    if not 0 <= args.threshold <= 1 or args.max_calls < 0:
        ap.error("threshold phải trong [0,1] và max-calls không âm")
    rows = read_labels(args.csv)
    os.makedirs(args.out, exist_ok=True)
    checkpoint = os.path.join(args.out, "jev_predictions.jsonl")
    cached = load_checkpoint(checkpoint)
    if not settings.typesafe_api_key and any(
            (row["sample_id"], hashlib.sha256(row["sentence_dev_or_sample"].strip().encode("utf-8")).hexdigest())
            not in cached for row in rows):
        raise SystemExit("Thiếu TYPESAFE_API_KEY để gọi Jev cho các câu chưa có checkpoint.")
    jev = JevQuestionClassifier(threshold=args.threshold)
    observed = []
    new_calls = 0
    with open(checkpoint, "a", encoding="utf-8") as fh:
        for row in rows:
            sentence = row["sentence_dev_or_sample"].strip()
            digest = hashlib.sha256(sentence.encode("utf-8")).hexdigest()
            key = (row["sample_id"], digest)
            item = cached.get(key)
            if item is None and (args.max_calls == 0 or new_calls < args.max_calls):
                prediction = jev.predict(sentence)
                item = {"sample_id": key[0], "text_sha256": key[1],
                        "probability": prediction.probability,
                        "latency_ms": round(prediction.latency_ms, 2), "error": prediction.error}
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
                fh.flush()
                new_calls += 1
            if item is not None:
                observed.append((row, sentence, item))

    if not observed:
        raise SystemExit("Chưa có dự đoán Jev để đánh giá.")
    gold = [int(row["human_label_0_or_1"]) for row, _, _ in observed]
    rules = [bool(extractor.agent_questions(sentence, {})) for _, sentence, _ in observed]
    probabilities = [item["probability"] for _, _, item in observed]
    jev_only = [p is not None and p >= args.threshold for p in probabilities]
    combined = [r or p for r, p in zip(rules, jev_only)]
    latencies = [item["latency_ms"] for _, _, item in observed if item["probability"] is not None]
    report = {"status": "complete" if len(observed) == len(rows) else "partial",
              "labeled": len(rows), "evaluated": len(observed), "new_jev_calls": new_calls,
              "threshold": args.threshold, "model_training": False,
              "rules": metrics(rules, gold), "jev_only": metrics(jev_only, gold),
              "jev_plus_rules": metrics(combined, gold),
              "jev_errors": sum(item["error"] is not None for _, _, item in observed),
              "jev_successful_calls": len(latencies),
              "latency_ms_p50": statistics.median(latencies) if latencies else None,
              "latency_ms_p95": percentile(latencies, 0.95),
              "note": "Đánh giá mô tả trên nhãn hiện có; ngưỡng 0.75 đã được chọn trong thử nghiệm trước, không coi đây là holdout mới."}
    with open(os.path.join(args.out, "question_detection_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "question_detection_predictions.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["sample_id", "human_gold", "rules", "jev_probability", "jev_plus_rules", "jev_error"])
        for (row, _, item), g, r, c in zip(observed, gold, rules, combined):
            writer.writerow([row["sample_id"], g, int(r), item["probability"], int(c), item["error"] or ""])
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
