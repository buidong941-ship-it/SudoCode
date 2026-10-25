#!/usr/bin/env python3
"""So router `laya` với nhãn Jev đã ghi trong trace, trên đúng các câu khách và cùng ngữ cảnh router đã thấy.

    # máy cá nhân: rút nhãn Jev từ trace thành file gọn (đóng gói cùng repo lên Kaggle)
    python scripts/router_agreement.py export --trace runs/kaggle/eval-b/out/eval-b/eval-b-4b-short-w1/{sample,dev,test}/full.jsonl \
        --out kaggle/ref/jev_routes.jsonl
    # Kaggle / máy có GPU: chạy Laya trên từng lượt rồi so
    python scripts/router_agreement.py replay --ref kaggle/ref/jev_routes.jsonl --langs vi en --out <thư mục>

Ngữ cảnh dựng lại giống `CallSession.turn`: 2 lượt gần nhất trong cùng cuộc gọi (khách + nhân viên) và tóm tắt phiên trước
trong Call Brief. Lượt Jev đã lùi về luật (`fallback`) không dùng làm nhãn so sánh vì nhãn đó là của luật.
Jev không phải đáp án đúng: tỷ lệ khớp chỉ cho biết Laya có thay được Jev mà hành vi planner không đổi hay không.
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FLAG_TH = {"agrees_to_buy": 0.5, "defers_decision": 0.5, "asks_if_bot": 0.6, "wants_data_deleted": 0.6,
           "medical_question": 0.7, "asks_internal_cost": 0.6, "mentions_competitor": 0.5}


def export(a):
    out, n = [], 0
    for path in a.trace:
        tag = os.path.basename(os.path.dirname(path))
        rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
        hist, summary = {}, {}
        for r in rows:
            key = (r["scenario_id"], r["call"])
            if r.get("turn") == 1:
                ls = (r.get("call_brief") or {}).get("last_session") or {}
                summary[key] = ls.get("summary") or ""
            h = hist.setdefault(key, [])
            rt = r.get("router") or {}
            out.append({"set": tag, "scenario_id": r["scenario_id"], "call": r["call"], "turn": r["turn"],
                        "text": r["customer_text"], "recent": h[-4:], "summary": summary.get(key, ""),
                        "jev": {k: rt.get(k) for k in ("intent", "confidence", "flags", "ms", "fallback")}})
            h += [{"role": "customer", "text": r["customer_text"]}, {"role": "agent", "text": r["agent_text"]}]
            n += 1
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        for x in out:
            fh.write(json.dumps(x, ensure_ascii=False) + "\n")
    print(f"{n} lượt → {a.out}")


def _pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))] if xs else None


def replay(a):
    from core.llm import router as R
    ref = [json.loads(l) for l in open(a.ref, encoding="utf-8") if l.strip()]
    rt = R.Router("laya")
    os.makedirs(a.out, exist_ok=True)
    report = {"n_rows": len(ref), "langs": {}}
    for lang in a.langs:
        preds, ms = [], []
        for x in ref:
            t0 = time.perf_counter()
            try:
                p = rt._laya(x["text"], {"recent": x["recent"], "summary": x["summary"]}, lang=lang)
            except Exception as e:
                p = {"error": f"{type(e).__name__}: {e}"}
            ms.append((time.perf_counter() - t0) * 1000)
            preds.append(p)
        both = [(x, p) for x, p in zip(ref, preds) if not x["jev"].get("fallback") and "error" not in p]
        agree = sum(1 for x, p in both if p["intent"] == x["jev"]["intent"])
        conf = {}
        for x, p in both:
            conf.setdefault(x["jev"]["intent"], {}).setdefault(p["intent"], 0)
            conf[x["jev"]["intent"]][p["intent"]] += 1
        flags = {}
        for f, th in FLAG_TH.items():
            tp = sum(1 for x, p in both if x["jev"]["flags"].get(f, 0) >= th and p["flags"][f] >= th)
            jp = sum(1 for x, p in both if x["jev"]["flags"].get(f, 0) >= th)
            lp = sum(1 for x, p in both if p["flags"][f] >= th)
            same = sum(1 for x, p in both if (x["jev"]["flags"].get(f, 0) >= th) == (p["flags"][f] >= th))
            flags[f] = {"threshold": th, "agree_pct": round(100 * same / max(1, len(both)), 1), "jev_on": jp, "laya_on": lp, "both_on": tp}
        low = sum(1 for _, p in both if p["confidence"] < R.settings.router_min_confidence)
        rep = {"n_compared": len(both), "n_jev_fallback": sum(1 for x in ref if x["jev"].get("fallback")),
               "n_errors": sum(1 for p in preds if "error" in p),
               "intent_agree_pct": round(100 * agree / max(1, len(both)), 1),
               "low_confidence_pct": round(100 * low / max(1, len(both)), 1),
               "truncated": sum(1 for p in preds if (p.get("usage") or {}).get("truncated")),
               "ms_p50": round(_pct(ms[3:] or ms, 50), 1), "ms_p95": round(_pct(ms[3:] or ms, 95), 1),
               "jev_ms_p50": _pct([x["jev"]["ms"] for x in ref if x["jev"].get("ms")], 50),
               "confusion_jev_to_laya": conf, "flags": flags}
        report["langs"][lang] = rep
        with open(os.path.join(a.out, f"laya_{lang}.jsonl"), "w", encoding="utf-8") as fh:
            for x, p in zip(ref, preds):
                fh.write(json.dumps({**{k: x[k] for k in ("set", "scenario_id", "call", "turn", "text", "jev")}, "laya": p},
                                    ensure_ascii=False) + "\n")
        print(f"[{lang}] khớp intent {rep['intent_agree_pct']}% trên {rep['n_compared']} lượt; "
              f"p50 {rep['ms_p50']} ms; cờ: " + ", ".join(f"{k} {v['agree_pct']}%" for k, v in flags.items()), flush=True)
    json.dump(report, open(os.path.join(a.out, "router_agreement.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--trace", nargs="+", required=True)
    e.add_argument("--out", required=True)
    r = sub.add_parser("replay")
    r.add_argument("--ref", required=True)
    r.add_argument("--langs", nargs="+", default=["vi", "en"])
    r.add_argument("--out", required=True)
    a = ap.parse_args()
    return export(a) if a.cmd == "export" else replay(a)


if __name__ == "__main__":
    sys.exit(main() or 0)
