#!/usr/bin/env python3
"""Compare local CPU and Jev question classifiers on one human-labeled Kaggle holdout.

Run after evaluate_question_clf_labels.py has trained models/question_clf/model.pkl.
The same deterministic 120/40/40 fit/tune/test split is used for both backends.
"""
import argparse
import csv
import json
import os
import pickle
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("RUN_PROFILE", "kaggle")
os.environ.setdefault("RAG_MODE", "bm25")

from sklearn.model_selection import train_test_split  # noqa: E402

from harness.question_classifiers import get_classifier  # noqa: E402
from harness.textnorm import fold  # noqa: E402
from scripts.evaluate_question_clf_labels import CSV, metrics  # noqa: E402
from scripts.train_question_clf import REQUEST_RX  # noqa: E402


def rule_prediction(text):
    return text.endswith("?") or bool(REQUEST_RX.search(fold(text)))


def score(pred, gold):
    m = metrics(pred, gold)
    tp, fp, fn = m["tp"], m["fp"], m["fn"]
    tn = len(gold) - tp - fp - fn
    m["tn"] = tn
    m["f1"] = (2 * tp / (2 * tp + fp + fn)) if 2 * tp + fp + fn else None
    m["accuracy"] = (tp + tn) / len(gold) if gold else None
    return m


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    return values[int(q * (len(values) - 1))]


