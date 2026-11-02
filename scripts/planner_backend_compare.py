"""B-H: so planner backend jev / qwen (và rules làm mốc) trên bộ nhãn goal tests/planner_eval/goals.jsonl.

Bộ nhãn: 28 lượt dev rơi vào fallback/closing (trace 01/11) + 8 câu tự viết cho goal ít gặp. Chỉ dev, không holdout/test.
Đo: độ chính xác chọn goal (tính trên lượt không abstain và trên tất cả), tỷ lệ abstain, latency p50/p95 của riêng lần gọi
planner. Quy tắc chốt (PLAN B-H): giữ Jev làm chính trừ khi Qwen chính xác hơn ≥10 điểm và p95 vẫn trong tiêu chí.

    python scripts/planner_backend_compare.py --backends jev qwen [--min-conf 0.6] [--out runs/planner_compare.json]
Cần TYPESAFE_API_KEY (jev) / vLLM ở QWEN_BASE_URL (qwen) — chạy trên Kaggle.
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core.config import settings  # noqa: E402
from harness import planner_llm  # noqa: E402


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))] if xs else None


def run(backend, items):
    res, ms = [], []
    for it in items:
        t0 = time.perf_counter()
        s = planner_llm.suggest(it["text"], it.get("recent", []), it["state"], backend=backend)
        ms.append((time.perf_counter() - t0) * 1000)
        res.append({"id": it["id"], "gold": it["gold"], "pred": s["goal"], "conf": s["confidence"],
                    "abstain": s["goal"] is None, "fallback": s["fallback"], "backend_used": s["backend"]})
    answered = [r for r in res if not r["abstain"]]
    correct = sum(r["pred"] == r["gold"] for r in answered)
    return {"n": len(res), "abstain_rate": round(1 - len(answered) / len(res), 3) if res else None,
            "acc_answered": round(correct / len(answered), 3) if answered else None,
            "acc_all": round(correct / len(res), 3) if res else None,
            "fallbacks": sum(1 for r in res if r["fallback"]), "ms_p50": round(pct(ms, 50) or 0), "ms_p95": round(pct(ms, 95) or 0),
            "errors": [r for r in res if r["pred"] != r["gold"]]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--backends", nargs="+", default=["jev", "qwen"])
    ap.add_argument("--min-conf", type=float, default=None, help="ghi đè PLANNER_JEV_MIN_CONF")
    ap.add_argument("--sweep", nargs="*", type=float, default=[], help="thử nhiều ngưỡng Jev, vd 0.4 0.5 0.6 0.7")
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "planner_compare.json"))
    a = ap.parse_args()
    items = [json.loads(l) for l in open(os.path.join(ROOT, "tests", "planner_eval", "goals.jsonl"), encoding="utf-8") if l.strip()]
    if a.min_conf is not None:
        settings.planner_jev_min_conf = a.min_conf
    report = {"n_items": len(items), "min_conf": settings.planner_jev_min_conf, "backends": {}}
    for b in a.backends:
        report["backends"][b] = r = run(b, items)
        print(f"{b:<5} chính xác (đã trả lời) {r['acc_answered']} · (tất cả) {r['acc_all']} · abstain {r['abstain_rate']} · "
              f"fallback {r['fallbacks']} · p50 {r['ms_p50']}ms p95 {r['ms_p95']}ms")
    for th in a.sweep:
        settings.planner_jev_min_conf = th
        r = run("jev", items)
        report.setdefault("jev_sweep", {})[str(th)] = {k: r[k] for k in ("acc_answered", "acc_all", "abstain_rate")}
        print(f"jev ngưỡng {th}: {report['jev_sweep'][str(th)]}")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(report, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("→", a.out)


if __name__ == "__main__":
    main()
