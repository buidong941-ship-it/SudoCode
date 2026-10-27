"""Huấn luyện bộ phân loại "câu agent có phải câu hỏi / yêu cầu khách không" từ nhãn yếu (data programming, Snorkel).

1. Câu chưa gán nhãn: agent_text trong mọi trace dev + sample ở runs/ (khử trùng), tách câu bằng extractor._sentences.
   Loại câu của kịch bản test (datagen/out*/test) và câu của bộ đo tests/extract_eval/agent.jsonl.
2. Labeling function (luật): dấu "?", REQUEST_RX, MAYBE_ASK_RX + từ khóa slot, đuôi hỏi (trừ "không… đâu"), câu kể ("em đã/sẽ",
   "cảm ơn", "nhé" không có khách làm chủ ngữ), nhãn câu hỏi do bộ trích hybrid ghi trong trace (nếu có). Gộp bằng bỏ phiếu có trọng số.
3. TF-IDF n-gram ký tự (trên chữ đã fold) + LogisticRegression. τ chọn trên nửa A của agent.jsonl (id chẵn), báo số trên nửa B.
4. Lưu models/question_clf/model.pkl ({vec, clf, tau}); extractor.agent_questions dùng khi QUESTION_CLF=1.

    python scripts/train_question_clf.py
"""
import glob
import json
import os
import pickle
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("RAG_MODE", "bm25")

from harness.extractor import REQUEST_RX, SLOT_KW, _sentences  # noqa: E402
from harness.llm_extract import MAYBE_ASK_RX, QUESTION_TAIL_RX  # noqa: E402
from harness.textnorm import fold  # noqa: E402

OUT = os.path.join(ROOT, "models", "question_clf", "model.pkl")
STATEMENT_RX = re.compile(r"^(da\W+)?(em|ben em|shop|don|gia|may|san pham|chuong trinh)\b.*\b(roi|nhe|nha|a)\W*$")
THANKS_RX = re.compile(r"\b(cam on|xin loi|chuc)\b")
ASSERT_NEG_RX = re.compile(r"\b(khong|chua|chang) (co|phai|con|mat|can)\b")
ADDRESS_ONLY_RX = re.compile(r"^(da\W+)?(vang\W+)?(anh|chi|co|chu|ban)(\s\w+)?\W+a\W*$")
NEG_DAU_RX = re.compile(r"\b(khong|chua|chang)\b[^,;]*\bdau\W*(a|nhe|nha)?\W*$")


def test_ids():
    ids = set()
    for d in ("datagen/out_nat/test", "datagen/out/test"):
        ids |= {os.path.basename(p)[:-5] for p in glob.glob(os.path.join(ROOT, d, "*.json"))}
    return ids


def lfs(s, trace_q):
    f = fold(s)
    votes = []
    if s.endswith("?"):
        votes.append((1, 3.0))
    if REQUEST_RX.search(f):
        votes.append((1, 2.0))
    if MAYBE_ASK_RX.search(f) and any(re.search(rx, f) for _, rx in SLOT_KW):
        votes.append((1, 1.5))
    if QUESTION_TAIL_RX.search(f) and not NEG_DAU_RX.search(f) and not ASSERT_NEG_RX.search(f):
        votes.append((1, 1.0))
    if not s.endswith("?") and (ASSERT_NEG_RX.search(f) or ADDRESS_ONLY_RX.search(f) or re.search(r"\d\.\d{3}\.\d{3}", s)):
        votes.append((0, 2.0))
    if trace_q is not None:
        votes.append((1 if trace_q else 0, 1.0))
    if not s.endswith("?"):
        if THANKS_RX.search(f):
            votes.append((0, 1.5))
        if STATEMENT_RX.search(f) and not MAYBE_ASK_RX.search(f):
            votes.append((0, 1.5))
        if not votes:
            votes.append((0, 1.0))
    return votes


def gather():
    bad = test_ids()
    held = {json.loads(l)["sentence"] for l in open(os.path.join(ROOT, "tests", "extract_eval", "agent.jsonl"), encoding="utf-8")}
    seen = {}
    files = [p for p in glob.glob(os.path.join(ROOT, "runs", "**", "*.jsonl"), recursive=True)
             if re.search(r"[\\/](dev|sample)[\\/]", p) and not re.search(r"[\\/]test[\\/]", p)]
    for p in files:
        for l in open(p, encoding="utf-8"):
            try:
                r = json.loads(l)
            except ValueError:
                continue
            if r.get("scenario_id") in bad or not r.get("agent_text"):
                continue
            qtexts = {q.get("text") for q in r.get("questions") or []}
            for s in _sentences(r["agent_text"]):
                if s in held or len(s) < 4:
                    continue
                q = s in qtexts if (r.get("extractor") or {}).get("backend", "rules") != "rules" else None
                prev = seen.get(s)
                seen[s] = q if prev is None else (prev or bool(q))
    return seen, len(files)


def label(seen):
    X, y = [], []
    for s, tq in seen.items():
        score = sum(w if v else -w for v, w in lfs(s, tq))
        if abs(score) >= 1.0:
            X.append(fold(s)); y.append(int(score > 0))
    return X, y


def evaluate(pred, gold):
    pred = [bool(p) for p in pred]
    tp = sum(p and g for p, g in zip(pred, gold)); fp = sum(p and not g for p, g in zip(pred, gold))
    fn = sum(g and not p for p, g in zip(pred, gold))
    return {"precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None, "tp": tp, "fp": fp, "fn": fn}


def main():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    seen, nfiles = gather()
    X, y = label(seen)
    print(f"{nfiles} file trace, {len(seen)} câu khác nhau, {len(X)} câu có nhãn yếu ({sum(y)} câu hỏi)")
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)
    clf = LogisticRegression(C=4.0, max_iter=2000, class_weight="balanced")
    clf.fit(vec.fit_transform(X), y)
    items = [json.loads(l) for l in open(os.path.join(ROOT, "tests", "extract_eval", "agent.jsonl"), encoding="utf-8")]
    halves = {h: [it for it in items if (int(re.sub(r"\D", "", it["id"]) or 0) % 2 == (h == "B"))] for h in ("A", "B")}
    prob = {h: clf.predict_proba(vec.transform([fold(it["sentence"]) for it in v]))[:, 1] for h, v in halves.items()}
    gold = {h: [bool(it["ask"]) for it in v] for h, v in halves.items()}
    rules = {h: [it["sentence"].endswith("?") or bool(REQUEST_RX.search(fold(it["sentence"]))) for it in v] for h, v in halves.items()}
    best = None
    for tau in [x / 100 for x in range(30, 96, 5)]:
        m = evaluate([r or p >= tau for r, p in zip(rules["A"], prob["A"])], gold["A"])
        if m["precision"] is not None and m["precision"] >= 0.95 and (best is None or m["recall"] > best[1]["recall"]):
            best = (tau, m)
    tau = best[0] if best else 0.9
    t0 = time.perf_counter()
    for it in items:
        clf.predict_proba(vec.transform([fold(it["sentence"])]))
    ms = (time.perf_counter() - t0) * 1000 / len(items)
    report = {"tau": tau, "half_A": best[1] if best else None,
              "half_B": evaluate([r or p >= tau for r, p in zip(rules["B"], prob["B"])], gold["B"]),
              "half_B_rules_only": evaluate(rules["B"], gold["B"]), "ms_per_sentence": round(ms, 2),
              "n_train": len(X), "n_train_questions": sum(y)}
    print(json.dumps(report, ensure_ascii=False, indent=1))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    pickle.dump({"vec": vec, "clf": clf, "tau": tau, "report": report}, open(OUT, "wb"))
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
