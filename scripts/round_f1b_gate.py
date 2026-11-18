#!/usr/bin/env python3
"""Chấm cổng vòng F1b trên bộ 19 theo TIÊU CHÍ v2, chốt TRƯỚC khi sửa:
docs/PLAN/TRIEN-KHAI-LATENCY-EMIT-VA-DEV-2026-11-13.md §8.9 (13/11).

Vòng F (v1, §8.3) vẫn là KHÔNG ĐẠT theo tiêu chí v1 (§8.8, scripts/round_f_gate.py giữ nguyên làm hồ sơ). Script này chỉ chấm
vòng F1b. Mốc so sánh là trace vòng F (rf-full / rf-base) lọc đúng bộ 19. Chỉ đọc trace và báo cáo, không gọi model,
không sửa eval/reference_eval.py.

    python scripts/round_f1b_gate.py --scenarios /tmp/suites/set19 --full new_full.jsonl --baseline new_base.jsonl \
        --ref-full rf_full.jsonl --ref-baseline rf_base.jsonl --report report.json --report-ref report_ref.json \
        --latency latency/latency_report.json --dev dev/dev_report.json --checks full=... --checks baseline=... --out <dir>

Thoát mã 3 nếu KHÔNG đạt (vẫn ghi đủ báo cáo và nguyên nhân từng tiêu chí)."""
import argparse
import collections
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from round_f_gate import API_KEYS, PSEUDO, creates, f2, f3, identical, load, lp  # noqa: E402  (hàm dùng chung với v1)

CRITERIA_VERSION = "v2"
TTFT_P95_MAX = 4180
# 2a: regex nội dung KHÔNG phân biệt hoa thường (v2)
CONTENT = {"stock": re.compile(r"còn hàng|hết hàng|có hàng", re.I),
           "promo": re.compile(r"ưu đãi|khuyến mãi|giảm|chương trình", re.I),
           "promo_end": re.compile(r"đến \d{1,2}/\d{1,2}|hết hạn|kết thúc|chưa có chương trình|không có chương trình", re.I),
           "gift": re.compile(r"tặng|quà", re.I)}
F1_EXCLUDE = {("GEN-T10-01", "call_1", 2)}          # tách sang F5 (người dùng chốt 13/11)
TARGETS = {("GEN-T02-01", "call_2", 2): re.compile(r"không có quà tặng", re.I),
           ("V3-141", "call_2", 1): re.compile(r"không có quà tặng", re.I),
           ("BTCL-051", "call_2", 2): re.compile(r"hết hạn", re.I)}


def key(r):
    return (r["scenario_id"], r["call"], r["turn"])


def where(r):
    return f"{r['scenario_id']}/{r['call']}/t{r['turn']}"


def f1_content(rows):
    bad = []
    for r in rows:
        if key(r) in F1_EXCLUDE:
            continue
        oc = lp(r).get("ask_outcome") or {}
        for a in (r.get("understanding") or {}).get("asks") or []:
            if a in CONTENT and (oc.get(a) or {}).get("outcome") == "answered" and not CONTENT[a].search(r.get("agent_text") or ""):
                bad.append({"where": where(r), "ask": a, "text": (r.get("agent_text") or "")[:200]})
    return bad


def inel_named(rows, pname):
    """2c: câu trả lời nêu tên một KM nằm trong ineligible_promos của chính lượt đó (trừ KM cũng đang áp dụng trong lượt)."""
    bad = []
    for r in rows:
        inel, applied = set(), set()
        for t in r.get("tool_calls") or []:
            if t.get("name") != "pricing.get_quote":
                continue
            res = t.get("result") or {}
            inel |= {x.get("promo_code") for x in res.get("ineligible_promos") or [] if isinstance(x, dict)}
            applied |= {x.get("promo_code") for x in res.get("applied_promos") or [] if isinstance(x, dict)}
        txt = (r.get("agent_text") or "").lower()
        hit = [c for c in sorted(inel - applied) if pname.get(c) and pname[c].lower() in txt]
        if hit:
            bad.append({"where": where(r), "promos": hit, "text": (r.get("agent_text") or "")[:200]})
    return bad


def rq_keys(rep_side):
    r = rep_side["repeat_question_rate"]
    ex = r.get("examples") or []
    return {(e["scenario"], e["call"], e["turn"], e.get("slot")) for e in ex}, r.get("redundant") or 0, len(ex)


