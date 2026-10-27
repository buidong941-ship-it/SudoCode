#!/usr/bin/env python3
"""Huấn luyện/đánh giá bộ hỏi agent sau khi người dùng điền CSV 200 câu."""
import csv
import json
import os
import pickle
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("RAG_MODE", "bm25")

from scripts.train_question_clf import REQUEST_RX, gather, label  # noqa: E402
from harness.textnorm import fold  # noqa: E402

CSV = os.path.join(ROOT, "docs", "REVIEW-QUESTION-CLF-200.csv")
OUT = os.path.join(ROOT, "models", "question_clf", "model.pkl")


def metrics(pred, gold):
    tp = int(sum(p and g for p, g in zip(pred, gold)))
    fp = int(sum(p and not g for p, g in zip(pred, gold)))
    fn = int(sum(g and not p for p, g in zip(pred, gold)))
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None}


def main():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split

    rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig", newline="")))
    if len(rows) != 200 or any(r.get("human_label_0_or_1", "").strip() not in ("0", "1") for r in rows):
        raise SystemExit("CSV cần đủ 200 nhãn người kiểm (`human_label_0_or_1` chỉ nhận 0 hoặc 1).")
    texts = [r["sentence_dev_or_sample"].strip() for r in rows]
    gold = [int(r["human_label_0_or_1"].strip()) for r in rows]
    if len(set(texts)) != len(texts):
        raise SystemExit("CSV có câu trùng; không đánh giá khi chưa khử trùng.")
    indices = list(range(len(rows)))
    train_idx, test_idx = train_test_split(indices, test_size=0.2, random_state=20261027, stratify=gold)
    fit_idx, tune_idx = train_test_split(train_idx, test_size=0.25, random_state=20261028,
                                         stratify=[gold[i] for i in train_idx])
    if min(sum(gold[i] for i in part) for part in (fit_idx, tune_idx, test_idx)) == 0:
        raise SystemExit("Mỗi phần train/tune/test cần có câu hỏi lẫn câu không hỏi.")

    seen, nfiles = gather()
    held = set(texts)
    weak_seen = {s: q for s, q in seen.items() if s not in held}
    weak_x, weak_y = label(weak_seen)
    fit_x = weak_x + [fold(texts[i]) for i in fit_idx]
    fit_y = weak_y + [gold[i] for i in fit_idx]
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)
    clf = LogisticRegression(C=4.0, max_iter=2000, class_weight="balanced")
    clf.fit(vec.fit_transform(fit_x), fit_y)
    rules = lambda ids: [texts[i].endswith("?") or bool(REQUEST_RX.search(fold(texts[i]))) for i in ids]
    tune_p = clf.predict_proba(vec.transform([fold(texts[i]) for i in tune_idx]))[:, 1]
    tune_r = rules(tune_idx)
    best = None
    for tau in [x / 100 for x in range(30, 96, 5)]:
        m = metrics([r or p >= tau for r, p in zip(tune_r, tune_p)], [gold[i] for i in tune_idx])
        if m["precision"] is not None and m["precision"] >= 0.95 and (best is None or m["recall"] > best[1]["recall"]):
            best = (tau, m)
    tau = best[0] if best else 0.9
    test_p = clf.predict_proba(vec.transform([fold(texts[i]) for i in test_idx]))[:, 1]
    test_r = rules(test_idx)
    human_test = [gold[i] for i in test_idx]
    baseline = metrics(test_r, human_test)
    combined = metrics([r or p >= tau for r, p in zip(test_r, test_p)], human_test)
    t0 = time.perf_counter()
    for s in texts:
        clf.predict_proba(vec.transform([fold(s)]))
    ms = round((time.perf_counter() - t0) * 1000 / len(texts), 2)
    report = {"n_human": len(rows), "train_human": len(fit_idx), "tune_human": len(tune_idx), "test_human": len(test_idx),
              "n_weak_train": len(weak_x), "trace_files": nfiles, "tau": tau,
              "tune": best[1] if best else None, "test_rules": baseline, "test_classifier_plus_rules": combined,
              "ms_per_sentence": ms}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    pickle.dump({"vec": vec, "clf": clf, "tau": tau, "report": report}, open(OUT, "wb"))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
