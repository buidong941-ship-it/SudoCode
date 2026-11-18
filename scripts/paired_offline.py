"""So cặp xác định (offline) giữa snapshot mã cũ và mã hiện tại — chạy trên Kaggle CPU, không gọi model.

    python scripts/paired_offline.py <snapshot.tar.gz> <out_dir> [--sets DIR ...] [--variant TAG:K=V;K=V ...]

Mỗi biến thể chạy run_eval (router rules, generator offline, extractor rules, transport direct) trên CÙNG bộ kịch bản của checkout
hiện tại, một lần bằng mã snapshot (giải nén vào out_dir/old_src) và một lần bằng mã hiện tại; chấm bằng eval/reference_eval.py
như BTC phát hành; rồi so từng lượt: goals, chuỗi tool (tên + đối số, bỏ generated_at), agent_text. Generator offline nên số
HR/RQR ở đây không phải số báo cáo — chỉ để thấy lượt nào đổi đường đi và đổi kết quả trước khi tốn GPU.
"""
import argparse
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_ENV = {"PYTHONIOENCODING": "utf-8", "RUN_PROFILE": "local", "RAG_MODE": "bm25", "LLM_CACHE": "off", "PRODUCT_LEXICON": "1",
            "ORDER_QTY": "1", "LEXICON_INCLUDE": "approved", "REPLY_STYLE": "short", "STRIP_QUESTIONS": "1", "GEN_PLACEHOLDERS": "0",
            "QUESTION_CLF": "0", "IMPROVE_DIR": "", "PLANNER_BACKEND": "rules", "JEV_SIMULATED": "1", "EXTRACTOR_LLM": "qwen"}


def run(src, scen, out, env):
    out.parent.mkdir(parents=True, exist_ok=True)
    e = dict(os.environ, **BASE_ENV, **env, DATABASE_URL="sqlite:///" + str(out.with_suffix(".db")).replace("\\", "/"))
    cmd = [sys.executable, "run_eval.py", "--scenarios", str(scen), "--config", "full", "--out", str(out), "--router", "rules",
           "--generator", "offline", "--extractor", "rules", "--transport", "direct", "--workers", "2"]
    r = subprocess.run(cmd, cwd=src, env=e, capture_output=True, text=True)
    out.with_suffix(".log").write_text(r.stdout[-20000:] + r.stderr[-20000:], encoding="utf-8")
    rep = out.with_suffix(".report.json")
    subprocess.run([sys.executable, "eval/reference_eval.py", "--scenarios", str(scen), "--trace", str(out), "--out", str(rep)],
                   cwd=ROOT, env=dict(os.environ, PYTHONIOENCODING="utf-8"), capture_output=True, text=True)
    return r.returncode, json.loads(rep.read_text(encoding="utf-8"))["system"] if rep.exists() else None


def rows(path):
    by = {}
    for line in open(path, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            by[(r["scenario_id"], r["call"], r.get("turn"))] = r
    return by


def view(r):
    tools = [(t["name"], {k: v for k, v in (t.get("args") or {}).items() if k not in ("brief",)}) for t in r.get("tool_calls", [])]
    return {"goals": r.get("goals"), "tools": tools, "text": r.get("agent_text")}


def summary(m):
    if not m:
        return None
    return {"TSR": m["task_success_rate"]["value"], "CCR": m["context_carryover_rate"]["value"], "RQR": m["repeat_question_rate"]["value"],
            "HR_price": m["hallucination_rate"]["price_promo_only"]["value"], "guardrail": m["guardrail_violations"]["total"],
            "failed": sorted({f["scenario"] for f in m["task_success_rate"]["failures"]})}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot"); ap.add_argument("out")
    ap.add_argument("--sets", nargs="+", default=["datagen/out_v3/final/dev", "datagen/out_redteam/dev"])
    ap.add_argument("--variant", action="append", default=[])
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    old = out / "old_src"
    if not old.exists():
        with tarfile.open(a.snapshot, "r:gz") as t:   # tên .bin: Kaggle tự giải nén file .tar.gz lồng trong dataset
            t.extractall(old)
    variants = [(v.split(":", 1)[0], dict(x.split("=", 1) for x in v.split(":", 1)[1].split(";") if x)) for v in a.variant] or \
               [("rules-gc", {"PLANNER_SELECTOR": "rules", "GOAL_CONTRACT": "1", "CONTRACT_V2": "0"})]
    report = []
    for tag, env in variants:
        for s in a.sets:
            scen = (ROOT / s).resolve()
            name = s.strip("/").replace("/", "_")
            res = {}
            for side, src in (("old", old), ("new", ROOT)):
                rc, m = run(src, scen, out / side / tag / f"{name}.jsonl", env)
                res[side] = {"rc": rc, **(summary(m) or {})}
            A, B = rows(out / "old" / tag / f"{name}.jsonl"), rows(out / "new" / tag / f"{name}.jsonl")
            diffs = []
            for k in sorted(set(A) | set(B), key=str):
                va, vb = view(A[k]) if k in A else None, view(B[k]) if k in B else None
                if va != vb:
                    diffs.append({"turn": list(k), "old": va, "new": vb})
            gained = sorted(set(res["old"].get("failed", [])) - set(res["new"].get("failed", [])))
            lost = sorted(set(res["new"].get("failed", [])) - set(res["old"].get("failed", [])))
            entry = {"variant": tag, "set": s, "old": res["old"], "new": res["new"], "turns_total": len(B),
                     "turns_changed": len(diffs), "scenarios_fixed": gained, "scenarios_broken": lost}
            report.append(entry)
            (out / f"diff_{tag}_{name}.json").write_text(json.dumps(diffs, ensure_ascii=False, indent=1), encoding="utf-8")
            print(json.dumps(entry, ensure_ascii=False), flush=True)
    (out / "paired_offline.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    bad = [e for e in report if e["old"]["rc"] or e["new"]["rc"]]
    print(json.dumps({"runs_with_error": [(e["variant"], e["set"]) for e in bad]}), flush=True)   # không chặn các bước sau (gate CPU)


if __name__ == "__main__":
    main()