def main():
    ap = argparse.ArgumentParser()
    for x in ("--scenarios", "--full", "--baseline", "--ref-full", "--ref-baseline", "--report", "--report-ref",
              "--latency", "--dev", "--out"):
        ap.add_argument(x, required=True)
    ap.add_argument("--checks", action="append", default=[])
    a = ap.parse_args()
    ids = set()
    for f in glob.glob(os.path.join(a.scenarios, "*.json")):
        sid = (json.load(open(f, encoding="utf-8")) or {}).get("scenario_id")
        if sid:
            ids.add(sid)
    raw = {"full": load(a.full), "baseline": load(a.baseline)}
    got_ids = {k: sorted({r["scenario_id"] for r in v}) for k, v in raw.items()}
    # mọi tiêu chí tính trên đúng bộ 19 ở cả trace mới lẫn mốc (lần chạy thật trace mới chỉ có 19; lọc để không lệch phạm vi)
    rows = {k: [r for r in v if r["scenario_id"] in ids] for k, v in raw.items()}
    ref = {"full": [r for r in load(a.ref_full) if r["scenario_id"] in ids],
           "baseline": [r for r in load(a.ref_baseline) if r["scenario_id"] in ids]}
    rep, rref = json.load(open(a.report, encoding="utf-8")), json.load(open(a.report_ref, encoding="utf-8"))
    lat = json.load(open(a.latency, encoding="utf-8"))
    dev = json.load(open(a.dev, encoding="utf-8"))
    pname = {p["promo_code"]: p.get("name") for p in json.load(open(os.path.join(ROOT, "catalog", "promotions.json"),
                                                                    encoding="utf-8"))["promotions"]}
    side = {"full": "system", "baseline": "baseline"}
    C = collections.OrderedDict()
    C["0_suite"] = {"ok": len(ids) == 19 and all(set(v) == ids for v in got_ids.values()),
                    "n_scenarios": len(ids), "missing": {k: sorted(ids - set(v)) for k, v in got_ids.items()}}

    # 1. checks CPU chạy lại trong chính hai job GPU
    cpu = {}
    for x in a.checks:
        name, path = x.split("=", 1)
        cpu[name] = [c["check"] for c in json.load(open(path, encoding="utf-8")) if c["rc"]]
    C["1_cpu_checks"] = {"ok": len(cpu) == 2 and not any(cpu.values()), "failed": cpu}

    # 2. F1
    a_bad = f1_content(rows["full"])
    by = {key(r): r for r in rows["full"]}
    b_res = {f"{k[0]}/{k[1]}/t{k[2]}": (bool(by.get(k)) and bool(rx.search(by[k].get("agent_text") or "")),
                                        (by.get(k) or {}).get("agent_text", "")[:200]) for k, rx in TARGETS.items()}
    c_bad = {k: inel_named(v, pname) for k, v in rows.items()}
    idt = {k: identical(v) for k, v in rows.items()}
    idt_ref = {k: identical(v) for k, v in ref.items()}
    d_ok = all(idt[k][0] <= idt_ref[k][0] for k in rows)
    C["2_f1"] = {"ok": not a_bad and all(v[0] for v in b_res.values()) and not any(c_bad.values()) and d_ok,
                 "a_answered_without_content_full": a_bad, "a_excluded_F5": [f"{k[0]}/{k[1]}/t{k[2]}" for k in F1_EXCLUDE],
                 "b_target_turns": b_res, "c_ineligible_promo_named": c_bad,
                 "d_identical": {k: {"new": idt[k][0], "ref": idt_ref[k][0], "where": idt[k][1]} for k in rows}}

    # 3. giữ F2 / F3 / F8
    f2b, f3b = f2(rows["full"]), f3(rows["full"])
    rt = {k: [where(r) for r in v if r["scenario_id"].startswith("RT-") and creates(r)] for k, v in rows.items()}
    pseudo = {k: [where(r) for r in v if PSEUDO.search(r.get("customer_text") or "") and creates(r)] for k, v in rows.items()}
    forb = {k: (dev["configs"][k]["writes"]["counts"] or {}).get("forbidden", 0) for k in rows}
    C["3_keep_f2_f3_f8"] = {"ok": not f2b and not f3b and not any(rt.values()) and not any(pseudo.values()) and not any(forb.values()),
                            "f2_named_not_quoted_full": f2b, "f3_blocker_question_full": f3b, "rt_creates": rt,
                            "pseudo_turn_creates": pseudo, "forbidden_writes": forb}

    # 4. không lùi (v2)
    def fails(rp, k):
        return {(f["scenario"], f["call"]): f["reasons"] for f in (rp[side[k]]["task_success_rate"].get("failures") or [])}
    tsr = {k: (rep[side[k]]["task_success_rate"]["passed"], rref[side[k]]["task_success_rate"]["passed"]) for k in rows}
    new_fail = {k: {f"{s}/{c}": rs for (s, c), rs in fails(rep, k).items() if (s, c) not in fails(rref, k)} for k in rows}
    forbidden_pat = {k: [x for x, rs in new_fail[k].items() if any("mẫu cấm" in z for z in rs)] for k in rows}
    rt10 = {k: ("RT-10", "call_2") not in fails(rep, k) for k in rows}
    hr = {k: ((rep[side[k]]["hallucination_rate"].get("price_promo_only") or {}),
              (rref[side[k]]["hallucination_rate"].get("price_promo_only") or {})) for k in rows}
    hr_ok = all(hr[k][0].get("wrong") is not None and hr[k][1].get("wrong") is not None and hr[k][0]["wrong"] <= hr[k][1]["wrong"]
                for k in rows)
    rq = {k: (rq_keys(rep[side[k]]), rq_keys(rref[side[k]])) for k in rows}
    full_new_keys, full_red, full_nex = rq["full"][0]
    full_ref_keys, full_ref_red, _ = rq["full"][1]
    full_complete = full_nex == full_red                 # examples đủ (BTC cắt ở 20) mới so được theo khóa
    new_redundant = sorted(f"{s}/{c}/t{t}:{sl}" for s, c, t, sl in full_new_keys - full_ref_keys)
    rq_ok = (full_complete and not new_redundant if full_complete else full_red <= full_ref_red) \
        and rq["baseline"][0][1] <= rq["baseline"][1][1]
    rqr_report = {k: {"rqr_btc_new": rep[side[k]]["repeat_question_rate"].get("value"),
                      "rqr_btc_ref": rref[side[k]]["repeat_question_rate"].get("value"),
                      "redundant_new": rep[side[k]]["repeat_question_rate"].get("redundant"),
                      "redundant_ref": rref[side[k]]["repeat_question_rate"].get("redundant"),
                      "questions_new": rep[side[k]]["repeat_question_rate"].get("total_questions"),
                      "questions_ref": rref[side[k]]["repeat_question_rate"].get("total_questions")} for k in rows}
    api = {k: {x: (dev["configs"][k]["api_errors"]["counts"] or {}).get(x, 0) for x in API_KEYS
               if (dev["configs"][k]["api_errors"]["counts"] or {}).get(x)} for k in rows}
    lc = lat["configs"]
    audit = {k: lc[k].get("audit_status") for k in lc}
    emit_bad = {k: lc[k].get("emit_check_failed") for k in lc}
    ttft = (lc["full"].get("ttft") or {}).get("p95_ms")
    C["4_no_regression_v2"] = {
        "ok": all(tsr[k][0] >= tsr[k][1] for k in rows) and all(rt10.values()) and not any(forbidden_pat.values())
        and hr_ok and rq_ok and not any(api.values()) and all(set((audit[k] or {}).keys()) == {"ok"} for k in audit)
        and not any(emit_bad.values()) and ttft is not None and ttft <= TTFT_P95_MAX,
        "a_tsr_passed_new_ref": tsr, "a_rt10_call2_pass": rt10, "a_new_failures": new_fail, "a_new_forbidden_pattern": forbidden_pat,
        "b_hr_price_promo_new_ref": hr,
        "c_redundant_questions": {"full_new_not_in_ref": new_redundant, "full_examples_complete": full_complete, **rqr_report},
        "d_api_errors": api, "d_audit_status": audit, "d_emit_check_failed": emit_bad, "d_ttft_p95_full": ttft,
        "d_ttft_p95_max": TTFT_P95_MAX, "n_valid_turns": {k: lc[k].get("n_valid_turns") for k in lc}}

    passed = all(v["ok"] for v in C.values())
    out = {"criteria_version": CRITERIA_VERSION, "round": "F1b",
           "note": "Vòng F (v1, §8.3) vẫn KHÔNG ĐẠT theo tiêu chí v1 (§8.8); kết quả này chỉ chấm vòng F1b theo tiêu chí v2 (§8.9).",
           "passed": passed, "criteria": C,
           "tsr_failures_full": rep["system"]["task_success_rate"].get("failures"),
           "tsr_failures_baseline": rep["baseline"]["task_success_rate"].get("failures")}
    os.makedirs(a.out, exist_ok=True)
    json.dump(out, open(os.path.join(a.out, "round_f1b_gate.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    L = [f"# Cổng vòng F1b (bộ 19, tiêu chí {CRITERIA_VERSION}): {'ĐẠT' if passed else 'KHÔNG ĐẠT'}", "", f"_{out['note']}_", ""]
    for k, v in C.items():
        L.append(f"- {k}: {'ok' if v['ok'] else 'KHÔNG ĐẠT'} — " + json.dumps({x: y for x, y in v.items() if x != "ok"}, ensure_ascii=False)[:1200])
    open(os.path.join(a.out, "round_f1b_gate.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))
    if not passed:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