def choose_tau(probabilities, gold, rules):
    best = None
    for tau in [x / 100 for x in range(30, 96, 5)]:
        pred = [r or (p is not None and p >= tau) for r, p in zip(rules, probabilities)]
        m = score(pred, gold)
        if m["precision"] is not None and m["precision"] >= 0.95:
            if best is None or m["recall"] > best[1]["recall"]:
                best = tau, m
    return best[0] if best else 0.9, (best[1] if best else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="Kaggle output directory for reports and model artifact")
    ap.add_argument("--model", default=os.path.join(ROOT, "models", "question_clf", "model.pkl"))
    ap.add_argument("--max-retries", type=int, default=2)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig", newline="")))
    if len(rows) != 200 or any(r.get("human_label_0_or_1", "").strip() not in ("0", "1") for r in rows):
        raise SystemExit("Cần đủ 200 nhãn người kiểm trong REVIEW-QUESTION-CLF-200.csv.")
    texts = [r["sentence_dev_or_sample"].strip() for r in rows]
    gold = [int(r["human_label_0_or_1"].strip()) for r in rows]
    if len(set(texts)) != len(texts):
        raise SystemExit("CSV chứa câu trùng; dừng để tránh rò rỉ train/test.")

    ids = list(range(len(rows)))
    train_idx, test_idx = train_test_split(ids, test_size=0.2, random_state=20261027, stratify=gold)
    fit_idx, tune_idx = train_test_split(train_idx, test_size=0.25, random_state=20261028,
                                         stratify=[gold[i] for i in train_idx])
    model = pickle.load(open(args.model, "rb"))
    local = get_classifier("local")
    jev = get_classifier("jev")

    # Cache responses in Kaggle output so an interrupted benchmark does not repeat Jev calls.
    checkpoint = os.path.join(args.out, "jev_predictions.jsonl")
    cached = {}
    if os.path.exists(checkpoint):
        for line in open(checkpoint, encoding="utf-8"):
            try:
                item = json.loads(line)
                if item.get("probability") is not None or item.get("error"):
                    cached[item["sample_id"]] = item
            except (ValueError, KeyError):
                continue

    jev_rows = {}
    with open(checkpoint, "a", encoding="utf-8") as fh:
        for index in tune_idx + test_idx:
            sample_id, text = rows[index]["sample_id"], texts[index]
            if sample_id in cached:
                jev_rows[index] = cached[sample_id]
                continue
            prediction = None
            for attempt in range(args.max_retries + 1):
                prediction = jev.predict(text)
                if prediction.error is None:
                    break
                if attempt < args.max_retries:
                    time.sleep(1.5 * (attempt + 1))
            item = {"sample_id": sample_id, "probability": prediction.probability,
                    "latency_ms": round(prediction.latency_ms, 2), "error": prediction.error}
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
            fh.flush()
            jev_rows[index] = item
            done = len(jev_rows)
            if done % 10 == 0 or done == len(tune_idx) + len(test_idx):
                print(f"Jev: {done}/{len(tune_idx) + len(test_idx)} câu; lỗi={sum(bool(x['error']) for x in jev_rows.values())}", flush=True)

    local_preds, local_probs, local_ms = {}, {}, []
    for index in tune_idx + test_idx:
        pred = local.predict(texts[index])
        local_preds[index], local_probs[index] = pred.is_question, pred.probability
        local_ms.append(pred.latency_ms)
    tune_gold = [gold[i] for i in tune_idx]
    tune_rules = [rule_prediction(texts[i]) for i in tune_idx]
    jev_tune_probs = [jev_rows[i]["probability"] for i in tune_idx]
    jev_tau, jev_tune_metrics = choose_tau(jev_tune_probs, tune_gold, tune_rules)

    test_gold = [gold[i] for i in test_idx]
    test_rules = [rule_prediction(texts[i]) for i in test_idx]
    test_jev_probs = [jev_rows[i]["probability"] for i in test_idx]
    local_test = [local_preds[i] for i in test_idx]
    local_rule_union = [r or p for r, p in zip(test_rules, local_test)]
    jev_raw = [p is not None and p >= jev_tau for p in test_jev_probs]
    jev_union = [r or p for r, p in zip(test_rules, jev_raw)]
    # Production-compatible fallback: on Jev errors keep the deterministic rule result.
    jev_fallback = [r if p is None else (r or p >= jev_tau) for r, p in zip(test_rules, test_jev_probs)]
    rule_only = test_rules
    report = {
        "status": "complete" if all(p is not None for p in test_jev_probs + jev_tune_probs) else "partial_jev_errors",
        "backend_contract": "predict(text) -> probability, threshold, latency_ms, error",
        "split": {"fit": len(fit_idx), "tune": len(tune_idx), "test": len(test_idx),
                  "random_state_test": 20261027, "random_state_tune": 20261028,
                  "test_ids": [rows[i]["sample_id"] for i in test_idx]},
        "local": {"tau": float(model["tau"]), "test": score(local_rule_union, test_gold),
                  "test_classifier_only": score(local_test, test_gold),
                  "tune": model.get("report", {}).get("tune"),
                  "latency_ms_mean": round(statistics.mean(local_ms), 3),
                  "latency_ms_p50": round(statistics.median(local_ms), 3),
                  "latency_ms_p95": round(sorted(local_ms)[int(0.95 * (len(local_ms) - 1))], 3)},
        "jev": {"tau": jev_tau, "test": score(jev_union, test_gold),
                "test_classifier_only": score(jev_raw, test_gold), "tune": jev_tune_metrics,
                "successful_test_calls": sum(p is not None for p in test_jev_probs),
                "test_calls": len(test_idx),
                "latency_ms_mean": round(statistics.mean([jev_rows[i]["latency_ms"] for i in tune_idx + test_idx]), 2),
                "latency_ms_p50": round(statistics.median([jev_rows[i]["latency_ms"] for i in tune_idx + test_idx]), 2),
                "latency_ms_p95": round(percentile([jev_rows[i]["latency_ms"] for i in tune_idx + test_idx], 0.95), 2),
                "errors": [{"sample_id": rows[i]["sample_id"], "error": jev_rows[i]["error"]}
                           for i in tune_idx + test_idx if jev_rows[i]["error"]]},
        "rules_baseline": score(rule_only, test_gold),
        "jev_failure_fallback": score(jev_fallback, test_gold),
        "notes": ["Human-labeled 40-row holdout; Jev threshold selected only on the 40-row tune split.",
                  "Local threshold comes from evaluate_question_clf_labels.py on the same deterministic split.",
                  "Rule union preserves the existing question-mark/request safety net; Jev errors fall back to rules."],
    }
    report_path = os.path.join(args.out, "question_classifier_comparison.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    with open(os.path.join(args.out, "question_classifier_predictions.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["sample_id", "split", "sentence", "human_gold", "rules", "local_probability", "local_union",
                         "jev_probability", "jev_union", "jev_error"])
        for index in tune_idx + test_idx:
            split = "tune" if index in set(tune_idx) else "test"
            r, lp, jp = rule_prediction(texts[index]), local_probs[index], jev_rows[index]["probability"]
            writer.writerow([rows[index]["sample_id"], split, texts[index], gold[index], int(r), round(lp, 6),
                             int(r or local_preds[index]), "" if jp is None else round(jp, 6),
                             int(r or (jp is not None and jp >= jev_tau)), jev_rows[index]["error"] or ""])

    with open(os.path.join(args.out, "question_classifier_comparison.md"), "w", encoding="utf-8") as fh:
        fh.write("# So sánh question classifier trên Kaggle\n\n")
        fh.write("Tập test người kiểm, cùng 40 câu; Jev và local chỉ chạy shadow, không đổi hành vi agent.\n\n")
        fh.write("| Phương án | Precision | Recall | F1 | Accuracy | p50 ms/câu | p95 ms/câu |\n|---|---:|---:|---:|---:|---:|---:|\n")
        entries = [("Rules", report["rules_baseline"], None, None),
                   ("Local + rules", report["local"]["test"], report["local"]["latency_ms_p50"], report["local"]["latency_ms_p95"]),
                   ("Jev + rules", report["jev"]["test"], report["jev"]["latency_ms_p50"], report["jev"]["latency_ms_p95"]),
                   ("Jev lỗi → rules", report["jev_failure_fallback"], report["jev"]["latency_ms_p50"], report["jev"]["latency_ms_p95"])]
        for name, m, p50, p95 in entries:
            pct = lambda x: "—" if x is None else f"{100*x:.1f}%"
            fh.write(f"| {name} | {pct(m['precision'])} | {pct(m['recall'])} | {pct(m['f1'])} | {pct(m['accuracy'])} | "
                     f"{'—' if p50 is None else f'{p50:.2f}'} | {'—' if p95 is None else f'{p95:.2f}'} |\n")
        fh.write(f"\nJev: tau={jev_tau:.2f}; API call thành công trên test {report['jev']['successful_test_calls']}/{len(test_idx)}.\n")
        fh.write("\n**Cảnh báo:** chỉ có 40 câu test; xem đây là phép so sánh ban đầu, không phải bằng chứng thống kê mạnh.\n")

    model_out = os.path.join(args.out, "question_clf_model.pkl")
    with open(args.model, "rb") as src, open(model_out, "wb") as dst:
        dst.write(src.read())
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    print(f"outputs: {args.out}", flush=True)


if __name__ == "__main__":
    main()
