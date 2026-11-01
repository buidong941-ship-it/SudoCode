"""D4: so sánh vòng N với vòng N+1 trên cùng bộ test, kèm khoảng dao động (C5).

Vào: mỗi vòng là một thư mục `improve/rounds/<tên>` (có round.json + reports/) HOẶC `TÊN=đường/dẫn/report.json`
(lặp lại `--set` cho nhiều bộ). Ra: bảng markdown chỉ số hệ thống + chênh lệch + ca TSR đổi trạng thái.

    python scripts/compare_rounds.py --round improve/rounds/r0 --round improve/rounds/r1
    python scripts/compare_rounds.py --round r0:dev=runs/a/report.json --round r1:dev=runs/b/report.json \
        --spread runs/c5_spread.json --out runs/compare_r0_r1.md

`--spread` là JSON {metric: độ lệch chuẩn} (hoặc {set: {metric: sd}}) lấy từ các lần chạy lặp của C5; chênh lệch
có |Δ| ≤ 2·sd được đánh dấu "≈ trong dao động". Không có spread thì không kết luận được gì về ý nghĩa.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from improve import store  # noqa: E402

METRICS = [("tsr", "Task Success Rate (%)", +1), ("rqr", "Repeat-Question Rate (%)", -1),
           ("hr", "Hallucination giá & KM (%)", -1), ("ccr", "Context Carryover Rate (%)", +1),
           ("guardrail", "Vi phạm guardrail", -1)]


def metric(rep, name):
    if name == "ccr":
        return (rep.get("system", rep).get("context_carryover_rate") or {}).get("value")
    return store.metric(rep, name)


def failures(rep):
    return {(f.get("scenario"), f.get("call")) for f in
            (rep.get("system", rep).get("task_success_rate") or {}).get("failures") or []}


def load_round(spec):
    """'improve/rounds/r0' hoặc 'r0:dev=path.json,test=path2.json'."""
    if os.path.isdir(spec):
        m = json.load(open(os.path.join(spec, "round.json"), encoding="utf-8"))
        reps = {k: json.load(open(os.path.join(spec, v), encoding="utf-8")) for k, v in m.get("reports", {}).items()}
        return m["name"], reps
    name, _, rest = spec.partition(":")
    reps = {}
    for part in rest.split(","):
        label, _, path = part.partition("=")
        reps[label] = json.load(open(path, encoding="utf-8"))
    return name, reps


def sd_for(spread, label, m):
    if not spread:
        return None
    v = spread.get(label, spread)
    return v.get(m) if isinstance(v, dict) else None


def fmt(v):
    return "—" if v is None else (f"{v:g}" if isinstance(v, (int, float)) else str(v))


def compare(rounds, spread=None):
    names = [n for n, _ in rounds]
    sets = sorted(set.intersection(*(set(r) for _, r in rounds)))
    lines = [f"# So sánh vòng: {' → '.join(names)}", ""]
    if not sets:
        return "\n".join(lines + ["Không có bộ test chung giữa các vòng."])
    for label in sets:
        lines += [f"## Bộ `{label}`", "", "| Chỉ số | " + " | ".join(names) + " | Δ (cuối − đầu) | Đánh giá |",
                  "|---|" + "---:|" * len(names) + "---:|---|"]
        for key, title, better in METRICS:
            vals = [metric(r[label], key) for _, r in rounds]
            first, last = vals[0], vals[-1]
            if first is None or last is None:
                d, verdict = None, ""
            else:
                d = round(last - first, 2)
                sd = sd_for(spread, label, key)
                if d == 0:
                    verdict = "không đổi"
                elif sd is not None and abs(d) <= 2 * sd:
                    verdict = f"≈ trong dao động (2·sd = {2 * sd:g})"
                else:
                    verdict = ("tốt hơn" if d * better > 0 else "**xấu hơn**") + ("" if sd is not None else " (chưa có spread)")
            lines.append(f"| {title} | " + " | ".join(fmt(v) for v in vals) + f" | {fmt(d)} | {verdict} |")
        f0, f1 = failures(rounds[0][1][label]), failures(rounds[-1][1][label])
        fixed, broke = sorted(f0 - f1), sorted(f1 - f0)
        lines += ["", f"- Ca được sửa ({len(fixed)}): " + (", ".join(f"{s}/{c}" for s, c in fixed) or "không"),
                  f"- Ca mới trượt ({len(broke)}): " + (", ".join(f"{s}/{c}" for s, c in broke) or "không"), ""]
        dec = store.rollback_decision({label: rounds[-2][1][label]}, {label: rounds[-1][1][label]})
        lines.append("- Quay lui (D5, so 2 vòng cuối): " + ("**CÓ** — " + "; ".join(dec["reasons"]) if dec["rollback"] else "không"))
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--round", action="append", required=True, help="thư mục vòng hoặc TÊN:bộ=report.json[,bộ=...]")
    ap.add_argument("--spread", help="JSON độ lệch chuẩn từ C5")
    ap.add_argument("--out", help="ghi markdown ra file")
    a = ap.parse_args()
    if len(a.round) < 2:
        ap.error("cần ít nhất 2 --round")
    spread = json.load(open(a.spread, encoding="utf-8")) if a.spread else None
    md = compare([load_round(s) for s in a.round], spread)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(md + "\n")
    print(md)


if __name__ == "__main__":
    main()
